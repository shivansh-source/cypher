"""Tool: recommend a budget-constrained control portfolio.

This function does not compute anything itself; it delegates entirely to
``core.optimizer.recommend_portfolio``. See repo-root ``CLAUDE.md``
principles 1, 2, and 7.
"""

from __future__ import annotations

from typing import Any


def optimize_investment(
    budget_inr: float, candidate_control_ids: list[str] | None = None
) -> dict[str, Any]:
    """Recommend which controls to fund within a given budget.

    Args:
        budget_inr: Total budget available, in INR.
        candidate_control_ids: Optional restriction to a specific set of
            candidate controls; None means consider all controls the
            system currently has cost/effect data for.

    Returns:
        A structured dict representing a
        ``core.optimizer.PortfolioRecommendation`` — selected controls,
        total cost, and the jointly-simulated risk reduction — plus the
        ``snapshot_id`` used.

    Must never:
        Adjust, re-rank, or second-guess ``core.optimizer``'s selection.
        Must never report a risk_reduction_inr other than the one
        ``core.optimizer.recommend_portfolio`` returned from its joint
        re-simulation.
    """
    raise NotImplementedError
