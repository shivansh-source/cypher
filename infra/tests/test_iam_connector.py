"""Tests for infra/connectors/iam_connector.py.

Reads a synthetic fixture shaped after real PMapper output's top-level keys
(``account``, ``date_and_time``, ``findings``) — the finding text is invented,
not captured PMapper output. Sets ``IAM_PMAPPER_OUTPUT_PATH`` via monkeypatch;
no network or AWS access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from infra.connectors.iam_connector import IAMConnector, IAMConnectorError
from infra.tests._snapshot_helpers import build_snapshot, merge_fragments

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pmapper_raw.json"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "aggregated_assets.schema.json"
_MFA_SLUG = "iam-users-with-administrative-permissions-but-no-mfa-device"


def _fixture() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return result


def test_fetch_reads_file_named_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IAM_PMAPPER_OUTPUT_PATH", str(_FIXTURE_PATH))
    assert IAMConnector().fetch() == _fixture()


def test_fetch_raises_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IAM_PMAPPER_OUTPUT_PATH", raising=False)
    with pytest.raises(IAMConnectorError, match="IAM_PMAPPER_OUTPUT_PATH"):
        IAMConnector().fetch()


def test_fetch_raises_on_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("IAM_PMAPPER_OUTPUT_PATH", str(tmp_path / "nope.json"))
    with pytest.raises(IAMConnectorError, match="could not read"):
        IAMConnector().fetch()


def test_run_attaches_findings_to_account_asset_and_is_schema_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IAM_PMAPPER_OUTPUT_PATH", str(_FIXTURE_PATH))
    fragments = IAMConnector().run()

    assert len(fragments) == 2
    assert {f["asset_id"] for f in fragments} == {"cloud:aws-account:111122223333"}
    assert all(not any(key.startswith("_") for key in f) for f in fragments)

    finding = fragments[0]["findings"][0]
    assert finding["finding_id"] == f"pmapper-{_MFA_SLUG}"
    assert finding["provenance"] == {"connector": "iam_connector", "raw_source_id": _MFA_SLUG}
    assert finding["criticality"] == "medium"
    assert finding["first_seen_at"] == "2026-09-24T12:00:00+00:00"
    assert fragments[1]["findings"][0]["criticality"] == "high"

    assets = merge_fragments(fragments)
    assert len(assets) == 1
    snapshot = build_snapshot(assets, reachable_scanners=["iam_connector"])
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=snapshot, schema=schema)


def test_naive_timestamp_is_treated_as_utc() -> None:
    raw = _fixture()
    raw["date_and_time"] = "2026-09-24 12:00:00.123456"
    fragments = IAMConnector().normalize(raw)
    assert fragments[0]["findings"][0]["first_seen_at"] == "2026-09-24T12:00:00.123456+00:00"


def test_missing_severity_is_unknown_not_null() -> None:
    raw = _fixture()
    del raw["findings"][0]["severity"]
    assert IAMConnector().normalize(raw)[0]["findings"][0]["criticality"] == "unknown"


@pytest.mark.parametrize("missing_key", ["account", "date_and_time", "findings"])
def test_missing_top_level_key_raises_naming_it(missing_key: str) -> None:
    raw = _fixture()
    del raw[missing_key]
    with pytest.raises(IAMConnectorError, match=missing_key):
        IAMConnector().normalize(raw)


def test_old_space_separated_key_is_rejected_not_guessed() -> None:
    raw = _fixture()
    raw["date and time"] = raw.pop("date_and_time")
    with pytest.raises(IAMConnectorError, match="date_and_time"):
        IAMConnector().normalize(raw)


def test_missing_title_raises_instead_of_inventing_id() -> None:
    raw = _fixture()
    del raw["findings"][0]["title"]
    with pytest.raises(IAMConnectorError, match="title"):
        IAMConnector().normalize(raw)


def test_unrecognized_severity_and_duplicate_title_raise() -> None:
    raw = _fixture()
    raw["findings"][0]["severity"] = "Catastrophic"
    with pytest.raises(IAMConnectorError, match="severity"):
        IAMConnector().normalize(raw)

    raw = _fixture()
    raw["findings"][1]["title"] = raw["findings"][0]["title"]
    with pytest.raises(IAMConnectorError, match="collide"):
        IAMConnector().normalize(raw)


def test_empty_findings_list_yields_no_fragments() -> None:
    raw = _fixture()
    raw["findings"] = []
    assert IAMConnector().normalize(raw) == []
