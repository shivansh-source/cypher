"""Orchestrating the full engine pipeline into a single RiskFigure."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from core.assumptions import VALUE_AT_RISK_PERCENTILE
from core.engine.attack_graph_inference import compute_graph_reachability
from core.engine.models import (
    LossEventContribution,
    LossExceedanceCurve,
    LossExceedancePoint,
    RiskFigure,
)
from core.engine.parameterization import parameterize_scenario
from core.engine.scenarios import build_loss_event_scenarios
from core.engine.simulation import run_monte_carlo

#: How many thresholds :func:`compute_loss_exceedance_curve` reports by
#: default. Display resolution only — it changes how finely the curve is
#: sampled, never the simulated distribution itself, so it is not a
#: modelling judgement and does not belong in ``core/assumptions.py``.
DEFAULT_LOSS_EXCEEDANCE_POINTS = 60


def _simulate(
    snapshot: dict[str, Any], seed: int | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build, parameterize and simulate every scenario in a snapshot.

    The single pipeline both :func:`compute_risk_figure` and
    :func:`compute_loss_exceedance_curve` run, so that for the same
    snapshot and seed they read off the very same simulated years.

    Attack-graph reachability is computed once per snapshot here, not per
    scenario, and applied to every scenario on an asset with known network
    topology (see ``core.engine.parameterization.parameterize_scenario``).

    Returns:
        The parameterized scenarios and ``run_monte_carlo``'s result.
    """
    scenarios = build_loss_event_scenarios(snapshot)
    graph_reachability = compute_graph_reachability(snapshot, seed=seed)
    parameterized_scenarios = [
        parameterize_scenario(scenario, snapshot, graph_reachability=graph_reachability)
        for scenario in scenarios
    ]
    return parameterized_scenarios, run_monte_carlo(parameterized_scenarios, seed=seed)


def compute_risk_figure(snapshot: dict[str, Any], *, seed: int | None = None) -> RiskFigure:
    """Run the full engine pipeline against a committed snapshot.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot. Must have
            already passed all 5 quality gates in ``core/snapshot.py`` —
            this function does not re-validate.
        seed: Override for ``run_monte_carlo``'s random seed. Defaults to a
            value derived from this snapshot's own content (see
            ``core.engine.simulation._derive_deterministic_seed``), which is
            correct for computing one real, reproducible figure. Callers
            comparing two *different* snapshots derived from the same base
            (e.g. ``core.optimizer.evaluate_portfolio`` comparing a
            candidate control portfolio against baseline) must pass the
            same explicit seed to both calls — common random numbers —
            since two independently-seeded runs of a low-probability
            scenario can differ by more than the true effect of the
            controls being compared, making a beneficial control look
            harmful by sampling noise alone.

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
    parameterized_scenarios, simulation = _simulate(snapshot, seed)

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


def compute_loss_exceedance_curve(
    snapshot: dict[str, Any],
    *,
    seed: int | None = None,
    points: int = DEFAULT_LOSS_EXCEEDANCE_POINTS,
) -> LossExceedanceCurve:
    """Compute the annual loss exceedance curve for a committed snapshot.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot, as for
            :func:`compute_risk_figure`.
        seed: As for :func:`compute_risk_figure`. Left at its default, the
            curve is read off exactly the simulated years that
            ``compute_risk_figure(snapshot)`` summarizes, so the curve is
            consistent with that figure's EAL and VaR by construction.
        points: How many thresholds to report (at least 2).

    Returns:
        A :class:`LossExceedanceCurve`: for each threshold, the fraction of
        simulated years whose total loss exceeded it.

    Must never:
        Smooth, fit or extrapolate the curve beyond the simulated years —
        every probability is a count of simulated years divided by the
        iteration count.
    """
    if points < 2:
        raise ValueError(f"points must be at least 2, got {points}")
    _, simulation = _simulate(snapshot, seed)
    total_samples = np.sort(np.asarray(simulation["total_annual_loss_samples_inr"], dtype=float))
    iterations = int(simulation["iterations"])

    positive = total_samples[total_samples > 0]
    probability_of_any_loss = float(positive.size / iterations) if iterations else 0.0
    curve_points: list[LossExceedancePoint] = []
    if positive.size:
        low, high = float(positive[0]), float(positive[-1])
        thresholds = [low] if low == high else list(np.geomspace(low, high, points))
        for threshold in thresholds:
            exceeding = iterations - int(np.searchsorted(total_samples, threshold, side="right"))
            curve_points.append(
                LossExceedancePoint(
                    loss_inr=float(threshold),
                    exceedance_probability=exceeding / iterations,
                )
            )

    return LossExceedanceCurve(
        snapshot_id=snapshot["snapshot_id"],
        monte_carlo_iterations=iterations,
        probability_of_any_loss=probability_of_any_loss,
        points=curve_points,
    )


def expected_annual_loss_by_asset(risk_figure: RiskFigure) -> dict[str, float]:
    """Roll a figure's Expected Annual Loss up to the asset each scenario is rooted in.

    Exact, not an approximation: Expected Annual Loss is a mean, means are
    linear, and every scenario belongs to exactly one asset, so each
    asset's roll-up is its scenarios' share of the headline figure and the
    roll-ups sum to it.

    Args:
        risk_figure: Output of :func:`compute_risk_figure`.

    Returns:
        asset_id -> that asset's share of ``expected_annual_loss_inr``, for
        every asset with at least one scenario, largest first.

    Must never:
        Be used to roll up Value at Risk. A percentile of a sum is not the
        sum of percentiles, so there is no per-asset VaR to derive this way.
    """
    by_asset: dict[str, float] = defaultdict(float)
    for contribution in risk_figure.top_contributors:
        by_asset[contribution.asset_id] += contribution.expected_annual_loss_inr
    return dict(sorted(by_asset.items(), key=lambda item: item[1], reverse=True))
