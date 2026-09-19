"""Verifies every number in an LLM-generated narration against real engine output.

This is the enforcement point for repo-root ``CLAUDE.md`` principle 2: an
LLM narration is never trusted to have restated a number correctly, and is
never allowed to introduce a number that didn't come from a real
``core.engine``/``core.optimizer``/``governance`` computation. This module
must run on every piece of LLM-generated text before it is shown to a user.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NumericClaim:
    """A single number found in LLM-generated text, pending verification.

    Attributes:
        raw_text: The exact substring of the narration this claim came
            from (e.g. "₹42,00,000" or "42 lakh"), for precise
            replacement/flagging.
        parsed_value: The claim's value normalized to a float in the same
            unit as the source-of-truth values it will be checked against
            (e.g. INR, not lakhs/crores) — conversion must be exact, not
            approximate.
        span: (start, end) character offsets of ``raw_text`` within the
            narration, for in-place correction or flagging.
    """

    raw_text: str
    parsed_value: float
    span: tuple[int, int]


@dataclass(frozen=True)
class GuardResult:
    """Outcome of checking a narration's numeric claims against ground truth.

    Attributes:
        all_claims_verified: True only if every extracted claim matched a
            value in the provided ground truth within tolerance.
        unverified_claims: Claims that did not match any ground-truth
            value — the caller must not display the narration as-is if
            this is non-empty.
        corrected_text: The narration with any unverified numeric claim
            replaced or flagged, safe to display. Must equal the input
            text unchanged if ``all_claims_verified`` is True.
    """

    all_claims_verified: bool
    unverified_claims: list[NumericClaim]
    corrected_text: str


def extract_numeric_claims(narration_text: str) -> list[NumericClaim]:
    """Find every number-like claim in LLM-generated text.

    Args:
        narration_text: The raw narration text produced by the LLM.

    Returns:
        Every :class:`NumericClaim` found, including rupee figures in any
        common Indian numbering convention (lakh/crore) or plain digits.

    Must never:
        Miss a numeric claim due to unfamiliar formatting — a false
        negative here means an unverified number reaches the user. Prefer
        over-extraction (flagging something that isn't really a
        risk-relevant number) to under-extraction.
    """
    raise NotImplementedError


def verify_against_ground_truth(
    claims: list[NumericClaim], ground_truth_values: dict[str, float], tolerance: float
) -> GuardResult:
    """Check extracted numeric claims against real engine/optimizer output.

    Args:
        claims: Output of :func:`extract_numeric_claims`.
        ground_truth_values: The actual computed values (e.g. from a
            ``core.engine.RiskFigure`` or
            ``core.optimizer.PortfolioRecommendation``) the narration is
            supposed to be describing, keyed by a stable field name.
        tolerance: Maximum allowed relative difference between a claim and
            its matching ground-truth value before it's flagged as
            unverified (e.g. to allow for reasonable rounding in prose).

    Returns:
        A :class:`GuardResult` describing whether every claim checked out.

    Must never:
        Treat a claim with no matching ground-truth key as verified by
        default — absence of a match is a failure to verify, not a pass.
    """
    raise NotImplementedError


def guard_narration(
    narration_text: str, ground_truth_values: dict[str, float], tolerance: float
) -> GuardResult:
    """Run the full extract -> verify pipeline on a piece of LLM narration.

    Args:
        narration_text: The raw narration text produced by the LLM.
        ground_truth_values: The actual computed values the narration
            should be describing.
        tolerance: Maximum allowed relative difference before a claim is
            flagged as unverified.

    Returns:
        A :class:`GuardResult`. Callers (``interfaces/api``,
        ``interfaces/cli``) must never display ``narration_text`` directly
        — they must display ``result.corrected_text`` instead, and must
        never bypass this function for any LLM-generated text destined for
        a user.

    Must never:
        Return a result with ``all_claims_verified=True`` while
        ``unverified_claims`` is non-empty, or vice versa — the two must be
        consistent.
    """
    raise NotImplementedError
