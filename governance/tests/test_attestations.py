"""Tests for governance/attestations.py."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from governance.attestations import (
    Attestation,
    compute_expiry,
    current_attestation,
    is_expired,
    load_attestations,
    most_recent_attestation_even_if_expired,
    record_attestation,
)


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def test_record_attestation_appends_without_removing_prior_records(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    record_attestation(
        store,
        "control_a",
        "test_fw",
        "alice",
        _dt(2026, 1, 1),
        "reviewed policy",
        ["doc-1"],
        "met",
    )
    record_attestation(
        store,
        "control_a",
        "test_fw",
        "bob",
        _dt(2026, 6, 1),
        "re-reviewed",
        ["doc-2"],
        "not_met",
    )
    records = load_attestations(store)
    assert len(records) == 2
    assert records[0].attested_by == "alice"
    assert records[1].attested_by == "bob"


def test_record_attestation_rejects_invalid_status(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    with pytest.raises(ValueError, match="status"):
        record_attestation(
            store,
            "control_a",
            "test_fw",
            "alice",
            _dt(2026, 1, 1),
            "reviewed",
            [],
            "definitely_compliant",  # type: ignore[arg-type]
        )


def test_load_attestations_on_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_attestations(tmp_path / "does_not_exist.json") == []


def test_compute_expiry_uses_default_when_no_override_or_control_specific_value() -> None:
    expiry = compute_expiry("some_control_with_no_override", _dt(2026, 1, 15), None)
    assert expiry == _dt(2027, 1, 15)  # DEFAULT_ATTESTATION_VALIDITY_MONTHS == 12


def test_compute_expiry_prefers_explicit_override_over_default() -> None:
    expiry = compute_expiry("some_control", _dt(2026, 1, 15), 6)
    assert expiry == _dt(2026, 7, 15)


def test_compute_expiry_clamps_day_for_shorter_target_month() -> None:
    # Jan 31 + 1 month must not overflow into March.
    expiry = compute_expiry("some_control", _dt(2026, 1, 31), 1)
    assert expiry == _dt(2026, 2, 28)


def test_is_expired_true_at_or_after_expiry() -> None:
    a = Attestation(
        control_id="c",
        framework="fw",
        attested_by="alice",
        attested_at=_dt(2026, 1, 1),
        expires_at=_dt(2026, 6, 1),
        evidence_description="x",
        evidence_document_refs=[],
        status="met",
    )
    assert is_expired(a, _dt(2026, 6, 1)) is True
    assert is_expired(a, _dt(2026, 5, 31)) is False


def test_current_attestation_returns_none_when_expired(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    # 18 months old, well past the 12-month default validity window.
    record_attestation(
        store,
        "control_a",
        "test_fw",
        "alice",
        _dt(2025, 1, 1),
        "reviewed",
        [],
        "met",
    )
    records = load_attestations(store)
    result = current_attestation(records, "control_a", "test_fw", _dt(2026, 9, 20))
    assert result is None


def test_current_attestation_returns_record_when_not_expired(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    record_attestation(
        store,
        "control_a",
        "test_fw",
        "alice",
        _dt(2026, 6, 1),
        "reviewed",
        [],
        "met",
    )
    records = load_attestations(store)
    result = current_attestation(records, "control_a", "test_fw", _dt(2026, 9, 20))
    assert result is not None
    assert result.status == "met"


def test_current_attestation_ignores_other_controls_and_frameworks(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    record_attestation(store, "control_a", "fw_1", "alice", _dt(2026, 6, 1), "x", [], "met")
    record_attestation(store, "control_b", "fw_1", "alice", _dt(2026, 6, 1), "x", [], "met")
    record_attestation(store, "control_a", "fw_2", "alice", _dt(2026, 6, 1), "x", [], "met")
    records = load_attestations(store)
    result = current_attestation(records, "control_a", "fw_1", _dt(2026, 9, 20))
    assert result is not None
    assert result.control_id == "control_a"
    assert result.framework == "fw_1"


def test_most_recent_attestation_even_if_expired_returns_expired_record(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    record_attestation(store, "control_a", "fw", "alice", _dt(2025, 1, 1), "x", [], "met")
    records = load_attestations(store)
    result = most_recent_attestation_even_if_expired(records, "control_a", "fw")
    assert result is not None
    assert is_expired(result, _dt(2026, 9, 20)) is True


def test_most_recent_attestation_picks_the_latest_of_several(tmp_path: Path) -> None:
    store = tmp_path / "attestations.json"
    record_attestation(store, "control_a", "fw", "alice", _dt(2025, 1, 1), "old", [], "not_met")
    record_attestation(store, "control_a", "fw", "bob", _dt(2026, 6, 1), "new", [], "met")
    records = load_attestations(store)
    result = most_recent_attestation_even_if_expired(records, "control_a", "fw")
    assert result is not None
    assert result.attested_by == "bob"
