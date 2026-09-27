"""Tests for infra/connectors/terraform_plan.py against recorded Terraform plans.

The ``tf_plan_*.json`` fixtures are real ``terraform show -json`` output
(Terraform 1.16.1, hashicorp/aws 5.100.0) for the repo's own
``infra/terraform/modules`` (network, compute, iam, backup), planned with
``-refresh=false`` against a local state that matches that configuration
exactly (a plan of the unedited configuration reports "No changes"). The
state and every id in it are SYNTHETIC: account 123456789012, invented
instance/volume/security-group ids, TEST-NET addresses. No AWS account was
contacted. One edit per fixture:

- ``open_db``: ``db_sg``'s Postgres rule opened from the VPC CIDR to 0.0.0.0/0 (V-02, widened).
- ``attach_admin``: AdministratorAccess attached to the ``loan-ops-stale-key`` user (V-03's pattern).
- ``drop_dlm``: the DB's DLM snapshot policy deleted (V-06, widened).
- ``reduce_risk``: V-03's attachment and V-04's console password removed.
- ``new_instance``: a new, never-scanned instance behind the portal security group.

``tf_plan_baseline.json`` is a SYNTHETIC committed snapshot of the same
estate (CMDB endpoints for the four instances, findings in the shape the
Greenbone/Prowler connectors emit, the manually-declared services).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from infra.connectors.terraform_plan import (
    CONNECTOR_NAME,
    PlanTranslation,
    TerraformPlanError,
    check_plan_document,
    load_plan_file,
    parse_plan,
)
from infra.tests._snapshot_helpers import default_asset

_FIXTURES = Path(__file__).parent / "fixtures"
_SCHEMA = json.loads(
    (Path(__file__).parents[2] / "schema" / "aggregated_assets.schema.json").read_text()
)
_ASSET_SCHEMA = _SCHEMA["properties"]["assets"]["items"]
_BACKUP_SCHEMA = _SCHEMA["properties"]["services"]["items"]["properties"]["backup"]
_TOPOLOGY_SCHEMA = _SCHEMA["properties"]["network_topology"]

_PLANS = ("open_db", "attach_admin", "drop_dlm", "reduce_risk", "new_instance")

_ACCOUNT = "123456789012"
_ROLE_ARN = f"arn:aws:iam::{_ACCOUNT}:role/loan-ops-analyst"
_NO_MFA_ARN = f"arn:aws:iam::{_ACCOUNT}:user/loan-ops-no-mfa"
_STALE_KEY_ARN = f"arn:aws:iam::{_ACCOUNT}:user/loan-ops-stale-key"
_DB_SG = "module.network.aws_security_group.db_sg"


def _plan(name: str) -> dict[str, Any]:
    return load_plan_file(_FIXTURES / f"tf_plan_{name}.json")


def _baseline() -> dict[str, Any]:
    baseline: dict[str, Any] = json.loads((_FIXTURES / "tf_plan_baseline.json").read_text())
    return baseline


def _patch(translation: PlanTranslation, asset_id: str) -> dict[str, Any]:
    return next(p for p in translation.asset_patches if p["asset_id"] == asset_id)


def _changed_addresses(plan: dict[str, Any]) -> set[str]:
    return {
        rc["address"]
        for rc in plan["resource_changes"]
        if rc["change"]["actions"] not in (["no-op"], ["read"])
    }


def test_baseline_fixture_is_schema_valid() -> None:
    jsonschema.validate(_baseline(), _SCHEMA)


@pytest.mark.parametrize("name", _PLANS)
def test_every_fragment_is_schema_shaped(name: str) -> None:
    baseline = _baseline()
    translation = parse_plan(_plan(name), baseline)

    existing = {a["asset_id"]: a for a in baseline["assets"]}
    for patch in translation.asset_patches:
        asset = copy.deepcopy(existing.get(patch["asset_id"])) or default_asset(patch["asset_id"])
        asset.update({k: v for k, v in patch.items() if k != "findings"})
        by_id = {f["finding_id"]: f for f in asset["findings"]}
        by_id.update({f["finding_id"]: f for f in patch.get("findings", [])})
        asset["findings"] = list(by_id.values())
        jsonschema.validate(asset, _ASSET_SCHEMA)
    for service_patch in translation.service_patches:
        jsonschema.validate(service_patch["backup"], _BACKUP_SCHEMA)
    if translation.network_topology is not None:
        jsonschema.validate(translation.network_topology, _TOPOLOGY_SCHEMA)


@pytest.mark.parametrize("name", _PLANS)
def test_every_changed_resource_is_accounted_for(name: str) -> None:
    plan = _plan(name)
    translation = parse_plan(plan, _baseline())

    reported = (
        {c.address for c in translation.modelled}
        | {c.address for c in translation.unmodelled}
        | {c.address for c in translation.no_effect}
    )
    assert _changed_addresses(plan) <= reported


def test_opening_db_to_the_internet_makes_it_internet_facing() -> None:
    translation = parse_plan(_plan("open_db"), _baseline())

    patch = _patch(translation, "cmdb:loanease-db")
    assert patch["network"]["internet_facing"] is True
    assert "findings" not in patch
    [change] = translation.modelled
    assert change.address == _DB_SG
    assert change.kind == "exposure"
    assert change.asset_ids == ("cmdb:loanease-db",)
    assert translation.unmodelled == []


def test_closing_the_db_again_works_in_the_other_direction() -> None:
    plan = _plan("open_db")
    for rc in plan["resource_changes"]:
        if rc["address"] == _DB_SG:
            rc["change"]["before"], rc["change"]["after"] = (
                rc["change"]["after"],
                rc["change"]["before"],
            )
    baseline = _baseline()
    db = next(a for a in baseline["assets"] if a["asset_id"] == "cmdb:loanease-db")
    db["network"] = {"internet_facing": True, "open_ports": [22, 5432]}

    translation = parse_plan(plan, baseline)

    network = _patch(translation, "cmdb:loanease-db")["network"]
    assert network == {"internet_facing": False, "open_ports": [22, 5432]}


def test_closing_a_groups_last_internet_rule_remediates_its_internet_findings() -> None:
    plan = _plan("open_db")
    for rc in plan["resource_changes"]:
        if rc["address"] == _DB_SG:
            rc["change"]["before"], rc["change"]["after"] = (
                rc["change"]["after"],
                rc["change"]["before"],
            )
    sg_arn = f"arn:aws:ec2:ap-south-1:{_ACCOUNT}:security-group/sg-0b0000000000000b3"
    check = "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_postgres_5432"
    baseline = _baseline()
    sg_asset = default_asset(f"cloud:{sg_arn}")
    sg_asset["findings"] = [
        {
            "finding_id": f"prowler-{check}-{sg_arn}",
            "type": "misconfiguration",
            "criticality": "high",
            "provenance": {"connector": "prowler_connector", "raw_source_id": check},
            "first_seen_at": "2026-09-24T14:07:22Z",
            "remediated_at": None,
        }
    ]
    baseline["assets"].append(sg_asset)

    translation = parse_plan(plan, baseline)

    [finding] = _patch(translation, f"cloud:{sg_arn}")["findings"]
    assert finding["remediated_at"] == plan["timestamp"]
    assert finding["provenance"]["connector"] == "prowler_connector"


def test_admin_attachment_raises_the_finding_prowler_would() -> None:
    plan = _plan("attach_admin")
    translation = parse_plan(plan, _baseline())

    asset_id = f"cloud:{_STALE_KEY_ARN.lower()}"
    [finding] = _patch(translation, asset_id)["findings"]
    assert finding["finding_id"] == f"prowler-iam_user_administrator_access_policy-{_STALE_KEY_ARN}"
    assert finding["type"] == "misconfiguration"
    assert finding["criticality"] == "high"
    assert finding["remediated_at"] is None
    assert finding["first_seen_at"] == plan["timestamp"]
    assert finding["provenance"] == {
        "connector": CONNECTOR_NAME,
        "raw_source_id": "module.iam.aws_iam_user_policy_attachment.stale_key_admin",
    }


def test_admin_attachment_already_found_by_a_scan_is_not_counted_twice() -> None:
    baseline = _baseline()
    translation = parse_plan(_plan("attach_admin"), baseline)
    raised = translation.asset_patches[0]
    existing = default_asset(raised["asset_id"])
    existing["findings"] = [
        {
            **raised["findings"][0],
            "provenance": {"connector": "prowler_connector", "raw_source_id": "x"},
        }
    ]
    baseline["assets"].append(existing)

    again = parse_plan(_plan("attach_admin"), baseline)

    assert again.asset_patches == []
    assert [c.address for c in again.no_effect] == [
        "module.iam.aws_iam_user_policy_attachment.stale_key_admin"
    ]


def test_dropping_the_dlm_policy_removes_the_db_services_backup() -> None:
    translation = parse_plan(_plan("drop_dlm"), _baseline())

    assert translation.service_patches == [
        {
            "service_id": "svc-loan-db",
            "backup": {
                "exists": False,
                "last_tested_at": None,
                "rpo_hours": None,
                "rto_hours": None,
                "immutable_copy": None,
            },
        }
    ]
    [change] = translation.modelled
    assert change.kind == "backup"
    assert change.service_ids == ("svc-loan-db",)


def test_risk_reducing_plan_remediates_the_existing_findings() -> None:
    plan = _plan("reduce_risk")
    baseline = _baseline()
    translation = parse_plan(plan, baseline)

    for arn, check in (
        (_ROLE_ARN, "iam_role_administratoraccess_policy"),
        (_NO_MFA_ARN, "iam_user_mfa_enabled_console_access"),
    ):
        asset_id = f"cloud:{arn.lower()}"
        [finding] = _patch(translation, asset_id)["findings"]
        original = next(
            f for a in baseline["assets"] if a["asset_id"] == asset_id for f in a["findings"]
        )
        assert finding == {**original, "remediated_at": plan["timestamp"]}
    assert {c.kind for c in translation.modelled} == {"finding"}
    assert translation.removed_asset_ids == []


def test_new_instance_is_unscanned_not_safe() -> None:
    translation = parse_plan(_plan("new_instance"), _baseline())

    assert translation.asset_patches == []
    assert translation.modelled == []
    [skipped] = translation.unmodelled
    assert skipped.address == "module.compute.aws_instance.reporting"
    assert skipped.action == "create"
    assert "unknown" in skipped.reason and "not zero" in skipped.reason


def test_a_resource_the_baseline_cannot_match_is_unmodelled() -> None:
    baseline = _baseline()
    baseline["endpoints"] = []
    baseline["assets"] = [a for a in baseline["assets"] if not a["asset_id"].startswith("cmdb:")]

    translation = parse_plan(_plan("open_db"), baseline)

    assert translation.asset_patches == []
    assert [c.address for c in translation.unmodelled] == [_DB_SG]


def test_deleted_instance_is_removed_and_replaced_instance_keeps_its_findings() -> None:
    plan = _plan("open_db")
    for rc in plan["resource_changes"]:
        if rc["address"] == "module.compute.aws_instance.endpoint_sim":
            rc["change"]["actions"] = ["delete"]
            rc["change"]["after"] = None
        if rc["address"] == "module.compute.aws_instance.loan_portal":
            rc["change"]["actions"] = ["delete", "create"]

    translation = parse_plan(plan, _baseline())

    assert translation.removed_asset_ids == ["cmdb:loanease-endpoint-1"]
    replaced = next(
        c for c in translation.no_effect if c.address == "module.compute.aws_instance.loan_portal"
    )
    assert "keeps every finding" in replaced.reason


def test_a_new_security_group_is_known_only_after_apply() -> None:
    plan = _plan("open_db")
    for rc in plan["resource_changes"]:
        if rc["address"] == _DB_SG:
            rc["change"]["actions"] = ["create"]
            rc["change"]["before"] = None
            rc["change"]["after_unknown"] = {"id": True, "arn": True}

    translation = parse_plan(plan, _baseline())

    assert translation.asset_patches == []
    assert [c.address for c in translation.unmodelled] == [_DB_SG]


def _segmented_baseline() -> dict[str, Any]:
    baseline = _baseline()
    segments = {
        "cmdb:loanease-portal": "seg-web",
        "cmdb:loanease-bastion-scanner": "seg-ops",
        "cmdb:loanease-db": "seg-data",
        "cmdb:loanease-endpoint-1": "seg-users",
    }
    for asset in baseline["assets"]:
        if asset["asset_id"] in segments:
            asset["network"] = {"segment_id": segments[asset["asset_id"]]}
    baseline["network_topology"] = {
        "segments": [{"segment_id": s, "name": s} for s in sorted(set(segments.values()))],
        "segment_reachability": [
            {"from_segment_id": "seg-web", "to_segment_id": "seg-data"},
            {"from_segment_id": "seg-ops", "to_segment_id": "seg-data"},
            {"from_segment_id": "seg-users", "to_segment_id": "seg-data"},
        ],
    }
    return baseline


def _narrow_db_to_portal(plan: dict[str, Any]) -> dict[str, Any]:
    """V-02 fixed: Postgres only from the portal's security group, not the whole VPC."""
    for rc in plan["resource_changes"]:
        if rc["address"] == _DB_SG:
            after = copy.deepcopy(rc["change"]["before"])
            after["ingress"][0]["cidr_blocks"] = []
            after["ingress"][0]["security_groups"] = ["sg-0b0000000000000b2"]
            rc["change"]["after"] = after
    return plan


def test_narrowing_internal_reachability_removes_a_segment_pair() -> None:
    translation = parse_plan(_narrow_db_to_portal(_plan("open_db")), _segmented_baseline())

    assert translation.network_topology is not None
    pairs = {
        (p["from_segment_id"], p["to_segment_id"])
        for p in translation.network_topology["segment_reachability"]
    }
    assert pairs == {("seg-web", "seg-data"), ("seg-ops", "seg-data")}
    [change] = translation.modelled
    assert change.topology and change.kind == "topology"
    assert change.address == _DB_SG


def test_internal_reachability_without_topology_is_unmodelled() -> None:
    translation = parse_plan(_narrow_db_to_portal(_plan("open_db")), _baseline())

    assert translation.network_topology is None
    assert translation.modelled == []
    [skipped] = translation.unmodelled
    assert skipped.address == _DB_SG
    assert "network_topology" in skipped.reason


def test_load_plan_file_refuses_a_binary_plan(tmp_path: Path) -> None:
    binary = tmp_path / "tf.plan"
    binary.write_bytes(b"PK\x03\x04\x14\x00\x08\x00\x08\x00")
    with pytest.raises(TerraformPlanError, match="not JSON"):
        load_plan_file(binary)


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"resource_changes": []},
        {"format_version": "1.0", "values": {}},
        {"format_version": "1.2", "resource_changes": [], "errored": True},
    ],
)
def test_check_plan_document_refuses_what_is_not_a_usable_plan(document: Any) -> None:
    with pytest.raises(TerraformPlanError):
        check_plan_document(document, "test")
