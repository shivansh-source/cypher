"""Tests for infra/connectors/greenbone_connector.py.

Mocks ``gvm.connections.TLSConnection`` and ``gvm.protocols.gmp.Gmp`` (as
imported into ``infra.connectors.greenbone_connector``) and
``infra.connectors._object_store.write_raw`` — no real GVM/network/S3 call
is made. The mocked ``Gmp.get_results()`` returns a real ``lxml`` element
tree parsed from a fixture XML file, so ``_results_to_dicts`` (real XML
element traversal) is exercised for real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import jsonschema
import pytest
from lxml import etree

from infra.connectors.greenbone_connector import GreenboneConnector
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"

_ENV = {
    "GREENBONE_HOST": "gvm.example.com",
    "GREENBONE_USERNAME": "gvm-user",
    "GREENBONE_PASSWORD": "gvm-pass",
}


def _load_fixture_root() -> Any:
    xml_bytes = (_FIXTURES_DIR / "greenbone_results.xml").read_bytes()
    return etree.fromstring(xml_bytes)


def _patched_connector(monkeypatch: pytest.MonkeyPatch) -> GreenboneConnector:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    return GreenboneConnector()


def _mock_gmp_context(results_root: Any) -> MagicMock:
    """Build the mock object ``Gmp(connection, transform=...)`` should return."""
    gmp_instance = MagicMock()
    gmp_instance.get_results.return_value = results_root
    gmp_context = MagicMock()
    gmp_context.__enter__.return_value = gmp_instance
    gmp_context.__exit__.return_value = False
    return gmp_context


@patch("infra.connectors.greenbone_connector._object_store.write_raw")
@patch("infra.connectors.greenbone_connector.Gmp")
@patch("infra.connectors.greenbone_connector.TLSConnection")
def test_fetch_parses_xml_results(
    mock_tls_connection: MagicMock,
    mock_gmp: MagicMock,
    mock_write_raw: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results_root = _load_fixture_root()
    mock_gmp.return_value = _mock_gmp_context(results_root)

    connector = _patched_connector(monkeypatch)
    raw = connector.fetch()

    assert len(raw) == 2
    assert raw[0]["host"] == "10.0.0.9"
    assert raw[0]["threat"] == "High"
    assert raw[0]["cve"] == "CVE-2026-12345"
    mock_write_raw.assert_called_once()
    assert mock_write_raw.call_args.args[0] == "greenbone_connector"
    mock_tls_connection.assert_called_once()


@patch("infra.connectors.greenbone_connector._object_store.write_raw")
@patch("infra.connectors.greenbone_connector.Gmp")
@patch("infra.connectors.greenbone_connector.TLSConnection")
def test_run_produces_schema_valid_snapshot(
    mock_tls_connection: MagicMock,
    mock_gmp: MagicMock,
    mock_write_raw: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results_root = _load_fixture_root()
    mock_gmp.return_value = _mock_gmp_context(results_root)

    connector = _patched_connector(monkeypatch)
    fragments = connector.run()

    assert {f["asset_id"] for f in fragments} == {"host:10.0.0.9", "host:10.0.0.10"}
    assert all(not any(key.startswith("_") for key in f) for f in fragments)

    high_fragment = next(f for f in fragments if f["asset_id"] == "host:10.0.0.9")
    finding = high_fragment["findings"][0]
    assert finding["type"] == "cve"
    assert finding["cve_id"] == "CVE-2026-12345"
    assert finding["criticality"] == "high"
    assert finding["provenance"]["connector"] == "greenbone_connector"

    log_fragment = next(f for f in fragments if f["asset_id"] == "host:10.0.0.10")
    log_finding = log_fragment["findings"][0]
    assert log_finding["criticality"] == "informational"
    assert log_finding["cve_id"] is None  # GVM's "NOCVE" sentinel normalizes to None

    assets = merge_fragments(fragments)
    snapshot = build_snapshot(assets, reachable_scanners=["greenbone_connector"])

    with open(_SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)
    jsonschema.validate(instance=snapshot, schema=schema)
