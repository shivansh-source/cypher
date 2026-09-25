"""FastAPI application entry point.

Every route here is a thin adapter over ``core/``, ``governance/``, and
``ai/`` — no route may contain risk-computation, compliance-mapping, or LLM
logic of its own. Any route that returns LLM-generated narration must pass
it through ``ai.numeric_guard.guard_narration`` before responding.

The chat routes satisfy that last rule structurally rather than by
convention: they never see the model's raw text. ``ai.chat.ChatEngine``
guards the text before returning a :class:`~ai.chat.ChatReply`, and these
routes serialize that reply. The one place raw model text does cross the
wire is the SSE ``text_delta`` event, which is explicitly labelled
unverified and superseded by the ``final`` event — see
``interfaces/api/README.md``.

A tool whose underlying computation does not exist yet answers 501, matching
the contract in ``interfaces/dashboard/README.md``: no committed snapshot and
no engine run means there is nothing to show, and that is reported as a
first-class state rather than as a zero.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from ai.chat import ChatEngine, ChatEvent, reply_to_dict
from ai.llm_client import LLMConfigurationError, LLMProviderError
from ai.sessions import (
    DEFAULT_MAX_SESSIONS,
    DEFAULT_SESSION_TTL_MINUTES,
    InMemorySessionStore,
)
from ai.tool_registry import execute_tool, tool_specs
from interfaces._dotenv import load_dotenv
from interfaces.api._http import execution_to_response
from interfaces.api.dashboard_routes import register_dashboard_routes

_store: InMemorySessionStore | None = None
_engine: ChatEngine | None = None


def get_session_store() -> InMemorySessionStore:
    """Return the process-wide chat session store, building it on first use."""
    global _store
    if _store is None:
        _store = InMemorySessionStore(
            ttl_minutes=int(
                os.environ.get("CHAT_SESSION_TTL_MINUTES", DEFAULT_SESSION_TTL_MINUTES)
            ),
            max_sessions=int(os.environ.get("CHAT_MAX_SESSIONS", DEFAULT_MAX_SESSIONS)),
        )
    return _store


def get_chat_engine() -> ChatEngine:
    """Return the process-wide chat engine, building it on first use."""
    global _engine
    if _engine is None:
        _engine = ChatEngine()
    return _engine


def reset_state(
    store: InMemorySessionStore | None = None, engine: ChatEngine | None = None
) -> None:
    """Replace the process-wide store and engine (tests, or an embedding host)."""
    global _store, _engine
    _store = store
    _engine = engine


class ChatRequest(BaseModel):
    """A chat turn from the client.

    Attributes:
        message: What the user typed.
        session_id: The conversation to continue. Omit to start a new one;
            an unknown or expired id also starts a new one, and the
            response's ``session_id`` is always the one to send next.
    """

    message: str = Field(min_length=1, max_length=8_000)
    session_id: str | None = None


class ToolCallResponse(BaseModel):
    """One tool call made while answering."""

    tool_name: str
    arguments: dict[str, Any]
    status: str
    detail: str | None = None
    result: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    """A verified assistant turn.

    ``text`` has already been through ``ai.numeric_guard``: any number it
    could not trace to a real tool result in this conversation is flagged
    inline and listed in ``unverified_claims``. Display ``text`` verbatim,
    including the flags.
    """

    session_id: str
    text: str
    all_claims_verified: bool
    unverified_claims: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    model: str = ""
    stop_reason: str = ""


class ToolDescription(BaseModel):
    """One tool the assistant can call, and whether it can answer today."""

    name: str
    description: str
    input_schema: dict[str, Any]
    available: bool
    unavailable_reason: str | None = None


def _sse(event: ChatEvent) -> str:
    """Encode one :class:`~ai.chat.ChatEvent` as a Server-Sent Event frame."""
    return f"event: {event.type}\ndata: {json.dumps(event.data, default=str)}\n\n"


def get_exposure_route() -> Any:
    """HTTP route handler wrapping ``ai.tools.get_exposure.get_exposure``.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.
    """

    def handler(scope: str | None = None) -> dict[str, Any]:
        arguments: dict[str, Any] = {"scope": scope} if scope else {}
        return execution_to_response(execute_tool("get_exposure", arguments))

    return handler


def optimize_investment_route() -> Any:
    """HTTP route handler wrapping ``ai.tools.optimize_investment.optimize_investment``.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.
    """

    def handler(budget_inr: float) -> dict[str, Any]:
        return execution_to_response(
            execute_tool("optimize_investment", {"budget_inr": budget_inr})
        )

    return handler


def chat_route() -> Any:
    """HTTP route handler for natural-language chat, wiring together
    ``ai.intent_classifier``, the relevant ``ai.tools`` module, and
    ``ai.numeric_guard`` before returning a response.

    Routing is done by the model's own tool-calling loop in
    ``ai.chat`` rather than by ``ai.intent_classifier``'s single-shot
    router, so that one question may use several tools and follow up on
    their results; the classifier remains available for one-shot callers.
    The guard step is unchanged and unconditional.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.

    Must never:
        Return LLM-generated text to the client without first passing it
        through ``ai.numeric_guard.guard_narration``.
    """
    from fastapi import HTTPException

    def handler(request: ChatRequest) -> ChatResponse:
        session = get_session_store().get_or_create(request.session_id)
        try:
            reply = get_chat_engine().run_turn(session, request.message)
        except LLMConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LLMProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ChatResponse.model_validate(reply_to_dict(reply))

    return handler


def chat_stream_route() -> Any:
    """HTTP route handler streaming a chat turn as Server-Sent Events.

    Event names are ``session``, ``text_delta``, ``tool_call``,
    ``tool_result``, ``final`` and ``error``; every stream ends with
    exactly one ``final`` or one ``error``.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.

    Must never:
        Let a client mistake ``text_delta`` for the answer. Those deltas
        are the model's raw, unverified output; the ``final`` event carries
        the guarded text and sets ``text_replaced`` when the two differ.
    """
    from fastapi.responses import StreamingResponse

    def handler(request: ChatRequest) -> StreamingResponse:
        session = get_session_store().get_or_create(request.session_id)
        engine = get_chat_engine()

        def events() -> Iterator[str]:
            for event in engine.stream_turn(session, request.message):
                yield _sse(event)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return handler


def chat_tools_route() -> Any:
    """HTTP route handler listing the tools the assistant can call.

    Each entry reports whether the tool can answer today: the wrappers in
    ``ai/tools/`` that depend on unimplemented parts of ``core/`` are
    listed with ``available: false`` and the reason, so a client can tell a
    user what the assistant cannot yet do without having to ask it.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.
    """

    def handler() -> list[ToolDescription]:
        descriptions: list[ToolDescription] = []
        for spec in tool_specs().values():
            probe = execute_tool(spec.name, _probe_arguments(spec.input_schema))
            available = probe.status != "unavailable"
            descriptions.append(
                ToolDescription(
                    name=spec.name,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    available=available,
                    unavailable_reason=None if available else probe.detail,
                )
            )
        return descriptions

    return handler


def _probe_arguments(input_schema: dict[str, Any]) -> dict[str, Any]:
    """Build placeholder arguments so a tool can be probed for availability.

    Only ever used to find out whether a wrapper raises
    ``NotImplementedError``; the values never reach a user and never reach
    ``ai.numeric_guard`` as ground truth.
    """
    placeholders: dict[str, Any] = {"string": "", "number": 0, "integer": 0, "array": []}
    properties: dict[str, Any] = input_schema.get("properties", {})
    return {
        name: placeholders.get(str(properties.get(name, {}).get("type")), None)
        for name in input_schema.get("required", [])
    }


def delete_session_route() -> Any:
    """HTTP route handler discarding one chat session's history.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.
    """

    def handler(session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "deleted": get_session_store().delete(session_id)}

    return handler


def create_app() -> Any:
    """Construct and configure the FastAPI application.

    Returns:
        A configured FastAPI app instance with all routes registered.

    Must never:
        Register a route that computes a risk figure inline instead of
        calling into ``core.engine``, or that returns LLM narration
        without first passing it through ``ai.numeric_guard``.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    # Before anything reads configuration: fills os.environ from the
    # repo-root .env without overriding variables the shell already set.
    load_dotenv()

    # No-op unless SNAPSHOT_S3_BUCKET is set: on a hosted API, pulls the snapshot store the
    # scheduled-ingest workflow publishes to S3 into SNAPSHOT_STORE_PATH.
    from interfaces.api.snapshot_sync import configure_from_env, sync_status

    configure_from_env()

    app = FastAPI(
        title="Su₹aksha API",
        description=(
            "Rupee-denominated cyber risk quantification. Every figure comes from "
            "the deterministic engine in core/; the chat assistant routes to it and "
            "narrates what it returned, and never produces a figure itself."
        ),
        version="0.1.0",
    )
    origins = [
        origin.strip()
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.get("/health")(lambda: {"status": "ok"})
    app.get("/health/snapshot-sync")(sync_status)
    app.get("/exposure")(get_exposure_route())
    app.get("/optimize")(optimize_investment_route())
    app.post("/chat", response_model=ChatResponse)(chat_route())
    app.post("/chat/stream")(chat_stream_route())
    app.get("/chat/tools", response_model=list[ToolDescription])(chat_tools_route())
    app.delete("/chat/sessions/{session_id}")(delete_session_route())
    register_dashboard_routes(app)

    # Signed S3 download links for published snapshots; refuses unless
    # SNAPSHOT_LINKS_TOKEN is set (see interfaces/api/snapshot_links.py).
    from interfaces.api.snapshot_links import register_snapshot_link_routes

    register_snapshot_link_routes(app)
    return app
