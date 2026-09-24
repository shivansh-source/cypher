"""Tests for infra/connectors/prowler_connector.py.

Mocks ``infra.connectors._object_store.read_latest`` — no real S3 call is
made.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import jsonschema

from infra.connectors.prowler_connector import ProwlerConnector, ProwlerConnectorError
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"


def _load_fixture() -> list[dict[str, Any]]:
    with open(_FIXTURES_DIR / "prowler_raw.json", encoding="utf-8") as handle:
        result: list[dict[str, Any]] = json.load(handle)
        return result


@patch("infra.connectors.prowler_connector._object_store.read_latest")
def test_fetch_returns_object_store_payload(mock_read_latest: Any) -> None:
    fixture = _load_fixture()
    mock_read_latest.return_value = fixture

    connector = ProwlerConnector()
    raw = connector.fetch()

    assert raw == fixture
    mock_read_latest.assert_called_once()
    assert mock_read_latest.call_args.args[0] == "prowler_connector"


@patch("infra.connectors.prowler_connector._object_store.read_latest")
def test_fetch_wraps_object_store_error(mock_read_latest: Any) -> None:
    from infra.connectors._object_store import ObjectStoreError

    mock_read_latest.side_effect = ObjectStoreError("boom")

    connector = ProwlerConnector()
    try:
        connector.fetch()
        raise AssertionError("expected ProwlerConnectorError")
    except ProwlerConnectorError as exc:
        assert "boom" in str(exc)


@patch("infra.connectors.prowler_connector._object_store.read_latest")
def test_run_skips_pass_and_produces_schema_valid_snapshot(mock_read_latest: Any) -> None:
    fixture = _load_fixture()
    mock_read_latest.return_value = fixture

    connector = ProwlerConnector()
    fragments = connector.run()

    # Only the two FAIL checks should produce findings; the PASS check must not.
    assert len(fragments) == 2
    assert all(f["asset_id"].startswith("cloud:") for f in fragments)
    assert all(not any(key.startswith("_") for key in f) for f in fragments)

    role_fragment = next(
        f
        for f in fragments
        if f["asset_id"] == "cloud:arn:aws:iam::123456789012:role/example-admin-role"
    )
    finding = role_fragment["findings"][0]
    assert finding["criticality"] == "high"
    assert finding["type"] == "misconfiguration"
    assert finding["provenance"] == {
        "connector": "prowler_connector",
        "raw_source_id": "iam_role_administratoraccess_policy",
    }
    assert finding["first_seen_at"] == "2026-09-24T14:07:22Z"

    assets = merge_fragments(fragments)
    snapshot = build_snapshot(assets, reachable_scanners=["prowler_connector"])

    with open(_SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)
    jsonschema.validate(instance=snapshot, schema=schema)


def test_missing_compliance_status_or_bad_generator_id_raises() -> None:
    import copy

    fixture = _load_fixture()
    broken = copy.deepcopy(fixture)
    del broken[0]["Compliance"]
    try:
        ProwlerConnector().normalize(broken)
        raise AssertionError("expected ProwlerConnectorError")
    except ProwlerConnectorError as exc:
        assert "Compliance.Status" in str(exc)

    broken = copy.deepcopy(fixture)
    broken[0]["GeneratorId"] = "not-prowler"
    try:
        ProwlerConnector().normalize(broken)
        raise AssertionError("expected ProwlerConnectorError")
    except ProwlerConnectorError as exc:
        assert "GeneratorId" in str(exc)
