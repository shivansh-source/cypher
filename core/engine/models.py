"""Public result types for the Open FAIR + Monte Carlo engine.

See ``core/engine/__init__.py`` for the module-level contract these types
serve (deterministic, no ML/LLM, schema-only input).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LossEventContribution:
    """A single loss-event scenario's contribution to overall risk.

    Attributes:
        scenario_id: Stable identifier for the loss event scenario (e.g.
            derived from an asset_id + threat event type pairing).
        asset_id: The asset this scenario is rooted in.
        expected_annual_loss_inr: This scenario's contribution to overall
            Expected Annual Loss, in INR.
        description: Human-readable description of the scenario, suitable
            for display without further interpretation.
    """

    scenario_id: str
    asset_id: str
    expected_annual_loss_inr: float
    description: str


@dataclass(frozen=True)
class RiskFigure:
    """The output of a full engine run against a committed snapshot.

    Attributes:
        snapshot_id: The snapshot this figure was computed from.
        expected_annual_loss_inr: Point estimate (mean of the Monte Carlo
            loss distribution), in INR.
        value_at_risk_inr: Value at Risk at the percentile configured in
            ``core.assumptions.VALUE_AT_RISK_PERCENTILE``, in INR.
        value_at_risk_percentile: The percentile actually used, copied from
            ``core.assumptions.VALUE_AT_RISK_PERCENTILE`` at computation
            time, so downstream consumers never have to assume it matches
            the current config.
        top_contributors: Loss event scenarios ranked by contribution to
            expected annual loss, largest first.
        monte_carlo_iterations: The iteration count actually used, copied
            from ``core.assumptions.MONTE_CARLO_ITERATIONS`` at computation
            time.
    """

    snapshot_id: str
    expected_annual_loss_inr: float
    value_at_risk_inr: float
    value_at_risk_percentile: float
    top_contributors: list[LossEventContribution]
    monte_carlo_iterations: int


@dataclass(frozen=True)
class LossExceedancePoint:
    """One point on a loss exceedance curve.

    Attributes:
        loss_inr: A total annual loss threshold, in INR.
        exceedance_probability: Fraction of simulated years whose total
            loss was strictly greater than ``loss_inr``.
    """

    loss_inr: float
    exceedance_probability: float


@dataclass(frozen=True)
class LossExceedanceCurve:
    """The annual loss exceedance curve for one committed snapshot.

    Read off the same joint total-loss distribution that
    :class:`RiskFigure`'s Expected Annual Loss and Value at Risk come from
    (same scenarios, same seed), so the curve and those two figures always
    describe one simulation rather than two independent ones.

    Attributes:
        snapshot_id: The snapshot this curve was computed from.
        monte_carlo_iterations: The iteration count actually used.
        probability_of_any_loss: Fraction of simulated years with a total
            loss above zero. The curve's points only span the years that
            had a loss; this is the curve's value at its left edge.
        points: Thresholds in ascending ``loss_inr`` order, log-spaced
            between the smallest and largest non-zero simulated annual
            loss. Empty when no simulated year had a loss at all.
    """

    snapshot_id: str
    monte_carlo_iterations: int
    probability_of_any_loss: float
    points: list[LossExceedancePoint]
