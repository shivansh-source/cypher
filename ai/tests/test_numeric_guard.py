"""Tests for ai/numeric_guard.py.

This is the most safety-critical test file in the repo: a bug here means a
hallucinated rupee figure could reach a user unflagged.
"""

from __future__ import annotations


def test_extract_numeric_claims_finds_plain_rupee_figures() -> None:
    """A narration containing a plain '₹42,00,000'-style figure must be extracted as a claim."""
    raise NotImplementedError


def test_extract_numeric_claims_finds_lakh_and_crore_phrasing() -> None:
    """A narration containing '42 lakh' or '1.2 crore' phrasing must be extracted and converted to the same unit as ground truth."""
    raise NotImplementedError


def test_verify_against_ground_truth_passes_matching_claim() -> None:
    """A claim matching a ground-truth value within tolerance must be marked verified."""
    raise NotImplementedError


def test_verify_against_ground_truth_fails_unmatched_claim() -> None:
    """A claim with no matching ground-truth key must be marked unverified, never verified by default."""
    raise NotImplementedError


def test_verify_against_ground_truth_fails_claim_outside_tolerance() -> None:
    """A claim close to but outside the given tolerance of a ground-truth value must be marked unverified."""
    raise NotImplementedError


def test_guard_narration_returns_unmodified_text_when_all_verified() -> None:
    """guard_narration's corrected_text must equal the input text exactly when every claim verifies."""
    raise NotImplementedError


def test_guard_narration_flags_or_replaces_unverified_claims() -> None:
    """guard_narration must not return corrected_text containing an unverified numeric claim unflagged."""
    raise NotImplementedError


def test_guard_result_flags_are_internally_consistent() -> None:
    """all_claims_verified must be False whenever unverified_claims is non-empty, and vice versa."""
    raise NotImplementedError
