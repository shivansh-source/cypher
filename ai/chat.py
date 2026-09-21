"""The chat assistant: a tool-calling loop over ``ai/tools/``.

This is the conversational front door to Su₹aksha. The model does exactly
two things here, both at the edges (repo-root ``CLAUDE.md`` principle 2):
it decides which ``ai/tools/`` wrapper answers the user's question, and it
narrates what that tool returned. Every figure in a reply came from
``core/`` or ``governance/`` via a real tool call, and every number in the
prose is checked against those tool results by ``ai.numeric_guard`` before
the reply leaves this module.

Why a tool-calling loop rather than the single-shot router in
``ai/intent_classifier.py``: a real question ("what drives our exposure,
and what would fixing the top one cost?") needs several tools and a
follow-up on their results. The classifier remains available for callers
that want cheap one-shot routing without a conversation.

The loop is written by hand rather than delegating to the SDK's tool
runner because each tool result has to be intercepted on the way past — to
accumulate ground truth for the guard, and to emit a stream event — and
because a beta helper is a poor dependency for the one code path that
enforces principle 2.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from ai.llm_client import (
    LLMConfigurationError,
    LLMProviderError,
    LLMTransport,
    get_transport,
    message_text,
)
from ai.numeric_guard import DEFAULT_TOLERANCE, collect_ground_truth, guard_narration
from ai.sessions import ChatSession
from ai.tool_registry import (
    ToolExecution,
    anthropic_tool_definitions,
    available_frameworks,
    execute_tool,
)

#: How many times the model may call tools before the loop stops and
#: answers with what it has. Enough for "get exposure, get its drivers,
#: check a framework, then answer"; low enough that a confused model
#: cannot spend a conversation's budget in one turn.
DEFAULT_MAX_TOOL_ITERATIONS = 6

CHAT_SYSTEM_PROMPT = """\
You are the Su₹aksha assistant. Su₹aksha quantifies an organization's cyber
risk in rupees — Expected Annual Loss and Value at Risk — from security
telemetry, recommends where to spend a security budget, and maps findings to
Indian regulatory frameworks (RBI Directions 2026, SEBI CSCRF/CCI, CIS
Controls, NIST CSF, ISO 27001). You answer questions about this
infrastructure for security and risk leaders.

How you work:

- Every figure you report must come from a tool call in this conversation.
  You never compute, estimate, approximate, extrapolate or illustrate a
  number yourself — not a rupee figure, not a count, not a percentage, not a
  date. The rupee figure is produced by a deterministic Open FAIR + Monte
  Carlo engine; your job is to route to it and to narrate what it returned.
- A verifier checks every number in your reply against the actual tool
  results and visibly flags any it cannot match. Inventing or "helpfully"
  adjusting a figure does not help the reader; it just gets flagged.
- When a tool reports that something is unavailable, say plainly what is not
  available and why, in your own words. Do not retry the tool, do not offer a
  placeholder or a typical industry value, and do not say what the number
  "would likely be".
- Always attribute a figure to its source: the snapshot_id it was computed
  from, and for compliance, the framework version and effective date.
- When you report Expected Annual Loss, also report what drives it. A
  bottom-line number with no explanation of its drivers cannot be acted on.
- Never collapse control-by-control compliance into an overall "compliant" or
  "non-compliant" verdict, and never call a control met because investment in
  it was recommended. Compliance follows evidence about controls and
  findings, nothing else.
- Never add up the risk reduction of individual controls. Overlapping
  controls make that sum badly overstate the benefit; only the optimizer's
  joint re-simulation gives a real combined figure.
- If a scanner did not report for the current snapshot, absence of a finding
  is not evidence of remediation. Say so when it matters to the answer.

Be direct and concise. Write for someone who has to defend these numbers to a
board or a regulator."""


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call the model made during a turn, as reported to the client.

    Attributes:
        tool_name: Which tool ran.
        arguments: The arguments the model chose, after validation.
        status: ``"ok"``, ``"unavailable"`` or ``"error"``.
        detail: Why, for a non-``ok`` status.
        result: The tool's structured output when ``status == "ok"``, so a
            client can render the underlying data alongside the prose.
    """

    tool_name: str
    arguments: dict[str, Any]
    status: str
    detail: str | None = None
    result: dict[str, Any] | None = None

    @classmethod
    def from_execution(cls, execution: ToolExecution) -> ToolCallRecord:
        """Build a record from a :class:`ai.tool_registry.ToolExecution`."""
        return cls(
            tool_name=execution.tool_name,
            arguments=execution.arguments,
            status=execution.status,
            detail=execution.detail,
            result=execution.result,
        )


@dataclass(frozen=True)
class ChatReply:
    """A completed assistant turn, ready to display.

    Attributes:
        session_id: The session this turn belongs to. A client that sent an
            unknown or expired session_id gets a new one here.
        text: The reply to display. Always
            ``ai.numeric_guard.GuardResult.corrected_text`` — never the
            model's raw output.
        all_claims_verified: Whether every number in ``text`` matched a
            value a real tool produced in this conversation.
        unverified_claims: The exact substrings that could not be matched,
            each already flagged inline in ``text``.
        tool_calls: Every tool call made during this turn, in order.
        model: The model that produced the turn, for auditability.
        stop_reason: The provider's stop reason for the final message
            (``"end_turn"``, ``"max_tokens"``, ``"refusal"``), or
            ``"max_tool_iterations"`` when this module stopped the loop.
    """

    session_id: str
    text: str
    all_claims_verified: bool
    unverified_claims: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    model: str = ""
    stop_reason: str = ""


ChatEventType = Literal["session", "text_delta", "tool_call", "tool_result", "final", "error"]


@dataclass(frozen=True)
class ChatEvent:
    """One event from :meth:`ChatEngine.stream_turn`.

    Attributes:
        type: ``"session"`` (first, carrying the session_id),
            ``"text_delta"`` (incremental prose),
            ``"tool_call"``/``"tool_result"`` (progress while tools run),
            ``"final"`` (the complete :class:`ChatReply`), or ``"error"``.
        data: Event payload, JSON-serializable.

    Must never:
        Let a client treat streamed ``text_delta`` text as the answer. The
        deltas are the model's raw output; the verified text arrives in the
        ``final`` event, which carries ``text_replaced`` when the guard
        changed it. A client that has already painted the deltas must
        repaint from ``final``.
    """

    type: ChatEventType
    data: dict[str, Any]


class ChatEngine:
    """Runs chat turns: model -> tools -> model -> guarded reply.

    Args:
        transport: The LLM transport to use; defaults to the process-wide
            one from ``ai.llm_client.get_transport``.
        tolerance: Relative tolerance passed to
            ``ai.numeric_guard.guard_narration``.
        max_tool_iterations: Ceiling on model/tool round trips per turn;
            defaults to ``CHAT_MAX_TOOL_ITERATIONS`` in the environment,
            then :data:`DEFAULT_MAX_TOOL_ITERATIONS`.
    """

    def __init__(
        self,
        transport: LLMTransport | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
        max_tool_iterations: int | None = None,
    ) -> None:
        self._transport = transport
        self._tolerance = tolerance
        self._max_iterations = max_tool_iterations or int(
            os.environ.get("CHAT_MAX_TOOL_ITERATIONS", DEFAULT_MAX_TOOL_ITERATIONS)
        )

    @property
    def transport(self) -> LLMTransport:
        """The transport this engine calls, resolved on first use."""
        if self._transport is None:
            self._transport = get_transport()
        return self._transport

    def run_turn(self, session: ChatSession, user_message: str) -> ChatReply:
        """Run one complete turn, returning a verified reply.

        Args:
            session: The conversation to continue. Mutated in place: the
                user turn, every assistant turn and every tool result are
                appended, and tool output is merged into its ground truth.
            user_message: What the user typed.

        Returns:
            A :class:`ChatReply` whose ``text`` has already been through
            ``ai.numeric_guard``.

        Raises:
            ai.llm_client.LLMConfigurationError: The provider is not
                configured (no API key, SDK not installed).
            ai.llm_client.LLMProviderError: The provider call failed.
        """
        self._begin_turn(session, user_message)
        tools = anthropic_tool_definitions()
        records: list[ToolCallRecord] = []
        answer_parts: list[str] = []
        model = self.transport.model
        stop_reason = "max_tool_iterations"

        for _ in range(self._max_iterations):
            message = self.transport.create_message(
                system=CHAT_SYSTEM_PROMPT,
                messages=session.messages,
                tools=tools,
            )
            model = str(message.get("model", model))
            stop_reason = str(message.get("stop_reason", ""))
            session.append({"role": "assistant", "content": message.get("content", [])})
            text = message_text(message)
            if text:
                answer_parts.append(text)
            if stop_reason != "tool_use":
                break
            tool_message, new_records = self._run_tool_calls(session, message)
            records.extend(new_records)
            session.append(tool_message)
        else:
            # The loop ran out of iterations with the model still calling tools.
            stop_reason = "max_tool_iterations"

        return self._finalize(session, answer_parts, records, model, stop_reason)

    def stream_turn(self, session: ChatSession, user_message: str) -> Iterator[ChatEvent]:
        """Run one complete turn, yielding progress events as they happen.

        Args:
            session: The conversation to continue; mutated exactly as in
                :meth:`run_turn`.
            user_message: What the user typed.

        Yields:
            A ``session`` event, then ``text_delta``/``tool_call``/
            ``tool_result`` events as the turn progresses, and finally
            either one ``final`` event carrying the verified
            :class:`ChatReply`, or one ``error`` event.

        Must never:
            End without a ``final`` or ``error`` event — a client that saw
            only deltas would be left displaying unverified text.
        """
        yield ChatEvent(type="session", data={"session_id": session.session_id})
        self._begin_turn(session, user_message)
        tools = anthropic_tool_definitions()
        records: list[ToolCallRecord] = []
        answer_parts: list[str] = []
        model = self.transport.model
        stop_reason = "max_tool_iterations"

        try:
            for _ in range(self._max_iterations):
                message: dict[str, Any] | None = None
                for chunk in self.transport.stream_message(
                    system=CHAT_SYSTEM_PROMPT,
                    messages=session.messages,
                    tools=tools,
                ):
                    if chunk.kind == "text_delta":
                        yield ChatEvent(type="text_delta", data={"text": chunk.text})
                    elif chunk.kind == "final_message":
                        message = chunk.message
                if message is None:
                    raise LLMProviderError("stream ended without a final message")

                model = str(message.get("model", model))
                stop_reason = str(message.get("stop_reason", ""))
                session.append({"role": "assistant", "content": message.get("content", [])})
                text = message_text(message)
                if text:
                    answer_parts.append(text)
                if stop_reason != "tool_use":
                    break

                for block in _tool_use_blocks(message):
                    yield ChatEvent(
                        type="tool_call",
                        data={
                            "tool_name": block.get("name", ""),
                            "arguments": block.get("input", {}),
                        },
                    )
                tool_message, new_records = self._run_tool_calls(session, message)
                records.extend(new_records)
                session.append(tool_message)
                for record in new_records:
                    yield ChatEvent(
                        type="tool_result",
                        data={
                            "tool_name": record.tool_name,
                            "status": record.status,
                            "detail": record.detail,
                        },
                    )
            else:
                stop_reason = "max_tool_iterations"
        except (LLMConfigurationError, LLMProviderError) as exc:
            yield ChatEvent(
                type="error",
                data={"error": type(exc).__name__, "message": str(exc)},
            )
            return

        reply = self._finalize(session, answer_parts, records, model, stop_reason)
        streamed = "\n\n".join(answer_parts)
        yield ChatEvent(
            type="final",
            data={**reply_to_dict(reply), "text_replaced": reply.text != streamed},
        )

    def _begin_turn(self, session: ChatSession, user_message: str) -> None:
        """Append the user turn and seed ground truth with repo-sourced facts.

        The framework keys come from the control library on disk, not from
        the model, so a reply naming "RBI Directions 2026" is restating a
        real fact rather than inventing a number — seeding them keeps the
        guard's flags meaningful instead of noisy.
        """
        if not session.ground_truth:
            session.record_ground_truth(
                collect_ground_truth(available_frameworks(), prefix="control_library.frameworks")
            )
        session.append({"role": "user", "content": user_message})

    def _run_tool_calls(
        self, session: ChatSession, message: dict[str, Any]
    ) -> tuple[dict[str, Any], list[ToolCallRecord]]:
        """Execute every tool_use block in one assistant message.

        Returns:
            The ``user`` message carrying every ``tool_result`` block — all
            of them in a single message, as the Messages API requires — and
            a record per call for the client.
        """
        results: list[dict[str, Any]] = []
        records: list[ToolCallRecord] = []
        for block in _tool_use_blocks(message):
            execution = execute_tool(str(block.get("name", "")), dict(block.get("input", {})))
            session.record_ground_truth(execution.ground_truth)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": execution.to_model_content(),
                    "is_error": execution.is_error,
                }
            )
            records.append(ToolCallRecord.from_execution(execution))
        return {"role": "user", "content": results}, records

    def _finalize(
        self,
        session: ChatSession,
        answer_parts: list[str],
        records: list[ToolCallRecord],
        model: str,
        stop_reason: str,
    ) -> ChatReply:
        """Guard the assembled answer and package it as a :class:`ChatReply`."""
        raw_text = "\n\n".join(part for part in answer_parts if part)
        if not raw_text:
            raw_text = _empty_answer_text(stop_reason)
        guarded = guard_narration(raw_text, session.ground_truth, self._tolerance)
        return ChatReply(
            session_id=session.session_id,
            text=guarded.corrected_text,
            all_claims_verified=guarded.all_claims_verified,
            unverified_claims=[claim.raw_text for claim in guarded.unverified_claims],
            tool_calls=records,
            model=model,
            stop_reason=stop_reason,
        )


def _tool_use_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ``tool_use`` content blocks of a provider message."""
    return [
        block
        for block in message.get("content", [])
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def _empty_answer_text(stop_reason: str) -> str:
    """Explain a turn that produced no prose, rather than returning nothing."""
    if stop_reason == "max_tool_iterations":
        return (
            "I stopped after reaching the limit on tool calls for one turn without "
            "reaching an answer. Please narrow the question and ask again."
        )
    if stop_reason == "refusal":
        return "The model declined to answer this request."
    if stop_reason == "max_tokens":
        return "The reply was cut off before any text was produced. Please ask again."
    return "No answer was produced for this turn."


def reply_to_dict(reply: ChatReply) -> dict[str, Any]:
    """Render a :class:`ChatReply` as a JSON-serializable dict."""
    return {
        "session_id": reply.session_id,
        "text": reply.text,
        "all_claims_verified": reply.all_claims_verified,
        "unverified_claims": list(reply.unverified_claims),
        "tool_calls": [
            {
                "tool_name": record.tool_name,
                "arguments": record.arguments,
                "status": record.status,
                "detail": record.detail,
                "result": record.result,
            }
            for record in reply.tool_calls
        ],
        "model": reply.model,
        "stop_reason": reply.stop_reason,
    }
