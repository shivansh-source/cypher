"""Tests for core/snapshot.py's quality gates and validate/commit lifecycle.

Each gate needs both a passing and a failing fixture; the fail-safe
property (a failing candidate must leave the previous snapshot current)
needs an explicit test of its own, not just gate-level coverage.
"""

from __future__ import annotations

import pytest

# core/snapshot.py (the 5 quality gates + validate/commit lifecycle) is not
# yet implemented — every test below is written against it and currently
# fails with NotImplementedError. xfail (not skip) so CI stays green for
# this known-incomplete state while pytest's own output still visibly
# reports these as xfailed, not silently absent. strict=False: these are
# expected to keep failing until core/snapshot.py exists, not a regression
# guard.
pytestmark = pytest.mark.xfail(
    reason="core/snapshot.py not yet implemented",
    strict=False,
)


def test_asset_count_delta_passes_within_tolerance() -> None:
    """A candidate with an asset count change within tolerance should pass gate 1."""
    raise NotImplementedError


def test_asset_count_delta_fails_when_assets_vanish() -> None:
    """A candidate whose asset population drops far beyond tolerance should fail gate 1."""
    raise NotImplementedError


def test_no_findings_from_unreachable_scanners_passes_when_consistent() -> None:
    """A candidate with no findings attributed to an unreachable scanner should pass gate 2."""
    raise NotImplementedError


def test_no_findings_from_unreachable_scanners_fails_on_inconsistency() -> None:
    """A candidate with a finding attributed to a scanner listed as unreachable should fail gate 2."""
    raise NotImplementedError


def test_criticality_null_fails_but_unknown_string_passes() -> None:
    """Gate 3 must reject a null criticality but accept the literal string 'unknown'."""
    raise NotImplementedError


def test_provenance_required_on_every_finding() -> None:
    """Gate 4 must reject any finding missing connector or raw_source_id provenance."""
    raise NotImplementedError


def test_no_ordinal_value_in_numeric_field() -> None:
    """Gate 5 must reject a candidate storing a string ordinal (e.g. 'High') in a numeric field."""
    raise NotImplementedError


def test_validate_snapshot_reports_every_gate_not_just_first_failure() -> None:
    """validate_snapshot must return all 5 GateResults even when multiple gates fail."""
    raise NotImplementedError


def test_commit_snapshot_sets_previous_valid_to() -> None:
    """Committing a new snapshot must set the previous snapshot's valid_to and leave it otherwise immutable."""
    raise NotImplementedError


def test_failed_validation_leaves_previous_snapshot_current() -> None:
    """A candidate that fails any gate must never become current; the previous snapshot must remain so (fail-safe)."""
    raise NotImplementedError
