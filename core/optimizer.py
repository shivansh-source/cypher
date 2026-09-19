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

from dataclasses import dataclass
from typing import Any

from core.engine import RiskFigure


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


def apply_controls_to_snapshot(snapshot: dict[str, Any], controls: list[Control]) -> dict[str, Any]:
    """Produce a hypothetical snapshot reflecting a candidate control portfolio.

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
    raise NotImplementedError


def evaluate_portfolio(snapshot: dict[str, Any], controls: list[Control]) -> RiskFigure:
    """Jointly re-simulate a candidate control portfolio's effect on risk.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        controls: The candidate portfolio of controls to evaluate together.

    Returns:
        The :class:`~core.engine.RiskFigure` computed by running
        ``core.engine.compute_risk_figure`` against the hypothetical
        snapshot from :func:`apply_controls_to_snapshot`.

    Must never:
        Compute or return a result derived from summing any control's
        individually-simulated delta. Every candidate portfolio, including
        a portfolio of size one, must go through a full joint simulation.
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError
