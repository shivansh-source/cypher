"""Tests for ai/groq_transport.py.

No network and no API key: the translation functions are pure, and the
transport is driven through a fake Groq client returning canned completions.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from ai.chat import ChatEngine
from ai.groq_transport import (
    GroqTransport,
    from_groq_message,
    to_groq_messages,
    to_groq_tool_choice,
    to_groq_tools,
)
from ai.llm_client import LLMConfigurationError, build_transport
from ai.sessions import InMemorySessionStore


class _Dumpable:
    """Stands in for an SDK pydantic object: exposes ``model_dump``."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return self._data


class _FakeCompletions:
    def __init__(self, replies: list[Any]) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self._replies.pop(0)


class _FakeGroq:
    def __init__(self, replies: list[Any]) -> None:
        self.completions = _FakeCompletions(replies)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _transport(replies: list[Any]) -> tuple[GroqTransport, _FakeCompletions]:
    transport = GroqTransport(api_key="test-key", model="test-model")
    fake = _FakeGroq(replies)
    transport._client = fake
    return transport, fake.completions


def _completion(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
) -> _Dumpable:
    return _Dumpable(
        {
            "model": "test-model",
            "choices": [
                {
                    "message": {"content": content, "tool_calls": tool_calls},
                    "finish_reason": finish_reason,
                }
            ],
        }
    )


def test_tools_become_groq_function_tools() -> None:
    schema = {"type": "object", "properties": {"scope": {"type": "string"}}, "required": []}
    converted = to_groq_tools(
        [{"name": "get_exposure", "description": "d", "input_schema": schema}]
    )
    assert converted == [
        {
            "type": "function",
            "function": {"name": "get_exposure", "description": "d", "parameters": schema},
        }
    ]


def test_tool_choice_translation() -> None:
    assert to_groq_tool_choice(None) is None
    assert to_groq_tool_choice({"type": "any"}) == "required"
    assert to_groq_tool_choice({"type": "auto"}) == "auto"
    assert to_groq_tool_choice({"type": "tool", "name": "x"}) == {
        "type": "function",
        "function": {"name": "x"},
    }


def test_history_with_a_tool_round_trip_converts_to_groq_messages() -> None:
    history: list[dict[str, Any]] = [
        {"role": "user", "content": "exposure?"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "private"},
                {"type": "text", "text": "Checking."},
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "get_exposure",
                    "input": {"scope": "s"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "{}", "is_error": True}
            ],
        },
    ]
    converted = to_groq_messages("SYS", history)
    assert converted[0] == {"role": "system", "content": "SYS"}
    assert converted[1] == {"role": "user", "content": "exposure?"}
    assistant = converted[2]
    assert assistant["content"] == "Checking."  # thinking dropped
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"scope": "s"}
    assert converted[3] == {"role": "tool", "tool_call_id": "call_1", "content": "{}"}


def test_assistant_turn_with_only_a_tool_call_has_null_content() -> None:
    converted = to_groq_messages(
        "S",
        [
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "c", "name": "t", "input": {}}],
            }
        ],
    )
    assert converted[1]["content"] is None


def test_malformed_tool_arguments_become_empty_input_not_a_crash() -> None:
    message = from_groq_message(
        model="m",
        text="",
        tool_calls=[{"id": "c", "function": {"name": "get_exposure", "arguments": "{not json"}}],
        finish_reason="tool_calls",
    )
    assert message["stop_reason"] == "tool_use"
    assert message["content"][0]["input"] == {}


def test_finish_reasons_map_to_the_chat_loops_vocabulary() -> None:
    assert (
        from_groq_message(model="m", text="x", tool_calls=[], finish_reason="stop")["stop_reason"]
        == "end_turn"
    )
    assert (
        from_groq_message(model="m", text="x", tool_calls=[], finish_reason="length")["stop_reason"]
        == "max_tokens"
    )


def test_create_message_returns_a_messages_api_shaped_reply() -> None:
    transport, completions = _transport(
        [
            _completion(
                tool_calls=[
                    {
                        "id": "call_9",
                        "function": {"name": "get_exposure", "arguments": '{"scope": "svc-1"}'},
                    }
                ],
                finish_reason="tool_calls",
            )
        ]
    )
    message = transport.create_message(
        system="S",
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "get_exposure", "description": "d", "input_schema": {"type": "object"}}],
        tool_choice={"type": "any"},
    )
    assert message["stop_reason"] == "tool_use"
    assert message["content"] == [
        {"type": "tool_use", "id": "call_9", "name": "get_exposure", "input": {"scope": "svc-1"}}
    ]
    request = completions.requests[0]
    assert request["model"] == "test-model"
    assert request["tool_choice"] == "required"
    assert request["messages"][0]["role"] == "system"


def test_stream_reassembles_tool_call_fragments_and_text() -> None:
    def chunk(delta: dict[str, Any], finish: str | None = None) -> _Dumpable:
        return _Dumpable(
            {"model": "test-model", "choices": [{"delta": delta, "finish_reason": finish}]}
        )

    stream = [
        chunk({"content": "Look"}),
        chunk({"content": "ing."}),
        chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "get_exposure"}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"sco'}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": 'pe": "a"}'}}]}, "tool_calls"),
    ]
    transport, _ = _transport([iter(stream)])
    chunks = list(
        transport.stream_message(system="S", messages=[{"role": "user", "content": "hi"}])
    )
    assert [c.text for c in chunks if c.kind == "text_delta"] == ["Look", "ing."]
    final = chunks[-1]
    assert final.kind == "final_message" and final.message is not None
    assert final.message["stop_reason"] == "tool_use"
    assert final.message["content"][0] == {"type": "text", "text": "Looking."}
    assert final.message["content"][1]["input"] == {"scope": "a"}


def test_chat_engine_runs_a_full_turn_over_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unmodified ChatEngine drives a Groq-shaped tool round trip and guards the answer."""
    transport, completions = _transport(
        [
            _completion(
                tool_calls=[
                    {"id": "call_1", "function": {"name": "get_exposure", "arguments": "{}"}}
                ],
                finish_reason="tool_calls",
            ),
            _completion(content="Your exposure is about ₹4.2 crore."),
        ]
    )
    reply = ChatEngine(transport=transport).run_turn(InMemorySessionStore().create(), "exposure?")

    assert [call.status for call in reply.tool_calls] == ["unavailable"]
    assert not reply.all_claims_verified  # the figure never came from a tool
    assert "[UNVERIFIED:" in reply.text
    # The tool result reached Groq as a role=tool message matched by id.
    tool_message = completions.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call_1"


def test_missing_api_key_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY"):
        GroqTransport().create_message(system="S", messages=[{"role": "user", "content": "hi"}])


def test_build_transport_selects_by_name() -> None:
    assert isinstance(build_transport("groq"), GroqTransport)
    assert isinstance(build_transport("GROQ"), GroqTransport)
    assert type(build_transport("anthropic")).__name__ == "AnthropicTransport"
    with pytest.raises(LLMConfigurationError, match="Unknown LLM_PROVIDER"):
        build_transport("openai")
