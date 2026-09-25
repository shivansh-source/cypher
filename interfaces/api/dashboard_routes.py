"""Read and what-if routes behind the dashboard (``interfaces/dashboard/``).

Like everything in ``interfaces/api/``, each route here is a thin adapter:
it loads the current committed snapshot, calls into ``core/``,
``governance/`` or an ``ai.tools`` wrapper, and reshapes the result into
JSON. None of them computes a rupee figure, maps a control, or talks to an
LLM of its own — the only arithmetic here is counting findings and joining
engine outputs to the snapshot records they describe.

Each rupee figure in a response comes from a call into ``core.engine`` or
``core.optimizer`` made while handling that request, so it always tracks
the current committed snapshot rather than a cached or remembered one.
"""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai.tool_registry import execute_tool
from core.engine import (
    build_loss_event_scenarios,
    compute_loss_exceedance_curve,
    compute_risk_figure,
    expected_annual_loss_by_asset,
    parameterize_scenario,
)
from core.optimizer import (
    APPLICABLE_CONTROL_CATEGORIES,
    Control,
    find_control_gaps,
    prioritize_controls,
    recommend_portfolio,
)
from core.snapshot import validate_snapshot
from core.snapshot_store import (
    load_current_snapshot,
    load_predecessor_snapshot,
    load_snapshot_history,
)
from governance.library_loader import load_all_control_libraries
from interfaces.api._http import (
    NO_SNAPSHOT_DETAIL,
    current_snapshot_or_404,
    execution_to_response,
    snapshot_store_path,
)

#: Where the versioned control library YAML files live.
_CONTROL_LIBRARY_DIR = Path(__file__).resolve().parents[2] / "governance" / "control_library"

#: Upper bound on candidate controls per optimizer request. A request-size
#: guard for the API (each candidate costs at least one full Monte Carlo
#: run), not a modelling constant.
_MAX_CANDIDATE_CONTROLS = 500

#: Most steps ``GET /optimize/plan`` lists. A response-size and latency
#: guard (each step costs Monte Carlo runs), not a modelling constant; the
#: response says when more steps would still reduce loss.
_MAX_PLAN_STEPS = 12

#: Priority plans already computed, by snapshot_id. A committed snapshot is
#: immutable and content-hashed (principle 5) and the assumptions are fixed
#: for the life of the process, so a plan for a given snapshot_id never
#: changes; only the most recent few are kept.
_PLAN_CACHE: dict[str, dict[str, Any]] = {}
_PLAN_CACHE_SIZE = 4

#: Scenario fields ``core.engine.parameterize_scenario`` adds that the
#: dashboard shows as an asset's FAIR parameters. The raw ``finding`` and
#: ``asset`` records are already in the response beside them.
_SCENARIO_PARAMETER_FIELDS = (
    "scenario_id",
    "description",
    "exposure_profile",
    "threat_event_frequency",
    "exploit_probability",
    "active_control_resistances",
    "vulnerability",
    "loss_event_frequency",
    "criticality_tier",
    "backup_posture",
    "loss_magnitude",
)


#: Finding fields ``schema/aggregated_assets.schema.json`` does not require.
#: ``/assets`` always includes them, as null when absent.
_OPTIONAL_FINDING_FIELDS = ("cve_id", "epss_score", "kev_listed", "remediated_at")


class HypotheticalControl(BaseModel):
    """One control a what-if applies. Mirrors ``core.optimizer.Control``."""

    control_id: str = Field(min_length=1)
    control_category: str = Field(min_length=1)
    affected_asset_ids: list[str] = Field(min_length=1)
    estimated_cost_inr: float = Field(default=0.0, ge=0)
    finding_id: str | None = None
    service_id: str | None = None


class SimulateRequest(BaseModel):
    """A what-if: controls to apply to the current snapshot, together."""

    hypothetical_controls: list[HypotheticalControl] = Field(min_length=1)


class CandidateControl(BaseModel):
    """A candidate control with a declared cost. Mirrors ``core.optimizer.Control``.

    ``estimated_cost_inr`` is a user-declared input — the system has no cost
    catalogue of its own, and the optimizer never invents one.
    """

    control_id: str = Field(min_length=1)
    control_category: str = Field(min_length=1)
    affected_asset_ids: list[str] = Field(min_length=1)
    estimated_cost_inr: float = Field(ge=0)
    finding_id: str | None = Field(default=None, description="For remediate_finding.")
    service_id: str | None = Field(default=None, description="For harden_backup.")


class OptimizeRequest(BaseModel):
    """A budget and the priced candidate controls the optimizer may choose from."""

    budget_inr: float = Field(ge=0)
    candidate_controls: list[CandidateControl] = Field(
        min_length=1, max_length=_MAX_CANDIDATE_CONTROLS
    )


def snapshot_route() -> Any:
    """GET /snapshot — provenance of the current committed snapshot.

    Returns the bitemporal identity and scan scope every figure on screen
    derives from, plus record counts. 404 if nothing has been committed.
    """

    def handler() -> dict[str, Any]:
        snapshot = current_snapshot_or_404()
        findings = [finding for asset in snapshot["assets"] for finding in asset["findings"]]
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "observed_at": snapshot["observed_at"],
            "valid_from": snapshot["valid_from"],
            "valid_to": snapshot.get("valid_to"),
            "scan_scope": snapshot["scan_scope"],
            "asset_count": len(snapshot["assets"]),
            "service_count": len(snapshot.get("services", [])),
            "finding_count": len(findings),
            "open_finding_count": sum(1 for f in findings if f.get("remediated_at") is None),
        }

    return handler


def snapshot_gates_route() -> Any:
    """GET /snapshot/gates — the five quality gates, re-run on the current snapshot.

    The gate results a snapshot passed at commit time are not persisted,
    so this re-evaluates ``core.snapshot.validate_snapshot`` now: the
    current snapshot as the candidate, the snapshot it superseded as the
    previous one. Every gate is reported individually, never collapsed.
    """

    def handler() -> dict[str, Any]:
        snapshot = current_snapshot_or_404()
        previous = load_predecessor_snapshot(snapshot_store_path(), snapshot)
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "compared_against_snapshot_id": previous["snapshot_id"] if previous else None,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "gates": [asdict(result) for result in validate_snapshot(snapshot, previous)],
        }

    return handler


def _observed_at_key(snapshot: dict[str, Any]) -> tuple[datetime, str]:
    """Sort key matching ``core.snapshot_store.load_snapshot_history``'s order."""
    parsed = datetime.fromisoformat(snapshot["observed_at"])
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC), snapshot["snapshot_id"])


def exposure_history_route() -> Any:
    """GET /exposure/history — the engine's figure for every committed snapshot.

    Each snapshot in the store's immutable history is run through
    ``core.engine.compute_risk_figure`` exactly as the current one is, so
    the newest point is the same figure ``/exposure`` reports.
    """
    from fastapi import HTTPException

    def handler() -> dict[str, Any]:
        store_path = snapshot_store_path()
        history = load_snapshot_history(store_path)
        current = load_current_snapshot(store_path)
        if current is not None and current["snapshot_id"] not in {
            s["snapshot_id"] for s in history
        }:
            history = sorted([*history, current], key=lambda snapshot: _observed_at_key(snapshot))
        if not history:
            raise HTTPException(status_code=404, detail=NO_SNAPSHOT_DETAIL)
        return {
            "snapshots": [
                {
                    "snapshot_id": snapshot["snapshot_id"],
                    "observed_at": snapshot["observed_at"],
                    "risk_figure": asdict(compute_risk_figure(snapshot)),
                }
                for snapshot in history
            ]
        }

    return handler


def exposure_exceedance_route() -> Any:
    """GET /exposure/exceedance — the current snapshot's loss exceedance curve.

    Read by ``core.engine.compute_loss_exceedance_curve`` off the same
    simulated years as ``/exposure``'s EAL and VaR.
    """

    def handler() -> dict[str, Any]:
        return asdict(compute_loss_exceedance_curve(current_snapshot_or_404()))

    return handler


def assets_route() -> Any:
    """GET /assets — every asset with its posture, findings and FAIR parameters.

    Posture and findings are the snapshot's own records, unchanged. Each
    open finding carries the scenario ``core.engine`` built for it, with
    the parameters ``parameterize_scenario`` gave it and the Expected
    Annual Loss ``compute_risk_figure`` attributed to it. Each asset's
    ``expected_annual_loss_inr`` is ``core.engine.expected_annual_loss_by_asset``;
    it is null for an asset with no open finding, because the engine models
    no scenario there — which is not the same as the asset being riskless.
    """

    def handler() -> dict[str, Any]:
        snapshot = current_snapshot_or_404()
        figure = compute_risk_figure(snapshot)
        contribution_by_scenario = {c.scenario_id: c for c in figure.top_contributors}
        asset_eal = expected_annual_loss_by_asset(figure)
        scenario_by_finding: dict[tuple[str, str], dict[str, Any]] = {}
        for scenario in build_loss_event_scenarios(snapshot):
            parameterized = parameterize_scenario(scenario, snapshot)
            contribution = contribution_by_scenario[parameterized["scenario_id"]]
            scenario_by_finding[(scenario["asset_id"], scenario["finding"]["finding_id"])] = {
                **{key: parameterized[key] for key in _SCENARIO_PARAMETER_FIELDS},
                "expected_annual_loss_inr": contribution.expected_annual_loss_inr,
            }

        services_by_id = {s["service_id"]: s for s in snapshot.get("services", [])}
        assets: list[dict[str, Any]] = []
        for asset in snapshot["assets"]:
            service_ids: list[str] = asset.get("service_ids", [])
            assets.append(
                {
                    "asset_id": asset["asset_id"],
                    "service_ids": service_ids,
                    "services": [services_by_id[s] for s in service_ids if s in services_by_id],
                    "unresolved_service_ids": [s for s in service_ids if s not in services_by_id],
                    "network": asset.get("network"),
                    "edr": asset.get("edr"),
                    "identity_access": asset.get("identity_access"),
                    "expected_annual_loss_inr": asset_eal.get(asset["asset_id"]),
                    "findings": [
                        {
                            # Schema-optional keys made explicit, so an absent
                            # remediated_at reads as open — exactly as the engine
                            # (``.get(...) is None``) reads it.
                            **dict.fromkeys(_OPTIONAL_FINDING_FIELDS),
                            **finding,
                            "scenario": scenario_by_finding.get(
                                (asset["asset_id"], finding["finding_id"])
                            ),
                        }
                        for finding in asset["findings"]
                    ],
                }
            )

        return {
            "snapshot_id": figure.snapshot_id,
            "observed_at": snapshot["observed_at"],
            "monte_carlo_iterations": figure.monte_carlo_iterations,
            "expected_annual_loss_inr": figure.expected_annual_loss_inr,
            "assets": assets,
        }

    return handler


def frameworks_route() -> Any:
    """GET /frameworks — every versioned control library in force today.

    Includes each framework's statutory penalty provisions exactly as
    sourced in its YAML file: statutory ceilings, never an expected loss,
    and never an input to any control's status (principle 6).
    """

    def handler() -> list[dict[str, Any]]:
        libraries = load_all_control_libraries(_CONTROL_LIBRARY_DIR, datetime.now(UTC).date())
        return [
            {
                "framework": library.framework,
                "version": library.version,
                "effective_from": library.effective_from,
                "effective_to": library.effective_to,
                "supersedes": library.supersedes,
                "control_count": len(library.controls),
                "penalty_provisions": [asdict(p) for p in library.penalty_provisions],
            }
            for library in libraries.values()
        ]

    return handler


def framework_status_route() -> Any:
    """GET /frameworks/{framework}/status — wraps ``ai.tools.get_framework_status``."""

    def handler(framework: str) -> dict[str, Any]:
        return execution_to_response(execute_tool("get_framework_status", {"framework": framework}))

    return handler


def simulate_route() -> Any:
    """POST /simulate — wraps ``ai.tools.simulate_scenario``.

    One joint re-simulation of every hypothetical control together, against
    a baseline re-simulated on the same random draws. 400 when the what-if
    is malformed (unknown asset, unsupported category), 501 with no snapshot.
    """

    def handler(request: SimulateRequest) -> dict[str, Any]:
        return execution_to_response(
            execute_tool(
                "simulate_scenario",
                {"hypothetical_controls": [c.model_dump() for c in request.hypothetical_controls]},
            )
        )

    return handler


def optimize_candidates_route() -> Any:
    """GET /optimize/candidates — ``core.optimizer.find_control_gaps`` on the current snapshot.

    Gaps carry no cost and no benefit: cost is for the caller to declare,
    and benefit only ever comes from a joint re-simulation.
    """

    def handler() -> dict[str, Any]:
        snapshot = current_snapshot_or_404()
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "applicable_categories": list(APPLICABLE_CONTROL_CATEGORIES),
            "gaps": [asdict(gap) for gap in find_control_gaps(snapshot)],
        }

    return handler


def optimize_plan_route() -> Any:
    """GET /optimize/plan — ``core.optimizer.prioritize_controls`` on the current snapshot.

    Needs no costs: every candidate change from ``find_control_gaps``,
    ordered by how much each reduces Expected Annual Loss given the ones
    before it, each step a joint re-simulation (principle 7). At most
    ``_MAX_PLAN_STEPS`` steps; ``truncated`` says whether more would help.
    """

    def handler() -> dict[str, Any]:
        snapshot = current_snapshot_or_404()
        snapshot_id = snapshot["snapshot_id"]
        cached = _PLAN_CACHE.get(snapshot_id)
        if cached is not None:
            return cached
        plan = prioritize_controls(
            snapshot, find_control_gaps(snapshot), max_steps=_MAX_PLAN_STEPS
        )
        response = {"snapshot_id": snapshot_id, **asdict(plan)}
        if len(_PLAN_CACHE) >= _PLAN_CACHE_SIZE:
            _PLAN_CACHE.pop(next(iter(_PLAN_CACHE)))
        _PLAN_CACHE[snapshot_id] = response
        return response

    return handler


def optimize_route() -> Any:
    """POST /optimize — ``core.optimizer.recommend_portfolio`` over declared-cost candidates.

    The reported ``risk_reduction_inr`` is the optimizer's own, from a joint
    re-simulation of the selected portfolio (principle 7).
    """
    from fastapi import HTTPException

    def handler(request: OptimizeRequest) -> dict[str, Any]:
        snapshot = current_snapshot_or_404()
        control_ids = [c.control_id for c in request.candidate_controls]
        duplicates = sorted({cid for cid in control_ids if control_ids.count(cid) > 1})
        if duplicates:
            raise HTTPException(
                status_code=400,
                detail=f"candidate control_id(s) listed more than once: {', '.join(duplicates)}",
            )
        known_assets = {asset["asset_id"] for asset in snapshot["assets"]}
        unknown = sorted(
            {a for c in request.candidate_controls for a in c.affected_asset_ids} - known_assets
        )
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"asset(s) not in the current snapshot: {', '.join(unknown)}",
            )
        controls = [
            Control(
                control_id=c.control_id,
                control_category=c.control_category,
                estimated_cost_inr=c.estimated_cost_inr,
                affected_asset_ids=list(c.affected_asset_ids),
                finding_id=c.finding_id,
                service_id=c.service_id,
            )
            for c in request.candidate_controls
        ]
        try:
            recommendation = recommend_portfolio(snapshot, controls, request.budget_inr)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"snapshot_id": snapshot["snapshot_id"], **asdict(recommendation)}

    return handler


_SECTION_MARKERS = ("ASSUMPTION", "JUSTIFICATION", "CALIBRATION")


def _comment_block_above(lines: list[str], lineno: int) -> list[str]:
    """The contiguous ``#`` comment lines directly above 1-based line ``lineno``."""
    block: list[str] = []
    index = lineno - 2
    while index >= 0 and lines[index].lstrip().startswith("#"):
        block.append(lines[index].lstrip()[1:].strip())
        index -= 1
    return list(reversed(block))


def _documented_sections(block: list[str]) -> dict[str, str | None]:
    """Split a constant's comment block into its ASSUMPTION/JUSTIFICATION/CALIBRATION text."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    marker = re.compile(rf"^({'|'.join(_SECTION_MARKERS)}):\s*(.*)$")
    for line in block:
        match = marker.match(line)
        if match:
            current = match.group(1)
            sections[current] = [match.group(2)]
        elif current is not None:
            sections[current].append(line)
    return {
        name.lower(): (" ".join(" ".join(sections[name]).split()) or None)
        if name in sections
        else None
        for name in _SECTION_MARKERS
    }


def assumptions_route() -> Any:
    """GET /assumptions — every constant in ``core/assumptions.py``, live.

    Values are read from the imported module, so the register can never
    disagree with what the engine actually used. Each constant's
    ASSUMPTION / JUSTIFICATION / CALIBRATION text is read from the comment
    block above it in that module's source, so the explanation cannot
    drift from the code either. Text is null when the source is not
    available (e.g. a bytecode-only install) or a constant has no block.
    """
    from core import assumptions

    def handler() -> list[dict[str, Any]]:
        try:
            source = inspect.getsource(assumptions)
        except (OSError, TypeError):
            source = ""
        lines = source.splitlines()
        documented: dict[str, dict[str, str | None]] = {}
        for node in ast.parse(source).body if source else []:
            targets: list[ast.expr]
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    documented[target.id] = _documented_sections(
                        _comment_block_above(lines, node.lineno)
                    )

        # Source order when the source is readable (the module groups related
        # constants together); alphabetical otherwise.
        names = [n for n in documented if n.isupper()] or sorted(
            n for n in dir(assumptions) if n.isupper() and not n.startswith("_")
        )
        empty: dict[str, str | None] = dict.fromkeys(("assumption", "justification", "calibration"))
        return [
            {"name": name, "value": getattr(assumptions, name), **documented.get(name, empty)}
            for name in names
            if not name.startswith("_")
        ]

    return handler


def register_dashboard_routes(app: Any) -> None:
    """Register every route in this module on a FastAPI app."""
    app.get("/snapshot")(snapshot_route())
    app.get("/snapshot/gates")(snapshot_gates_route())
    app.get("/exposure/history")(exposure_history_route())
    app.get("/exposure/exceedance")(exposure_exceedance_route())
    app.get("/assets")(assets_route())
    app.get("/frameworks")(frameworks_route())
    app.get("/frameworks/{framework}/status")(framework_status_route())
    app.post("/simulate")(simulate_route())
    app.get("/optimize/candidates")(optimize_candidates_route())
    app.get("/optimize/plan")(optimize_plan_route())
    app.post("/optimize")(optimize_route())
    app.get("/assumptions")(assumptions_route())
