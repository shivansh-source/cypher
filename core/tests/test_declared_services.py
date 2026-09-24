"""Tests for core/declared_services.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from core.declared_services import (
    DeclaredServicesError,
    apply_declared_services,
    load_declared_services,
)
from core.snapshot import validate_snapshot

_SANDBOX_FILE = Path(__file__).parent.parent / "declared" / "loanease_sandbox_services.json"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"


_ARN = "cloud:arn:aws:ec2:ap-south-1:627984120842:"
_DB_INSTANCE = _ARN + "instance/i-06d59432543fb1af9"
_DB_VOLUME = _ARN + "volume/vol-050e7c1b5d5fd25b1"


def _asset(asset_id: str) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "findings": [],
        "threat_intel": {},
        "edr": {"agent_installed": False, "agent_healthy": None},
        "identity_access": {},
        "network": {},
    }


def test_sandbox_file_loads_and_matches_schema_service_shape() -> None:
    declared = load_declared_services(_SANDBOX_FILE)
    assert {s["service_id"] for s in declared.services} == {
        "svc-loan-portal",
        "svc-loan-db",
        "svc-endpoint-sim",
        "svc-scanner-ops",
    }
    db = next(s for s in declared.services if s["service_id"] == "svc-loan-db")
    endpoint = next(s for s in declared.services if s["service_id"] == "svc-endpoint-sim")
    assert db["backup"]["exists"] is True
    assert endpoint["backup"]["exists"] is False  # V-06


def test_apply_links_observed_assets_and_reports_unmatched() -> None:
    declared = load_declared_services(_SANDBOX_FILE)
    assets = [_asset(_DB_INSTANCE)]
    services, unmatched = apply_declared_services(declared, assets)

    assert assets[0]["service_ids"] == ["svc-loan-db"]
    assert _DB_VOLUME in unmatched and _DB_INSTANCE not in unmatched
    assert len(services) == 4
    assert [a["asset_id"] for a in assets] == [_DB_INSTANCE]  # nothing created


def test_snapshot_with_declared_services_is_schema_valid_and_passes_gates() -> None:
    declared = load_declared_services(_SANDBOX_FILE)
    assets = [_asset(_DB_INSTANCE)]
    services, _ = apply_declared_services(declared, assets)
    snapshot: dict[str, Any] = {
        "snapshot_id": "sha256:test",
        "observed_at": "2026-09-24T00:00:00Z",
        "valid_from": "2026-09-24T00:00:00Z",
        "valid_to": None,
        "scan_scope": {"reachable_scanners": [], "unreachable_scanners": [], "coverage": []},
        "services": services,
        "assets": assets,
        "endpoints": [],
    }
    jsonschema.validate(snapshot, json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))
    assert all(result.passed for result in validate_snapshot(snapshot, None))


def _write(tmp_path: Path, mutate: Any) -> Path:
    document = json.loads(_SANDBOX_FILE.read_text(encoding="utf-8"))
    mutate(document)
    path = tmp_path / "declared.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize("key", ["declared_by", "declared_at", "basis"])
def test_missing_provenance_key_is_rejected(tmp_path: Path, key: str) -> None:
    path = _write(tmp_path, lambda d: d.pop(key))
    with pytest.raises(DeclaredServicesError, match=key):
        load_declared_services(path)


def test_incomplete_service_is_rejected_not_defaulted(tmp_path: Path) -> None:
    path = _write(tmp_path, lambda d: d["services"][0].pop("backup"))
    with pytest.raises(DeclaredServicesError, match="backup"):
        load_declared_services(path)


def test_link_to_undeclared_service_and_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, lambda d: d["asset_links"].update({"svc-ghost": ["host:1"]}))
    with pytest.raises(DeclaredServicesError, match="undeclared"):
        load_declared_services(path)

    path = _write(tmp_path, lambda d: d["services"].append(dict(d["services"][0])))
    with pytest.raises(DeclaredServicesError, match="duplicate"):
        load_declared_services(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DeclaredServicesError, match="could not read"):
        load_declared_services(tmp_path / "nope.json")
