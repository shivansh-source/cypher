"""`cypher` — command-line interface for Cypher.

Every command here is a thin adapter over ``core/``, ``governance/``, and
``ai/`` — no command may contain risk-computation, compliance-mapping, or
LLM logic of its own.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.declared_services import (
    DeclaredServicesError,
    apply_declared_services,
    load_declared_services,
)
from infra.connectors import (
    GreenboneConnector,
    IAMConnector,
    ProwlerConnector,
    ScoutSuiteConnector,
    WazuhConnector,
)
from infra.connectors._identity_resolution import (
    CandidateMerge,
    MergeDecision,
    cmdb_records_from_endpoints,
    decide_merge,
    find_candidate_merges,
    record_merge_decision,
    render_evidence_state,
)
from infra.connectors.cmdb_connector import CMDBConnector, CMDBConnectorError
from infra.connectors.greenbone_connector import GreenboneConnectorError
from infra.connectors.iam_connector import IAMConnectorError
from infra.connectors.prowler_connector import ProwlerConnectorError
from infra.connectors.scoutsuite_connector import ScoutSuiteConnectorError
from infra.connectors.terraform_plan import (
    CONNECTOR_NAME as TERRAFORM_PLAN_CONNECTOR,
)
from infra.connectors.terraform_plan import (
    PlanTranslation,
    TerraformPlanError,
    load_plan_file,
    parse_plan,
    run_terraform_plan,
)
from infra.connectors.wazuh_connector import WazuhConnectorError
from interfaces._dotenv import load_dotenv
from interfaces._snapshot_mirror import BUCKET_ENV, s3_source_from_env, sync_once

#: Default shape for ``assets[].edr`` when no connector contributed EDR data
#: for an asset — matches the schema's "no agent seen" reading rather than
#: silently implying the asset is protected. See ``ingest_command``'s
#: docstring for the full defaulting policy.
_DEFAULT_EDR: dict[str, Any] = {
    "agent_installed": False,
    "agent_healthy": None,
    "detection_rules_active": None,
    "recent_alerts": None,
}

#: Matches SNAPSHOT_STORE_PATH's default in .env.example.
_DEFAULT_SNAPSHOT_STORE_PATH = "./data/snapshots"

#: Matches ATTESTATION_STORE_PATH's default in .env.example.
_DEFAULT_ATTESTATION_STORE_PATH = "./data/attestations.json"

#: Where the versioned control library YAML files live.
_CONTROL_LIBRARY_DIR = Path(__file__).resolve().parents[2] / "governance" / "control_library"


def validate_snapshot_command(candidate_path: str) -> None:
    """CLI command: validate a candidate snapshot file against the 5 quality gates.

    Args:
        candidate_path: Path to a candidate aggregated-snapshot JSON file.

    Must never:
        Commit the candidate itself — this command only reports gate
        results, matching ``.claude/commands/validate-snapshot.md``.
    """
    from core.snapshot import validate_snapshot
    from core.snapshot_store import load_current_snapshot

    candidate = json.loads(Path(candidate_path).read_text())
    store_path = Path(os.environ.get("SNAPSHOT_STORE_PATH", _DEFAULT_SNAPSHOT_STORE_PATH))
    previous = load_current_snapshot(store_path)

    results = validate_snapshot(candidate, previous)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        typer.echo(f"[{status}] {result.gate_name}: {result.detail}")

    if all(result.passed for result in results):
        typer.echo("all gates passed")
    else:
        typer.echo("one or more gates failed; candidate would not be committed")


def run_engine_command(snapshot_path: str) -> None:
    """CLI command: run the engine against a committed snapshot file and print the risk figure.

    Args:
        snapshot_path: Path to a committed aggregated-snapshot JSON file.
    """
    from core.engine import compute_risk_figure

    snapshot = json.loads(Path(snapshot_path).read_text())
    risk_figure = compute_risk_figure(snapshot)

    typer.echo(f"snapshot_id: {risk_figure.snapshot_id}")
    typer.echo(f"expected_annual_loss_inr: {risk_figure.expected_annual_loss_inr:,.2f}")
    typer.echo(
        f"value_at_risk_inr (p{risk_figure.value_at_risk_percentile:.0%}): "
        f"{risk_figure.value_at_risk_inr:,.2f}"
    )
    typer.echo("top contributors:")
    for contributor in risk_figure.top_contributors:
        typer.echo(
            f"  {contributor.scenario_id}: {contributor.expected_annual_loss_inr:,.2f} INR "
            f"— {contributor.description}"
        )


def optimize_command(budget_inr: float, snapshot_path: str) -> None:
    """CLI command: run the optimizer against a committed snapshot and print the recommendation.

    Args:
        budget_inr: Total budget available, in INR.
        snapshot_path: Path to a committed aggregated-snapshot JSON file.
    """
    raise NotImplementedError


def framework_status_command(framework: str) -> None:
    """CLI command: print control-by-control status against a named regulatory framework.

    Args:
        framework: Framework key matching a filename under
            ``governance/control_library/``.
    """
    from core.snapshot_store import load_current_snapshot
    from governance.attestations import load_attestations
    from governance.library_loader import load_control_library
    from governance.mapper import compute_all_control_statuses

    store_path = Path(os.environ.get("SNAPSHOT_STORE_PATH", _DEFAULT_SNAPSHOT_STORE_PATH))
    snapshot = load_current_snapshot(store_path)
    if snapshot is None:
        typer.echo("no snapshot has been committed yet")
        raise typer.Exit(code=1)

    as_of = datetime.now(UTC)
    library = load_control_library(_CONTROL_LIBRARY_DIR / f"{framework}.yaml", as_of.date())
    attestation_store = Path(
        os.environ.get("ATTESTATION_STORE_PATH", _DEFAULT_ATTESTATION_STORE_PATH)
    )
    attestations = load_attestations(attestation_store)

    statuses = compute_all_control_statuses(snapshot, library, attestations, as_of)
    typer.echo(f"{library.framework} ({library.version})")
    for status in statuses:
        typer.echo(f"  [{status.status}] {status.control_id} (confidence={status.confidence})")


def _default_asset(asset_id: str) -> dict[str, Any]:
    """Build a schema-complete ``assets[]`` entry with every section defaulted empty.

    Args:
        asset_id: The resolved asset_id this entry belongs to.

    Returns:
        A dict with all of ``asset_id, findings, threat_intel, edr,
        identity_access, network`` present, per
        ``schema/aggregated_assets.schema.json``'s required fields:
        ``findings`` defaults to ``[]``, ``threat_intel``/``identity_access``/
        ``network`` default to ``{}``, and ``edr`` defaults to
        :data:`_DEFAULT_EDR` (agent not installed, nothing else known) —
        this is an explicit assumption that "no connector reported EDR data
        for this asset" means no agent was seen, not that its status is
        merely unreported.
    """
    return {
        "asset_id": asset_id,
        "findings": [],
        "threat_intel": {},
        "edr": dict(_DEFAULT_EDR),
        "identity_access": {},
        "network": {},
    }


#: Default path for the append-only identity-merge-decision store, used
#: when IDENTITY_RECONCILIATION_STORE_PATH is not set. Mirrors
#: SNAPSHOT_STORE_PATH's own default-under-data/ convention in
#: .env.example — operational configuration, not a modelling constant.
_DEFAULT_IDENTITY_RECONCILIATION_STORE_PATH = "./data/identity_reconciliation.json"


def _endpoints_from_cmdb_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reshape cmdb_connector.py's run() output into schema-shaped ``endpoints[]`` entries.

    cmdb_connector.py's fragments already carry ``endpoint_id``/
    ``address_type``/``address``/``resolved_asset_id`` (see its
    ``normalize()`` docstring); the extra ``asset_id`` key
    ``Connector.run()`` also attaches (identical to ``resolved_asset_id``)
    is dropped here rather than merged into ``assets[]`` — CMDB's output
    belongs in ``endpoints[]``, not ``assets[]`` (see
    ``cmdb_connector.py``'s module docstring on why).
    """
    return [
        {
            "endpoint_id": fragment["endpoint_id"],
            "address_type": fragment["address_type"],
            "address": fragment["address"],
            "resolved_asset_id": fragment["resolved_asset_id"],
        }
        for fragment in fragments
    ]


def _merge_asset_records(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Fold one asset record's sections into another, in place.

    Same field-by-field policy as :func:`_merge_connector_fragments`:
    findings are concatenated (never overwritten — a merged asset keeps
    every finding either id contributed), other sections use "last write
    wins".
    """
    target["findings"].extend(source["findings"])
    for section in ("edr", "threat_intel", "identity_access", "network"):
        if source.get(section):
            target[section] = source[section]


def _apply_identity_merges(
    assets: list[dict[str, Any]], decisions: list[MergeDecision]
) -> list[dict[str, Any]]:
    """Rewrite ``assets[]`` so every merged placeholder id is folded into its canonical id.

    Args:
        assets: The candidate snapshot's ``assets[]``, still keyed by
            whatever id each connector originally produced (placeholder or
            already-canonical).
        decisions: Every identity-resolution decision made this run.
            Non-merged decisions leave their placeholder asset untouched.

    Returns:
        A new ``assets[]`` list with every asset from a merged decision
        folded into its canonical asset's record (creating that record if
        nothing else already produced one under the canonical id — the
        common case, since CMDB's own output lives in ``endpoints[]``, not
        ``assets[]``).

    Must never:
        Drop a finding during a merge — every finding from the placeholder
        asset must survive into the merged canonical asset's findings list.
    """
    assets_by_id = {asset["asset_id"]: asset for asset in assets}
    merge_targets = {d.placeholder_asset_id: d.canonical_asset_id for d in decisions if d.merged}

    for placeholder_id, canonical_id in merge_targets.items():
        source = assets_by_id.pop(placeholder_id, None)
        if source is None:
            continue
        target = assets_by_id.setdefault(canonical_id, _default_asset(canonical_id))
        _merge_asset_records(target, source)

    return list(assets_by_id.values())


def _resolve_identities(
    assets: list[dict[str, Any]],
    endpoints: list[dict[str, Any]],
    fragments_by_connector: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[MergeDecision]]:
    """Reconcile placeholder asset ids against CMDB canonical identity, via Jev.

    For every (placeholder asset id, CMDB canonical asset) pair with shared
    evidence (``infra.connectors._identity_resolution.find_candidate_merges``),
    asks Jev (``ai.jev_transport``) whether they're the same real-world
    asset, and applies
    ``infra.connectors._identity_resolution.MERGE_CONFIDENCE_THRESHOLD`` to
    the answer.

    ``ai.jev_transport`` is imported here rather than in
    ``infra/connectors/`` because ``infra/connectors/`` may never import
    from ``ai/`` (see repo-root ``CLAUDE.md``'s module ownership map) —
    ``interfaces/`` is the layer allowed to bridge the two, exactly the
    reasoning :func:`ingest_command` already gives for importing
    ``core.snapshot`` here rather than in ``infra/``.

    Args:
        assets: The candidate snapshot's ``assets[]``, pre-identity-resolution.
        endpoints: The candidate snapshot's ``endpoints[]``
            (``cmdb_connector.py``'s output), used as the source of CMDB
            canonical identity records.
        fragments_by_connector: Every reachable connector's raw ``run()``
            output, used only to describe which connector observed each
            placeholder asset id in the evidence sent to Jev — never to
            special-case behavior (repo-root ``CLAUDE.md`` principle 3).

    Returns:
        The (possibly merged) ``assets[]`` list, and every
        :class:`~infra.connectors._identity_resolution.MergeDecision` made
        this run — merged or not — for the caller to persist.

    Must never:
        Merge a candidate whose Jev confidence could not be obtained (a
        ``JevProviderError`` for that one candidate) — it is left unmerged
        and undecided (no ``MergeDecision`` recorded for it) rather than
        defaulted either way; a transient provider failure must not
        silently resolve in either direction. Must never treat a
        predicted-False answer's own confidence as evidence *for* merging
        — see the inline comment below.
    """
    from ai.jev_transport import (
        JevConfigurationError,
        JevProviderError,
        TypedQuestion,
        get_jev_transport,
    )

    cmdb_records = cmdb_records_from_endpoints(endpoints)
    placeholder_source = {
        fragment["asset_id"]: connector_name
        for connector_name, fragments in fragments_by_connector.items()
        for fragment in fragments
    }
    candidates: list[CandidateMerge] = find_candidate_merges(placeholder_source, cmdb_records)
    if not candidates:
        return assets, []

    try:
        transport = get_jev_transport()
    except JevConfigurationError as exc:
        typer.echo(f"identity resolution skipped: {exc}")
        return assets, []

    decisions: list[MergeDecision] = []
    for candidate in candidates:
        state = render_evidence_state(candidate)
        question = TypedQuestion(
            id="same_asset",
            prompt=(
                "Given the evidence below, are the placeholder asset and the "
                "CMDB canonical asset the same real-world asset?"
            ),
            answer_type="bool",
        )
        try:
            [answer] = transport.classify(state, [question])
        except JevConfigurationError as exc:
            # The transport only checks its API key when first called, so a
            # missing key surfaces here rather than at get_jev_transport().
            # Keep any merges already decided; leave the rest undecided.
            typer.echo(f"identity resolution skipped: {exc}")
            break
        except JevProviderError as exc:
            typer.echo(
                f"identity resolution: Jev call failed for "
                f"{candidate.placeholder_asset_id} vs {candidate.canonical_asset_id}, "
                f"leaving unresolved: {exc}"
            )
            continue

        # TypedAnswer.confidence is "confidence in the predicted value" (see
        # ai.jev_transport.TypedAnswer's docstring), not p(true) directly —
        # so a confident "not the same asset" must never be read as
        # evidence FOR merging. Only a predicted True feeds decide_merge
        # with its own confidence; a predicted False is recorded as a
        # zero-confidence "not same asset" decision instead.
        confidence_for_merge = answer.confidence if answer.value is True else 0.0
        decision = decide_merge(candidate, confidence_for_merge, datetime.now(UTC))
        decisions.append(decision)

    return _apply_identity_merges(assets, decisions), decisions


def _merge_connector_fragments(
    fragments_by_connector: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge every connector's asset_id-attached fragments into full ``assets[]`` entries.

    Args:
        fragments_by_connector: Each reachable connector's ``name`` mapped
            to its ``Connector.run()`` output.

    Returns:
        A list of schema-shaped ``assets[]`` entries, one per distinct
        ``asset_id`` seen across all connectors. ``findings`` from every
        contributing fragment are concatenated (never overwritten, since a
        single asset can accumulate findings from more than one scanner).
        ``edr``/``threat_intel``/``identity_access``/``network`` are each
        taken from whichever fragment last supplied that section for the
        asset — in the current connector set this never actually
        conflicts, since only ``wazuh_connector`` populates ``edr`` and
        none of the four connectors wired into :func:`ingest_command`
        populate ``threat_intel``/``identity_access``/``network`` at all;
        this "last write wins" rule is documented here as the assumption to
        revisit once a connector that can conflict with another is added.

    Must never:
        Sum or otherwise combine two connectors' findings into one
        synthetic finding — every finding from every connector survives
        as its own entry in the merged ``findings`` list.
    """
    assets_by_id: dict[str, dict[str, Any]] = {}
    for fragments in fragments_by_connector.values():
        for fragment in fragments:
            asset_id: str = fragment["asset_id"]
            asset = assets_by_id.setdefault(asset_id, _default_asset(asset_id))
            if "findings" in fragment:
                asset["findings"].extend(fragment["findings"])
            if "edr" in fragment:
                asset["edr"] = fragment["edr"]
            if "threat_intel" in fragment:
                asset["threat_intel"] = fragment["threat_intel"]
            if "identity_access" in fragment:
                asset["identity_access"] = fragment["identity_access"]
            if "network" in fragment:
                asset["network"] = fragment["network"]
    return list(assets_by_id.values())


def ingest_command(commit: bool = True) -> None:
    """CLI command: run every implemented connector and assemble a candidate snapshot.

    Runs :class:`infra.connectors.WazuhConnector`,
    :class:`infra.connectors.GreenboneConnector`,
    :class:`infra.connectors.ProwlerConnector`,
    :class:`infra.connectors.ScoutSuiteConnector`, and
    :class:`infra.connectors.cmdb_connector.CMDBConnector`. Each
    connector's own exception type is caught individually so that one
    connector's failure never prevents the others from running: a failed
    connector's ``name`` is recorded under the candidate snapshot's
    ``scan_scope.unreachable_scanners``, a succeeded one under
    ``scan_scope.reachable_scanners``. No nmap connector exists yet, so the
    candidate's ``services`` is always an empty list (CMDBConnector
    normalizes identity data into ``endpoints[]`` only — see its own
    module docstring on why ``services[]`` normalization remains a
    documented gap).

    ``core.snapshot`` is imported here rather than in ``infra/`` because
    ``infra/connectors/`` may never import from ``core/`` (see repo-root
    ``CLAUDE.md``'s module ownership map) — ``interfaces/`` is the layer
    allowed to bridge the two, which is exactly why the commit call lives
    in this command rather than inside any connector's ``fetch()``. The
    same reasoning is why the Jev-based identity-resolution step
    (:func:`_resolve_identities`) lives here too, rather than in
    ``cmdb_connector.py``: ``infra/connectors/`` may also never import
    from ``ai/``.

    Args:
        commit: If True (default) and every quality gate passes, commit the
            candidate snapshot via ``core.snapshot.commit_snapshot``. If any
            gate fails, or ``commit`` is False, the candidate is never
            committed.

    Must never:
        Commit a candidate that failed any quality gate — this command
        must remain fail-safe, never fail-open, matching
        ``core/snapshot.py``'s own contract.
    """
    from core.snapshot import commit_snapshot, validate_snapshot
    from core.snapshot_store import load_current_snapshot, save_snapshot

    connectors: list[tuple[Any, type[Exception]]] = [
        (WazuhConnector(), WazuhConnectorError),
        (GreenboneConnector(), GreenboneConnectorError),
        (ProwlerConnector(), ProwlerConnectorError),
        (ScoutSuiteConnector(), ScoutSuiteConnectorError),
        (IAMConnector(), IAMConnectorError),
        (CMDBConnector(), CMDBConnectorError),
    ]

    reachable_scanners: list[str] = []
    unreachable_scanners: list[str] = []
    fragments_by_connector: dict[str, list[dict[str, Any]]] = {}

    for connector, error_type in connectors:
        try:
            fragments_by_connector[connector.name] = connector.run()
            reachable_scanners.append(connector.name)
        except error_type as exc:
            typer.echo(f"{connector.name} failed, recording as unreachable: {exc}")
            unreachable_scanners.append(connector.name)

    cmdb_fragments = fragments_by_connector.pop(CMDBConnector.name, [])
    endpoints = _endpoints_from_cmdb_fragments(cmdb_fragments)
    assets = _merge_connector_fragments(fragments_by_connector)

    assets, decisions = _resolve_identities(assets, endpoints, fragments_by_connector)
    if decisions:
        store_path = Path(
            os.environ.get(
                "IDENTITY_RECONCILIATION_STORE_PATH", _DEFAULT_IDENTITY_RECONCILIATION_STORE_PATH
            )
        )
        for decision in decisions:
            record_merge_decision(store_path, decision)
        merged_count = sum(1 for d in decisions if d.merged)
        typer.echo(
            f"identity resolution: {merged_count}/{len(decisions)} candidate merge(s) "
            f"applied, all decisions recorded to {store_path}"
        )

    services: list[dict[str, Any]] = []
    declared_path = os.environ.get("DECLARED_SERVICES_PATH")
    if declared_path:
        try:
            declared = load_declared_services(Path(declared_path))
        except DeclaredServicesError as exc:
            typer.echo(f"declared services not applied: {exc}")
        else:
            services, unmatched = apply_declared_services(declared, assets)
            typer.echo(f"applied {len(services)} manually-declared service(s) from {declared_path}")
            if unmatched:
                typer.echo(
                    "declared assets no connector observed this run (not created): "
                    + ", ".join(unmatched)
                )
    else:
        typer.echo("DECLARED_SERVICES_PATH not set; services[] left empty")

    now = datetime.now(UTC).isoformat()

    candidate: dict[str, Any] = {
        # Computed by commit_snapshot on success; left blank until then per
        # its own contract ("computed ... if not already set").
        "snapshot_id": "",
        "observed_at": now,
        "valid_from": now,
        "valid_to": None,
        "scan_scope": {
            "reachable_scanners": reachable_scanners,
            "unreachable_scanners": unreachable_scanners,
            "coverage": [],
        },
        "services": services,
        "assets": assets,
        "endpoints": endpoints,
    }

    store_path = Path(os.environ.get("SNAPSHOT_STORE_PATH", _DEFAULT_SNAPSHOT_STORE_PATH))
    previous = load_current_snapshot(store_path)

    gate_results = validate_snapshot(candidate, previous)
    failed_gates = [gate for gate in gate_results if not gate.passed]
    if failed_gates:
        for gate in failed_gates:
            typer.echo(f"gate failed: {gate.gate_name}: {gate.detail}")
        typer.echo("candidate snapshot not committed")
        return

    if not commit:
        typer.echo("all quality gates passed; not committing (commit=False)")
        return

    committed = commit_snapshot(candidate, previous)
    save_snapshot(store_path, committed)
    typer.echo(f"candidate snapshot committed: {committed['snapshot_id']}")


# ---------------------------------------------------------------------------
# cypher plan
# ---------------------------------------------------------------------------

#: Relative size of a per-scenario change below which it counts as no
#: change (floating-point noise from reordered sums). A numerical
#: tolerance, not a modelling judgement.
_SCENARIO_CHANGE_TOLERANCE = 1e-9

#: How many changed loss scenarios the text report lists (``--json`` lists
#: all). Display only.
_REPORT_SCENARIO_LIMIT = 10

#: Modelled-change kinds that move attack-graph inputs (internet exposure,
#: segment reachability) and so can change loss on assets they do not name.
_REACHABILITY_KINDS = ("exposure", "topology")

#: Exit code when ``--fail-on-eal-increase`` is exceeded; 1 is kept for
#: errors (no baseline, unreadable plan, failed quality gate).
_EXIT_THRESHOLD_EXCEEDED = 2


def _overlay_asset_patch(target: dict[str, Any], patch: dict[str, Any]) -> None:
    """Apply one plan fragment to an asset record, in place.

    Sections follow :func:`_merge_asset_records` (last write wins). Findings
    differ in one way: a fragment's finding *replaces* the asset's finding
    with the same ``finding_id`` instead of being appended beside it, since
    a plan fragment re-states a known finding (e.g. with ``remediated_at``
    set) rather than reporting a second one.
    """
    positions = {finding["finding_id"]: i for i, finding in enumerate(target["findings"])}
    for finding in patch.get("findings", []):
        if finding["finding_id"] in positions:
            target["findings"][positions[finding["finding_id"]]] = copy.deepcopy(finding)
        else:
            target["findings"].append(copy.deepcopy(finding))
    _merge_asset_records(target, {**copy.deepcopy(patch), "findings": []})


def _build_proposed_snapshot(
    baseline: dict[str, Any], translation: PlanTranslation
) -> dict[str, Any]:
    """The baseline as it would be after the plan: a copy with the plan's changes overlaid.

    Removed assets (and the ``endpoints[]`` resolving to them) are dropped,
    asset and service fragments are overlaid, ``network_topology`` is
    replaced if the plan changes it, and ``terraform_plan`` joins
    ``scan_scope.reachable_scanners`` as the provenance of any finding the
    plan raises. The result gets a ``hypothetical:`` id, never a
    ``sha256:`` one, and is never committed or saved.

    Must never:
        Mutate ``baseline``.
    """
    proposed = copy.deepcopy(baseline)
    removed = set(translation.removed_asset_ids)
    assets = {a["asset_id"]: a for a in proposed["assets"] if a["asset_id"] not in removed}
    for patch in translation.asset_patches:
        asset = assets.setdefault(patch["asset_id"], _default_asset(patch["asset_id"]))
        _overlay_asset_patch(asset, patch)
    proposed["assets"] = list(assets.values())
    proposed["endpoints"] = [
        e for e in proposed["endpoints"] if e.get("resolved_asset_id") not in removed
    ]
    services = {service["service_id"]: service for service in proposed["services"]}
    for service_patch in translation.service_patches:
        services[service_patch["service_id"]]["backup"] = copy.deepcopy(service_patch["backup"])
    if translation.network_topology is not None:
        proposed["network_topology"] = copy.deepcopy(translation.network_topology)
    reachable = proposed["scan_scope"]["reachable_scanners"]
    if TERRAFORM_PLAN_CONNECTOR not in reachable:
        reachable.append(TERRAFORM_PLAN_CONNECTOR)
    proposed["snapshot_id"] = ""
    content = json.dumps(proposed, sort_keys=True, default=str).encode("utf-8")
    proposed["snapshot_id"] = f"hypothetical:{hashlib.sha256(content).hexdigest()}"
    return proposed


#: One lakh and one crore, for the short form of a rupee amount. Units, not
#: modelling constants.
_LAKH = 100_000
_CRORE = 10_000_000

#: Width the report is laid out at when stdout is not a terminal (CI logs,
#: pipes), so long ARNs and snapshot ids are not folded mid-token. Display only.
_NON_TERMINAL_WIDTH = 140

#: Colour per Terraform action in the report. Display only.
_ACTION_STYLE = {
    "create": "green",
    "update": "yellow",
    "delete": "red",
    "replace": "magenta",
}


def _indian_grouping(whole: int) -> str:
    """``10891328`` -> ``1,08,91,328``: the last three digits, then pairs."""
    digits = str(whole)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *pairs, tail])


def _inr(amount: float, *, signed: bool = False) -> str:
    """A rupee amount for display, to the whole rupee, grouped the Indian way.

    Display rounding only: ``--json`` carries the engine's figures unrounded.
    """
    sign = ("+" if amount > 0 else "-" if amount < 0 else "±") if signed else ""
    return f"{sign}₹{_indian_grouping(round(abs(amount)))}"


def _inr_short(amount: float) -> str:
    """``₹3.13 Cr`` / ``₹11.58 L`` / ``₹9,500`` — the magnitude at a glance."""
    size = abs(amount)
    if size >= _CRORE:
        return f"₹{size / _CRORE:,.2f} Cr"
    if size >= _LAKH:
        return f"₹{size / _LAKH:,.2f} L"
    return _inr(size)


def _age(observed_at: str, now: datetime) -> str:
    observed = datetime.fromisoformat(observed_at)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    hours = (now - observed).total_seconds() / 3600
    return f"{hours:.1f} hours ago" if hours < 48 else f"{hours / 24:.1f} days ago"


@dataclass(frozen=True)
class BaselineSource:
    """Where ``cypher plan``'s baseline snapshot came from.

    Attributes:
        kind: ``"s3"`` (the published store, mirrored locally first), ``"local"``
            (``SNAPSHOT_STORE_PATH`` as it is), or ``"file"`` (``--snapshot``).
        location: The S3 URI, store directory or file it was read from.
        refreshed: True if the local store was just brought up to date from S3.
        warning: Why a refresh from S3 failed, if it did; the baseline is then the
            local copy, however old (its age is in the report).
    """

    kind: str
    location: str
    refreshed: bool = False
    warning: str | None = None


def _resolve_baseline(
    snapshot_file: Path | None, offline: bool
) -> tuple[dict[str, Any] | None, BaselineSource]:
    """Find ``cypher plan``'s baseline: ``--snapshot``, else S3 mirrored locally, else local.

    With ``SNAPSHOT_S3_BUCKET`` set (and not ``--offline``), the published snapshot store
    is mirrored into ``SNAPSHOT_STORE_PATH`` first (``interfaces._snapshot_mirror.sync_once``:
    download-only, history never rewritten, ``current.json`` replaced by the published one),
    then read from there. A failed refresh falls back to the local copy with a warning.

    Returns:
        The baseline (None if there is none anywhere) and where it came from.
    """
    from core.snapshot_store import load_current_snapshot

    if snapshot_file is not None:
        try:
            snapshot = json.loads(snapshot_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            typer.echo(f"cannot read --snapshot {snapshot_file}: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        return snapshot, BaselineSource("file", str(snapshot_file))

    store_path = Path(os.environ.get("SNAPSHOT_STORE_PATH", _DEFAULT_SNAPSHOT_STORE_PATH))
    s3 = None if offline else s3_source_from_env()
    if s3 is None:
        return load_current_snapshot(store_path), BaselineSource("local", str(store_path))

    bucket, prefix = s3
    location = f"s3://{bucket}/{prefix}"
    try:
        sync_once(bucket, prefix, store_path)
    except Exception as exc:  # noqa: BLE001 - any S3/credential/network failure falls back
        warning = (
            f"{type(exc).__name__}: {exc}. Using the local copy in {store_path}; "
            "check AWS credentials for the bucket, or pass --offline to skip S3."
        )
        return load_current_snapshot(store_path), BaselineSource(
            "local", str(store_path), warning=warning
        )
    return load_current_snapshot(store_path), BaselineSource("s3", location, refreshed=True)


def _plan_report(
    baseline: dict[str, Any],
    proposed: dict[str, Any],
    translation: PlanTranslation,
    comparison: Any,
    fail_on_eal_increase: float | None,
    source: BaselineSource,
) -> dict[str, Any]:
    """Everything ``cypher plan`` reports, as JSON-ready data (text output renders this).

    Per-scenario changes are the difference of each scenario's own
    contribution in the two joint simulations (read off their
    ``top_contributors``), never summed into the headline change, which is
    the difference of the two headline figures.
    """
    before = {c.scenario_id: c for c in comparison.baseline_risk_figure.top_contributors}
    after = {c.scenario_id: c for c in comparison.proposed_risk_figure.top_contributors}
    tolerance = _SCENARIO_CHANGE_TOLERANCE * max(
        comparison.baseline_risk_figure.expected_annual_loss_inr, 1.0
    )
    services_of = {
        a["asset_id"]: set(a.get("service_ids") or [])
        for a in baseline["assets"] + proposed["assets"]
    }
    reachability_causes = sorted(
        {m.address for m in translation.modelled if m.kind in _REACHABILITY_KINDS}
    )

    scenario_changes: list[dict[str, Any]] = []
    for scenario_id in sorted(set(before) | set(after)):
        old = before[scenario_id].expected_annual_loss_inr if scenario_id in before else 0.0
        new = after[scenario_id].expected_annual_loss_inr if scenario_id in after else 0.0
        if abs(new - old) <= tolerance:
            continue
        contribution = after.get(scenario_id) or before[scenario_id]
        asset_id = contribution.asset_id
        caused_by = sorted(
            {
                m.address
                for m in translation.modelled
                if asset_id in m.asset_ids or services_of.get(asset_id, set()) & set(m.service_ids)
            }
        )
        scenario_changes.append(
            {
                "scenario_id": scenario_id,
                "asset_id": asset_id,
                "description": contribution.description,
                "baseline_expected_annual_loss_inr": old,
                "proposed_expected_annual_loss_inr": new,
                "change_inr": new - old,
                "caused_by": caused_by or reachability_causes,
                "indirect": not caused_by,
            }
        )
    scenario_changes.sort(key=lambda change: abs(change["change_inr"]), reverse=True)

    change = comparison.expected_annual_loss_change_inr
    return {
        "baseline": {
            "snapshot_id": baseline["snapshot_id"],
            "observed_at": baseline["observed_at"],
            "source": asdict(source),
            "expected_annual_loss_inr": comparison.baseline_risk_figure.expected_annual_loss_inr,
            "value_at_risk_inr": comparison.baseline_risk_figure.value_at_risk_inr,
        },
        "proposed": {
            "snapshot_id": proposed["snapshot_id"],
            "expected_annual_loss_inr": comparison.proposed_risk_figure.expected_annual_loss_inr,
            "value_at_risk_inr": comparison.proposed_risk_figure.value_at_risk_inr,
        },
        "value_at_risk_percentile": comparison.baseline_risk_figure.value_at_risk_percentile,
        "change": {
            "expected_annual_loss_inr": change,
            "value_at_risk_inr": comparison.value_at_risk_change_inr,
            "covers_every_change": not translation.unmodelled,
        },
        "terraform": {
            "version": translation.terraform_version,
            "plan_timestamp": translation.plan_timestamp,
        },
        "scenario_changes": scenario_changes,
        "modelled": [asdict(m) for m in translation.modelled],
        "unmodelled": [asdict(u) for u in translation.unmodelled],
        "no_effect": [asdict(n) for n in translation.no_effect],
        "threshold": {
            "fail_on_eal_increase_inr": fail_on_eal_increase,
            "exceeded": fail_on_eal_increase is not None and change > fail_on_eal_increase,
        },
    }


def _change_text(amount: float, baseline: float, *, partial: bool) -> Text:
    """A coloured change: red up-arrow for more loss, green down-arrow for less."""
    if amount > 0:
        arrow, style = "▲ ", "bold red"
    elif amount < 0:
        arrow, style = "▼ ", "bold green"
    else:
        arrow, style = "", "dim"
    text = Text(f"{arrow}{_inr(amount, signed=True)}", style=style)
    if amount and baseline:
        text.append(f"  {amount / baseline:+.0%}", style=style.replace("bold ", ""))
    if partial:
        text.append(" *", style="yellow")
    return text


def _action_text(action: str) -> Text:
    return Text(action, style=_ACTION_STYLE.get(action, "cyan"))


def _plan_report_renderables(report: dict[str, Any], now: datetime) -> list[RenderableType]:
    """The human-readable form of :func:`_plan_report`'s output, as rich renderables.

    Every piece of text from the plan or the snapshot is passed as
    :class:`rich.text.Text`, never as markup, so a Terraform address such as
    ``aws_instance.web[0]`` is printed as-is.
    """
    baseline, proposed, change = report["baseline"], report["proposed"], report["change"]
    unmodelled = report["unmodelled"]
    nothing_modelled = not report["modelled"] and bool(unmodelled)
    partial = bool(unmodelled) and not nothing_modelled
    out: list[RenderableType] = []

    header = Table.grid(padding=(0, 2))
    header.add_column(style="bold")
    header.add_column()
    header.add_row("Baseline", Text(baseline["snapshot_id"]))
    header.add_row(
        "Observed",
        Text.assemble(
            baseline["observed_at"],
            (f"  ({_age(baseline['observed_at'], now)})", "dim"),
        ),
    )
    source = baseline["source"]
    note = {
        "s3": "refreshed now",
        "file": "--snapshot",
        "local": "local store, not refreshed",
    }[source["kind"]]
    header.add_row(
        "Source",
        Text.assemble(source["location"], (f"  ({note})", "dim")),
    )
    header.add_row(
        "Plan",
        Text(
            f"terraform {report['terraform']['version'] or '?'}, "
            f"made {report['terraform']['plan_timestamp'] or '?'}"
        ),
    )
    out.append(
        Panel(
            Group(
                Text("Change in modelled cyber risk if this Terraform plan is applied\n"),
                header,
                Text(
                    "\nFigures are only as current as the last `cypher ingest`.",
                    style="dim italic",
                ),
            ),
            title="[bold]cypher plan[/bold]",
            title_align="left",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    if source["warning"]:
        out.append(
            Panel(
                Text(source["warning"]),
                title="[bold yellow]Could not refresh the baseline from S3[/bold yellow]",
                title_align="left",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

    figures = Table(box=box.SIMPLE_HEAVY, show_edge=False, pad_edge=False)
    figures.add_column("")
    figures.add_column("Baseline", justify="right")
    figures.add_column("Proposed", justify="right")
    figures.add_column("Change", justify="right")
    percentile = f"p{report['value_at_risk_percentile'] * 100:.0f}"
    for label, key in (
        ("Expected Annual Loss", "expected_annual_loss_inr"),
        (f"Value at Risk ({percentile})", "value_at_risk_inr"),
    ):
        delta = (
            Text("unknown", style="bold yellow")
            if nothing_modelled
            else _change_text(change[key], baseline[key], partial=partial)
        )
        figures.add_row(
            Text(label, style="bold"),
            Text(_inr(baseline[key])),
            Text(_inr(proposed[key])),
            delta,
        )
    out.append(figures)
    if nothing_modelled:
        out.append(
            Text(
                "Nothing in this plan could be modelled, so its effect on risk is "
                "unknown, not zero.",
                style="yellow",
            )
        )
    elif partial:
        out.append(
            Text(
                f"* Covers the modelled changes only. {len(unmodelled)} change(s) could not "
                "be modelled: their risk is unknown, not zero.",
                style="yellow",
            )
        )

    scenarios = report["scenario_changes"]
    if scenarios:
        table = Table(
            title="Loss scenarios that moved (largest first)",
            title_style="bold",
            title_justify="left",
            box=box.SIMPLE,
            show_header=False,
            show_edge=False,
            pad_edge=False,
            expand=True,
        )
        table.add_column(justify="right", no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for item in scenarios[:_REPORT_SCENARIO_LIMIT]:
            amounts = _change_text(item["change_inr"], 0.0, partial=False)
            amounts.append(
                f"\n{_inr_short(item['baseline_expected_annual_loss_inr'])} → "
                f"{_inr_short(item['proposed_expected_annual_loss_inr'])}",
                style="dim",
            )
            detail = Text(item["asset_id"], style="bold")
            detail.append("\n" + item["description"], style="dim")
            detail.append("\ncaused by ", style="italic")
            if item["indirect"]:
                detail.append("(indirectly, via attack-graph reachability) ", style="italic")
            detail.append(
                ", ".join(item["caused_by"]) or "(no single Terraform change)", style="cyan"
            )
            table.add_row(amounts, detail)
        out.append(table)
        hidden = len(scenarios) - _REPORT_SCENARIO_LIMIT
        if hidden > 0:
            out.append(Text(f"… and {hidden} more (use --json to see all)", style="dim"))

    if report["modelled"]:
        table = Table(
            title="Terraform changes in the model",
            title_style="bold",
            title_justify="left",
            box=box.SIMPLE,
            show_header=False,
            show_edge=False,
            pad_edge=False,
            expand=True,
        )
        table.add_column(no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for entry in report["modelled"]:
            table.add_row(
                _action_text(entry["action"]),
                Text(entry["address"], style="bold") + Text("\n" + entry["effect"]),
            )
        out.append(table)

    if unmodelled:
        table = Table(box=None, show_header=False, pad_edge=False, expand=True)
        table.add_column(no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for entry in unmodelled:
            table.add_row(
                _action_text(entry["action"]),
                Text(entry["address"], style="bold") + Text("\n" + entry["reason"]),
            )
        out.append(
            Panel(
                table,
                title="[bold yellow]Not modelled: risk unknown, not zero[/bold yellow]",
                title_align="left",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

    if report["no_effect"]:
        table = Table(
            title="Evaluated, no modelled effect",
            title_style="dim bold",
            title_justify="left",
            box=None,
            show_header=False,
            pad_edge=False,
            expand=True,
        )
        table.add_column(no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for entry in report["no_effect"]:
            table.add_row(
                _action_text(entry["action"]),
                Text(entry["address"], style="dim") + Text("  " + entry["reason"], style="dim"),
            )
        out.append(table)

    threshold = report["threshold"]
    if threshold["fail_on_eal_increase_inr"] is not None:
        limit = _inr(threshold["fail_on_eal_increase_inr"])
        if threshold["exceeded"]:
            verdict = Text(
                f"✗ Expected Annual Loss rises by more than {limit} (--fail-on-eal-increase): exit 2",
                style="bold red",
            )
        else:
            verdict = Text(f"✓ Within --fail-on-eal-increase {limit}", style="bold green")
            if unmodelled:
                verdict.append(
                    f" (modelled changes only; {len(unmodelled)} not modelled)", style="yellow"
                )
        out.append(verdict)
    return out


def _print_plan_report(report: dict[str, Any], now: datetime) -> None:
    """Print the report to stdout: coloured on a terminal, plain and wide when piped."""
    console = Console(highlight=False, emoji=False)
    if not console.is_terminal:
        console = Console(highlight=False, emoji=False, width=_NON_TERMINAL_WIDTH)
    for renderable in _plan_report_renderables(report, now):
        console.print(renderable)
        console.print()


def plan_command(
    plan_path: Annotated[
        Path | None,
        typer.Argument(help="`terraform show -json <planfile>` output. Omit when using --dir."),
    ] = None,
    directory: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            help="Run `terraform plan` and `terraform show -json` in this directory instead.",
        ),
    ] = None,
    fail_on_eal_increase: Annotated[
        float | None,
        typer.Option(
            "--fail-on-eal-increase",
            metavar="INR",
            help="Exit 2 if the plan raises Expected Annual Loss by more than this many rupees.",
        ),
    ] = None,
    json_out: Annotated[
        bool, typer.Option("--json", help="Print a machine-readable report (for CI).")
    ] = False,
    snapshot_file: Annotated[
        Path | None,
        typer.Option(
            "--snapshot",
            help="Use this snapshot JSON as the baseline instead of the snapshot store.",
        ),
    ] = None,
    offline: Annotated[
        bool,
        typer.Option(
            "--offline",
            help="Do not refresh the snapshot store from S3; use the local copy as it is.",
        ),
    ] = False,
) -> None:
    """CLI command: what a Terraform plan would change in modelled cyber risk, before apply.

    Loads the current committed snapshot as the baseline (refreshed from the
    S3-published store first when ``SNAPSHOT_S3_BUCKET`` is set; see
    :func:`_resolve_baseline`), translates the
    plan into schema-shaped changes (``infra.connectors.terraform_plan``),
    overlays them on a copy of the baseline, checks the result against the
    same quality gates a committed snapshot passes, and re-simulates both
    jointly on the same random draws (``core.optimizer.compare_snapshots``).
    Reports both figures and the change, which loss scenarios moved and
    which Terraform address moved them, and every change that could not be
    modelled.

    Exit codes: 0 report printed; 1 no committed snapshot, unreadable plan,
    or a proposed snapshot that fails a quality gate; 2 the Expected Annual
    Loss increase is above ``--fail-on-eal-increase``.

    Must never:
        Produce a figure without a committed baseline (it exits instead —
        principle 1), commit or save the proposed snapshot, or present an
        unmodelled change as a zero change.
    """
    from core.optimizer import compare_snapshots
    from core.snapshot import validate_snapshot

    if (plan_path is None) == (directory is None):
        typer.echo("give exactly one of PLAN_PATH or --dir", err=True)
        raise typer.Exit(code=1)

    baseline, source = _resolve_baseline(snapshot_file, offline)
    if baseline is None:
        if source.warning:
            typer.echo(f"could not refresh the baseline from S3: {source.warning}", err=True)
        hint = (
            ""
            if source.warning or s3_source_from_env()
            else f" (or set {BUCKET_ENV} to fetch the published snapshot from S3)"
        )
        typer.echo(
            f"no committed snapshot in {source.location}: run `cypher ingest` first{hint}. "
            "cypher plan compares against a real baseline and never estimates one.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        plan = load_plan_file(plan_path) if plan_path is not None else None
        if plan is None:
            assert directory is not None
            plan = run_terraform_plan(directory)
        translation = parse_plan(plan, baseline)
    except TerraformPlanError as exc:
        typer.echo(f"cannot read the plan: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    proposed = _build_proposed_snapshot(baseline, translation)
    failed = [gate for gate in validate_snapshot(proposed, baseline) if not gate.passed]
    if failed:
        for gate in failed:
            typer.echo(f"proposed snapshot fails gate {gate.gate_name}: {gate.detail}", err=True)
        typer.echo("not simulated: the engine only runs on gate-passing snapshots", err=True)
        raise typer.Exit(code=1)

    comparison = compare_snapshots(baseline, proposed)
    report = _plan_report(baseline, proposed, translation, comparison, fail_on_eal_increase, source)
    if json_out:
        typer.echo(json.dumps(report, indent=2))
    else:
        _print_plan_report(report, datetime.now(UTC))
    if report["threshold"]["exceeded"]:
        raise typer.Exit(code=_EXIT_THRESHOLD_EXCEEDED)


def build_cli() -> Any:
    """Construct the Typer application with all commands registered.

    Returns:
        A configured Typer app instance.
    """
    # Fills os.environ from the repo-root .env without overriding variables
    # the shell already set, so every command sees the same configuration.
    load_dotenv()
    app = typer.Typer(
        name="cypher",
        help="Cypher: security telemetry to rupee-denominated cyber risk (Open FAIR + Monte Carlo).",
        no_args_is_help=True,
    )
    app.command("validate-snapshot")(validate_snapshot_command)
    app.command("run-engine")(run_engine_command)
    app.command("optimize")(optimize_command)
    app.command("framework-status")(framework_status_command)
    app.command("ingest")(ingest_command)
    app.command("plan")(plan_command)
    return app


def main() -> None:
    """Console entry point: ``cypher <command>`` (see ``[project.scripts]``)."""
    build_cli()()


if __name__ == "__main__":
    main()
