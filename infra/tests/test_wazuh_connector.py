"""Tests for infra/connectors/wazuh_connector.py.

Mocks ``requests.get``/``requests.post`` and
``infra.connectors._object_store.write_raw`` — no real network or S3 call
is made.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import jsonschema
import pytest

from infra.connectors.wazuh_connector import WazuhConnector
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"

_ENV = {
    "WAZUH_API_URL": "https://wazuh.example.com",
    "WAZUH_API_USERNAME": "wazuh-user",
    "WAZUH_API_PASSWORD": "wazuh-pass",
    "WAZUH_INDEXER_URL": "https://indexer.example.com",
    "WAZUH_INDEXER_USERNAME": "indexer-user",
    "WAZUH_INDEXER_PASSWORD": "indexer-pass",
}


def _load_fixture() -> dict[str, Any]:
    with open(_FIXTURES_DIR / "wazuh_raw.json", encoding="utf-8") as handle:
        result: dict[str, Any] = json.load(handle)
        return result


def _mock_response(body: Any, ok: bool = True, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.ok = ok
    response.status_code = status_code
    response.json.return_value = body
    return response


def _patched_connector(monkeypatch: pytest.MonkeyPatch) -> WazuhConnector:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    return WazuhConnector()


@patch("infra.connectors.wazuh_connector._object_store.write_raw")
@patch("infra.connectors.wazuh_connector.requests.post")
@patch("infra.connectors.wazuh_connector.requests.get")
def test_fetch_combines_agents_and_alerts(
    mock_get: MagicMock,
    mock_post: MagicMock,
    mock_write_raw: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _load_fixture()

    def post_side_effect(url: str, **kwargs: Any) -> MagicMock:
        if url.endswith("/security/user/authenticate"):
            return _mock_response(fixture["auth_response"])
        if url.endswith("/_search"):
            return _mock_response(fixture["alerts_response"])
        raise AssertionError(f"unexpected POST {url}")

    def get_side_effect(url: str, **kwargs: Any) -> MagicMock:
        if url.endswith("/agents"):
            return _mock_response(fixture["agents_response"])
        if url.endswith("/packages"):
            return _mock_response(fixture["packages_response"])
        if url.endswith("/ports"):
            return _mock_response(fixture["ports_response"])
        raise AssertionError(f"unexpected GET {url}")

    mock_post.side_effect = post_side_effect
    mock_get.side_effect = get_side_effect

    connector = _patched_connector(monkeypatch)
    raw = connector.fetch()

    assert len(raw["agents"]) == 2
    assert raw["alerts"] == fixture["alerts_response"]["hits"]["hits"]
    mock_write_raw.assert_called_once()
    assert mock_write_raw.call_args.args[0] == "wazuh_connector"


@patch("infra.connectors.wazuh_connector._object_store.write_raw")
@patch("infra.connectors.wazuh_connector.requests.post")
@patch("infra.connectors.wazuh_connector.requests.get")
def test_run_produces_schema_valid_snapshot(
    mock_get: MagicMock,
    mock_post: MagicMock,
    mock_write_raw: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _load_fixture()

    def post_side_effect(url: str, **kwargs: Any) -> MagicMock:
        if url.endswith("/security/user/authenticate"):
            return _mock_response(fixture["auth_response"])
        if url.endswith("/_search"):
            return _mock_response(fixture["alerts_response"])
        raise AssertionError(f"unexpected POST {url}")

    def get_side_effect(url: str, **kwargs: Any) -> MagicMock:
        if url.endswith("/agents"):
            return _mock_response(fixture["agents_response"])
        if url.endswith("/packages"):
            return _mock_response(fixture["packages_response"])
        if url.endswith("/ports"):
            return _mock_response(fixture["ports_response"])
        raise AssertionError(f"unexpected GET {url}")

    mock_post.side_effect = post_side_effect
    mock_get.side_effect = get_side_effect

    connector = _patched_connector(monkeypatch)
    fragments = connector.run()

    assert {fragment["asset_id"] for fragment in fragments} == {"host:10.0.0.5", "host:10.0.0.6"}
    for fragment in fragments:
        assert not any(key.startswith("_") for key in fragment)

    active_fragment = next(f for f in fragments if f["asset_id"] == "host:10.0.0.5")
    assert active_fragment["edr"]["agent_installed"] is True
    assert active_fragment["edr"]["agent_healthy"] is True
    assert len(active_fragment["edr"]["recent_alerts"]) == 1

    inactive_fragment = next(f for f in fragments if f["asset_id"] == "host:10.0.0.6")
    assert inactive_fragment["edr"]["agent_healthy"] is False
    assert inactive_fragment["edr"]["recent_alerts"] == []

    assets = merge_fragments(fragments)
    snapshot = build_snapshot(assets, reachable_scanners=["wazuh_connector"])

    with open(_SCHEMA_PATH, encoding="utf-8") as handle:
        schema = json.load(handle)
    jsonschema.validate(instance=snapshot, schema=schema)
