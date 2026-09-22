"""Tests for infra/connectors/cmdb_connector.py.

Mocks ``requests.get`` — no real network call is made, matching
infra/tests/test_wazuh_connector.py's style.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import jsonschema
import pytest

from infra.connectors.cmdb_connector import CMDBConnector, CMDBConnectorError
from infra.tests._snapshot_helpers import build_snapshot

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"
_ENV = {"CMDB_BASE_URL": "https://cmdb.example.com/api", "CMDB_API_TOKEN": "cmdb-token"}

_RAW_RECORDS: list[dict[str, Any]] = [
    {
        "id": "AST-04821",
        "hostnames": ["web-01", "web-01.corp.local"],
        "ip_addresses": ["10.0.0.5"],
        "cloud_instance_ids": [],
    },
    {"id": "AST-09911", "hostnames": [], "ip_addresses": [], "cloud_instance_ids": ["i-0abc123"]},
    {"id": "AST-00001"},  # no identifiers on file at all
]


def _mock_response(body: Any, ok: bool = True, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.ok = ok
    response.status_code = status_code
    response.json.return_value = body
    response.text = "" if ok else str(body)
    return response


def _patched_connector(monkeypatch: pytest.MonkeyPatch) -> CMDBConnector:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    return CMDBConnector()


def test_fetch_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CMDB_BASE_URL", raising=False)
    monkeypatch.setenv("CMDB_API_TOKEN", "token")
    with pytest.raises(CMDBConnectorError, match="CMDB_BASE_URL"):
        CMDBConnector().fetch()


@patch("infra.connectors.cmdb_connector.requests.get")
def test_fetch_returns_parsed_json_list(
    mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = _patched_connector(monkeypatch)
    mock_get.return_value = _mock_response(_RAW_RECORDS)

    result = connector.fetch()

    assert result == _RAW_RECORDS
    called_url = mock_get.call_args.args[0]
    assert called_url == "https://cmdb.example.com/api/assets"
    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer cmdb-token"


@patch("infra.connectors.cmdb_connector.requests.get")
def test_fetch_non_ok_response_raises(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    connector = _patched_connector(monkeypatch)
    mock_get.return_value = _mock_response({"error": "unauthorized"}, ok=False, status_code=401)
    with pytest.raises(CMDBConnectorError, match="HTTP 401"):
        connector.fetch()


@patch("infra.connectors.cmdb_connector.requests.get")
def test_fetch_non_list_body_raises(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    connector = _patched_connector(monkeypatch)
    mock_get.return_value = _mock_response({"not": "a list"})
    with pytest.raises(CMDBConnectorError, match="expected a JSON list"):
        connector.fetch()


def test_normalize_produces_one_endpoint_fragment_per_known_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector = _patched_connector(monkeypatch)
    fragments = connector.normalize(_RAW_RECORDS)

    # AST-04821: 2 hostnames + 1 ip = 3 fragments. AST-09911: 1 cloud id.
    # AST-00001: no identifiers -> no fragments.
    assert len(fragments) == 4
    by_address = {f["address"]: f for f in fragments}
    assert by_address["web-01"]["resolved_asset_id"] == "cmdb:AST-04821"
    assert by_address["web-01"]["address_type"] == "hostname"
    assert by_address["10.0.0.5"]["address_type"] == "ipv4"
    assert by_address["i-0abc123"]["address_type"] == "cloud_instance_id"
    assert by_address["i-0abc123"]["resolved_asset_id"] == "cmdb:AST-09911"


def test_normalize_rejects_record_missing_id(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = _patched_connector(monkeypatch)
    with pytest.raises(CMDBConnectorError, match="missing its id"):
        connector.normalize([{"hostnames": ["x"]}])


def test_resolve_asset_id_returns_precomputed_canonical_id(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = _patched_connector(monkeypatch)
    fragment = {
        "endpoint_id": "cmdb-AST-04821-host-0",
        "address_type": "hostname",
        "address": "web-01",
        "resolved_asset_id": "cmdb:AST-04821",
    }
    assert connector.resolve_asset_id(fragment) == "cmdb:AST-04821"


def test_run_end_to_end_produces_schema_legal_endpoint_fragments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connector.run()'s output, reshaped into endpoints[], must validate against the schema."""
    connector = _patched_connector(monkeypatch)
    with patch(
        "infra.connectors.cmdb_connector.requests.get", return_value=_mock_response(_RAW_RECORDS)
    ):
        fragments = connector.run()

    endpoints = [
        {
            "endpoint_id": f["endpoint_id"],
            "address_type": f["address_type"],
            "address": f["address"],
            "resolved_asset_id": f["resolved_asset_id"],
        }
        for f in fragments
    ]
    snapshot = build_snapshot(assets=[], reachable_scanners=["cmdb_connector"])
    snapshot["endpoints"] = endpoints
    schema = json.loads(_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(snapshot)
