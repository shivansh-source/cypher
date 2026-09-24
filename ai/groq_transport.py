"""Groq implementation of :class:`ai.llm_client.LLMTransport`.

Groq's chat API is OpenAI-shaped: tool calls live in ``message.tool_calls``
and tool results are ``role: "tool"`` messages. The rest of ``ai/`` speaks
a content-block shape instead (``tool_use`` / ``tool_result``
blocks), and the session store keeps history in that shape. This module is
the whole translation boundary: it converts requests on the way out and
responses on the way back, so ``ai/chat.py``, ``ai/sessions.py`` and
``ai/tool_registry.py`` neither know nor care which provider answered, and a
conversation's history stays valid if the provider is switched.

The translation functions are pure (dicts in, dicts out) so they are tested
without a network call or an API key.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from typing import Any

from ai.llm_client import (
    LLMConfigurationError,
    LLMProviderError,
    StreamChunk,
    _as_provider_error,
)

#: Default Groq model. Overridable with GROQ_MODEL (see .env.example). Must
#: be a model that supports tool calling — a model that does not will reject
#: every chat request. This is an infrastructure choice, not a modelling
#: constant, so it does not belong in ``core/assumptions.py``.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

#: Output token ceiling per request. Well under the context limits of
#: Groq-hosted models.
DEFAULT_GROQ_MAX_TOKENS = 8_192

#: Provider ``finish_reason`` -> the stop_reason vocabulary ``ai/chat.py``
#: understands.
_STOP_REASONS = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}


def to_groq_tools(tools: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert provider-neutral tool definitions to Groq function tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def to_groq_tool_choice(tool_choice: dict[str, Any] | None) -> str | dict[str, Any] | None:
    """Convert a provider-neutral ``tool_choice`` to Groq's."""
    if tool_choice is None:
        return None
    kind = tool_choice.get("type")
    if kind == "any":
        return "required"
    if kind == "none":
        return "none"
    if kind == "tool":
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return "auto"


def to_groq_messages(system: str, messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a content-block conversation to Groq chat messages.

    Args:
        system: The system prompt.
        messages: Conversation history. Assistant content may hold ``text``
            and ``tool_use`` blocks; a user turn may hold ``tool_result``
            blocks.

    Returns:
        Groq messages. Every ``tool_use`` becomes an entry in the assistant
        message's ``tool_calls`` and every ``tool_result`` becomes its own
        ``role: "tool"`` message, matched by id.
    """
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        role = message["role"]
        content = message["content"]
        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            tool_calls = [
                {
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                }
                for block in content
                if block.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            converted.append(entry)
            continue
        # A user turn: tool results become their own messages, any text follows.
        text_parts: list[str] = []
        for block in content:
            if block.get("type") == "tool_result":
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": str(block.get("content", "")),
                    }
                )
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        if text_parts:
            converted.append({"role": "user", "content": "".join(text_parts)})
    return converted


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    """Parse a tool call's JSON arguments, tolerating a malformed emission.

    Models served through Groq occasionally emit invalid JSON for tool
    arguments. An empty dict is returned rather than raising: the tool
    registry then reports a missing required argument back to the model as a
    normal tool error, which it can correct on the next iteration.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def from_groq_message(
    *, model: str, text: str, tool_calls: Sequence[dict[str, Any]], finish_reason: str | None
) -> dict[str, Any]:
    """Assemble a content-block message from a Groq completion's parts."""
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for call in tool_calls:
        function = call.get("function", {})
        content.append(
            {
                "type": "tool_use",
                "id": call.get("id", ""),
                "name": function.get("name", ""),
                "input": _parse_arguments(function.get("arguments")),
            }
        )
    stop_reason = _STOP_REASONS.get(finish_reason or "", finish_reason or "end_turn")
    if tool_calls:
        stop_reason = "tool_use"
    return {"model": model, "role": "assistant", "stop_reason": stop_reason, "content": content}


class GroqTransport:
    """:class:`ai.llm_client.LLMTransport` backed by Groq's chat completions API.

    Args:
        api_key: Provider API key; defaults to ``GROQ_API_KEY``.
        model: Model identifier; defaults to ``GROQ_MODEL``, then
            :data:`DEFAULT_GROQ_MODEL`. Must support tool calling.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
        self._model = model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._model

    def _sdk_client(self) -> Any:
        """Build (once) the provider client, or explain why we cannot."""
        if self._client is not None:
            return self._client
        try:
            import groq
        except ImportError as exc:  # pragma: no cover - depends on install state
            raise LLMConfigurationError(
                "The 'groq' package is not installed. Install the backend "
                "dependencies (pip install -e '.[dev]') to enable the chat assistant."
            ) from exc
        if not self._api_key:
            raise LLMConfigurationError(
                "GROQ_API_KEY is not set. The chat assistant cannot answer "
                "without it — see .env.example."
            )
        self._client = groq.Groq(api_key=self._api_key)
        return self._client

    def _request_kwargs(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        tool_choice: dict[str, Any] | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": to_groq_messages(system, messages),
            "max_completion_tokens": max_tokens or DEFAULT_GROQ_MAX_TOKENS,
        }
        if tools:
            kwargs["tools"] = to_groq_tools(tools)
            choice = to_groq_tool_choice(tool_choice)
            if choice is not None:
                kwargs["tool_choice"] = choice
        return kwargs

    def create_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        client = self._sdk_client()
        kwargs = self._request_kwargs(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
        )
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # re-raised as one of this module's error types
            raise _as_provider_error(exc) from exc
        dumped: dict[str, Any] = response.model_dump(mode="json")
        choice = dumped["choices"][0]
        message = choice["message"]
        return from_groq_message(
            model=str(dumped.get("model", self._model)),
            text=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason"),
        )

    def stream_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[StreamChunk]:
        client = self._sdk_client()
        kwargs = self._request_kwargs(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=None,
            max_tokens=max_tokens,
        )
        text_parts: list[str] = []
        # Tool calls arrive as fragments keyed by index: the id and name in
        # the first fragment, the JSON arguments spread across the rest.
        calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        model = self._model
        try:
            for chunk in client.chat.completions.create(stream=True, **kwargs):
                data: dict[str, Any] = chunk.model_dump(mode="json")
                model = str(data.get("model") or model)
                for choice in data.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text_parts.append(delta["content"])
                        yield StreamChunk(kind="text_delta", text=delta["content"])
                    for fragment in delta.get("tool_calls") or []:
                        call = calls.setdefault(
                            int(fragment.get("index", 0)),
                            {"id": "", "function": {"name": "", "arguments": ""}},
                        )
                        if fragment.get("id"):
                            call["id"] = fragment["id"]
                        function = fragment.get("function") or {}
                        if function.get("name"):
                            call["function"]["name"] = function["name"]
                        if function.get("arguments"):
                            call["function"]["arguments"] += function["arguments"]
                    finish_reason = choice.get("finish_reason") or finish_reason
        except Exception as exc:  # re-raised as one of this module's error types
            raise _as_provider_error(exc) from exc
        if finish_reason is None and not text_parts and not calls:
            raise LLMProviderError("Groq stream ended without producing a message")
        yield StreamChunk(
            kind="final_message",
            message=from_groq_message(
                model=model,
                text="".join(text_parts),
                tool_calls=[calls[index] for index in sorted(calls)],
                finish_reason=finish_reason,
            ),
        )
