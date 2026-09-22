"""Orchestrating the full engine pipeline into a single RiskFigure."""

from __future__ import annotations

from typing import Any

import numpy as np

from core.assumptions import VALUE_AT_RISK_PERCENTILE
from core.engine.models import LossEventContribution, RiskFigure
from core.engine.parameterization import parameterize_scenario
from core.engine.scenarios import build_loss_event_scenarios
from core.engine.simulation import run_monte_carlo


def compute_risk_figure(snapshot: dict[str, Any]) -> RiskFigure:
    """Run the full engine pipeline against a committed snapshot.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot. Must have
            already passed all 5 quality gates in ``core/snapshot.py`` —
            this function does not re-validate.

    Returns:
        A :class:`RiskFigure` with Expected Annual Loss, Value at Risk, and
        the ranked top loss-event contributors. ``expected_annual_loss_inr``
        is the mean of ``run_monte_carlo``'s joint (shared-latent-factor
        correlated, see its docstring) total loss distribution — which,
        because the mean is linear, is exactly the sum of each
        contributor's own mean. ``value_at_risk_inr`` is a percentile of
        that same joint distribution, which is *not* additive across
        scenarios (a percentile of a sum isn't the sum of percentiles) —
        this is why VaR is computed once on the joint total rather than
        derived from per-scenario figures.

    Must never:
        Call an ML model or an LLM at any point in this pipeline. Must
        never return a figure without the ``top_contributors`` breakdown —
        a bottom-line number with no explanation of what drives it cannot
        be defended or acted on. See repo-root ``CLAUDE.md`` principle 1.
    """
    scenarios = build_loss_event_scenarios(snapshot)
    parameterized_scenarios = [parameterize_scenario(scenario, snapshot) for scenario in scenarios]
    simulation = run_monte_carlo(parameterized_scenarios)

    total_samples = simulation["total_annual_loss_samples_inr"]
    per_scenario_samples = simulation["per_scenario_annual_loss_samples_inr"]

    top_contributors = sorted(
        (
            LossEventContribution(
                scenario_id=scenario["scenario_id"],
                asset_id=scenario["asset_id"],
                expected_annual_loss_inr=float(
                    np.mean(per_scenario_samples[scenario["scenario_id"]])
                ),
                description=scenario["description"],
            )
            for scenario in parameterized_scenarios
        ),
        key=lambda contribution: contribution.expected_annual_loss_inr,
        reverse=True,
    )

    return RiskFigure(
        snapshot_id=snapshot["snapshot_id"],
        expected_annual_loss_inr=float(np.mean(total_samples)),
        value_at_risk_inr=float(np.percentile(total_samples, VALUE_AT_RISK_PERCENTILE * 100)),
        value_at_risk_percentile=VALUE_AT_RISK_PERCENTILE,
        top_contributors=top_contributors,
        monte_carlo_iterations=simulation["iterations"],
    )
