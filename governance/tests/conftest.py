"""Shared fixtures for governance/ tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

AS_OF_DATE = date(2026, 9, 20)
AS_OF_DATETIME = datetime(2026, 9, 20, tzinfo=UTC)


@pytest.fixture
def schema() -> dict[str, Any]:
    contents: dict[str, Any] = json.loads(
        (REPO_ROOT / "schema" / "aggregated_assets.schema.json").read_text()
    )
    return contents


@pytest.fixture
def sample_snapshot() -> dict[str, Any]:
    contents: dict[str, Any] = json.loads(
        (REPO_ROOT / "schema" / "sample_aggregated.json").read_text()
    )
    return contents


@pytest.fixture
def as_of_date() -> date:
    return AS_OF_DATE


@pytest.fixture
def as_of_datetime() -> datetime:
    return AS_OF_DATETIME


def minimal_control(**overrides: Any) -> dict[str, Any]:
    """A minimal, valid control entry dict, with fields overridable for tests."""
    control: dict[str, Any] = {
        "id": "test_control",
        "framework_ref": "TEST-1",
        "parameter_name": "Test control",
        "weight": None,
        "description": "A control used only in tests.",
        "maturity_bands": None,
        "source": "test fixture, not a real citation",
        "confidence": "medium",
        "verified_by_human": False,
        "telemetry_check": {
            "derivable_from_telemetry": False,
            "source_field": None,
            "logic": None,
            "check_type": None,
            "check_params": {},
        },
        "manual_attestation_required": False,
        "attestation_prompt": None,
        "attestation_validity_months": None,
    }
    control.update(overrides)
    return control


def minimal_penalty_provision(**overrides: Any) -> dict[str, Any]:
    """A minimal, valid penalty provision dict, with fields overridable for tests."""
    provision: dict[str, Any] = {
        "id": "test_penalty",
        "statute": "Test Statute Act, 2026",
        "provision_ref": "Section 1",
        "description": "A penalty provision used only in tests.",
        "penalty_amount_inr": 100_000.0,
        "penalty_formula": "flat ₹1,00,000",
        "currently_in_force": True,
        "in_force_from": None,
        "source": "test fixture, not a real citation",
        "confidence": "medium",
        "verified_by_human": False,
    }
    provision.update(overrides)
    return provision


def write_library_yaml(
    path: Path,
    framework: str = "test_framework",
    version: str = "1.0",
    effective_from: str | None = "2026-01-01",
    effective_to: str | None = None,
    supersedes: str | None = None,
    controls: list[dict[str, Any]] | None = None,
    penalty_provisions: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a minimal, valid control library YAML file to `path` and return it."""
    payload = {
        "framework": framework,
        "version": version,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "supersedes": supersedes,
        "sources": [
            {
                "url_or_citation": "test fixture",
                "retrieved": "2026-09-20",
                "covers": "everything in this test file",
            }
        ],
        "controls": controls if controls is not None else [minimal_control()],
        "penalty_provisions": penalty_provisions if penalty_provisions is not None else [],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path
