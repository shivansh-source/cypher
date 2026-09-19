"""Thin client wrapping whichever LLM provider is configured, plus the
narration path.

This is the second (and last) place an LLM is invoked in this codebase,
alongside ``ai/intent_classifier.py``. Any text produced here that will be
shown to a user must be passed through ``ai/numeric_guard.py`` before
display — this module does not do that itself; callers are responsible for
calling the guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    raise NotImplementedError


def complete(prompt: str, **kwargs: Any) -> LLMResponse:
    """Low-level passthrough to the configured LLM provider.

    Args:
        prompt: The full prompt to send.
        **kwargs: Provider-specific generation parameters (temperature,
            max tokens, etc).

    Returns:
        An :class:`LLMResponse`.

    Must never:
        Be called directly by anything outside ``ai/`` — all other
        packages must go through a purpose-specific function
        (:func:`narrate_risk_figure`, or a classifier in
        ``ai/intent_classifier.py``) so that every LLM call site has a
        clearly bounded contract.
    """
    raise NotImplementedError
