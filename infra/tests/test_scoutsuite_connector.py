"""Tests for infra/connectors/scoutsuite_connector.py.

Mocks ``infra.connectors._object_store.read_latest_text`` — no real S3 call
is made.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import jsonschema

from infra.connectors.scoutsuite_connector import ScoutSuiteConnector, ScoutSuiteConnectorError
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"


def _load_fixture_text() -> str:
    return (_FIXTURES_DIR / "scoutsuite_raw.js").read_text(encoding="utf-8")


@patch("infra.connectors.scoutsuite_connector._object_store.read_latest_text")
def test_fetch_unwraps_js_variable(mock_read_latest_text: object) -> None:
    mock_read_latest_text.return_value = _load_fixture_text()  # type: ignore[attr-defined]

    connector = ScoutSuiteConnector()
    raw = connector.fetch()

    assert raw["account_id"] == "123456789012"
    assert "s3" in raw["services"]


@patch("infra.connectors.scoutsuite_connector._object_store.read_latest_text")
def test_fetch_rejects_non_js_wrapped_text(mock_read_latest_text: object) -> None:
    mock_read_latest_text.return_value = "{}"  # type: ignore[attr-defined]

    connector = ScoutSuiteConnector()
    try:
        connector.fetch()
        raise AssertionError("expected ScoutSuiteConnectorError")
    except ScoutSuiteConnectorError as exc:
        assert "JS-wrapped" in str(exc)


@patch("infra.connectors.scoutsuite_connector._object_store.read_latest_text")
def test_run_skips_good_level_and_produces_schema_valid_snapshot(
    mock_read_latest_text: object,
) -> None:
    mock_read_latest_text.return_value = _load_fixture_text()  # type: ignore[attr-defined]

    connector = ScoutSuiteConnector()
    fragments = connector.run()

    # danger (1 item) + warning (2 items) = 3 fragments; the "good" finding is skipped.
    assert len(fragments) == 3
    # Every finding lands on the one account-level asset, not one asset per ScoutSuite path.
    assert {f["asset_id"] for f in fragments} == {"cloud:aws-account:123456789012"}
    assert all(not any(key.startswith("_") for key in f) for f in fragments)
    # ScoutSuite overlaps Prowler, so its findings are evidence only, not extra loss events.
    assert all(f["findings"][0]["counts_toward_loss"] is False for f in fragments)

    danger_fragment = next(f for f in fragments if f["findings"][0]["criticality"] == "high")
    assert danger_fragment["findings"][0]["finding_id"] == (
        "scoutsuite-s3-bucket-no-mfa-delete-s3.buckets.example-bucket"
    )
    assert danger_fragment["findings"][0]["type"] == "misconfiguration"
    assert danger_fragment["findings"][0]["provenance"]["connector"] == "scoutsuite_connector"

    assets = merge_fragments(fragments)
    snapshot = build_snapshot(assets, reachable_scanners=["scoutsuite_connector"])

    with open(_SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)
    jsonschema.validate(instance=snapshot, schema=schema)


@patch("infra.connectors.scoutsuite_connector._object_store.read_latest_text")
def test_fetch_accepts_wrapper_with_or_without_trailing_semicolon(
    mock_read_latest_text: object,
) -> None:
    body = '{"account_id": "1", "last_run": {"time": "2026-01-01 00:00:00+0000"}, "services": {}}'
    wrappers = ("scoutsuite_results =\n" + body + "\n", "scoutsuite_results = " + body + ";\n")
    for text in wrappers:
        mock_read_latest_text.return_value = text  # type: ignore[attr-defined]
        assert ScoutSuiteConnector().fetch()["account_id"] == "1"


def test_normalize_requires_an_account_id() -> None:
    raw = {"last_run": {"time": "2026-01-01 00:00:00+0000"}, "services": {}}
    try:
        ScoutSuiteConnector().normalize(raw)
        raise AssertionError("expected ScoutSuiteConnectorError")
    except ScoutSuiteConnectorError as exc:
        assert "account_id" in str(exc)
