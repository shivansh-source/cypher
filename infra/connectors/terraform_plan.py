"""Translator for Terraform plans: ``terraform show -json`` -> schema-shaped changes.

``cypher plan`` (``interfaces/cli/cypher.py``) asks what a Terraform change
would do to modelled cyber risk *before* it is applied. This module is the
only place in the codebase that knows what a Terraform plan looks like
(repo-root ``CLAUDE.md`` principle 3): it reads the plan's
``resource_changes[]`` (each resource's ``before``/``after`` state and
``actions``) and translates the security-relevant ones into
``schema/aggregated_assets.schema.json``-shaped changes against a baseline
snapshot. The caller overlays those changes on a copy of the baseline and
re-simulates it jointly (``core.optimizer.compare_snapshots``); nothing
here produces or estimates a rupee figure.

This is not a :class:`infra.connectors.base.Connector` subclass. A plan
does not describe assets that a scan observed; it describes *differences*
(an exposure opened, a finding fixed, a backup dropped, a resource
deleted), and some of them are keyed by ``service_id`` or apply to
``network_topology``. None of that fits ``base.py``'s
one-asset-id-per-fragment contract, for the same reason
``cmdb_connector.py`` gives for ``services[]``.

What the rules model, one small function each:

- **Network exposure** (``aws_security_group``,
  ``aws_security_group_rule``, ``aws_vpc_security_group_ingress_rule``,
  ``aws_instance``): an instance with a public IP whose security groups
  allow ingress from ``0.0.0.0/0`` or ``::/0`` is internet-facing. When a
  plan changes that, ``network.internet_facing`` changes on the
  instance's asset(s), in either direction. Ports those groups admit
  update ``network.open_ports`` where the baseline already lists them.
  Which instances can reach which inside the VPC becomes
  ``network_topology`` segment pairs when the baseline has segments for
  both ends. Closing a group's last internet rule also fixes the group's
  own open "ingress from the internet" findings.
- **IAM** (``aws_iam_role_policy_attachment``,
  ``aws_iam_user_policy_attachment``, ``aws_iam_policy_attachment``,
  ``aws_iam_role_policy``, ``aws_iam_user_policy``,
  ``aws_iam_user_login_profile``, ``aws_iam_virtual_mfa_device``):
  attaching ``AdministratorAccess`` (or an inline ``*`` on ``*`` policy),
  or giving a user a console password with no MFA device, raises the
  same misconfiguration finding, with the same id, that
  ``prowler_connector.py`` would raise after apply. Undoing it marks that
  finding remediated.
- **Backup** (``aws_dlm_lifecycle_policy``, ``aws_ec2_tag``, instance and
  volume tags): when a plan changes whether any enabled DLM policy
  targets a service's volumes, ``services[].backup.exists`` follows.
- **Deletion**: deleting an instance, IAM role/user or security group
  removes its asset(s). A *replaced* resource keeps its asset and every
  finding on it, since a rebuild from the same image is not a fix.

What it cannot model is returned, never hidden: a created resource
(nothing has scanned it, so its risk is unknown, not zero), a value known
only after apply, a resource the baseline cannot be matched to, and any
resource type these rules do not cover. See :class:`PlanTranslation`.

Identity resolution reads only the baseline snapshot: ``endpoints[]``
(CMDB's instance ids, ARNs, Name tags and private IPs) and the placeholder
``cloud:<arn>`` / ``host:<ip>`` asset ids the other connectors mint.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: This translator's ``provenance.connector`` value, and the name it adds
#: to a proposed snapshot's ``scan_scope.reachable_scanners``.
CONNECTOR_NAME = "terraform_plan"

# ---------------------------------------------------------------------------
# Terraform and AWS vocabulary. Facts about those tools' shapes, not
# modelling judgements, so they live here rather than in core/assumptions.py.
# ---------------------------------------------------------------------------

#: Source CIDRs that mean "anyone on the internet".
_INTERNET_CIDRS = frozenset({"0.0.0.0/0", "::/0"})

#: The AWS-managed AdministratorAccess policy, in any partition.
_ADMINISTRATOR_ACCESS = re.compile(r"^arn:[a-z-]+:iam::aws:policy/AdministratorAccess$")

#: Protocol values meaning "every protocol and port".
_ALL_PROTOCOLS = frozenset({"-1", "all"})

#: Port ranges wider than this are not listed port-by-port in
#: ``network.open_ports``. A representation limit (a 0-65535 rule would
#: otherwise add 65,536 entries), not a modelling judgement; such a rule
#: still counts for ``internet_facing``.
_MAX_LISTED_PORT_RANGE = 64

#: Prowler checks whose finding this translator raises or clears, with the
#: severity Prowler reports for each (``infra/terraform/manifest.yaml``
#: records the role-admin and console-MFA checks from a real 5.43.0 run).
#: Finding ids follow ``prowler_connector.py``: ``prowler-<check id>-<resource
#: ARN>``, with the principal's ARN as the resource. For the inline-policy
#: check that resource is not yet confirmed against a real Prowler report;
#: if Prowler keys it differently, a plan that removes an inline admin
#: policy reports "no open finding to remediate" rather than a wrong figure.
_ROLE_ADMIN_CHECK = "iam_role_administratoraccess_policy"
_USER_ADMIN_CHECK = "iam_user_administrator_access_policy"
_INLINE_ADMIN_CHECK = "iam_inline_policy_no_administrative_privileges"
_CONSOLE_WITHOUT_MFA_CHECK = "iam_user_mfa_enabled_console_access"
_CHECK_CRITICALITY: dict[str, str] = {
    _ROLE_ADMIN_CHECK: "high",
    _USER_ADMIN_CHECK: "high",
    _INLINE_ADMIN_CHECK: "high",
    _CONSOLE_WITHOUT_MFA_CHECK: "high",
}

#: Every Prowler check about a security group admitting internet traffic
#: starts with this; all of them pass once the group has no internet rule.
_SG_INTERNET_CHECK_PREFIX = "ec2_securitygroup_allow_ingress_from_internet_to_"

#: Resource types that are themselves assets. Creating one adds something
#: no scanner has seen.
_ASSET_TYPES = frozenset(
    {
        "aws_instance",
        "aws_iam_role",
        "aws_iam_user",
        "aws_db_instance",
        "aws_rds_cluster",
        "aws_s3_bucket",
        "aws_lambda_function",
        "aws_eks_cluster",
        "aws_lb",
        "aws_elb",
    }
)

_SG_RULE_TYPES = frozenset(
    {"aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule"}
)
_IAM_TYPES = frozenset(
    {
        "aws_iam_role",
        "aws_iam_user",
        "aws_iam_role_policy_attachment",
        "aws_iam_user_policy_attachment",
        "aws_iam_policy_attachment",
        "aws_iam_role_policy",
        "aws_iam_user_policy",
        "aws_iam_user_login_profile",
        "aws_iam_virtual_mfa_device",
    }
)
_BACKUP_TYPES = frozenset({"aws_dlm_lifecycle_policy", "aws_ec2_tag", "aws_ebs_volume"})
_HANDLED_TYPES = _SG_RULE_TYPES | _IAM_TYPES | _BACKUP_TYPES | {"aws_instance"}

_BEFORE = "before"
_AFTER = "after"


class TerraformPlanError(RuntimeError):
    """Raised when a plan cannot be produced, read, or recognized as ``terraform show -json`` output."""


@dataclass(frozen=True)
class ModelledChange:
    """One Terraform change the translation carried into the proposed snapshot.

    Attributes:
        address: The Terraform resource address that caused it.
        action: ``create``, ``update``, ``delete`` or ``replace``.
        kind: ``exposure`` (``network`` on an asset), ``topology``
            (``network_topology``), ``finding``, ``backup`` or ``removal``.
            Exposure and topology changes move attack-graph reachability,
            so they can change loss on assets they do not name.
        effect: What changed in the snapshot, in words.
        asset_ids: Assets whose record this changed (for attribution).
        service_ids: Services whose record this changed.
        topology: True if it changed ``network_topology``, which can move
            any asset's attack-graph reachability.
    """

    address: str
    action: str
    kind: str
    effect: str
    asset_ids: tuple[str, ...] = ()
    service_ids: tuple[str, ...] = ()
    topology: bool = False


@dataclass(frozen=True)
class SkippedChange:
    """A Terraform change that is not in the proposed snapshot, and why.

    Attributes:
        address: The Terraform resource address.
        action: ``create``, ``update``, ``delete`` or ``replace``.
        reason: Why it is not modelled (or, in
            :attr:`PlanTranslation.no_effect`, why it changes nothing the
            engine reads).
    """

    address: str
    action: str
    reason: str


@dataclass(frozen=True)
class PlanTranslation:
    """A Terraform plan, translated into schema-shaped changes to a baseline snapshot.

    Every fragment below is shaped by ``schema/aggregated_assets.schema.json``.

    Attributes:
        asset_patches: One fragment per changed asset: ``asset_id``, plus
            any of ``network`` / ``identity_access`` (the whole new
            section) and ``findings`` (findings to add or replace, matched
            by ``finding_id``; a replaced finding carries
            ``remediated_at``). An ``asset_id`` absent from the baseline is
            a principal the plan newly gives a finding to.
        service_patches: ``{"service_id", "backup"}`` with the whole new
            ``backup`` object.
        removed_asset_ids: Assets the plan deletes.
        network_topology: The whole new ``network_topology``, or None if
            the plan does not change it.
        modelled: What the changes above are, and which address caused each.
        no_effect: Changes the rules evaluated and found to change nothing
            the engine reads (e.g. a tag or description edit).
        unmodelled: Changes whose effect on risk is unknown. Never read as
            zero: a caller must show these next to any figure.
        terraform_version: From the plan.
        plan_timestamp: When the plan was made (ISO-8601), or None.
    """

    asset_patches: list[dict[str, Any]]
    service_patches: list[dict[str, Any]]
    removed_asset_ids: list[str]
    network_topology: dict[str, Any] | None
    modelled: list[ModelledChange]
    no_effect: list[SkippedChange]
    unmodelled: list[SkippedChange]
    terraform_version: str
    plan_timestamp: str | None


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def load_plan_file(path: Path) -> dict[str, Any]:
    """Read a ``terraform show -json <planfile>`` document from disk.

    Raises:
        TerraformPlanError: If the file cannot be read, is not JSON (e.g.
            the binary plan file itself), or is not a Terraform plan.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TerraformPlanError(f"could not read {path}: {exc}") from exc
    try:
        plan = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TerraformPlanError(
            f"{path} is not JSON. Pass the output of `terraform show -json <planfile>`, "
            "or use --dir to run terraform for you."
        ) from exc
    return check_plan_document(plan, str(path))


def run_terraform_plan(directory: Path, terraform_bin: str = "terraform") -> dict[str, Any]:
    """Run ``terraform plan -out`` then ``terraform show -json`` in ``directory``.

    Terraform runs with the operator's own configuration and credentials
    (``terraform init`` must already have run there). The plan is written
    to a temporary file and deleted afterwards; nothing is applied.

    Raises:
        TerraformPlanError: If terraform is not installed or either command fails.
    """
    executable = shutil.which(terraform_bin)
    if executable is None:
        raise TerraformPlanError(f"{terraform_bin!r} was not found on PATH")
    if not directory.is_dir():
        raise TerraformPlanError(f"{directory} is not a directory")
    with tempfile.TemporaryDirectory(prefix="cypher-plan-") as scratch:
        plan_file = Path(scratch) / "cypher.tfplan"
        commands = [
            [
                executable,
                f"-chdir={directory}",
                "plan",
                "-input=false",
                "-no-color",
                f"-out={plan_file}",
            ],
            [executable, f"-chdir={directory}", "show", "-json", str(plan_file)],
        ]
        output = ""
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise TerraformPlanError(
                    f"`terraform {command[2]}` failed in {directory} "
                    f"(exit {result.returncode}): {result.stderr.strip()[:2000]}"
                )
            output = result.stdout
    try:
        plan = json.loads(output)
    except json.JSONDecodeError as exc:
        raise TerraformPlanError(f"`terraform show -json` did not print JSON: {exc}") from exc
    return check_plan_document(plan, f"terraform show -json in {directory}")


def check_plan_document(plan: Any, source: str) -> dict[str, Any]:
    """Refuse anything that is not a ``terraform show -json`` plan; return it typed.

    Raises:
        TerraformPlanError: If ``plan`` is not a JSON object with a 1.x
            ``format_version`` and a ``resource_changes`` list (state
            output from ``terraform show -json`` with no plan has none), or
            if Terraform reported the plan as errored.
    """
    if not isinstance(plan, dict):
        raise TerraformPlanError(f"{source}: expected a JSON object, got {type(plan).__name__}")
    version = str(plan.get("format_version", ""))
    if not version.startswith("1."):
        raise TerraformPlanError(
            f"{source}: unsupported or missing format_version {version!r} "
            "(expected `terraform show -json` output, format 1.x)"
        )
    if "resource_changes" not in plan and "planned_values" not in plan:
        raise TerraformPlanError(
            f"{source}: no resource_changes — this looks like state, not a plan"
        )
    if not isinstance(plan.get("resource_changes", []), list):
        raise TerraformPlanError(f"{source}: resource_changes is not a list")
    if plan.get("errored") is True:
        raise TerraformPlanError(f"{source}: terraform reported this plan as errored")
    return plan


# ---------------------------------------------------------------------------
# Reading resource_changes
# ---------------------------------------------------------------------------


class _Unknown:
    """Marker for a value Terraform will only know after apply."""

    def __repr__(self) -> str:
        return "(known after apply)"


UNKNOWN = _Unknown()


def _has_unknown(flag: Any) -> bool:
    """Whether an ``after_unknown`` entry marks this value, or anything inside it, unknown."""
    if flag is True:
        return True
    if isinstance(flag, list):
        return any(_has_unknown(item) for item in flag)
    if isinstance(flag, dict):
        return any(_has_unknown(item) for item in flag.values())
    return False


@dataclass(frozen=True, eq=False)
class _Resource:
    """One ``resource_changes[]`` entry for a managed resource."""

    address: str
    type: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    after_unknown: dict[str, Any]

    def exists(self, side: str) -> bool:
        return (self.before if side == _BEFORE else self.after) is not None

    def get(self, side: str, key: str) -> Any:
        """The attribute's value on ``side``, :data:`UNKNOWN` if known only after apply.

        None if the resource does not exist on that side or has no such
        attribute.
        """
        state = self.before if side == _BEFORE else self.after
        if state is None:
            return None
        if side == _AFTER and _has_unknown(self.after_unknown.get(key)):
            return UNKNOWN
        return state.get(key)

    @property
    def changed(self) -> bool:
        return self.action != "no-op"


def _action(actions: list[str]) -> str:
    if sorted(actions) == ["create", "delete"]:
        return "replace"
    return actions[0] if len(actions) == 1 else "+".join(actions)


def _resources(plan: dict[str, Any]) -> list[_Resource]:
    resources: list[_Resource] = []
    for change in plan.get("resource_changes") or []:
        if change.get("mode", "managed") != "managed":
            continue
        body = change.get("change") or {}
        resources.append(
            _Resource(
                address=str(change["address"]),
                type=str(change["type"]),
                action=_action(list(body.get("actions") or ["no-op"])),
                before=body.get("before"),
                after=body.get("after"),
                after_unknown=body.get("after_unknown") or {},
            )
        )
    return resources


def _tag(tags: Any, key: str) -> str | None:
    if isinstance(tags, dict):
        value = tags.get(key)
        return str(value) if value else None
    return None


def _account_and_partition(resources: list[_Resource]) -> tuple[str | None, str]:
    """The AWS account id and partition, read off any ARN already in the plan."""
    pattern = re.compile(r"^arn:([a-z-]+):[a-z0-9-]+:[a-z0-9-]*:(\d{12}):")
    for resource in resources:
        for side in (_BEFORE, _AFTER):
            arn = resource.get(side, "arn")
            if isinstance(arn, str):
                match = pattern.match(arn)
                if match:
                    return match.group(2), match.group(1)
    return None, "aws"


# ---------------------------------------------------------------------------
# Identity: Terraform resources -> baseline asset ids
# ---------------------------------------------------------------------------


class _AssetIndex:
    """Matches a resource's identifiers to baseline asset ids.

    An identifier matches an ``endpoints[]`` address (CMDB's instance ids,
    ARNs, hostnames, private IPs), or an asset whose id is that identifier
    under the placeholder schemes other connectors mint (``cloud:<arn or
    id>``, ``host:<ip or name>``) or CMDB's own (``cmdb:<Name tag or
    instance id>``). One machine can match several assets (e.g. a
    ``cloud:`` instance ARN asset and a ``host:`` IP asset that identity
    resolution has not merged yet); every one of them is returned.
    """

    def __init__(self, baseline: dict[str, Any]) -> None:
        self.asset_ids = {asset["asset_id"] for asset in baseline["assets"]}
        self._by_address: dict[str, set[str]] = {}
        for endpoint in baseline.get("endpoints") or []:
            resolved = endpoint.get("resolved_asset_id")
            if resolved:
                self._by_address.setdefault(str(endpoint["address"]).lower(), set()).add(resolved)

    def resolve(self, identifiers: Iterable[str | None]) -> list[str]:
        matched: set[str] = set()
        for identifier in identifiers:
            if not isinstance(identifier, str) or not identifier:
                continue
            key = str(identifier).lower()
            matched |= self._by_address.get(key, set())
            for prefix in ("cloud:", "host:", "cmdb:"):
                for candidate in (f"{prefix}{key}", f"{prefix}{identifier}"):
                    if candidate in self.asset_ids:
                        matched.add(candidate)
        return sorted(matched)


# ---------------------------------------------------------------------------
# Working copy of the changes
# ---------------------------------------------------------------------------


class _Changes:
    """Accumulates schema-shaped changes against the baseline, then emits fragments."""

    def __init__(self, baseline: dict[str, Any], timestamp: str) -> None:
        self._baseline_assets = {asset["asset_id"]: asset for asset in baseline["assets"]}
        self._baseline_services = {
            service["service_id"]: service for service in baseline.get("services") or []
        }
        self.timestamp = timestamp
        self._network: dict[str, dict[str, Any]] = {}
        self._findings: dict[str, dict[str, dict[str, Any]]] = {}
        self._backup: dict[str, dict[str, Any]] = {}
        self.removed: set[str] = set()
        self.topology: dict[str, Any] | None = None
        self.modelled: list[ModelledChange] = []
        self.no_effect: list[SkippedChange] = []
        self.unmodelled: list[SkippedChange] = []
        self._accounted: set[str] = set()

    def settled(self) -> list[SkippedChange]:
        """``no_effect``, minus anything some other part of the plan's analysis records."""
        elsewhere = {c.address for c in self.modelled} | {c.address for c in self.unmodelled}
        return [c for c in self.no_effect if c.address not in elsewhere]

    # -- bookkeeping ------------------------------------------------------

    def model(self, resources: Iterable[_Resource], kind: str, effect: str, **kwargs: Any) -> None:
        for resource in resources:
            self.modelled.append(
                ModelledChange(resource.address, resource.action, kind, effect, **kwargs)
            )
            self._accounted.add(resource.address)

    def skip(self, resource: _Resource, reason: str) -> None:
        """Record a change (or part of one) whose effect on risk is unknown."""
        entry = SkippedChange(resource.address, resource.action, reason)
        if entry not in self.unmodelled:
            self.unmodelled.append(entry)
        self._accounted.add(resource.address)

    def settle(self, resource: _Resource, reason: str) -> None:
        """Record an evaluated change that alters nothing the engine reads (first reason wins)."""
        if resource.address not in self._accounted:
            self.no_effect.append(SkippedChange(resource.address, resource.action, reason))
            self._accounted.add(resource.address)

    def accounted(self, resource: _Resource) -> bool:
        return resource.address in self._accounted

    # -- assets -----------------------------------------------------------

    def network(self, asset_id: str) -> dict[str, Any]:
        if asset_id not in self._network:
            baseline = self._baseline_assets.get(asset_id) or {}
            self._network[asset_id] = copy.deepcopy(baseline.get("network") or {})
        return self._network[asset_id]

    def finding(self, asset_id: str, finding_id: str) -> dict[str, Any] | None:
        patched = self._findings.get(asset_id, {}).get(finding_id)
        if patched is not None:
            return patched
        for finding in (self._baseline_assets.get(asset_id) or {}).get("findings", []):
            if finding.get("finding_id") == finding_id:
                return dict(finding)
        return None

    def open_findings(self, asset_id: str) -> list[dict[str, Any]]:
        ids = [
            f["finding_id"] for f in (self._baseline_assets.get(asset_id) or {}).get("findings", [])
        ]
        ids += [i for i in self._findings.get(asset_id, {}) if i not in ids]
        found = [self.finding(asset_id, finding_id) for finding_id in ids]
        return [f for f in found if f is not None and f.get("remediated_at") is None]

    def raise_finding(self, asset_id: str, finding: dict[str, Any]) -> bool:
        """Add ``finding`` unless the same finding is already open. True if anything changed."""
        existing = self.finding(asset_id, finding["finding_id"])
        if existing is not None and existing.get("remediated_at") is None:
            return False
        self._findings.setdefault(asset_id, {})[finding["finding_id"]] = finding
        return True

    def remediate(self, asset_id: str, finding_id: str) -> bool:
        """Mark an open finding remediated as of the plan. True if one was open."""
        existing = self.finding(asset_id, finding_id)
        if existing is None or existing.get("remediated_at") is not None:
            return False
        self._findings.setdefault(asset_id, {})[finding_id] = {
            **existing,
            "remediated_at": self.timestamp,
        }
        return True

    # -- services ---------------------------------------------------------

    def backup(self, service_id: str) -> dict[str, Any]:
        if service_id not in self._backup:
            service = self._baseline_services.get(service_id) or {}
            self._backup[service_id] = copy.deepcopy(service.get("backup") or {})
        return self._backup[service_id]

    def services_of(self, asset_ids: Iterable[str]) -> list[str]:
        services: set[str] = set()
        for asset_id in asset_ids:
            services.update((self._baseline_assets.get(asset_id) or {}).get("service_ids") or [])
        return sorted(s for s in services if s in self._baseline_services)

    # -- output -----------------------------------------------------------

    def asset_patches(self) -> list[dict[str, Any]]:
        patches: dict[str, dict[str, Any]] = {}
        for asset_id, network in self._network.items():
            baseline = (self._baseline_assets.get(asset_id) or {}).get("network") or {}
            if network != baseline and asset_id not in self.removed:
                patches.setdefault(asset_id, {"asset_id": asset_id})["network"] = network
        for asset_id, findings in self._findings.items():
            if asset_id not in self.removed:
                patches.setdefault(asset_id, {"asset_id": asset_id})["findings"] = list(
                    findings.values()
                )
        return [patches[asset_id] for asset_id in sorted(patches)]

    def service_patches(self) -> list[dict[str, Any]]:
        return [
            {"service_id": service_id, "backup": backup}
            for service_id, backup in sorted(self._backup.items())
            if backup != (self._baseline_services.get(service_id, {}).get("backup") or {})
        ]


def _shown(value: Any) -> str:
    """A schema value as the report shows it: ``null`` reads as unknown, booleans in lower case."""
    if value is None:
        return "unknown"
    return str(value).lower() if isinstance(value, bool) else str(value)


def _prowler_finding(check: str, resource_arn: str, address: str, timestamp: str) -> dict[str, Any]:
    """The finding ``prowler_connector.py`` would raise for ``check`` on ``resource_arn``.

    Same ``finding_id``, type and criticality, so an issue the plan
    introduces and the scan that later confirms it are one finding, never
    two. Provenance is this translator, with the Terraform address as the
    raw source.
    """
    return {
        "finding_id": f"prowler-{check}-{resource_arn}",
        "type": "misconfiguration",
        "cve_id": None,
        "epss_score": None,
        "kev_listed": None,
        "criticality": _CHECK_CRITICALITY[check],
        "provenance": {"connector": CONNECTOR_NAME, "raw_source_id": address},
        "first_seen_at": timestamp,
        "remediated_at": None,
    }


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------


@dataclass
class _Instance:
    resource: _Resource
    asset_ids: list[str]

    def sg_ids(self, side: str) -> set[str] | _Unknown | None:
        value = self.resource.get(side, "vpc_security_group_ids")
        if isinstance(value, _Unknown):
            # An in-place update that does not touch the groups keeps them.
            if self.resource.action == "update":
                before = self.resource.get(_BEFORE, "vpc_security_group_ids")
                return set(before or [])
            return UNKNOWN
        if value is None and not self.resource.exists(side):
            return None
        return set(value or [])

    def public(self, side: str) -> bool | _Unknown:
        for key in ("public_ip", "associate_public_ip_address"):
            value = self.resource.get(side, key)
            if isinstance(value, _Unknown) and self.resource.exists(_BEFORE):
                # The plan does not set it; the instance keeps what it has.
                value = self.resource.get(_BEFORE, key)
            if isinstance(value, _Unknown):
                return UNKNOWN
            if value:
                return True
        return False

    def private_ip(self, side: str) -> str | None:
        value = self.resource.get(side, "private_ip")
        if isinstance(value, _Unknown):
            value = self.resource.get(_BEFORE, "private_ip")
        return value if isinstance(value, str) and value else None

    def volume_ids(self, side: str) -> set[str]:
        volumes: set[str] = set()
        for key in ("root_block_device", "ebs_block_device"):
            blocks = self.resource.get(side, key)
            if isinstance(blocks, _Unknown):
                blocks = self.resource.get(_BEFORE, key)
            for block in blocks or []:
                volume_id = block.get("volume_id") if isinstance(block, dict) else None
                if volume_id:
                    volumes.add(volume_id)
        return volumes

    def name(self) -> str:
        for side in (_BEFORE, _AFTER):
            name = _tag(self.resource.get(side, "tags"), "Name")
            if name:
                return name
        return self.resource.address


def _instance_identifiers(resource: _Resource) -> list[str | None]:
    """Every identifier the baseline might know an existing instance by."""
    before = resource.before or {}
    private_dns = before.get("private_dns")
    identifiers: list[str | None] = [
        before.get("id"),
        before.get("arn"),
        before.get("private_ip"),
        private_dns,
        private_dns.split(".")[0] if isinstance(private_dns, str) else None,
        _tag(before.get("tags"), "Name"),
    ]
    arn = before.get("arn")
    if isinstance(arn, str) and ":instance/" in arn:
        prefix = arn.split(":instance/")[0]
        for key in ("root_block_device", "ebs_block_device"):
            for block in before.get(key) or []:
                if isinstance(block, dict) and block.get("volume_id"):
                    identifiers.append(f"{prefix}:volume/{block['volume_id']}")
    return identifiers


# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Rule:
    address: str
    protocol: str
    from_port: int | None
    to_port: int | None
    cidrs: frozenset[str]
    source_sgs: frozenset[str]
    self_reference: bool

    @property
    def from_internet(self) -> bool:
        return bool(self.cidrs & _INTERNET_CIDRS)

    def ports(self) -> set[int] | None:
        """The ports this rule lists, or None when it is all/too many ports to list."""
        if self.protocol in _ALL_PROTOCOLS or self.from_port is None or self.to_port is None:
            return None
        if self.to_port - self.from_port >= _MAX_LISTED_PORT_RANGE:
            return None
        return set(range(self.from_port, self.to_port + 1))


def _port(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


class _SecurityGroups:
    """Ingress rules per security group id, on each side of the plan."""

    def __init__(self, resources: list[_Resource]) -> None:
        self.rules: dict[str, dict[str, list[_Rule]]] = {_BEFORE: {}, _AFTER: {}}
        #: Group ids whose rules cannot be known on a side.
        self.unknown: dict[str, set[str]] = {_BEFORE: set(), _AFTER: set()}
        #: Changed resources that touch each group id (either side).
        self.changed_by: dict[str, list[_Resource]] = {}
        #: Changed rule resources whose group is known only after apply.
        self.unresolved: list[_Resource] = []
        self.arn: dict[str, str] = {}
        for resource in resources:
            if resource.type in _SG_RULE_TYPES:
                self._read(resource)

    def _add(self, side: str, sg_id: Any, rule: _Rule | None, resource: _Resource) -> None:
        if not isinstance(sg_id, str):
            return
        self.rules[side].setdefault(sg_id, [])
        if rule is not None:
            self.rules[side][sg_id].append(rule)
        if resource.changed and resource not in self.changed_by.setdefault(sg_id, []):
            self.changed_by[sg_id].append(resource)

    def _read(self, resource: _Resource) -> None:
        for side in (_BEFORE, _AFTER):
            if not resource.exists(side):
                continue
            if resource.type == "aws_security_group":
                sg_id = resource.get(side, "id")
                if isinstance(sg_id, _Unknown):
                    if resource.changed:
                        self.unresolved.append(resource)
                    continue
                arn = resource.get(side, "arn")
                if isinstance(arn, str):
                    self.arn[sg_id] = arn
                ingress = resource.get(side, "ingress")
                if isinstance(ingress, _Unknown):
                    self.unknown[side].add(sg_id)
                    self._add(side, sg_id, None, resource)
                    continue
                self._add(side, sg_id, None, resource)
                for block in ingress or []:
                    self._add(side, sg_id, self._inline_rule(resource.address, block), resource)
                continue

            sg_id = resource.get(side, "security_group_id")
            if (
                resource.type == "aws_security_group_rule"
                and resource.get(side, "type") != "ingress"
            ):
                continue
            if isinstance(sg_id, _Unknown):
                if resource.changed:
                    self.unresolved.append(resource)
                continue
            rule = self._standalone_rule(resource, side)
            if isinstance(rule, _Unknown):
                self.unknown[side].add(sg_id)
                self._add(side, sg_id, None, resource)
            else:
                assert isinstance(rule, _Rule)
                self._add(side, sg_id, rule, resource)

    @staticmethod
    def _inline_rule(address: str, block: dict[str, Any]) -> _Rule:
        return _Rule(
            address=address,
            protocol=str(block.get("protocol", "")).lower(),
            from_port=_port(block.get("from_port")),
            to_port=_port(block.get("to_port")),
            cidrs=frozenset(
                (block.get("cidr_blocks") or []) + (block.get("ipv6_cidr_blocks") or [])
            ),
            source_sgs=frozenset(block.get("security_groups") or []),
            self_reference=bool(block.get("self")),
        )

    @staticmethod
    def _standalone_rule(resource: _Resource, side: str) -> _Rule | _Unknown:
        if resource.type == "aws_security_group_rule":
            keys = (
                "protocol",
                "from_port",
                "to_port",
                "cidr_blocks",
                "ipv6_cidr_blocks",
                "source_security_group_id",
                "self",
            )
            values = {key: resource.get(side, key) for key in keys}
            if any(isinstance(value, _Unknown) for value in values.values()):
                return UNKNOWN
            source = values["source_security_group_id"]
            return _Rule(
                address=resource.address,
                protocol=str(values["protocol"] or "").lower(),
                from_port=_port(values["from_port"]),
                to_port=_port(values["to_port"]),
                cidrs=frozenset((values["cidr_blocks"] or []) + (values["ipv6_cidr_blocks"] or [])),
                source_sgs=frozenset([source] if source else []),
                self_reference=bool(values["self"]),
            )
        vpc_keys = (
            "ip_protocol",
            "from_port",
            "to_port",
            "cidr_ipv4",
            "cidr_ipv6",
            "referenced_security_group_id",
        )
        values = {key: resource.get(side, key) for key in vpc_keys}
        if any(isinstance(value, _Unknown) for value in values.values()):
            return UNKNOWN
        source = values["referenced_security_group_id"]
        return _Rule(
            address=resource.address,
            protocol=str(values["ip_protocol"] or "").lower(),
            from_port=_port(values["from_port"]),
            to_port=_port(values["to_port"]),
            cidrs=frozenset(c for c in (values["cidr_ipv4"], values["cidr_ipv6"]) if c),
            source_sgs=frozenset([source] if source else []),
            self_reference=False,
        )

    def rules_for(self, side: str, sg_ids: set[str]) -> list[_Rule] | _Unknown:
        if sg_ids & self.unknown[side]:
            return UNKNOWN
        return [rule for sg_id in sorted(sg_ids) for rule in self.rules[side].get(sg_id, [])]

    def internet_open(self, side: str, sg_id: str) -> bool | _Unknown:
        if sg_id in self.unknown[side]:
            return UNKNOWN
        return any(rule.from_internet for rule in self.rules[side].get(sg_id, []))


def _exposure(
    instance: _Instance, side: str, groups: _SecurityGroups
) -> tuple[bool, set[int]] | _Unknown:
    """(internet-facing, listable open ports) for an instance on one side of the plan."""
    sg_ids = instance.sg_ids(side)
    if isinstance(sg_ids, _Unknown) or sg_ids is None:
        return UNKNOWN
    assert isinstance(sg_ids, set)
    rules = groups.rules_for(side, sg_ids)
    public = instance.public(side)
    if isinstance(rules, _Unknown) or isinstance(public, _Unknown):
        return UNKNOWN
    assert isinstance(rules, list)
    ports: set[int] = set()
    for rule in rules:
        ports |= rule.ports() or set()
    return bool(public) and any(rule.from_internet for rule in rules), ports


def _apply_network_rules(
    instances: list[_Instance], groups: _SecurityGroups, changes: _Changes
) -> None:
    for instance in instances:
        resource = instance.resource
        if not (resource.exists(_BEFORE) and resource.exists(_AFTER)) or not instance.asset_ids:
            continue
        before_sgs = instance.sg_ids(_BEFORE)
        after_sgs = instance.sg_ids(_AFTER)
        causes: list[_Resource] = []
        for sg_id in sorted(
            (before_sgs if isinstance(before_sgs, set) else set())
            | (after_sgs if isinstance(after_sgs, set) else set())
        ):
            causes += [c for c in groups.changed_by.get(sg_id, []) if c not in causes]
        if resource.changed and (
            before_sgs != after_sgs or instance.public(_BEFORE) != instance.public(_AFTER)
        ):
            causes.append(resource)
        if not causes:
            continue
        before, after = _exposure(instance, _BEFORE, groups), _exposure(instance, _AFTER, groups)
        if isinstance(before, _Unknown) or isinstance(after, _Unknown):
            for cause in causes:
                changes.skip(
                    cause,
                    f"which ports {instance.name()} exposes is known only after apply",
                )
            continue
        assert isinstance(before, tuple) and isinstance(after, tuple)
        effects: list[str] = []
        touched: list[str] = []
        for asset_id in instance.asset_ids:
            network = changes.network(asset_id)
            if before[0] != after[0] and network.get("internet_facing") is not after[0]:
                effects.append(
                    f"{asset_id} internet_facing: {_shown(network.get('internet_facing'))} → {_shown(after[0])}"
                )
                network["internet_facing"] = after[0]
                touched.append(asset_id)
            listed = network.get("open_ports")
            opened, closed = after[1] - before[1], before[1] - after[1]
            if isinstance(listed, list) and (opened or closed):
                updated = sorted((set(listed) | opened) - closed)
                if updated != sorted(listed):
                    effects.append(f"{asset_id} open_ports: {sorted(listed)} → {updated}")
                    network["open_ports"] = updated
                    touched.append(asset_id)
        if effects:
            changes.model(
                causes, "exposure", "; ".join(effects), asset_ids=tuple(sorted(set(touched)))
            )
            continue
        if before[0] != after[0]:
            reason = (
                f"the baseline already records internet_facing={after[0]} for {instance.name()}"
            )
        else:
            reason = f"does not change whether {instance.name()} is internet-facing"
        if before[1] != after[1]:
            reason += " (its open ports change, but the baseline does not list open_ports)"
        for cause in causes:
            changes.settle(cause, reason)


def _apply_sg_findings(groups: _SecurityGroups, changes: _Changes, index: _AssetIndex) -> None:
    """A group whose last internet rule is removed passes every Prowler internet-ingress check."""
    for sg_id, causes in groups.changed_by.items():
        if not all(c.exists(_AFTER) for c in causes if c.type == "aws_security_group"):
            continue
        if groups.internet_open(_BEFORE, sg_id) is not True:
            continue
        if groups.internet_open(_AFTER, sg_id) is not False:
            continue
        arn = groups.arn.get(sg_id)
        fixed: list[str] = []
        for asset_id in index.resolve([arn, sg_id]):
            for finding in changes.open_findings(asset_id):
                finding_id = str(finding["finding_id"])
                internet_check = finding_id.startswith(f"prowler-{_SG_INTERNET_CHECK_PREFIX}")
                if internet_check and changes.remediate(asset_id, finding_id):
                    fixed.append(asset_id)
        if fixed:
            changes.model(
                causes,
                "finding",
                f"{sg_id} no longer admits the internet: its internet-ingress findings are remediated",
                asset_ids=tuple(sorted(set(fixed))),
            )


def _within(ip: str | None, cidrs: frozenset[str]) -> bool:
    if ip is None:
        return False
    address = ipaddress.ip_address(ip)
    for cidr in cidrs:
        try:
            if address in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _internal_edges(
    instances: list[_Instance], groups: _SecurityGroups, side: str
) -> set[tuple[str, str]] | _Unknown:
    """(source address, target address) pairs of instances whose groups let one reach the other."""
    present = [i for i in instances if i.resource.exists(side)]
    sgs: dict[str, set[str]] = {}
    for instance in present:
        value = instance.sg_ids(side)
        if not isinstance(value, set):
            return UNKNOWN
        sgs[instance.resource.address] = value
    edges: set[tuple[str, str]] = set()
    for target in present:
        rules = groups.rules_for(side, sgs[target.resource.address])
        if isinstance(rules, _Unknown):
            return UNKNOWN
        assert isinstance(rules, list)
        for source in present:
            if source is target:
                continue
            source_sgs = sgs[source.resource.address]
            for rule in rules:
                if (
                    _within(source.private_ip(side), rule.cidrs)
                    or rule.source_sgs & source_sgs
                    or (rule.self_reference and sgs[target.resource.address] & source_sgs)
                ):
                    edges.add((source.resource.address, target.resource.address))
                    break
    return edges


def _apply_topology_rules(
    baseline: dict[str, Any],
    instances: list[_Instance],
    groups: _SecurityGroups,
    changes: _Changes,
) -> None:
    """Changes in which instance can reach which inside the network, as segment pairs."""
    kept = [i for i in instances if i.resource.exists(_BEFORE) and i.resource.exists(_AFTER)]
    before, after = _internal_edges(kept, groups, _BEFORE), _internal_edges(kept, groups, _AFTER)
    if isinstance(before, _Unknown) or isinstance(after, _Unknown):
        return  # _apply_network_rules already reports the unknowns per instance.
    assert isinstance(before, set) and isinstance(after, set)
    if before == after:
        return
    by_address = {i.resource.address: i for i in kept}

    def causes_of(edge: tuple[str, str]) -> list[_Resource]:
        found: list[_Resource] = []
        for address in edge:
            instance = by_address[address]
            for side in (_BEFORE, _AFTER):
                sg_ids = instance.sg_ids(side)
                for sg_id in sorted(sg_ids) if isinstance(sg_ids, set) else []:
                    found += [c for c in groups.changed_by.get(sg_id, []) if c not in found]
            if instance.resource.changed:
                found.append(instance.resource)
        return found

    segment_of: dict[str, str] = {}
    for asset in baseline["assets"]:
        segment = (asset.get("network") or {}).get("segment_id")
        if segment:
            segment_of[asset["asset_id"]] = segment

    def segments(address: str) -> set[str]:
        return {segment_of[a] for a in by_address[address].asset_ids if a in segment_of}

    topology = baseline.get("network_topology")
    pairs: dict[str, set[tuple[str, str]]] = {_BEFORE: set(), _AFTER: set()}
    for side, edges in ((_BEFORE, before), (_AFTER, after)):
        for source, target in edges:
            for s in segments(source):
                for t in segments(target):
                    if s != t:
                        pairs[side].add((s, t))

    for edge in sorted(before ^ after):
        source, target = (by_address[a].name() for a in edge)
        verb = "may now reach" if edge in after else "can no longer reach"
        if topology is None or not segments(edge[0]) or not segments(edge[1]):
            for cause in causes_of(edge):
                changes.skip(
                    cause,
                    f"{source} {verb} {target} inside the network, but the baseline has no "
                    "network_topology segment for both, so internal reachability is not modelled",
                )

    added, removed = pairs[_AFTER] - pairs[_BEFORE], pairs[_BEFORE] - pairs[_AFTER]
    if topology is None or not (added or removed):
        for edge in sorted(before ^ after):
            if topology is not None and segments(edge[0]) and segments(edge[1]):
                for cause in causes_of(edge):
                    changes.settle(cause, "reachability changes only within one network segment")
        return
    current = {(p["from_segment_id"], p["to_segment_id"]) for p in topology["segment_reachability"]}
    updated = (current | added) - removed
    if updated == current:
        return
    changes.topology = {
        "segments": copy.deepcopy(topology["segments"]),
        "segment_reachability": [
            {"from_segment_id": s, "to_segment_id": t} for s, t in sorted(updated)
        ],
    }
    effects = [f"segment {s} → {t} added" for s, t in sorted(added - current)]
    effects += [f"segment {s} → {t} removed" for s, t in sorted(removed & current)]
    causes: list[_Resource] = []
    for edge in sorted(before ^ after):
        causes += [c for c in causes_of(edge) if c not in causes]
    changes.model(causes, "topology", "; ".join(effects), topology=True)


# ---------------------------------------------------------------------------
# IAM
# ---------------------------------------------------------------------------


def _is_admin_document(document: Any) -> bool | _Unknown:
    """Whether an IAM policy document allows every action on every resource."""
    if isinstance(document, _Unknown):
        return UNKNOWN
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except json.JSONDecodeError:
            return UNKNOWN
    statements = (document or {}).get("Statement") if isinstance(document, dict) else None
    if isinstance(statements, dict):
        statements = [statements]
    for statement in statements or []:
        if not isinstance(statement, dict) or statement.get("Effect") != "Allow":
            continue
        actions = statement.get("Action")
        resources = statement.get("Resource")
        actions = [actions] if isinstance(actions, str) else actions or []
        resources = [resources] if isinstance(resources, str) else resources or []
        if "*" in actions and "*" in resources:
            return True
    return False


class _Principals:
    """IAM roles and users in the plan: name -> ARN, and which exist on each side."""

    def __init__(self, resources: list[_Resource], account: str | None, partition: str) -> None:
        self.arns: dict[tuple[str, str], str] = {}
        self.resources: dict[tuple[str, str], _Resource] = {}
        for resource in resources:
            kind = {"aws_iam_role": "role", "aws_iam_user": "user"}.get(resource.type)
            if kind is None:
                continue
            for side in (_BEFORE, _AFTER):
                name = resource.get(side, "name")
                if not isinstance(name, str):
                    continue
                self.resources[(kind, name)] = resource
                arn = resource.get(side, "arn")
                if isinstance(arn, str):
                    self.arns[(kind, name)] = arn
                elif account and (kind, name) not in self.arns:
                    path = resource.get(side, "path")
                    path = path if isinstance(path, str) and path else "/"
                    self.arns[(kind, name)] = f"arn:{partition}:iam::{account}:{kind}{path}{name}"

    def arn(self, kind: str, name: str) -> str | None:
        return self.arns.get((kind, name))


def _attachment_targets(resource: _Resource, side: str) -> list[tuple[str, str]] | _Unknown:
    """(kind, name) principals an attachment/inline-policy resource applies to on a side."""
    if resource.type in ("aws_iam_role_policy_attachment", "aws_iam_role_policy"):
        keys = [("role", "role")]
    elif resource.type in ("aws_iam_user_policy_attachment", "aws_iam_user_policy"):
        keys = [("user", "user")]
    else:
        keys = [("role", "roles"), ("user", "users")]
    targets: list[tuple[str, str]] = []
    for kind, key in keys:
        value = resource.get(side, key)
        if isinstance(value, _Unknown):
            return UNKNOWN
        for name in [value] if isinstance(value, str) else value or []:
            targets.append((kind, str(name)))
    return targets


def _admin_grants(
    resources: list[_Resource], side: str
) -> tuple[dict[tuple[str, str, str], list[_Resource]], list[_Resource]]:
    """Admin grants on a side: (kind, name, check) -> granting resources; plus unreadable ones."""
    grants: dict[tuple[str, str, str], list[_Resource]] = {}
    unreadable: list[_Resource] = []
    for resource in resources:
        if not resource.exists(side):
            continue
        if resource.type.endswith("policy_attachment"):
            policy = resource.get(side, "policy_arn")
            admin: bool | _Unknown = (
                UNKNOWN
                if isinstance(policy, _Unknown)
                else bool(_ADMINISTRATOR_ACCESS.match(str(policy)))
            )
            inline = False
        elif resource.type in ("aws_iam_role_policy", "aws_iam_user_policy"):
            admin = _is_admin_document(resource.get(side, "policy"))
            inline = True
        else:
            continue
        targets = _attachment_targets(resource, side)
        if isinstance(admin, _Unknown) or isinstance(targets, _Unknown):
            unreadable.append(resource)
            continue
        if not admin:
            continue
        assert isinstance(targets, list)
        for kind, name in targets:
            check = (
                _INLINE_ADMIN_CHECK
                if inline
                else (_ROLE_ADMIN_CHECK if kind == "role" else _USER_ADMIN_CHECK)
            )
            grants.setdefault((kind, name, check), []).append(resource)
    return grants, unreadable


def _console_users(resources: list[_Resource], side: str) -> dict[str, list[_Resource]] | _Unknown:
    """Users with a console password on a side, and the login-profile resource(s) giving it."""
    users: dict[str, list[_Resource]] = {}
    for resource in resources:
        if resource.type != "aws_iam_user_login_profile" or not resource.exists(side):
            continue
        user = resource.get(side, "user")
        if isinstance(user, _Unknown):
            return UNKNOWN
        users.setdefault(str(user), []).append(resource)
    return users


def _mfa_users(resources: list[_Resource], side: str) -> set[str]:
    """Users a Terraform-managed virtual MFA device is enabled for on a side."""
    return {
        str(resource.get(side, "user_name"))
        for resource in resources
        if resource.type == "aws_iam_virtual_mfa_device"
        and resource.exists(side)
        and isinstance(resource.get(side, "user_name"), str)
        and resource.get(side, "user_name")
    }


def _principal_assets(
    principals: _Principals, index: _AssetIndex, kind: str, name: str
) -> tuple[list[str], str] | None:
    """Assets for a principal, and its ARN; a ``cloud:<arn>`` placeholder if none exists yet."""
    arn = principals.arn(kind, name)
    if arn is None:
        return None
    return index.resolve([arn]) or [f"cloud:{arn.lower()}"], arn


def _apply_iam_rules(
    resources: list[_Resource],
    principals: _Principals,
    changes: _Changes,
    index: _AssetIndex,
) -> None:
    iam = [r for r in resources if r.type in _IAM_TYPES]
    before, unreadable_before = _admin_grants(iam, _BEFORE)
    after, unreadable_after = _admin_grants(iam, _AFTER)
    for resource in unreadable_before + unreadable_after:
        if resource.changed:
            changes.skip(resource, "the policy or principal is known only after apply")

    for key in sorted(set(before) | set(after)):
        kind, name, check = key
        granted, revoked = key in after and key not in before, key in before and key not in after
        causes = [r for r in after.get(key, []) + before.get(key, []) if r.changed]
        if not (granted or revoked) or not causes:
            continue
        principal = principals.resources.get((kind, name))
        if revoked and principal is not None and not principal.exists(_AFTER):
            for cause in causes:
                changes.settle(cause, f"IAM {kind} {name!r} is itself deleted by this plan")
            continue
        resolved = _principal_assets(principals, index, kind, name)
        if resolved is None:
            for cause in causes:
                changes.skip(
                    cause, f"IAM {kind} {name!r} is not in this plan, so its ARN is unknown"
                )
            continue
        asset_ids, arn = resolved
        for asset_id in asset_ids:
            if granted:
                timestamp = changes.timestamp
                if changes.raise_finding(
                    asset_id, _prowler_finding(check, arn, causes[0].address, timestamp)
                ):
                    changes.model(
                        causes,
                        "finding",
                        f"{asset_id}: new open finding {check}",
                        asset_ids=(asset_id,),
                    )
                else:
                    for cause in causes:
                        changes.settle(cause, f"{asset_id} already has an open {check} finding")
            elif changes.remediate(asset_id, f"prowler-{check}-{arn}"):
                changes.model(
                    causes,
                    "finding",
                    f"{asset_id}: finding {check} remediated",
                    asset_ids=(asset_id,),
                )
            else:
                for cause in causes:
                    changes.settle(cause, f"{asset_id} has no open {check} finding to remediate")

    console_before, console_after = _console_users(iam, _BEFORE), _console_users(iam, _AFTER)
    mfa_before, mfa_after = _mfa_users(iam, _BEFORE), _mfa_users(iam, _AFTER)
    if isinstance(console_before, _Unknown) or isinstance(console_after, _Unknown):
        for resource in iam:
            if resource.type == "aws_iam_user_login_profile" and resource.changed:
                changes.skip(resource, "the user is known only after apply")
        return
    assert isinstance(console_before, dict) and isinstance(console_after, dict)
    for user in sorted(set(console_before) | set(console_after)):
        exposed_before = user in console_before and user not in mfa_before
        exposed_after = user in console_after and user not in mfa_after
        profiles = console_after.get(user, []) + console_before.get(user, [])
        devices = [
            r
            for r in iam
            if r.type == "aws_iam_virtual_mfa_device"
            and user in (r.get(_BEFORE, "user_name"), r.get(_AFTER, "user_name"))
        ]
        causes = [r for r in dict.fromkeys(profiles + devices) if r.changed]
        if exposed_before == exposed_after or not causes:
            continue
        principal = principals.resources.get(("user", user))
        if principal is not None and not principal.exists(_AFTER):
            for cause in causes:
                changes.settle(cause, f"IAM user {user!r} is itself deleted by this plan")
            continue
        resolved = _principal_assets(principals, index, "user", user)
        if resolved is None:
            for cause in causes:
                changes.skip(cause, f"IAM user {user!r} is not in this plan, so its ARN is unknown")
            continue
        asset_ids, arn = resolved
        check = _CONSOLE_WITHOUT_MFA_CHECK
        for asset_id in asset_ids:
            if exposed_after:
                finding = _prowler_finding(check, arn, causes[0].address, changes.timestamp)
                if changes.raise_finding(asset_id, finding):
                    changes.model(
                        causes,
                        "finding",
                        f"{asset_id}: new open finding {check} (console password, no Terraform-managed MFA device)",
                        asset_ids=(asset_id,),
                    )
                else:
                    for cause in causes:
                        changes.settle(cause, f"{asset_id} already has an open {check} finding")
            elif changes.remediate(asset_id, f"prowler-{check}-{arn}"):
                changes.model(
                    causes,
                    "finding",
                    f"{asset_id}: finding {check} remediated",
                    asset_ids=(asset_id,),
                )
            else:
                for cause in causes:
                    changes.settle(cause, f"{asset_id} has no open {check} finding to remediate")


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _Policy:
    resource: _Resource
    resource_types: frozenset[str]
    target_tags: dict[str, str]
    interval_hours: float | None


def _dlm_policies(resources: list[_Resource], side: str) -> list[_Policy] | _Unknown:
    policies: list[_Policy] = []
    for resource in resources:
        if resource.type != "aws_dlm_lifecycle_policy" or not resource.exists(side):
            continue
        state, details = resource.get(side, "state"), resource.get(side, "policy_details")
        if isinstance(state, _Unknown) or isinstance(details, _Unknown):
            return UNKNOWN
        if state != "ENABLED" or not details:
            continue
        detail = details[0]
        interval: float | None = None
        for schedule in detail.get("schedule") or []:
            for rule in schedule.get("create_rule") or []:
                if rule.get("interval") and str(rule.get("interval_unit", "HOURS")) == "HOURS":
                    hours = float(rule["interval"])
                    interval = hours if interval is None else min(interval, hours)
        policies.append(
            _Policy(
                resource=resource,
                resource_types=frozenset(detail.get("resource_types") or []),
                target_tags={str(k): str(v) for k, v in (detail.get("target_tags") or {}).items()},
                interval_hours=interval,
            )
        )
    return policies


def _volume_tags(
    resources: list[_Resource], instances: list[_Instance], side: str
) -> dict[str, dict[str, str]]:
    """Tags on each EBS volume on a side, from every resource that can set them."""
    tags: dict[str, dict[str, str]] = {}
    for instance in instances:
        if not instance.resource.exists(side):
            continue
        shared = instance.resource.get(side, "volume_tags")
        for key in ("root_block_device", "ebs_block_device"):
            blocks = instance.resource.get(side, key)
            for block in blocks if isinstance(blocks, list) else []:
                volume_id = block.get("volume_id")
                if volume_id:
                    merged = tags.setdefault(volume_id, {})
                    merged.update(shared if isinstance(shared, dict) else {})
                    merged.update(block.get("tags_all") or block.get("tags") or {})
    for resource in resources:
        if not resource.exists(side):
            continue
        if resource.type == "aws_ebs_volume":
            volume_id = resource.get(side, "id")
            if isinstance(volume_id, str):
                tags.setdefault(volume_id, {}).update(resource.get(side, "tags_all") or {})
        elif resource.type == "aws_ec2_tag":
            target, key, value = (resource.get(side, k) for k in ("resource_id", "key", "value"))
            if all(isinstance(v, str) for v in (target, key, value)):
                tags.setdefault(target, {})[key] = value
    return tags


def _covered(
    instance: _Instance,
    side: str,
    policies: list[_Policy],
    volume_tags: dict[str, dict[str, str]],
) -> list[_Policy]:
    """The enabled DLM policies that target this instance or one of its volumes on a side."""
    instance_tags = instance.resource.get(side, "tags_all")
    instance_tags = instance_tags if isinstance(instance_tags, dict) else {}
    covering: list[_Policy] = []
    for policy in policies:
        targets = set(policy.target_tags.items())
        if (
            "INSTANCE" in policy.resource_types
            and targets & set(instance_tags.items())
            or "VOLUME" in policy.resource_types
            and any(
                targets & set(volume_tags.get(volume_id, {}).items())
                for volume_id in instance.volume_ids(side)
            )
        ):
            covering.append(policy)
    return covering


def _apply_backup_rules(
    resources: list[_Resource], instances: list[_Instance], changes: _Changes
) -> None:
    backup_resources = [r for r in resources if r.type in _BACKUP_TYPES]
    if not any(r.changed for r in backup_resources) and not any(
        i.resource.changed for i in instances
    ):
        return
    policies = {side: _dlm_policies(resources, side) for side in (_BEFORE, _AFTER)}
    if any(isinstance(p, _Unknown) for p in policies.values()):
        for resource in backup_resources:
            if resource.type == "aws_dlm_lifecycle_policy" and resource.changed:
                changes.skip(resource, "the policy's targets are known only after apply")
        return
    tags = {side: _volume_tags(resources, instances, side) for side in (_BEFORE, _AFTER)}

    # Per service, each kept instance's covering policies on both sides. A
    # created or deleted instance is not compared: its asset is unscanned
    # or removed, which the other rules report.
    services: dict[str, list[tuple[_Instance, list[_Policy], list[_Policy]]]] = {}
    for instance in instances:
        kept = instance.resource.exists(_BEFORE) and instance.resource.exists(_AFTER)
        if not instance.asset_ids or not kept:
            continue
        before_policies, after_policies = policies[_BEFORE], policies[_AFTER]
        assert isinstance(before_policies, list) and isinstance(after_policies, list)
        cover = (
            instance,
            _covered(instance, _BEFORE, before_policies, tags[_BEFORE]),
            _covered(instance, _AFTER, after_policies, tags[_AFTER]),
        )
        for service_id in changes.services_of(instance.asset_ids):
            services.setdefault(service_id, []).append(cover)

    for service_id, covers in sorted(services.items()):
        before = any(cover_before for _, cover_before, _ in covers)
        after = any(cover_after for _, _, cover_after in covers)
        if before == after:
            continue
        volumes = {
            v for i, _, _ in covers for side in (_BEFORE, _AFTER) for v in i.volume_ids(side)
        }
        causes = [p.resource for _, b, a in covers for p in b + a if p.resource.changed]
        causes += [
            r
            for r in backup_resources
            if r.changed
            and r.type in ("aws_ec2_tag", "aws_ebs_volume")
            and {r.get(side, key) for side in (_BEFORE, _AFTER) for key in ("id", "resource_id")}
            & volumes
        ]
        causes += [i.resource for i, b, a in covers if i.resource.changed and bool(b) != bool(a)]
        causes = list(dict.fromkeys(causes))
        backup = changes.backup(service_id)
        if bool(backup.get("exists")) == after:
            for cause in causes:
                changes.settle(cause, f"{service_id} backup.exists is already {after}")
            continue
        if after:
            intervals = [p.interval_hours for _, _, a in covers for p in a if p.interval_hours]
            new_backup = {
                "exists": True,
                "last_tested_at": None,
                "rpo_hours": min(intervals) if intervals else None,
                "rto_hours": None,
                "immutable_copy": None,
            }
            effect = f"{service_id} backup.exists: false → true (untested snapshots)"
        else:
            new_backup = {
                "exists": False,
                "last_tested_at": None,
                "rpo_hours": None,
                "rto_hours": None,
                "immutable_copy": None,
            }
            effect = f"{service_id} backup.exists: true → false (no enabled DLM policy targets it)"
        backup.clear()
        backup.update(new_backup)
        changes.model(causes, "backup", effect, service_ids=(service_id,))


# ---------------------------------------------------------------------------
# Deletions, creations, everything else
# ---------------------------------------------------------------------------


def _apply_deletions(
    resources: list[_Resource],
    instances: list[_Instance],
    principals: _Principals,
    changes: _Changes,
    index: _AssetIndex,
) -> None:
    for instance in instances:
        resource = instance.resource
        if resource.action == "delete":
            if instance.asset_ids:
                changes.removed.update(instance.asset_ids)
                changes.model(
                    [resource],
                    "removal",
                    f"deleted: {', '.join(instance.asset_ids)} removed",
                    asset_ids=tuple(instance.asset_ids),
                )
            else:
                changes.settle(resource, "deleted, and no asset in the baseline matches it")
        elif resource.action == "replace" and instance.asset_ids:
            changes.settle(
                resource,
                "replaced: its asset keeps every finding (a rebuild from the same image is not a fix)",
            )
    for (kind, name), resource in sorted(principals.resources.items()):
        if resource.action != "delete":
            continue
        arn = principals.arn(kind, name)
        asset_ids = index.resolve([arn]) if arn else []
        if asset_ids:
            changes.removed.update(asset_ids)
            changes.model(
                [resource],
                "removal",
                f"deleted: {', '.join(asset_ids)} removed",
                asset_ids=tuple(asset_ids),
            )
        else:
            changes.settle(resource, f"deleted; the baseline has no asset for IAM {kind} {name!r}")
    for resource in resources:
        if resource.type != "aws_security_group" or resource.action != "delete":
            continue
        asset_ids = index.resolve([resource.get(_BEFORE, "arn"), resource.get(_BEFORE, "id")])
        if asset_ids:
            changes.removed.update(asset_ids)
            changes.model(
                [resource],
                "removal",
                f"deleted: {', '.join(asset_ids)} removed",
                asset_ids=tuple(asset_ids),
            )


def _settle_the_rest(resources: list[_Resource], changes: _Changes) -> None:
    """Every changed resource ends up modelled, no-effect or unmodelled — never silently dropped."""
    for resource in resources:
        if not resource.changed or resource.action == "read" or changes.accounted(resource):
            continue
        if resource.action == "create" and resource.type in _ASSET_TYPES:
            changes.skip(
                resource,
                "new resource: nothing has scanned it yet, so its risk is unknown (not zero); "
                "run `cypher ingest` after apply",
            )
        elif resource.type not in _HANDLED_TYPES:
            changes.skip(
                resource, f"no cypher rule for {resource.type}; its effect on risk is not modelled"
            )
        elif resource.type in _SG_RULE_TYPES:
            changes.skip(
                resource,
                "no instance in this plan that the baseline knows uses this security group "
                "(other resources, e.g. load balancers or databases, are not modelled)",
            )
        elif resource.type in _BACKUP_TYPES:
            changes.settle(
                resource, "does not change whether any baseline service's volumes are backed up"
            )
        else:
            changes.settle(resource, "changes nothing the risk engine reads")


def parse_plan(plan: dict[str, Any], baseline: dict[str, Any]) -> PlanTranslation:
    """Translate a Terraform plan into schema-shaped changes to ``baseline``.

    Args:
        plan: ``terraform show -json <planfile>`` output (see
            :func:`load_plan_file`, :func:`run_terraform_plan`).
        baseline: The committed, schema-shaped snapshot the plan will be
            compared against. Read only for identity (``endpoints[]``,
            asset ids), for the current value of each section a change
            edits, and for which findings are open.

    Returns:
        A :class:`PlanTranslation`. Every changed resource in the plan
        appears in ``modelled`` or ``unmodelled`` (a change can be partly
        both), or else once in ``no_effect`` — never nowhere.

    Must never:
        Produce, estimate or imply a rupee figure; report a created or
        unmatched resource as risk-free; or mark a finding remediated for
        any reason other than the plan removing its cause.
    """
    check_plan_document(plan, "plan")
    resources = _resources(plan)
    timestamp = str(plan.get("timestamp") or baseline["observed_at"])
    index = _AssetIndex(baseline)
    changes = _Changes(baseline, timestamp)
    account, partition = _account_and_partition(resources)

    instances = [
        _Instance(r, index.resolve(_instance_identifiers(r)) if r.exists(_BEFORE) else [])
        for r in resources
        if r.type == "aws_instance"
    ]
    groups = _SecurityGroups(resources)
    principals = _Principals(resources, account, partition)

    for resource in groups.unresolved:
        changes.skip(
            resource,
            "its security group is new, so which instances use it is known only after apply",
        )
    _apply_deletions(resources, instances, principals, changes, index)
    _apply_network_rules(instances, groups, changes)
    _apply_sg_findings(groups, changes, index)
    _apply_topology_rules(baseline, instances, groups, changes)
    _apply_iam_rules(resources, principals, changes, index)
    _apply_backup_rules(resources, instances, changes)
    for instance in instances:
        resource = instance.resource
        if (
            resource.exists(_BEFORE)
            and resource.changed
            and not instance.asset_ids
            and not changes.accounted(resource)
        ):
            changes.skip(resource, "no asset in the baseline snapshot matches this instance")
    _settle_the_rest(resources, changes)
    if plan.get("complete") is False:
        changes.unmodelled.append(
            SkippedChange("(plan)", "incomplete", "terraform deferred some changes to a later plan")
        )

    return PlanTranslation(
        asset_patches=changes.asset_patches(),
        service_patches=changes.service_patches(),
        removed_asset_ids=sorted(changes.removed),
        network_topology=changes.topology,
        modelled=changes.modelled,
        no_effect=changes.settled(),
        unmodelled=changes.unmodelled,
        terraform_version=str(plan.get("terraform_version", "")),
        plan_timestamp=plan.get("timestamp"),
    )
