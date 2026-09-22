"""Tests for governance/library_loader.py."""

from __future__ import annotations

import warnings
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from governance.library_loader import (
    collect_confidence_warnings,
    emit_loud_confidence_warning,
    load_all_control_libraries,
    load_control_library,
    validate_source_fields,
)
from governance.tests.conftest import (
    minimal_control,
    minimal_penalty_provision,
    write_library_yaml,
)


def test_rejects_framework_with_effective_to_in_the_past(tmp_path: Path, as_of_date: date) -> None:
    path = write_library_yaml(tmp_path / "lapsed.yaml", effective_to="2020-01-01")
    with pytest.raises(ValueError, match="lapsed"):
        load_control_library(path, as_of_date)


def test_accepts_framework_with_effective_to_in_the_future(
    tmp_path: Path, as_of_date: date
) -> None:
    path = write_library_yaml(tmp_path / "current.yaml", effective_to="2099-01-01")
    library = load_control_library(path, as_of_date)
    assert library.effective_to is not None


def test_accepts_framework_with_null_effective_to(tmp_path: Path, as_of_date: date) -> None:
    path = write_library_yaml(tmp_path / "current.yaml", effective_to=None)
    library = load_control_library(path, as_of_date)
    assert library.effective_to is None


def test_verified_by_human_true_without_source_fails_validation(
    tmp_path: Path, as_of_date: date
) -> None:
    control = minimal_control(verified_by_human=True, source="")
    path = write_library_yaml(tmp_path / "bad.yaml", controls=[control])
    with pytest.raises(ValueError, match="verified_by_human"):
        load_control_library(path, as_of_date)


def test_verified_by_human_true_with_source_is_accepted(tmp_path: Path, as_of_date: date) -> None:
    control = minimal_control(verified_by_human=True, source="a real citation")
    path = write_library_yaml(tmp_path / "ok.yaml", controls=[control])
    library = load_control_library(path, as_of_date)
    assert library.controls[0].verified_by_human is True


def test_invalid_confidence_level_rejected(tmp_path: Path, as_of_date: date) -> None:
    control = minimal_control(confidence="extremely-confident")
    path = write_library_yaml(tmp_path / "bad.yaml", controls=[control])
    with pytest.raises(ValueError, match="confidence"):
        load_control_library(path, as_of_date)


def test_unknown_check_type_rejected(tmp_path: Path, as_of_date: date) -> None:
    control = minimal_control(
        telemetry_check={
            "derivable_from_telemetry": True,
            "source_field": "assets[].identity_access.mfa_enforced",
            "logic": "made up",
            "check_type": "definitely_not_a_real_check",
            "check_params": {},
        }
    )
    path = write_library_yaml(tmp_path / "bad.yaml", controls=[control])
    with pytest.raises(ValueError, match="Unknown telemetry_check.check_type"):
        load_control_library(path, as_of_date)


def test_no_unremediated_findings_unknown_match_key_rejected(
    tmp_path: Path, as_of_date: date
) -> None:
    control = minimal_control(
        telemetry_check={
            "derivable_from_telemetry": True,
            "source_field": "assets[].findings[]",
            "logic": "made up",
            "check_type": "no_unremediated_findings",
            "check_params": {"match": {"not_a_real_key": True}},
        }
    )
    path = write_library_yaml(tmp_path / "bad.yaml", controls=[control])
    with pytest.raises(ValueError, match="unknown key"):
        load_control_library(path, as_of_date)


def test_every_source_field_in_real_control_libraries_resolves_against_schema(
    schema: dict[str, Any],
) -> None:
    """Every real control library file's executable telemetry checks must
    reference real schema/aggregated_assets.schema.json fields."""
    control_library_dir = Path(__file__).resolve().parents[1] / "control_library"
    libraries = load_all_control_libraries(control_library_dir, date(2026, 9, 20))
    assert len(libraries) == 6

    all_errors: list[str] = []
    for library in libraries.values():
        all_errors.extend(validate_source_fields(library, schema))
    assert all_errors == []


def test_validate_source_fields_flags_unresolvable_path(
    tmp_path: Path, as_of_date: date, schema: dict[str, Any]
) -> None:
    control = minimal_control(
        telemetry_check={
            "derivable_from_telemetry": True,
            "source_field": "assets[].nonexistent_field",
            "logic": "made up",
            "check_type": "all_assets_field_true",
            "check_params": {"field_path": "nonexistent_field"},
        }
    )
    path = write_library_yaml(tmp_path / "bad_field.yaml", controls=[control])
    library = load_control_library(path, as_of_date)
    errors = validate_source_fields(library, schema)
    assert len(errors) == 1
    assert "nonexistent_field" in errors[0]


def test_collect_confidence_warnings_flags_low_confidence_and_unverified(
    tmp_path: Path, as_of_date: date
) -> None:
    controls = [
        minimal_control(id="c1", confidence="low"),
        minimal_control(id="c2", confidence="high"),
    ]
    path = write_library_yaml(tmp_path / "mixed.yaml", controls=controls)
    library = load_control_library(path, as_of_date)

    load_warnings = collect_confidence_warnings(library)
    reasons_by_control: dict[str, set[str]] = {}
    for w in load_warnings:
        reasons_by_control.setdefault(w.control_id, set()).add(w.reason)

    assert "confidence=low" in reasons_by_control["c1"]
    assert "not yet verified_by_human" in reasons_by_control["c1"]
    assert "confidence=low" not in reasons_by_control["c2"]
    assert "not yet verified_by_human" in reasons_by_control["c2"]


def test_emit_loud_confidence_warning_actually_warns(tmp_path: Path, as_of_date: date) -> None:
    path = write_library_yaml(tmp_path / "any.yaml")
    library = load_control_library(path, as_of_date)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        emit_loud_confidence_warning(library)
    assert len(caught) == 1
    assert "not yet verified_by_human" in str(caught[0].message)


def test_penalty_provision_round_trips(tmp_path: Path, as_of_date: date) -> None:
    provision = minimal_penalty_provision(
        id="test_penalty",
        penalty_amount_inr=10_000_000.0,
        currently_in_force=False,
        in_force_from="2027-05-13",
    )
    path = write_library_yaml(tmp_path / "penalty.yaml", penalty_provisions=[provision])
    library = load_control_library(path, as_of_date)

    assert len(library.penalty_provisions) == 1
    loaded = library.penalty_provisions[0]
    assert loaded.id == "test_penalty"
    assert loaded.penalty_amount_inr == 10_000_000.0
    assert loaded.currently_in_force is False
    assert loaded.in_force_from == date(2027, 5, 13)


def test_library_without_penalty_provisions_defaults_to_empty_list(
    tmp_path: Path, as_of_date: date
) -> None:
    path = write_library_yaml(tmp_path / "no_penalties.yaml", penalty_provisions=[])
    library = load_control_library(path, as_of_date)
    assert library.penalty_provisions == []


def test_penalty_provision_invalid_confidence_level_rejected(
    tmp_path: Path, as_of_date: date
) -> None:
    provision = minimal_penalty_provision(confidence="extremely-confident")
    path = write_library_yaml(tmp_path / "bad.yaml", penalty_provisions=[provision])
    with pytest.raises(ValueError, match="confidence"):
        load_control_library(path, as_of_date)


def test_penalty_provision_verified_by_human_true_without_source_fails_validation(
    tmp_path: Path, as_of_date: date
) -> None:
    provision = minimal_penalty_provision(verified_by_human=True, source="")
    path = write_library_yaml(tmp_path / "bad.yaml", penalty_provisions=[provision])
    with pytest.raises(ValueError, match="verified_by_human"):
        load_control_library(path, as_of_date)


def test_collect_confidence_warnings_covers_penalty_provisions(
    tmp_path: Path, as_of_date: date
) -> None:
    provision = minimal_penalty_provision(id="p1", confidence="low")
    path = write_library_yaml(tmp_path / "mixed.yaml", penalty_provisions=[provision])
    library = load_control_library(path, as_of_date)

    load_warnings = collect_confidence_warnings(library)
    reasons = {w.reason for w in load_warnings if w.control_id == "p1"}
    assert "confidence=low" in reasons
    assert "not yet verified_by_human" in reasons


def test_real_control_libraries_have_no_penalty_provision_marked_met_by_optimizer(
    schema: dict[str, Any],
) -> None:
    """Penalty provisions must never carry telemetry_check/status fields that
    could be mistaken for a compliance verdict — they are monetary facts
    only, never a "met"/"not_met" signal (CLAUDE.md principle 6)."""
    control_library_dir = Path(__file__).resolve().parents[1] / "control_library"
    libraries = load_all_control_libraries(control_library_dir, date(2026, 9, 20))
    for library in libraries.values():
        for provision in library.penalty_provisions:
            assert not hasattr(provision, "status")
            assert not hasattr(provision, "telemetry_check")
