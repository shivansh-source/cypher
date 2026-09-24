"""`riskctl` — command-line interface for Su₹aksha.

Every command here is a thin adapter over ``core/``, ``governance/``, and
``ai/`` — no command may contain risk-computation, compliance-mapping, or
LLM logic of its own.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

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
from infra.connectors.wazuh_connector import WazuhConnectorError
from interfaces._dotenv import load_dotenv

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
            typer.echo(
                f"applied {len(services)} manually-declared service(s) from {declared_path}"
            )
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


def build_cli() -> Any:
    """Construct the Typer application with all commands registered.

    Returns:
        A configured Typer app instance.
    """
    # Fills os.environ from the repo-root .env without overriding variables
    # the shell already set, so every command sees the same configuration.
    load_dotenv()
    app = typer.Typer()
    app.command("validate-snapshot")(validate_snapshot_command)
    app.command("run-engine")(run_engine_command)
    app.command("optimize")(optimize_command)
    app.command("framework-status")(framework_status_command)
    app.command("ingest")(ingest_command)
    return app
