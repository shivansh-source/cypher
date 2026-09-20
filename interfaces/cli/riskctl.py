"""`riskctl` — command-line interface for Su₹aksha.

Every command here is a thin adapter over ``core/``, ``governance/``, and
``ai/`` — no command may contain risk-computation, compliance-mapping, or
LLM logic of its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import typer

from infra.connectors import (
    GreenboneConnector,
    ProwlerConnector,
    ScoutSuiteConnector,
    WazuhConnector,
)
from infra.connectors.greenbone_connector import GreenboneConnectorError
from infra.connectors.prowler_connector import ProwlerConnectorError
from infra.connectors.scoutsuite_connector import ScoutSuiteConnectorError
from infra.connectors.wazuh_connector import WazuhConnectorError

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


def validate_snapshot_command(candidate_path: str) -> None:
    """CLI command: validate a candidate snapshot file against the 5 quality gates.

    Args:
        candidate_path: Path to a candidate aggregated-snapshot JSON file.

    Must never:
        Commit the candidate itself — this command only reports gate
        results, matching ``.claude/commands/validate-snapshot.md``.
    """
    raise NotImplementedError


def run_engine_command(snapshot_path: str) -> None:
    """CLI command: run the engine against a committed snapshot file and print the risk figure.

    Args:
        snapshot_path: Path to a committed aggregated-snapshot JSON file.
    """
    raise NotImplementedError


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
    raise NotImplementedError


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
    :class:`infra.connectors.ProwlerConnector`, and
    :class:`infra.connectors.ScoutSuiteConnector`. Each connector's own
    exception type is caught individually so that one connector's failure
    never prevents the others from running: a failed connector's ``name``
    is recorded under the candidate snapshot's
    ``scan_scope.unreachable_scanners``, a succeeded one under
    ``scan_scope.reachable_scanners``. No CMDB/nmap connector exists yet,
    so the candidate's ``services``/``endpoints`` are always empty lists.

    ``core.snapshot`` is imported here rather than in ``infra/`` because
    ``infra/connectors/`` may never import from ``core/`` (see repo-root
    ``CLAUDE.md``'s module ownership map) — ``interfaces/`` is the layer
    allowed to bridge the two, which is exactly why the commit call lives
    in this command rather than inside any connector's ``fetch()``.

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

    connectors: list[tuple[Any, type[Exception]]] = [
        (WazuhConnector(), WazuhConnectorError),
        (GreenboneConnector(), GreenboneConnectorError),
        (ProwlerConnector(), ProwlerConnectorError),
        (ScoutSuiteConnector(), ScoutSuiteConnectorError),
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

    assets = _merge_connector_fragments(fragments_by_connector)
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
        "services": [],
        "assets": assets,
        "endpoints": [],
    }

    # TODO: read the actual current snapshot once a snapshot store exists;
    # out of scope for this command — every ingest run is validated as if
    # it were the first snapshot ever committed.
    previous: dict[str, Any] | None = None

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

    commit_snapshot(candidate, previous)
    typer.echo("candidate snapshot committed")


def build_cli() -> Any:
    """Construct the Typer application with all commands registered.

    Returns:
        A configured Typer app instance.
    """
    app = typer.Typer()
    app.command("validate-snapshot")(validate_snapshot_command)
    app.command("run-engine")(run_engine_command)
    app.command("optimize")(optimize_command)
    app.command("framework-status")(framework_status_command)
    app.command("ingest")(ingest_command)
    return app
