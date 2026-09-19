"""Turns a user's natural-language request into a structured tool call.

This is one of exactly two places an LLM is invoked in this codebase (the
other is ``ai/llm_client.py``'s narration path). This module's output is a
tool name plus structured arguments — never a number, never a risk
statement, never prose. See repo-root ``CLAUDE.md`` principle 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def classify_intent(user_message: str, available_tools: list[str]) -> ToolCall:
    """Classify a user's natural-language message into a structured tool call.

    Args:
        user_message: The raw text the user typed.
        available_tools: Names of tools currently available to be called
            (must match module names under ``ai/tools/``).

    Returns:
        A :class:`ToolCall` naming one of ``available_tools`` and
        structured arguments for it.

    Must never:
        Return a tool_name not present in ``available_tools``. Must never
        compute or embed a rupee figure, risk statement, or any other
        number derived from reasoning about the user's situation — this
        function's entire job is routing, not computation. See repo-root
        ``CLAUDE.md`` principles 1 and 2.
    """
    raise NotImplementedError
