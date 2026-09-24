"""Tests for infra/inventory/export_ec2_inventory.py and cmdb_connector.py's file source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from infra.connectors._identity_resolution import (
    cmdb_records_from_endpoints,
    find_candidate_merges,
)
from infra.connectors.cmdb_connector import CMDBConnector, CMDBConnectorError
from infra.inventory.export_ec2_inventory import records_from_describe_instances

_ACCOUNT = "123456789012"
_DB_ARN = f"arn:aws:ec2:ap-south-1:{_ACCOUNT}:instance/i-0db"
_DB_VOL_ARN = f"arn:aws:ec2:ap-south-1:{_ACCOUNT}:volume/vol-0db"

_RESPONSE: dict[str, Any] = {
    "Reservations": [
        {
            "OwnerId": _ACCOUNT,
            "Instances": [
                {
                    "InstanceId": "i-0db",
                    "PrivateIpAddress": "10.0.1.5",
                    "PublicIpAddress": "203.0.113.9",
                    "State": {"Name": "running"},
                    "Tags": [{"Key": "Name", "Value": "loanease-db"}],
                    "BlockDeviceMappings": [{"Ebs": {"VolumeId": "vol-0db"}}],
                },
                {
                    "InstanceId": "i-0gone",
                    "State": {"Name": "terminated"},
                    "PrivateIpAddress": "10.0.1.6",
                },
                {"InstanceId": "i-0noname", "State": {"Name": "stopped"}},
            ],
        }
    ]
}


def test_records_carry_name_private_ip_and_arns_but_not_public_ip() -> None:
    records = records_from_describe_instances(_RESPONSE, "ap-south-1")

    assert [r["id"] for r in records] == ["loanease-db", "i-0noname"]
    db = records[0]
    assert db["hostnames"] == ["loanease-db"]
    assert db["ip_addresses"] == ["10.0.1.5"]
    assert db["cloud_instance_ids"] == ["i-0db", _DB_ARN, _DB_VOL_ARN]
    assert "203.0.113.9" not in json.dumps(records)
    assert records[1]["hostnames"] == [] and records[1]["ip_addresses"] == []


def test_export_feeds_cmdb_connector_and_matches_prowler_style_placeholder_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export = tmp_path / "inventory.json"
    export.write_text(json.dumps(records_from_describe_instances(_RESPONSE, "ap-south-1")))
    monkeypatch.setenv("CMDB_EXPORT_PATH", str(export))

    fragments = CMDBConnector().run()
    assert {f["resolved_asset_id"] for f in fragments} == {"cmdb:loanease-db", "cmdb:i-0noname"}

    endpoints = [
        {k: f[k] for k in ("endpoint_id", "address_type", "address", "resolved_asset_id")}
        for f in fragments
    ]
    candidates = find_candidate_merges(
        {f"cloud:{_DB_ARN}": "prowler_connector", f"cloud:{_DB_VOL_ARN}": "prowler_connector"},
        cmdb_records_from_endpoints(endpoints),
    )
    assert {c.placeholder_asset_id for c in candidates} == {
        f"cloud:{_DB_ARN}",
        f"cloud:{_DB_VOL_ARN}",
    }
    assert {c.canonical_asset_id for c in candidates} == {"cmdb:loanease-db"}
    assert all(item.same_kind for c in candidates for item in c.evidence)


def test_cmdb_export_path_errors_are_named(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CMDB_EXPORT_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(CMDBConnectorError, match="could not read"):
        CMDBConnector().fetch()

    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a list"}')
    monkeypatch.setenv("CMDB_EXPORT_PATH", str(bad))
    with pytest.raises(CMDBConnectorError, match="JSON list"):
        CMDBConnector().fetch()
