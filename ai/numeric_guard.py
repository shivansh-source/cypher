"""Verifies every number in an LLM-generated narration against real engine output.

This is the enforcement point for repo-root ``CLAUDE.md`` principle 2: an
LLM narration is never trusted to have restated a number correctly, and is
never allowed to introduce a number that didn't come from a real
``core.engine``/``core.optimizer``/``governance`` computation. This module
must run on every piece of LLM-generated text before it is shown to a user.

The guard is deliberately biased toward over-extraction: a claim it cannot
match against ground truth is flagged, even when the number is innocuous
(a control count, a framework year). A flagged-but-correct number costs a
reader a second look; an unflagged invented rupee figure is the failure
this module exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Maximum relative difference between a narrated number and a ground-truth
#: value before the claim is flagged. 1% admits the rounding prose
#: legitimately does ("₹4.2 crore" for ₹4,21,37,000) while still catching a
#: figure that was restated wrongly or invented outright.
#:
#: This is a verification-policy constant, not a modelling one: it never
#: enters a risk computation and changing it cannot change a rupee figure,
#: only how strictly prose about that figure is checked. That is why it
#: lives here and not in ``core/assumptions.py``, which is reserved for
#: constants the engine and optimizer consume.
DEFAULT_TOLERANCE = 0.01

#: Multipliers for Indian and international magnitude words, applied to the
#: digits preceding them so that "1.2 crore" is compared against ground
#: truth in the same unit (INR) as the engine produced it.
_SCALE_WORDS: dict[str, float] = {
    "thousand": 1e3,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "million": 1e6,
    "mn": 1e6,
    "billion": 1e9,
    "bn": 1e9,
}

#: One number-like claim: an optional currency marker, digits with optional
#: Indian or Western comma grouping, an optional decimal part, and an
#: optional magnitude word or percent sign.
_CLAIM_PATTERN = re.compile(
    r"""
    (?P<currency>₹|Rs\.?|INR)?
    \s*
    (?P<digits>\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    (?P<suffix>%|thousand|lakhs?|lacs?|crores?|cr|million|mn|billion|bn)?
    """,
    re.VERBOSE | re.IGNORECASE,
)

#: How an unverified claim is marked in ``GuardResult.corrected_text``.
#: Callers display this text verbatim; the marker is what tells a reader
#: (and a screenshot) that the figure was not traceable to engine output.
_FLAG_TEMPLATE = "[UNVERIFIED: {claim}]"


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
    claims: list[NumericClaim] = []
    for match in _CLAIM_PATTERN.finditer(narration_text):
        digits = match.group("digits")
        if digits is None:
            continue
        value = _parse_digits(digits)
        if value is None:
            continue
        suffix = (match.group("suffix") or "").lower()
        if suffix and suffix != "%":
            value *= _SCALE_WORDS[suffix]
        start, end = match.span()
        # Trim whitespace the pattern absorbed between the parts, so the
        # span stays tight around what a reader would call "the number".
        raw = narration_text[start:end]
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        claims.append(
            NumericClaim(
                raw_text=raw[lead : len(raw) - trail],
                parsed_value=value,
                span=(start + lead, end - trail),
            )
        )
    return claims


def _parse_digits(digits: str) -> float | None:
    """Parse a grouped digit string ("42,00,000", "1 234.5") into a float."""
    cleaned = digits.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:  # pragma: no cover - the pattern only matches numbers
        return None


def _matches(claim_value: float, truth_value: float, tolerance: float) -> bool:
    """Whether a claim is within ``tolerance`` (relative) of a ground-truth value."""
    if truth_value == 0.0:
        return claim_value == 0.0
    return abs(claim_value - truth_value) <= tolerance * abs(truth_value)


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
        ``corrected_text`` is empty here — this function has no access to
        the narration; use :func:`guard_narration` for the full pipeline.

    Must never:
        Treat a claim with no matching ground-truth key as verified by
        default — absence of a match is a failure to verify, not a pass.
    """
    truths = list(ground_truth_values.values())
    unverified: list[NumericClaim] = []
    for claim in claims:
        # A percentage in prose ("12%") legitimately narrates a ground-truth
        # probability stored as a fraction (0.12), so a percent-suffixed
        # claim may match either form — but it still has to match a real
        # value; nothing is accepted without one.
        candidates = [claim.parsed_value]
        if claim.raw_text.rstrip().endswith("%"):
            candidates.append(claim.parsed_value / 100.0)
        if not any(_matches(c, truth, tolerance) for c in candidates for truth in truths):
            unverified.append(claim)
    return GuardResult(
        all_claims_verified=not unverified,
        unverified_claims=unverified,
        corrected_text="",
    )


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
    claims = extract_numeric_claims(narration_text)
    verified = verify_against_ground_truth(claims, ground_truth_values, tolerance)
    if verified.all_claims_verified:
        return GuardResult(
            all_claims_verified=True,
            unverified_claims=[],
            corrected_text=narration_text,
        )
    corrected = narration_text
    # Right to left, so each replacement leaves earlier spans valid.
    for claim in sorted(verified.unverified_claims, key=lambda c: c.span[0], reverse=True):
        start, end = claim.span
        corrected = (
            corrected[:start] + _FLAG_TEMPLATE.format(claim=claim.raw_text) + corrected[end:]
        )
    return GuardResult(
        all_claims_verified=False,
        unverified_claims=verified.unverified_claims,
        corrected_text=corrected,
    )


def collect_ground_truth(payload: Any, prefix: str = "") -> dict[str, float]:
    """Flatten every number a real computation produced into ground truth.

    Walks a structured tool/engine result and collects each numeric leaf,
    keyed by its dotted path, so that :func:`guard_narration` has the full
    set of values a narration is entitled to restate. Numbers embedded in
    string values (a framework key like ``"rbi_2026_directions"``, a
    version like ``"v1.2"``) are collected too — they came from real
    output, so a narration quoting them is restating, not inventing.

    Args:
        payload: Any JSON-shaped structure returned by ``core/``,
            ``governance/``, or an ``ai.tools`` wrapper around them.
        prefix: Dotted path prefix, used when recursing.

    Returns:
        A dict of dotted field path -> value, suitable as
        ``ground_truth_values``.

    Must never:
        Be given a value the model produced (a narration, a tool argument
        the model chose) — that would let the model authorize its own
        numbers, which is exactly what this module exists to prevent.
    """
    truths: dict[str, float] = {}
    if isinstance(payload, bool):
        return truths
    if isinstance(payload, int | float):
        truths[prefix or "value"] = float(payload)
        return truths
    if isinstance(payload, str):
        for index, match in enumerate(re.finditer(r"\d+(?:\.\d+)?", payload)):
            truths[f"{prefix or 'value'}#{index}"] = float(match.group())
        return truths
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            truths.update(collect_ground_truth(value, child))
        return truths
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            truths.update(collect_ground_truth(value, f"{prefix}[{index}]"))
        return truths
    return truths
