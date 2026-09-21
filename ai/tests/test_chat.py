"""Tests for ai/chat.py.

Every test here runs against a scripted transport, so the tool-calling
loop and the guard are exercised without a network call or an API key.
What is being asserted is the contract that matters: no number reaches a
caller without having come from a real tool result first.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import replace
from typing import Any

import pytest

from ai import tool_registry
from ai.chat import ChatEngine
from ai.llm_client import StreamChunk
from ai.sessions import InMemorySessionStore
from ai.tool_registry import tool_specs


class ScriptedTransport:
    """An :class:`ai.llm_client.LLMTransport` that replays canned messages."""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = list(script)
        self.requests: list[list[dict[str, Any]]] = []

    @property
    def model(self) -> str:
        return "scripted-model"

    def create_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        self.requests.append([dict(message) for message in messages])
        return self._script.pop(0)

    def stream_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[StreamChunk]:
        message = self.create_message(system=system, messages=messages, tools=tools)
        for block in message.get("content", []):
            if block.get("type") == "text":
                yield StreamChunk(kind="text_delta", text=block["text"])
        yield StreamChunk(kind="final_message", message=message)


def _text_message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "model": "scripted-model",
        "stop_reason": stop_reason,
        "content": [{"type": "text", "text": text}],
    }


def _tool_message(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "scripted-model",
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", "id": "toolu_1", "name": tool_name, "input": arguments}
        ],
    }


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


def test_a_turn_with_no_tool_call_is_still_guarded(session_store: InMemorySessionStore) -> None:
    """A model that answers with a figure it never fetched must be flagged."""
    transport = ScriptedTransport([_text_message("Your exposure is about ₹4.2 crore.")])
    reply = ChatEngine(transport=transport).run_turn(
        session_store.create(), "what is our exposure?"
    )
    assert not reply.all_claims_verified
    assert "[UNVERIFIED:" in reply.text
    assert reply.unverified_claims


def test_tool_output_is_what_makes_a_figure_narratable(
    session_store: InMemorySessionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same figure verifies once a real tool produced it."""

    def fake_exposure(**_: Any) -> dict[str, Any]:
        return {"snapshot_id": "snap-1", "expected_annual_loss_inr": 42_000_000.0}

    monkeypatch.setitem(
        tool_registry.tool_specs(),
        "get_exposure",
        replace(tool_specs()["get_exposure"], handler=fake_exposure),
    )
    transport = ScriptedTransport(
        [
            _tool_message("get_exposure", {}),
            _text_message("Expected annual loss is ₹4.2 crore on snapshot snap-1."),
        ]
    )
    session = session_store.create()
    reply = ChatEngine(transport=transport).run_turn(session, "what is our exposure?")

    assert reply.all_claims_verified
    assert reply.text == "Expected annual loss is ₹4.2 crore on snapshot snap-1."
    assert [call.tool_name for call in reply.tool_calls] == ["get_exposure"]
    assert reply.tool_calls[0].status == "ok"
    assert 42_000_000.0 in session.ground_truth.values()


def test_unavailable_tool_reaches_the_model_as_a_refusal_to_guess(
    session_store: InMemorySessionStore,
) -> None:
    """An unimplemented tool produces an 'unavailable' tool_result, not a blank one."""
    transport = ScriptedTransport(
        [
            _tool_message("get_exposure", {}),
            _text_message("No exposure figure has been computed yet."),
        ]
    )
    reply = ChatEngine(transport=transport).run_turn(session_store.create(), "exposure?")

    assert reply.tool_calls[0].status == "unavailable"
    assert reply.tool_calls[0].result is None
    tool_turn = transport.requests[-1][-1]
    assert tool_turn["role"] == "user"
    assert tool_turn["content"][0]["is_error"] is True
    assert "unavailable" in tool_turn["content"][0]["content"]
    assert reply.all_claims_verified  # the reply states the gap, and states no figure


def test_ground_truth_persists_across_turns_in_one_session(
    session_store: InMemorySessionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A follow-up may restate a figure computed in an earlier turn."""

    def fake_exposure(**_: Any) -> dict[str, Any]:
        return {"snapshot_id": "snap-1", "expected_annual_loss_inr": 42_000_000.0}

    monkeypatch.setitem(
        tool_registry.tool_specs(),
        "get_exposure",
        replace(tool_specs()["get_exposure"], handler=fake_exposure),
    )
    session = session_store.create()
    engine = ChatEngine(
        transport=ScriptedTransport(
            [_tool_message("get_exposure", {}), _text_message("EAL is ₹4.2 crore.")]
        )
    )
    engine.run_turn(session, "exposure?")

    follow_up = ChatEngine(
        transport=ScriptedTransport([_text_message("As I said, EAL is ₹4.2 crore.")])
    ).run_turn(session, "say that again")
    assert follow_up.all_claims_verified


def test_loop_stops_at_the_tool_iteration_ceiling(session_store: InMemorySessionStore) -> None:
    """A model that only ever calls tools must not spin forever."""
    transport = ScriptedTransport([_tool_message("get_exposure", {}) for _ in range(10)])
    reply = ChatEngine(transport=transport, max_tool_iterations=3).run_turn(
        session_store.create(), "exposure?"
    )
    assert reply.stop_reason == "max_tool_iterations"
    assert len(reply.tool_calls) == 3
    assert "limit on tool calls" in reply.text


def test_stream_turn_ends_with_a_final_event_carrying_the_guarded_text(
    session_store: InMemorySessionStore,
) -> None:
    """Streamed deltas are raw; the final event is the verified answer."""
    transport = ScriptedTransport([_text_message("Your exposure is about ₹4.2 crore.")])
    events = list(ChatEngine(transport=transport).stream_turn(session_store.create(), "exposure?"))

    assert events[0].type == "session"
    assert any(event.type == "text_delta" for event in events)
    final = events[-1]
    assert final.type == "final"
    assert final.data["text_replaced"] is True
    assert "[UNVERIFIED:" in final.data["text"]
    assert final.data["all_claims_verified"] is False


def test_stream_turn_reports_tool_progress(session_store: InMemorySessionStore) -> None:
    transport = ScriptedTransport(
        [_tool_message("get_exposure", {}), _text_message("Nothing has been computed yet.")]
    )
    events = list(ChatEngine(transport=transport).stream_turn(session_store.create(), "exposure?"))
    types = [event.type for event in events]
    assert types.index("tool_call") < types.index("tool_result")
    result_event = next(event for event in events if event.type == "tool_result")
    assert result_event.data["status"] == "unavailable"
    assert events[-1].type == "final"
