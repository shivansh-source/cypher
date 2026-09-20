"""Tests for governance/mapper.py.

The most important properties: a missing/null telemetry field must resolve
to "unknown", never "not_met"; an expired attestation must resolve to
"expired_attestation", never "met"; and a weighted score must always report
both its coverage fraction and its low-confidence fraction.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from governance.attestations import load_attestations, record_attestation
from governance.library_loader import load_control_library
from governance.mapper import (
    ControlStatus,
    compute_all_control_statuses,
    compute_control_status,
    compute_weighted_score,
)
from governance.tests.conftest import minimal_control, write_library_yaml


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _telemetry_control(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "telemetry_check": {
            "derivable_from_telemetry": True,
            "source_field": "assets[].identity_access.mfa_enforced",
            "logic": "mfa must be enforced",
            "check_type": "all_assets_field_true",
            "check_params": {"field_path": "identity_access.mfa_enforced"},
        }
    }
    base.update(overrides)
    return minimal_control(**base)


def test_all_assets_field_true_met_when_all_true(
    sample_snapshot: dict[str, Any], as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    snapshot = {
        **sample_snapshot,
        "assets": [sample_snapshot["assets"][0]],
    }  # only asset-web-01, mfa_enforced=true
    control = _telemetry_control(id="mfa_check")
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    status = compute_control_status(snapshot, library, library.controls[0], [], as_of_datetime)
    assert status.status == "met"


def test_all_assets_field_true_not_met_when_any_false(
    sample_snapshot: dict[str, Any], as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    # asset-hr-db-01 has mfa_enforced=false.
    control = _telemetry_control(id="mfa_check")
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    status = compute_control_status(
        sample_snapshot, library, library.controls[0], [], as_of_datetime
    )
    assert status.status == "not_met"
    assert "asset-hr-db-01" in status.evidence_refs


def test_missing_field_resolves_to_unknown_never_not_met(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    snapshot = {
        "assets": [
            {
                "asset_id": "asset-x",
                "findings": [],
                "threat_intel": {},
                "edr": {"agent_installed": True, "agent_healthy": True},
                "identity_access": {"mfa_enforced": None},  # never evaluated
                "network": {},
            }
        ],
        "services": [],
    }
    control = _telemetry_control(id="mfa_check")
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    status = compute_control_status(snapshot, library, library.controls[0], [], as_of_datetime)
    assert status.status == "unknown"


def test_no_applicable_assets_resolves_to_unknown(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    snapshot: dict[str, Any] = {"assets": [], "services": []}
    control = _telemetry_control(id="mfa_check")
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    status = compute_control_status(snapshot, library, library.controls[0], [], as_of_datetime)
    assert status.status == "unknown"


def test_attestation_required_control_with_no_attestation_is_unknown(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    control = minimal_control(
        id="policy_review",
        manual_attestation_required=True,
        attestation_prompt="Provide the policy.",
    )
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    status = compute_control_status(
        {"assets": [], "services": []}, library, library.controls[0], [], as_of_datetime
    )
    assert status.status == "unknown"


def test_attestation_required_control_uses_current_unexpired_attestation(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    control = minimal_control(id="policy_review", manual_attestation_required=True)
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control], framework="fw")
    library = load_control_library(path, as_of_date)

    store = tmp_path / "attestations.json"
    record_attestation(
        store, "policy_review", "fw", "alice", _dt(2026, 6, 1), "reviewed", [], "met"
    )
    attestations = load_attestations(store)

    status = compute_control_status(
        {"assets": [], "services": []}, library, library.controls[0], attestations, as_of_datetime
    )
    assert status.status == "met"


def test_expired_attestation_resolves_to_expired_never_met(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    control = minimal_control(id="policy_review", manual_attestation_required=True)
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control], framework="fw")
    library = load_control_library(path, as_of_date)

    store = tmp_path / "attestations.json"
    # 18 months before as_of_datetime (2026-09-20) — past the 12-month default window.
    record_attestation(
        store, "policy_review", "fw", "alice", _dt(2025, 1, 1), "reviewed", [], "met"
    )
    attestations = load_attestations(store)

    status = compute_control_status(
        {"assets": [], "services": []}, library, library.controls[0], attestations, as_of_datetime
    )
    assert status.status == "expired_attestation"


def test_optimizer_module_is_never_imported_by_mapper() -> None:
    """compute_control_status must never consider anything from core.optimizer."""
    import governance.mapper as mapper_module

    import_lines = [
        line.strip()
        for line in Path(mapper_module.__file__).read_text().splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any("optimizer" in line for line in import_lines)


def test_no_unremediated_findings_flags_open_kev_listed_cve(
    sample_snapshot: dict[str, Any], as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    control = minimal_control(
        id="vuln_check",
        telemetry_check={
            "derivable_from_telemetry": True,
            "source_field": "assets[].findings[]",
            "logic": "no open kev-listed cve",
            "check_type": "no_unremediated_findings",
            "check_params": {"match": {"type": "cve", "kev_listed": True}},
        },
    )
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    # sample_aggregated.json's finding-0001 is type=cve, kev_listed=true, remediated_at=null.
    status = compute_control_status(
        sample_snapshot, library, library.controls[0], [], as_of_datetime
    )
    assert status.status == "not_met"
    assert "finding-0001" in status.evidence_refs


def test_backup_tested_within_days_uses_default_recency(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    control = minimal_control(
        id="backup_check",
        telemetry_check={
            "derivable_from_telemetry": True,
            "source_field": "services[].backup.last_tested_at",
            "logic": "backup must be recently tested",
            "check_type": "backup_tested_within_days",
            "check_params": {"days": None},
        },
    )
    path = write_library_yaml(tmp_path / "lib.yaml", controls=[control])
    library = load_control_library(path, as_of_date)

    stale_snapshot = {
        "assets": [],
        "services": [
            {
                "service_id": "svc-1",
                "backup": {
                    "exists": True,
                    "last_tested_at": "2020-01-01T00:00:00Z",
                    "rpo_hours": 1,
                    "rto_hours": 1,
                },
            }
        ],
    }
    status = compute_control_status(
        stale_snapshot, library, library.controls[0], [], as_of_datetime
    )
    assert status.status == "not_met"


def test_compute_weighted_score_reports_coverage_and_low_confidence_fractions(
    as_of_date: date, tmp_path: Path
) -> None:
    controls = [
        minimal_control(id="met_high", weight=40.0, confidence="high"),
        minimal_control(id="not_met_low", weight=30.0, confidence="low"),
        minimal_control(id="unknown_high", weight=20.0, confidence="high"),
        minimal_control(id="no_weight", weight=None, confidence="high"),
    ]
    path = write_library_yaml(tmp_path / "lib.yaml", controls=controls)
    library = load_control_library(path, as_of_date)

    statuses = [
        ControlStatus("met_high", "test_framework", "1.0", "met", [], "high", False),
        ControlStatus("not_met_low", "test_framework", "1.0", "not_met", [], "low", False),
        ControlStatus("unknown_high", "test_framework", "1.0", "unknown", [], "high", False),
        ControlStatus("no_weight", "test_framework", "1.0", "met", [], "high", False),
    ]

    result = compute_weighted_score(library, statuses)

    assert result.total_weight == 90.0  # excludes the unweighted control
    assert result.determined_weight == 70.0  # met_high + not_met_low, not unknown_high
    assert result.score == 40.0 / 90.0
    assert result.coverage_fraction == 70.0 / 90.0
    assert result.low_confidence_weight_among_determined == 30.0
    assert result.low_confidence_fraction_of_determined == 30.0 / 70.0
    assert result.controls_excluded_no_weight == ["no_weight"]


def test_compute_weighted_score_score_is_none_when_no_control_has_a_weight(
    as_of_date: date, tmp_path: Path
) -> None:
    controls = [minimal_control(id="c1", weight=None)]
    path = write_library_yaml(tmp_path / "lib.yaml", controls=controls)
    library = load_control_library(path, as_of_date)

    statuses = [ControlStatus("c1", "test_framework", "1.0", "unknown", [], "medium", False)]
    result = compute_weighted_score(library, statuses)

    assert result.score is None
    assert result.coverage_fraction is None
    assert result.low_confidence_fraction_of_determined is None


def test_compute_all_control_statuses_covers_every_control_in_order(
    as_of_date: date, as_of_datetime: datetime, tmp_path: Path
) -> None:
    controls = [minimal_control(id="c1"), minimal_control(id="c2"), minimal_control(id="c3")]
    path = write_library_yaml(tmp_path / "lib.yaml", controls=controls)
    library = load_control_library(path, as_of_date)

    statuses = compute_all_control_statuses(
        {"assets": [], "services": []}, library, [], as_of_datetime
    )
    assert [s.control_id for s in statuses] == ["c1", "c2", "c3"]
