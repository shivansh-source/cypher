"""Turns a user's natural-language request into a structured tool call.

This is one of exactly two places an LLM is invoked in this codebase (the
other is ``ai/llm_client.py``'s narration path). This module's output is a
tool name plus structured arguments — never a number, never a risk
statement, never prose. See repo-root ``CLAUDE.md`` principle 2.

This is single-shot routing: one message in, one tool call out. The chat
assistant (``ai/chat.py``) does not use it — a conversation needs several
tools and follow-ups on their results, which is what the chat
engine's own tool-calling loop is for. This function stays for callers that want
cheap routing without a conversation (a CLI one-liner, a search box).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ai.llm_client import LLMTransport, get_transport
from ai.tool_registry import tool_definitions, tool_names

#: The single tool the classifier is allowed to call. Routing is expressed
#: as one structured call rather than free text so the model cannot answer
#: the question itself on the way past.
_ROUTER_TOOL_NAME = "route_request"

_CLASSIFIER_SYSTEM_PROMPT = (
    "You route a user's question to exactly one Su₹aksha tool. You do not "
    "answer the question, do not describe what the answer might be, and do "
    "not produce any number — you only choose the tool and fill in its "
    "arguments. If the question does not clearly match a tool, still choose "
    "the closest one and report low confidence, so the caller can ask the "
    "user to clarify instead of acting on a guess."
)


@dataclass(frozen=True)
class ToolCall:
    """A structured tool invocation derived from a user's request.

    Attributes:
        tool_name: Must match one of the tool modules in ``ai/tools/``
            (e.g. "get_exposure", "optimize_investment").
        arguments: Structured arguments for that tool, already validated
            against the tool's expected input shape.
        confidence: The classifier's confidence in this mapping, used by
            the caller to decide whether to ask the user for
            clarification instead of proceeding.
    """

    tool_name: str
    arguments: dict[str, Any]
    confidence: float


def _router_tool(available_tools: list[str]) -> dict[str, Any]:
    """Build the routing tool definition, restricted to ``available_tools``."""
    return {
        "name": _ROUTER_TOOL_NAME,
        "description": "Route the user's question to exactly one tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "enum": available_tools,
                    "description": "The tool that answers this question.",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments for the chosen tool, per its own schema.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": (
                        "How confident this routing is. Report below 0.5 when the "
                        "question is ambiguous or matches no tool well."
                    ),
                },
            },
            "required": ["tool_name", "arguments", "confidence"],
        },
    }


def classify_intent(user_message: str, available_tools: list[str]) -> ToolCall:
    """Classify a user's natural-language message into a structured tool call.

    Args:
        user_message: The raw text the user typed.
        available_tools: Names of tools currently available to be called
            (must match module names under ``ai/tools/``).

    Returns:
        A :class:`ToolCall` naming one of ``available_tools`` and
        structured arguments for it.

    Raises:
        ValueError: If ``available_tools`` is empty or names a tool that is
            not registered, or if the model returned no routing call.

    Must never:
        Return a tool_name not present in ``available_tools``. Must never
        compute or embed a rupee figure, risk statement, or any other
        number derived from reasoning about the user's situation — this
        function's entire job is routing, not computation. See repo-root
        ``CLAUDE.md`` principles 1 and 2.
    """
    return classify_intent_with(get_transport(), user_message, available_tools)


def classify_intent_with(
    transport: LLMTransport, user_message: str, available_tools: list[str]
) -> ToolCall:
    """:func:`classify_intent` against an explicit transport (for tests)."""
    if not available_tools:
        raise ValueError("available_tools must name at least one tool.")
    registered = set(tool_names())
    unknown = [name for name in available_tools if name not in registered]
    if unknown:
        raise ValueError(f"not registered in ai.tool_registry: {', '.join(unknown)}")

    catalogue = [
        definition
        for definition in tool_definitions()
        if definition["name"] in set(available_tools)
    ]
    prompt = (
        "Choose the tool that answers this question, and fill in its "
        f"arguments.\n\nTOOLS:\n{json.dumps(catalogue, indent=2)}\n\n"
        f"QUESTION:\n{user_message}"
    )
    message = transport.create_message(
        system=_CLASSIFIER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        tools=[_router_tool(available_tools)],
        # Forced tool choice: the classifier must route, never answer.
        tool_choice={"type": "any"},
    )
    for block in message.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != _ROUTER_TOOL_NAME:
            continue
        routed = dict(block.get("input", {}))
        tool_name = str(routed.get("tool_name", ""))
        if tool_name not in set(available_tools):
            raise ValueError(f"classifier chose unavailable tool '{tool_name}'.")
        arguments = routed.get("arguments") or {}
        return ToolCall(
            tool_name=tool_name,
            arguments=dict(arguments),
            confidence=float(routed.get("confidence", 0.0)),
        )
    raise ValueError("classifier returned no routing call.")
