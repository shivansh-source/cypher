"""Tests for the export-file sources of greenbone_connector.py and wazuh_connector.py,
and for infra/inventory/build_wazuh_bundle.py.

Every input here is SYNTHETIC: hand-written in the real tools' formats, using the
reserved documentation range 192.0.2.0/24 and invented host names. None of it is
captured from a real environment.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from infra.connectors.greenbone_connector import GreenboneConnector, GreenboneConnectorError
from infra.connectors.wazuh_connector import WazuhConnector, WazuhConnectorError
from infra.inventory.build_wazuh_bundle import build_bundle, parse_agent_control_list
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURES = Path(__file__).parent / "fixtures"
_SCHEMA = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"

_AGENT_LIST = """Wazuh agent_control. List of available agents:
   ID: 000, Name: example-manager (server), IP: 127.0.0.1, Active/Local
   ID: 001, Name: example-web, IP: 192.0.2.10, Active
   ID: 002, Name: example-db, IP: 192.0.2.11, Disconnected
   ID: 003, Name: roaming, IP: any, Never connected

List of agentless devices:
"""

_ALERTS = "\n".join(
    json.dumps(a)
    for a in (
        {
            "timestamp": "2026-09-24T06:37:18.427+0000",
            "rule": {
                "level": 7,
                "description": "Dpkg (Debian Package) half configured.",
                "id": "2904",
            },
            "agent": {"id": "001", "name": "example-web", "ip": "192.0.2.10"},
        },
        {
            "timestamp": "2026-09-24T07:00:00.000+0000",
            "rule": {"level": 3, "id": "5501"},
            "agent": {"id": "000", "name": "example-manager"},
        },
    )
)


# --- Greenbone --------------------------------------------------------------


def test_greenbone_reads_report_export_including_log_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(_FIXTURES / "greenbone_report.xml"))

    fragments = GreenboneConnector().run()

    by_asset = {f["asset_id"]: f["findings"][0] for f in fragments}
    assert set(by_asset) == {"host:192.0.2.10", "host:192.0.2.20"}
    banner = by_asset["host:192.0.2.10"]
    assert banner["criticality"] == "informational" and banner["cve_id"] is None
    assert banner["provenance"]["raw_source_id"] == "1.3.6.1.4.1.25623.1.0.10107"
    assert by_asset["host:192.0.2.20"]["criticality"] == "high"

    snapshot = build_snapshot(
        merge_fragments(fragments), reachable_scanners=["greenbone_connector"]
    )
    jsonschema.validate(snapshot, json.loads(_SCHEMA.read_text(encoding="utf-8")))


def test_greenbone_export_errors_are_named(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(tmp_path / "missing.xml"))
    with pytest.raises(GreenboneConnectorError, match="could not read"):
        GreenboneConnector().fetch()

    not_xml = tmp_path / "bad.xml"
    not_xml.write_text("this is not xml")
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(not_xml))
    with pytest.raises(GreenboneConnectorError, match="parseable XML"):
        GreenboneConnector().fetch()

    empty = tmp_path / "empty.xml"
    empty.write_text("<report><report><results/></report></report>")
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(empty))
    with pytest.raises(GreenboneConnectorError, match="no <result>"):
        GreenboneConnector().fetch()


# --- Wazuh ------------------------------------------------------------------


def test_agent_list_parser_handles_server_any_and_status_forms() -> None:
    agents = {a["id"]: a for a in parse_agent_control_list(_AGENT_LIST)}

    assert agents["000"] == {"id": "000", "name": "example-manager", "ip": None, "status": "active"}
    assert agents["001"]["ip"] == "192.0.2.10" and agents["001"]["status"] == "active"
    assert agents["002"]["status"] == "disconnected"
    assert agents["003"]["ip"] is None and agents["003"]["status"] == "never connected"


def test_agent_list_parser_refuses_output_with_no_agents() -> None:
    with pytest.raises(ValueError, match="no 'ID:"):
        parse_agent_control_list("agent_control: Permission denied")


def test_wazuh_reads_bundle_and_reports_real_agent_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(build_bundle(_ALERTS, _AGENT_LIST)))
    monkeypatch.setenv("WAZUH_EXPORT_PATH", str(bundle))

    fragments = WazuhConnector().run()

    edr = {f["asset_id"]: f["edr"] for f in fragments}
    assert set(edr) == {
        "host:example-manager",  # manager: no usable IP, so identified by name
        "host:192.0.2.10",
        "host:192.0.2.11",
    }  # the never-connected "roaming" registration is not an installed agent
    assert edr["host:192.0.2.10"]["agent_healthy"] is True
    assert edr["host:192.0.2.11"]["agent_healthy"] is False  # disconnected, not inferred healthy
    assert [a["rule_id"] for a in edr["host:192.0.2.10"]["recent_alerts"]] == ["2904"]
    assert [a["rule_id"] for a in edr["host:example-manager"]["recent_alerts"]] == ["5501"]

    snapshot = build_snapshot(merge_fragments(fragments), reachable_scanners=["wazuh_connector"])
    jsonschema.validate(snapshot, json.loads(_SCHEMA.read_text(encoding="utf-8")))


def test_wazuh_bundle_errors_are_named(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WAZUH_EXPORT_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(WazuhConnectorError, match="could not read"):
        WazuhConnector().fetch()

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"alerts": []}))
    monkeypatch.setenv("WAZUH_EXPORT_PATH", str(bad))
    with pytest.raises(WazuhConnectorError, match="'agents' and 'alerts'"):
        WazuhConnector().fetch()


_CSV_HEADER = (
    "IP,Hostname,Port,Port Protocol,CVSS,Severity,QoD,Solution Type,NVT Name,Summary,"
    "Specific Result,NVT OID,CVEs,Task ID,Task Name,Timestamp,Result ID,Impact,Solution,"
    "Affected Software/OS,Vulnerability Insight,Vulnerability Detection Method,"
    "Product Detection Result,BIDs,CERTs,Other References"
)


def _csv_row(ip: str, cvss: str, severity: str, name: str, oid: str, cves: str, rid: str) -> str:
    # A multi-line quoted summary, as in real exports, to prove the reader copes.
    return (
        f'{ip},host.example,,,{cvss},{severity},80,"Mitigation","{name}","line one\n  line two",'
        f'"result",{oid},"{cves}",task-1,"example-scan",2026-01-01T00:00:00Z,{rid},"","","","","","","","",""'
    )


def test_greenbone_reads_csv_export_with_real_gsa_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SYNTHETIC rows under the header of a real GSA 'CSV Results' export."""
    export = tmp_path / "report.csv"
    export.write_text(
        "\n".join(
            [
                _CSV_HEADER,
                _csv_row("192.0.2.10", "7.5", "High", "Example high", "1.2.3.1", "", "r-1"),
                _csv_row("192.0.2.10", "0.0", "Log", "Example banner", "1.2.3.2", "", "r-2"),
                _csv_row(
                    "192.0.2.11",
                    "9.8",
                    "High",
                    "Example cve",
                    "1.2.3.3",
                    "CVE-2099-0001, CVE-2099-0002",
                    "r-3",
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(export))

    fragments = GreenboneConnector().run()

    findings = {
        f["findings"][0]["finding_id"]: (f["asset_id"], f["findings"][0]) for f in fragments
    }
    assert set(findings) == {"greenbone-r-1", "greenbone-r-2", "greenbone-r-3"}
    assert findings["greenbone-r-2"][1]["criticality"] == "informational"
    assert findings["greenbone-r-1"][1]["cve_id"] is None
    assert findings["greenbone-r-3"][1]["cve_id"] == "CVE-2099-0001"
    assert findings["greenbone-r-3"][0] == "host:192.0.2.11"
    assert findings["greenbone-r-1"][1]["first_seen_at"] == "2026-01-01T00:00:00Z"


def test_greenbone_csv_errors_are_named(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("a,b\n1,2\n")
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(wrong))
    with pytest.raises(GreenboneConnectorError, match="missing expected CSV column"):
        GreenboneConnector().fetch()

    header_only = tmp_path / "header_only.csv"
    header_only.write_text(_CSV_HEADER + "\n")
    monkeypatch.setenv("GREENBONE_EXPORT_PATH", str(header_only))
    with pytest.raises(GreenboneConnectorError, match="no result rows"):
        GreenboneConnector().fetch()


_AGENTS_WITH_ANY_IP = (
    "ID: 001, Name: example-web, IP: any, Active\nID: 002, Name: example-db, IP: any, Active\n"
)


def test_agent_ip_any_is_filled_from_the_ip_wazuh_reported_in_alerts() -> None:
    alerts = "\n".join(
        json.dumps({"agent": {"id": i, "name": n, "ip": ip}, "rule": {"id": "1"}})
        for i, n, ip in (
            ("001", "example-web", "192.0.2.10"),
            ("001", "example-web", "192.0.2.10"),
            ("002", "example-db", "192.0.2.11"),
            ("002", "example-db", "192.0.2.99"),  # conflicting reports for 002
        )
    )

    bundle = build_bundle(alerts, _AGENTS_WITH_ANY_IP)

    ips = {a["agent"]["id"]: a["agent"]["ip"] for a in bundle["agents"]}
    assert ips == {"001": "192.0.2.10", "002": None}  # conflicting reports are not guessed


def test_never_connected_agent_is_not_reported_as_edr_coverage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agents = (
        "ID: 001, Name: example-web, IP: 192.0.2.10, Active\n"
        "ID: 004, Name: probe.local, IP: any, Never connected\n"
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(build_bundle("", agents)))
    monkeypatch.setenv("WAZUH_EXPORT_PATH", str(bundle))

    assert [f["asset_id"] for f in WazuhConnector().run()] == ["host:192.0.2.10"]
