"""Tests for ai/numeric_guard.py.

This is the most safety-critical test file in the repo: a bug here means a
hallucinated rupee figure could reach a user unflagged.
"""

from __future__ import annotations

from ai.numeric_guard import (
    DEFAULT_TOLERANCE,
    collect_ground_truth,
    extract_numeric_claims,
    guard_narration,
    verify_against_ground_truth,
)


def test_extract_numeric_claims_finds_plain_rupee_figures() -> None:
    """A narration containing a plain '₹42,00,000'-style figure must be extracted as a claim."""
    text = "Expected annual loss is ₹42,00,000 for the current snapshot."
    claims = extract_numeric_claims(text)
    values = [claim.parsed_value for claim in claims]
    assert 4_200_000.0 in values
    claim = next(c for c in claims if c.parsed_value == 4_200_000.0)
    assert text[claim.span[0] : claim.span[1]] == claim.raw_text
    assert "42,00,000" in claim.raw_text


def test_extract_numeric_claims_finds_lakh_and_crore_phrasing() -> None:
    """A narration containing '42 lakh' or '1.2 crore' phrasing must be extracted and converted to the same unit as ground truth."""
    claims = extract_numeric_claims("EAL is 42 lakh; VaR95 is 1.2 crore.")
    values = [claim.parsed_value for claim in claims]
    assert 4_200_000.0 in values
    assert 12_000_000.0 in values


def test_extract_numeric_claims_does_not_miss_bare_digits() -> None:
    """Plain digits with no currency marker or scale word are still claims."""
    values = [claim.parsed_value for claim in extract_numeric_claims("There are 7 contributors.")]
    assert 7.0 in values


def test_verify_against_ground_truth_passes_matching_claim() -> None:
    """A claim matching a ground-truth value within tolerance must be marked verified."""
    claims = extract_numeric_claims("EAL is ₹42,00,000.")
    result = verify_against_ground_truth(
        claims, {"expected_annual_loss_inr": 4_200_000.0}, DEFAULT_TOLERANCE
    )
    assert result.all_claims_verified
    assert result.unverified_claims == []


def test_verify_against_ground_truth_fails_unmatched_claim() -> None:
    """A claim with no matching ground-truth key must be marked unverified, never verified by default."""
    claims = extract_numeric_claims("EAL is ₹99,00,000.")
    result = verify_against_ground_truth(
        claims, {"expected_annual_loss_inr": 4_200_000.0}, DEFAULT_TOLERANCE
    )
    assert not result.all_claims_verified
    assert [claim.parsed_value for claim in result.unverified_claims] == [9_900_000.0]


def test_verify_against_ground_truth_with_empty_ground_truth_verifies_nothing() -> None:
    """With no ground truth at all, every claim is unverified — absence is not a pass."""
    claims = extract_numeric_claims("EAL is ₹42,00,000.")
    result = verify_against_ground_truth(claims, {}, DEFAULT_TOLERANCE)
    assert not result.all_claims_verified
    assert len(result.unverified_claims) == len(claims)


def test_verify_against_ground_truth_fails_claim_outside_tolerance() -> None:
    """A claim close to but outside the given tolerance of a ground-truth value must be marked unverified."""
    claims = extract_numeric_claims("EAL is ₹42,50,000.")
    inside = verify_against_ground_truth(claims, {"eal": 4_200_000.0}, 0.05)
    outside = verify_against_ground_truth(claims, {"eal": 4_200_000.0}, 0.001)
    assert inside.all_claims_verified
    assert not outside.all_claims_verified


def test_verify_accepts_a_percentage_narrating_a_fractional_ground_truth() -> None:
    """'12%' may narrate a stored 0.12, but only against a real ground-truth value."""
    claims = extract_numeric_claims("The EPSS score is 12%.")
    assert verify_against_ground_truth(claims, {"epss_score": 0.12}, DEFAULT_TOLERANCE)
    assert not verify_against_ground_truth(
        claims, {"epss_score": 0.40}, DEFAULT_TOLERANCE
    ).all_claims_verified


def test_guard_narration_returns_unmodified_text_when_all_verified() -> None:
    """guard_narration's corrected_text must equal the input text exactly when every claim verifies."""
    text = "Expected annual loss is ₹42,00,000 across 7 scenarios."
    result = guard_narration(text, {"eal": 4_200_000.0, "count": 7.0}, DEFAULT_TOLERANCE)
    assert result.all_claims_verified
    assert result.corrected_text == text


def test_guard_narration_flags_or_replaces_unverified_claims() -> None:
    """guard_narration must not return corrected_text containing an unverified numeric claim unflagged."""
    result = guard_narration("EAL is ₹99,00,000.", {"eal": 4_200_000.0}, DEFAULT_TOLERANCE)
    assert not result.all_claims_verified
    assert "UNVERIFIED" in result.corrected_text
    assert "₹99,00,000." not in result.corrected_text.replace("[UNVERIFIED: ", "")


def test_guard_narration_flags_every_unverified_claim_in_order() -> None:
    """Multiple unverified claims must each be flagged, leaving verified ones untouched."""
    result = guard_narration(
        "EAL is ₹42,00,000, VaR is ₹88,00,000 and there are 3 drivers.",
        {"eal": 4_200_000.0, "drivers": 3.0},
        DEFAULT_TOLERANCE,
    )
    assert result.corrected_text.count("[UNVERIFIED:") == 1
    assert "[UNVERIFIED: ₹88,00,000]" in result.corrected_text
    assert "₹42,00,000" in result.corrected_text


def test_guard_result_flags_are_internally_consistent() -> None:
    """all_claims_verified must be False whenever unverified_claims is non-empty, and vice versa."""
    for text, truth in [
        ("EAL is ₹42,00,000.", {"eal": 4_200_000.0}),
        ("EAL is ₹99,00,000.", {"eal": 4_200_000.0}),
        ("No figures here.", {}),
        ("EAL is ₹42,00,000.", {}),
    ]:
        result = guard_narration(text, truth, DEFAULT_TOLERANCE)
        assert result.all_claims_verified == (not result.unverified_claims)


def test_collect_ground_truth_walks_nested_tool_output() -> None:
    """Numbers at any depth of a tool result become ground truth, keyed by path."""
    truths = collect_ground_truth(
        {
            "snapshot_id": "snap-2026",
            "expected_annual_loss_inr": 4_200_000.0,
            "top_contributors": [{"expected_annual_loss_inr": 1_500_000.0}],
            "converged": True,
        },
        prefix="get_exposure",
    )
    values = set(truths.values())
    assert 4_200_000.0 in values
    assert 1_500_000.0 in values
    # Numbers embedded in real string output count — they came from a tool.
    assert 2026.0 in values
    # Booleans are not numbers a narration may restate as a figure.
    assert collect_ground_truth({"converged": True}) == {}
