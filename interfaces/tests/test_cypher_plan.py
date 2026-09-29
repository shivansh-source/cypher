"""Tests for ``cypher plan`` (interfaces/cli/cypher.py) against recorded Terraform plans.

Uses the recorded plans and the SYNTHETIC baseline snapshot under
``infra/tests/fixtures/`` (see ``infra/tests/test_terraform_plan.py`` for how
they were produced). The baseline is placed in a temporary snapshot store,
exactly where ``cypher ingest`` would have committed it.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from typer.testing import CliRunner

from core.snapshot import validate_snapshot
from infra.connectors.terraform_plan import load_plan_file, parse_plan
from interfaces import _snapshot_mirror
from interfaces.cli import cypher
from interfaces.cli.cypher import _build_proposed_snapshot, build_cli

_FIXTURES = Path(__file__).parents[2] / "infra" / "tests" / "fixtures"
_SCHEMA = json.loads(
    (Path(__file__).parents[2] / "schema" / "aggregated_assets.schema.json").read_text()
)


@pytest.fixture(autouse=True)
def no_real_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty (not unset), so a developer's .env cannot switch S3 on: load_dotenv never overrides."""
    monkeypatch.setenv("SNAPSHOT_S3_BUCKET", "")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    store = tmp_path / "snapshots"
    store.mkdir()
    shutil.copy(_FIXTURES / "tf_plan_baseline.json", store / "current.json")
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(store))
    return store


class _FakeS3:
    """Just enough of an S3 client for sync_once: one listing, file downloads."""

    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = objects
        self.calls = 0

    def get_paginator(self, name: str) -> Any:
        self.calls += 1
        keys = list(self.objects)

        class _Paginator:
            def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
                return [{"Contents": [{"Key": k} for k in keys if k.startswith(Prefix)]}]

        return _Paginator()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_text(self.objects[key])


class _BrokenS3:
    calls = 0

    def get_paginator(self, name: str) -> Any:
        self.calls += 1
        raise RuntimeError("Unable to locate credentials")


def _use_s3(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    monkeypatch.setenv("SNAPSHOT_S3_BUCKET", "published-bucket")
    monkeypatch.setattr(
        cypher,
        "sync_once",
        lambda bucket, prefix, dest: _snapshot_mirror.sync_once(
            bucket, prefix, dest, client=client
        ),
    )


def _run(*args: str) -> Any:
    return CliRunner().invoke(build_cli(), ["plan", *args])


def _report(*args: str) -> tuple[int, dict[str, Any]]:
    result = _run(*args, "--json")
    return result.exit_code, json.loads(result.stdout)


def test_opening_the_db_raises_expected_annual_loss_and_trips_the_threshold(store: Path) -> None:
    code, report = _report(str(_FIXTURES / "tf_plan_open_db.json"), "--fail-on-eal-increase", "0")

    assert code == 2
    assert report["change"]["expected_annual_loss_inr"] > 0
    assert report["change"]["covers_every_change"] is True
    assert report["threshold"] == {"fail_on_eal_increase_inr": 0.0, "exceeded": True}
    assert (
        report["baseline"]["expected_annual_loss_inr"]
        < report["proposed"]["expected_annual_loss_inr"]
    )
    changed = report["scenario_changes"]
    assert changed and all(c["asset_id"] == "cmdb:loanease-db" for c in changed)
    assert all(
        c["caused_by"] == ["module.network.aws_security_group.db_sg"] and not c["indirect"]
        for c in changed
    )
    # Expected Annual Loss is a mean, so the per-scenario changes add up to the headline.
    assert sum(c["change_inr"] for c in changed) == pytest.approx(
        report["change"]["expected_annual_loss_inr"]
    )


def test_threshold_above_the_increase_passes(store: Path) -> None:
    result = _run(str(_FIXTURES / "tf_plan_open_db.json"), "--fail-on-eal-increase", "1e12")

    assert result.exit_code == 0
    assert "Within --fail-on-eal-increase" in result.stdout


def test_risk_reducing_plan_lowers_expected_annual_loss(store: Path) -> None:
    code, report = _report(
        str(_FIXTURES / "tf_plan_reduce_risk.json"), "--fail-on-eal-increase", "0"
    )

    assert code == 0
    assert report["change"]["expected_annual_loss_inr"] < 0
    assert report["threshold"]["exceeded"] is False


def test_new_unscanned_instance_is_reported_unknown_not_zero(store: Path) -> None:
    code, report = _report(str(_FIXTURES / "tf_plan_new_instance.json"))

    assert code == 0
    assert report["change"]["covers_every_change"] is False
    assert [u["address"] for u in report["unmodelled"]] == ["module.compute.aws_instance.reporting"]

    text = _run(str(_FIXTURES / "tf_plan_new_instance.json")).stdout
    assert "unknown" in text
    assert "±₹0" not in text and "+₹0 " not in text


def test_report_names_the_baseline_snapshot_and_its_age(store: Path) -> None:
    baseline = json.loads((store / "current.json").read_text())

    text = _run(str(_FIXTURES / "tf_plan_drop_dlm.json")).stdout

    assert baseline["snapshot_id"] in text
    assert baseline["observed_at"] in text
    assert "ago" in text
    assert "svc-loan-db backup.exists: true → false" in text


def test_no_committed_snapshot_exits_without_a_figure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path / "empty"))

    result = _run(str(_FIXTURES / "tf_plan_open_db.json"))

    assert result.exit_code == 1
    assert "₹" not in result.stdout
    assert "cypher ingest" in result.stderr


@pytest.mark.parametrize("args", [[], ["plan.json", "--dir", "."]])
def test_needs_exactly_one_plan_source(store: Path, args: list[str]) -> None:
    assert _run(*args).exit_code == 1


def test_unreadable_plan_exits_1(store: Path, tmp_path: Path) -> None:
    binary = tmp_path / "tf.plan"
    binary.write_bytes(b"PK\x03\x04")

    result = _run(str(binary))

    assert result.exit_code == 1
    assert "not JSON" in result.stderr


@pytest.mark.parametrize(
    "name", ["open_db", "attach_admin", "drop_dlm", "reduce_risk", "new_instance"]
)
def test_proposed_snapshot_is_schema_valid_gate_passing_and_leaves_baseline_alone(
    name: str,
) -> None:
    baseline = json.loads((_FIXTURES / "tf_plan_baseline.json").read_text())
    untouched = copy.deepcopy(baseline)

    proposed = _build_proposed_snapshot(
        baseline, parse_plan(load_plan_file(_FIXTURES / f"tf_plan_{name}.json"), baseline)
    )

    assert baseline == untouched
    jsonschema.validate(proposed, _SCHEMA)
    assert all(gate.passed for gate in validate_snapshot(proposed, baseline))
    assert proposed["snapshot_id"].startswith("hypothetical:")


def test_remediated_finding_replaces_the_open_one_instead_of_sitting_beside_it() -> None:
    baseline = json.loads((_FIXTURES / "tf_plan_baseline.json").read_text())
    translation = parse_plan(load_plan_file(_FIXTURES / "tf_plan_reduce_risk.json"), baseline)

    proposed = _build_proposed_snapshot(baseline, translation)

    role = next(
        a
        for a in proposed["assets"]
        if a["asset_id"] == "cloud:arn:aws:iam::123456789012:role/loan-ops-analyst"
    )
    [finding] = role["findings"]
    assert finding["remediated_at"] is not None


def test_rupees_are_grouped_in_lakhs_and_crores() -> None:
    from interfaces.cli.cypher import _inr, _inr_short

    assert _inr(10_891_328.06) == "₹1,08,91,328"
    assert _inr(-2_279_351.19, signed=True) == "-₹22,79,351"
    assert _inr(950.4) == "₹950"
    assert _inr_short(31_260_498.37) == "₹3.13 Cr"
    assert _inr_short(1_158_164.41) == "₹11.58 L"


def test_cli_is_named_cypher_and_lists_plan() -> None:
    result = CliRunner().invoke(build_cli(), ["--help"])

    assert result.exit_code == 0
    for command in (
        "ingest",
        "validate-snapshot",
        "run-engine",
        "optimize",
        "framework-status",
        "plan",
    ):
        assert command in result.stdout


def test_baseline_is_fetched_from_s3_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "snapshots"
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(store))
    published = (_FIXTURES / "tf_plan_baseline.json").read_text()
    _use_s3(monkeypatch, _FakeS3({"snapshots/current.json": published}))

    code, report = _report(str(_FIXTURES / "tf_plan_open_db.json"), "--fail-on-eal-increase", "0")

    assert code == 2
    assert report["baseline"]["source"] == {
        "kind": "s3",
        "location": "s3://published-bucket/snapshots/",
        "refreshed": True,
        "warning": None,
    }
    assert (store / "current.json").read_text() == published


def test_unreachable_s3_falls_back_to_the_local_copy_and_says_so(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_s3(monkeypatch, _BrokenS3())

    code, report = _report(str(_FIXTURES / "tf_plan_open_db.json"))
    text = _run(str(_FIXTURES / "tf_plan_open_db.json")).stdout

    assert code == 0
    assert report["baseline"]["source"]["kind"] == "local"
    assert report["baseline"]["source"]["refreshed"] is False
    assert "Unable to locate credentials" in report["baseline"]["source"]["warning"]
    assert "Could not refresh the baseline from S3" in text


def test_unreachable_s3_and_no_local_copy_exits_without_a_figure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path / "empty"))
    _use_s3(monkeypatch, _BrokenS3())

    result = _run(str(_FIXTURES / "tf_plan_open_db.json"))

    assert result.exit_code == 1
    assert "₹" not in result.stdout
    assert "Unable to locate credentials" in result.stderr


def test_offline_never_touches_s3(store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s3 = _BrokenS3()
    _use_s3(monkeypatch, s3)

    code, report = _report(str(_FIXTURES / "tf_plan_open_db.json"), "--offline")

    assert code == 0
    assert s3.calls == 0
    assert report["baseline"]["source"]["kind"] == "local"
    assert report["baseline"]["source"]["warning"] is None


def test_snapshot_option_uses_that_file_and_never_touches_s3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path / "empty"))
    s3 = _BrokenS3()
    _use_s3(monkeypatch, s3)
    baseline = _FIXTURES / "tf_plan_baseline.json"

    code, report = _report(str(_FIXTURES / "tf_plan_reduce_risk.json"), "--snapshot", str(baseline))

    assert code == 0
    assert s3.calls == 0
    assert report["baseline"]["source"]["kind"] == "file"
    assert report["change"]["expected_annual_loss_inr"] < 0
