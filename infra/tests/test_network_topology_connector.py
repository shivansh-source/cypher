"""Tests for infra/connectors/network_topology_connector.py.

The fixture (network_topology_raw.json) is hand-written in the export script's real output
shape, with synthetic ids/IPs (documentation range 10.99.0.0/16, not a captured environment).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from infra.connectors.network_topology_connector import (
    NetworkTopologyConnector,
    NetworkTopologyConnectorError,
)
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURE = Path(__file__).parent / "fixtures" / "network_topology_raw.json"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"


def test_fetch_reads_file_named_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETWORK_TOPOLOGY_EXPORT_PATH", str(_FIXTURE))
    raw = NetworkTopologyConnector().fetch()
    assert raw["vpc_id"] == "vpc-syn0000"


def test_fetch_raises_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NETWORK_TOPOLOGY_EXPORT_PATH", raising=False)
    with pytest.raises(NetworkTopologyConnectorError, match="NETWORK_TOPOLOGY_EXPORT_PATH"):
        NetworkTopologyConnector().fetch()


def test_run_emits_a_host_and_a_cloud_fragment_per_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NETWORK_TOPOLOGY_EXPORT_PATH", str(_FIXTURE))
    connector = NetworkTopologyConnector()

    fragments = connector.run()

    # 2 instances x 2 identity schemes each = 4 fragments.
    assert {f["asset_id"] for f in fragments} == {
        "host:10.99.1.20",
        "cloud:arn:aws:ec2:ap-south-1:999999999999:instance/i-syn0000",
        "host:10.99.1.21",
        "cloud:arn:aws:ec2:ap-south-1:999999999999:instance/i-syn0001",
    }
    assert all(not any(key.startswith("_") for key in f) for f in fragments)

    portal = next(f for f in fragments if f["asset_id"] == "host:10.99.1.20")
    assert portal["network"] == {"internet_facing": True, "segment_id": "subnet-syn0000"}
    db = next(f for f in fragments if f["asset_id"] == "host:10.99.1.21")
    assert db["network"]["internet_facing"] is False


def test_topology_attribute_is_set_after_run_and_snapshot_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NETWORK_TOPOLOGY_EXPORT_PATH", str(_FIXTURE))
    connector = NetworkTopologyConnector()
    assert connector.topology is None  # nothing yet before run()

    fragments = connector.run()

    assert connector.topology == {
        "segments": [{"segment_id": "subnet-syn0000", "name": "synthetic-public"}],
        "segment_reachability": [],
    }

    snapshot = build_snapshot(
        merge_fragments(fragments), reachable_scanners=["network_topology_connector"]
    )
    snapshot["network_topology"] = connector.topology
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=snapshot, schema=schema)


def test_missing_segments_or_instances_list_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = NetworkTopologyConnector()
    with pytest.raises(NetworkTopologyConnectorError, match="segments"):
        connector.normalize({"instances": []})
    with pytest.raises(NetworkTopologyConnectorError, match="instances"):
        connector.normalize({"segments": [], "segment_reachability": []})


def test_instance_missing_segment_id_or_internet_facing_raises() -> None:
    connector = NetworkTopologyConnector()
    bad = {
        "segments": [],
        "segment_reachability": [],
        "instances": [{"instance_id": "i-bad", "private_ip": "10.99.1.1"}],
    }
    with pytest.raises(NetworkTopologyConnectorError, match="i-bad"):
        connector.normalize(bad)


def test_instance_with_neither_private_ip_nor_arn_produces_no_fragment() -> None:
    connector = NetworkTopologyConnector()
    doc = {
        "segments": [],
        "segment_reachability": [],
        "instances": [
            {
                "instance_id": "i-unreachable",
                "segment_id": "subnet-x",
                "internet_facing": False,
                "private_ip": None,
                "instance_arn": None,
            }
        ],
    }
    assert connector.normalize(doc) == []
