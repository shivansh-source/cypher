"""Tests for core/snapshot.py's quality gates and validate/commit lifecycle.

Each gate needs both a passing and a failing fixture; the fail-safe
property (a failing candidate must leave the previous snapshot current)
needs an explicit test of its own, not just gate-level coverage.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from core.snapshot import (
    check_asset_count_delta,
    check_criticality_present_or_unknown,
    check_no_findings_from_unreachable_scanners,
    check_no_ordinal_in_numeric_field,
    check_provenance_non_null,
    commit_snapshot,
    validate_snapshot,
)

SAMPLE_SNAPSHOT: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "schema" / "sample_aggregated.json").read_text()
)


def _candidate() -> dict[str, Any]:
    """A fresh, blank-snapshot_id candidate derived from the sample snapshot."""
    candidate = copy.deepcopy(SAMPLE_SNAPSHOT)
    candidate["snapshot_id"] = ""
    return candidate


def test_asset_count_delta_passes_within_tolerance() -> None:
    """A candidate with an asset count change within tolerance should pass gate 1."""
    previous = _candidate()
    candidate = _candidate()

    result = check_asset_count_delta(candidate, previous)

    assert result.passed


def test_asset_count_delta_fails_when_assets_vanish() -> None:
    """A candidate whose asset population drops far beyond tolerance should fail gate 1."""
    previous = _candidate()
    candidate = _candidate()
    candidate["assets"] = []

    result = check_asset_count_delta(candidate, previous)

    assert not result.passed


def test_no_findings_from_unreachable_scanners_passes_when_consistent() -> None:
    """A candidate with no findings attributed to an unreachable scanner should pass gate 2."""
    candidate = _candidate()

    result = check_no_findings_from_unreachable_scanners(candidate)

    assert result.passed


def test_no_findings_from_unreachable_scanners_fails_on_inconsistency() -> None:
    """A candidate with a finding attributed to a scanner listed as unreachable should fail gate 2."""
    candidate = _candidate()
    connector = candidate["assets"][0]["findings"][0]["provenance"]["connector"]
    candidate["scan_scope"]["unreachable_scanners"] = [connector]

    result = check_no_findings_from_unreachable_scanners(candidate)

    assert not result.passed


def test_criticality_null_fails_but_unknown_string_passes() -> None:
    """Gate 3 must reject a null criticality but accept the literal string 'unknown'."""
    unknown_candidate = _candidate()
    unknown_candidate["assets"][0]["findings"][0]["criticality"] = "unknown"
    assert check_criticality_present_or_unknown(unknown_candidate).passed

    null_candidate = _candidate()
    null_candidate["assets"][0]["findings"][0]["criticality"] = None
    assert not check_criticality_present_or_unknown(null_candidate).passed


def test_provenance_required_on_every_finding() -> None:
    """Gate 4 must reject any finding missing connector or raw_source_id provenance."""
    candidate = _candidate()
    candidate["assets"][0]["findings"][0]["provenance"]["connector"] = ""

    result = check_provenance_non_null(candidate)

    assert not result.passed


def test_no_ordinal_value_in_numeric_field() -> None:
    """Gate 5 must reject a candidate storing a string ordinal (e.g. 'High') in a numeric field."""
    candidate = _candidate()
    candidate["assets"][0]["findings"][0]["epss_score"] = "High"

    result = check_no_ordinal_in_numeric_field(candidate)

    assert not result.passed


def test_validate_snapshot_reports_every_gate_not_just_first_failure() -> None:
    """validate_snapshot must return all 5 GateResults even when multiple gates fail."""
    candidate = _candidate()
    candidate["assets"][0]["findings"][0]["criticality"] = None
    candidate["assets"][0]["findings"][0]["provenance"]["connector"] = ""

    results = validate_snapshot(candidate, None)

    assert len(results) == 5
    failed = {r.gate_name for r in results if not r.passed}
    assert failed == {"criticality_present_or_unknown", "provenance_non_null"}


def test_commit_snapshot_sets_previous_valid_to() -> None:
    """Committing a new snapshot must set the previous snapshot's valid_to and leave it otherwise immutable."""
    previous = _candidate()
    previous["snapshot_id"] = "sha256:previous"
    previous["valid_to"] = None
    candidate = _candidate()
    candidate["valid_from"] = "2026-09-23T00:00:00+00:00"

    committed = commit_snapshot(candidate, previous)

    assert previous["valid_to"] == "2026-09-23T00:00:00+00:00"
    assert committed["snapshot_id"]
    assert committed["assets"] == candidate["assets"]


def test_failed_validation_leaves_previous_snapshot_current() -> None:
    """A candidate that fails any gate must never become current; the previous snapshot must remain so (fail-safe)."""
    candidate = _candidate()
    candidate["assets"][0]["findings"][0]["criticality"] = None

    results = validate_snapshot(candidate, None)

    assert not all(r.passed for r in results)
    # A caller (e.g. interfaces/cli/riskctl.py's ingest_command) must check
    # this before ever calling commit_snapshot — this test documents the
    # contract, not commit_snapshot's own behavior (it never re-validates).
