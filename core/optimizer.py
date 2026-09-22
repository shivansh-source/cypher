"""Budget allocation optimizer.

Recommends which controls to fund, given a fixed budget, to maximize risk
reduction. The central constraint on this module: candidate portfolios of
controls must always be evaluated by re-running the full Monte Carlo
simulation (``core.engine.run_monte_carlo``) against the portfolio as a
whole, never by summing each control's individually-simulated delta. See
repo-root ``CLAUDE.md`` principle 7.

Overlapping controls (e.g. patching a CVE *and* hardening the EDR that
would have caught exploitation of that same CVE) make naive addition badly
overstate combined benefit — the true joint benefit is smaller than the
sum of the parts, and only a joint re-simulation captures that.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from core.assumptions import CONTROL_RESISTANCE_STRENGTH
from core.engine import RiskFigure, compute_risk_figure


def _derive_comparison_seed(snapshot: dict[str, Any]) -> int:
    """Derive a Monte Carlo seed from the original (pre-control) snapshot.

    Every candidate portfolio evaluated against the same base snapshot
    gets this same seed, rather than each hypothetical snapshot deriving
    its own from its own (different) content — deliberately, since that
    makes every evaluation a common-random-numbers comparison: the same
    underlying draws, differing only in the modelled effect of the
    controls under test. Without this, two independently-seeded Monte
    Carlo runs of a low-probability scenario can differ by more than the
    controls' true effect, making a genuinely beneficial control look
    harmful from sampling noise alone. This mirrors the SIH105 project
    doc's lab-validation protocol (page 11), which uses the identical
    technique — seeding paired control on/off runs identically — for the
    same reason.
    """
    content = json.dumps(snapshot, sort_keys=True, default=str)
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % (2**32)


@dataclass(frozen=True)
class Control:
    """A candidate control investment.

    Attributes:
        control_id: Stable identifier for this control instance (e.g. "patch
            CVE-2026-00001 on asset-web-01", "enable MFA org-wide").
        control_category: Category key matching
            ``core.assumptions.CONTROL_RESISTANCE_STRENGTH``.
        estimated_cost_inr: Estimated one-time or annualized cost to
            implement this control, in INR.
        affected_asset_ids: Assets this control would apply to, used to
            detect overlap with other candidate controls during joint
            simulation.
    """

    control_id: str
    control_category: str
    estimated_cost_inr: float
    affected_asset_ids: list[str]


@dataclass(frozen=True)
class PortfolioRecommendation:
    """The optimizer's recommended set of controls for a given budget.

    Attributes:
        selected_controls: The controls recommended for funding.
        total_cost_inr: Sum of ``estimated_cost_inr`` across
            ``selected_controls`` — this sum is a cost total and is fine to
            compute by addition; it is loss/benefit figures that must never
            be summed this way.
        baseline_risk_figure: The engine's output against the snapshot with
            no candidate controls applied.
        post_investment_risk_figure: The engine's output from a joint
            re-simulation of the snapshot with every selected control's
            effect applied simultaneously.
        risk_reduction_inr: ``baseline_risk_figure.expected_annual_loss_inr
            - post_investment_risk_figure.expected_annual_loss_inr``,
            derived from the two jointly-simulated figures above, never
            from summing individual control deltas.
    """

    selected_controls: list[Control]
    total_cost_inr: float
    baseline_risk_figure: RiskFigure
    post_investment_risk_figure: RiskFigure
    risk_reduction_inr: float


def _apply_control_to_asset(asset: dict[str, Any], control: Control) -> None:
    """Mutate one asset in place to reflect one control's posture change.

    Only categories with a modelled resistance value in
    ``core.assumptions.CONTROL_RESISTANCE_STRENGTH`` are applicable — a
    category the engine has no resistance value for would have zero
    measurable effect on the risk figure regardless of what this function
    did, so applying one is a configuration error, not a no-op.
    """
    if control.control_category not in CONTROL_RESISTANCE_STRENGTH:
        raise ValueError(
            f"Control {control.control_id!r} has control_category "
            f"{control.control_category!r}, which has no entry in "
            "core.assumptions.CONTROL_RESISTANCE_STRENGTH — applying it "
            "would have no modelled effect on the risk figure. Add the "
            "category there first, or fix the control's category."
        )
    if control.control_category == "mfa_enforced":
        asset.setdefault("identity_access", {})["mfa_enforced"] = True
    elif control.control_category == "edr_active":
        edr = asset.setdefault("edr", {})
        edr["agent_installed"] = True
        edr["agent_healthy"] = True
    else:
        # A category can be added to CONTROL_RESISTANCE_STRENGTH (e.g. once
        # a connector exposes a patch-currency or segmentation signal)
        # before this function is taught how to apply it to a snapshot.
        raise ValueError(
            f"control_category {control.control_category!r} is a known "
            "resistance category but apply_controls_to_snapshot does not "
            "yet know which schema field it corresponds to — add a case "
            "for it here."
        )


def apply_controls_to_snapshot(snapshot: dict[str, Any], controls: list[Control]) -> dict[str, Any]:
    """Produce a hypothetical snapshot reflecting a candidate control portfolio.

    Every control's effect is applied to a single deep copy of the
    snapshot before that copy is ever read by anything — there is no
    intermediate "per-control snapshot" that gets its own risk figure
    computed, which is what would let overlap slip in through the back
    door even if the final numbers were computed jointly.

    Known limitation: a control can currently only represent "this
    resistance category is now active on these assets" (e.g. org-wide MFA,
    an EDR rollout) via ``core.assumptions.CONTROL_RESISTANCE_STRENGTH``
    categories — not yet "this one specific finding is remediated" (e.g.
    patching a single named CVE), since ``Control`` has no
    finding-targeting field. Two different categories applied to the same
    asset already demonstrate genuine sub-additive overlap today (see
    ``core.engine.parameterization._combine_resistances``: combined
    resistance from two controls is ``1 - (1-r1)(1-r2)``, strictly less
    than ``r1 + r2``), which is what
    :func:`test_overlapping_controls_do_not_double_count_benefit` in
    ``core/tests/test_optimizer.py`` relies on.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        controls: The candidate portfolio of controls to hypothetically
            apply together.

    Returns:
        A new, hypothetical schema-shaped snapshot with the effects of
        every control in ``controls`` applied jointly (e.g. affected
        findings marked remediated, affected assets' control posture
        updated) — never a real snapshot, and never committed via
        ``core.snapshot.commit_snapshot``.

    Must never:
        Apply controls one at a time and cache each one's isolated effect
        for later summation — the whole point of this function is to
        produce one combined hypothetical state that
        ``core.engine.compute_risk_figure`` can be run against as a whole.
    """
    hypothetical_snapshot = copy.deepcopy(snapshot)

    controls_by_asset_id: dict[str, list[Control]] = defaultdict(list)
    for control in controls:
        for asset_id in control.affected_asset_ids:
            controls_by_asset_id[asset_id].append(control)

    for asset in hypothetical_snapshot["assets"]:
        for control in controls_by_asset_id.get(asset["asset_id"], []):
            _apply_control_to_asset(asset, control)

    return hypothetical_snapshot


def evaluate_portfolio(snapshot: dict[str, Any], controls: list[Control]) -> RiskFigure:
    """Jointly re-simulate a candidate control portfolio's effect on risk.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        controls: The candidate portfolio of controls to evaluate together.

    Returns:
        The :class:`~core.engine.RiskFigure` computed by running
        ``core.engine.compute_risk_figure`` against the hypothetical
        snapshot from :func:`apply_controls_to_snapshot`, seeded from the
        original ``snapshot`` (see :func:`_derive_comparison_seed`) so a
        result from this function is directly, fairly comparable to any
        other ``evaluate_portfolio`` call against the same base snapshot
        — including a baseline via ``evaluate_portfolio(snapshot, [])``.

    Must never:
        Compute or return a result derived from summing any control's
        individually-simulated delta. Every candidate portfolio, including
        a portfolio of size one, must go through a full joint simulation.
    """
    hypothetical_snapshot = apply_controls_to_snapshot(snapshot, controls)
    comparison_seed = _derive_comparison_seed(snapshot)
    return compute_risk_figure(hypothetical_snapshot, seed=comparison_seed)


def recommend_portfolio(
    snapshot: dict[str, Any],
    candidate_controls: list[Control],
    budget_inr: float,
) -> PortfolioRecommendation:
    """Select the subset of candidate controls that maximizes risk reduction
    within budget.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        candidate_controls: All controls under consideration.
        budget_inr: The total budget available, in INR.

    Returns:
        A :class:`PortfolioRecommendation` describing the selected subset,
        its cost, and its jointly-simulated risk reduction versus baseline.

    Must never:
        Rank or select controls using a precomputed per-control benefit
        estimate as a proxy for search efficiency and then report that
        estimate as the final answer — any search heuristic used to narrow
        the candidate space is allowed internally, but the reported
        ``risk_reduction_inr`` on the final recommended portfolio must come
        from an actual joint re-simulation via :func:`evaluate_portfolio`,
        not from the heuristic. See repo-root ``CLAUDE.md`` principle 7.

    This is a greedy forward-selection search, not an exhaustive one — it
    is not guaranteed to find the true optimal subset (that would require
    evaluating a combinatorial number of candidate subsets), only a
    defensible one:

    1. Estimate each candidate's standalone benefit (its own
       ``evaluate_portfolio`` result alone, versus baseline) purely to
       decide *search order* — cost-effectiveness, most effective per
       rupee first. This estimate is never returned to the caller.
    2. Walk candidates in that order. For each, tentatively add it to the
       current selection and actually re-simulate the *whole* resulting
       portfolio jointly. Keep it only if it fits the remaining budget and
       the real joint simulation shows an improvement over the current
       selection — a control fully absorbed by overlap with what's
       already selected (zero marginal joint benefit) is correctly
       rejected here even though its standalone estimate looked good.
    3. Report the final selection's own joint simulation result — never
       the sum of the per-step standalone estimates used to order the
       search.
    """
    baseline_figure = evaluate_portfolio(snapshot, [])

    if not candidate_controls:
        return PortfolioRecommendation(
            selected_controls=[],
            total_cost_inr=0.0,
            baseline_risk_figure=baseline_figure,
            post_investment_risk_figure=baseline_figure,
            risk_reduction_inr=0.0,
        )

    standalone_reduction_inr: dict[str, float] = {
        control.control_id: (
            baseline_figure.expected_annual_loss_inr
            - evaluate_portfolio(snapshot, [control]).expected_annual_loss_inr
        )
        for control in candidate_controls
    }

    def cost_effectiveness(control: Control) -> float:
        if control.estimated_cost_inr <= 0:
            return float("inf")
        return standalone_reduction_inr[control.control_id] / control.estimated_cost_inr

    search_order = sorted(candidate_controls, key=cost_effectiveness, reverse=True)

    selected_controls: list[Control] = []
    total_cost_inr = 0.0
    current_figure = baseline_figure
    for control in search_order:
        prospective_cost_inr = total_cost_inr + control.estimated_cost_inr
        if prospective_cost_inr > budget_inr:
            continue
        prospective_figure = evaluate_portfolio(snapshot, [*selected_controls, control])
        if prospective_figure.expected_annual_loss_inr < current_figure.expected_annual_loss_inr:
            selected_controls.append(control)
            total_cost_inr = prospective_cost_inr
            current_figure = prospective_figure

    return PortfolioRecommendation(
        selected_controls=selected_controls,
        total_cost_inr=total_cost_inr,
        baseline_risk_figure=baseline_figure,
        post_investment_risk_figure=current_figure,
        risk_reduction_inr=baseline_figure.expected_annual_loss_inr
        - current_figure.expected_annual_loss_inr,
    )
