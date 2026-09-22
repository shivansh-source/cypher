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
