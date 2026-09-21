"""Thin client wrapping whichever LLM provider is configured, plus the
narration path.

This is the second (and last) place an LLM is invoked in this codebase,
alongside ``ai/intent_classifier.py``. Any text produced here that will be
shown to a user must be passed through ``ai/numeric_guard.py`` before
display — this module does not do that itself; callers are responsible for
calling the guard.

The provider is Groq (``ai/groq_transport.py``). Every request goes through
an :class:`LLMTransport`, so that ``ai/chat.py`` and
``ai/intent_classifier.py`` can be exercised in tests without a network call
or an API key. Conversations cross the transport boundary as plain
content-block dicts (``text`` / ``tool_use`` / ``tool_result``);
``ai/groq_transport.py`` translates to and from Groq's OpenAI-shaped API. The
Groq SDK is imported lazily inside that transport, so this module stays
importable where it is not installed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM provider is not usable (no API key, no SDK installed).

    Callers in ``interfaces/`` must surface this as an explicit "the
    assistant is not configured" state rather than degrading into an
    answer produced without a model.
    """


class LLMProviderError(RuntimeError):
    """Raised when the provider was reachable but the call failed.

    Wraps the provider's own exception so that no caller outside this
    module has to import the provider SDK to handle an error.
    """


@dataclass(frozen=True)
class LLMResponse:
    """Raw response from the configured LLM provider.

    Attributes:
        text: The generated text, not yet passed through
            ``ai.numeric_guard``.
        model: Identifier of the model that produced this response, for
            logging/auditability.
        raw_provider_response: The unmodified provider response object,
            kept for debugging only — must never be parsed by any caller
            outside this module.
    """

    text: str
    model: str
    raw_provider_response: Any


@dataclass(frozen=True)
class StreamChunk:
    """One item from :meth:`LLMTransport.stream_message`.

    Attributes:
        kind: ``"text_delta"`` for an incremental piece of assistant text,
            ``"final_message"`` for the single terminating chunk carrying
            the fully accumulated provider message.
        text: The incremental text, for ``kind="text_delta"``; empty
            otherwise.
        message: The accumulated provider message as a JSON-shaped dict,
            for ``kind="final_message"``; None otherwise.

    Must never:
        Be yielded with ``kind="final_message"`` more than once per
        stream, or with any chunk following it — consumers treat it as the
        end of the turn.
    """

    kind: Literal["text_delta", "final_message"]
    text: str = ""
    message: dict[str, Any] | None = None


class LLMTransport(Protocol):
    """The provider surface the rest of ``ai/`` is allowed to depend on.

    Messages, tool definitions and tool results cross this boundary as
    plain JSON-shaped dicts (a content-block shape), deliberately:
    it keeps ``ai/chat.py`` testable against a fake and keeps the provider
    SDK's types from leaking into modules that must not depend on them.
    """

    @property
    def model(self) -> str:
        """Identifier of the model this transport will call."""

    def create_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send one non-streaming request and return the provider message as a dict."""

    def stream_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[StreamChunk]:
        """Send one streaming request, yielding text deltas then one final message."""


def _as_provider_error(exc: Exception) -> Exception:
    """Translate a provider exception into one of this module's error types."""
    if isinstance(exc, LLMConfigurationError | LLMProviderError):
        return exc
    return LLMProviderError(f"{type(exc).__name__}: {exc}")


_default_transport: LLMTransport | None = None


def get_transport() -> LLMTransport:
    """Return the process-wide :class:`LLMTransport`, building it on first use.

    Returns:
        The configured transport. Construction never contacts the provider,
        so a missing API key surfaces at call time as
        :class:`LLMConfigurationError`, not at import time.
    """
    global _default_transport
    if _default_transport is None:
        from ai.groq_transport import GroqTransport

        _default_transport = GroqTransport()
    return _default_transport


def set_transport(transport: LLMTransport | None) -> None:
    """Replace the process-wide transport (tests).

    Args:
        transport: The transport to use, or None to fall back to a freshly
            built :class:`ai.groq_transport.GroqTransport` on next use.
    """
    global _default_transport
    _default_transport = transport


def message_text(message: dict[str, Any]) -> str:
    """Concatenate the text blocks of a provider message.

    Args:
        message: A provider message dict (as returned by
            :meth:`LLMTransport.create_message`).

    Returns:
        Every ``text`` content block joined in order.
    """
    parts: list[str] = []
    for block in message.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def narrate_risk_figure(
    risk_figure: dict[str, Any], user_context: str | None = None
) -> LLMResponse:
    """Generate prose narrating an already-computed risk figure.

    Args:
        risk_figure: A serialized ``core.engine.RiskFigure`` (or
            ``core.optimizer.PortfolioRecommendation``) — every number the
            narration may reference must appear here already computed.
        user_context: Optional free text describing what the user asked,
            used only to shape tone/framing, never to recompute or
            reinterpret any figure.

    Returns:
        An :class:`LLMResponse` whose ``text`` still requires verification
        via ``ai.numeric_guard.guard_narration`` before being shown to a
        user — this function does not call the guard itself.

    Must never:
        Ask the LLM to estimate, adjust, round in a way that changes the
        value, or fill in any number not already present in
        ``risk_figure``. See repo-root ``CLAUDE.md`` principles 1 and 2.
    """
    transport = get_transport()
    prompt_parts = [
        (
            "Narrate the following already-computed risk figure for a security "
            "leader. Every number you write must appear verbatim in the JSON "
            "below. Do not compute, estimate, adjust, extrapolate or round any "
            "value, and do not introduce a number that is not in the JSON. If "
            "something the reader would want is not in the JSON, say it was not "
            "computed rather than supplying a figure."
        ),
        "",
        "FIGURE (JSON):",
        json.dumps(risk_figure, indent=2, sort_keys=True, default=str),
    ]
    if user_context:
        prompt_parts += ["", "The user asked:", user_context]
    message = transport.create_message(
        system=NARRATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
    )
    return LLMResponse(
        text=message_text(message),
        model=str(message.get("model", transport.model)),
        raw_provider_response=message,
    )


def complete(prompt: str, **kwargs: Any) -> LLMResponse:
    """Low-level passthrough to the configured LLM provider.

    Args:
        prompt: The full prompt to send.
        **kwargs: Provider-specific generation parameters (``system``,
            ``max_tokens``).

    Returns:
        An :class:`LLMResponse`.

    Must never:
        Be called directly by anything outside ``ai/`` — all other
        packages must go through a purpose-specific function
        (:func:`narrate_risk_figure`, ``ai.chat.ChatEngine``, or a
        classifier in ``ai/intent_classifier.py``) so that every LLM call
        site has a clearly bounded contract.
    """
    transport = get_transport()
    system = str(kwargs.pop("system", NARRATION_SYSTEM_PROMPT))
    max_tokens = kwargs.pop("max_tokens", None)
    message = transport.create_message(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return LLMResponse(
        text=message_text(message),
        model=str(message.get("model", transport.model)),
        raw_provider_response=message,
    )


#: System prompt for the narration path. The chat assistant has its own,
#: larger prompt in ``ai/chat.py``; both encode the same prohibition.
NARRATION_SYSTEM_PROMPT = (
    "You narrate cyber-risk figures that have already been computed by a "
    "deterministic Open FAIR + Monte Carlo engine. You never compute, "
    "estimate or adjust a figure yourself, and every number in your prose "
    "must appear verbatim in the data you were given. A separate verifier "
    "checks every number you write against real engine output and flags any "
    "it cannot match, so inventing or rounding a figure does not help the "
    "reader — it just gets flagged. When the data does not contain something "
    "the reader would want, say plainly that it was not computed."
)
