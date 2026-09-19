"""The Open FAIR + Monte Carlo risk quantification engine.

This is the only place in the codebase that produces a rupee-denominated
risk figure. It is deterministic given its inputs (a committed snapshot,
the named assumptions in ``core/assumptions.py``, and a fixed random seed
for the Monte Carlo simulation) — it never calls an ML model or an LLM. See
repo-root ``CLAUDE.md`` principle 1.

The engine reads only ``schema/aggregated_assets.schema.json``-shaped data.
It must never contain a branch keyed on which connector produced a given
finding — see principle 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def build_loss_event_scenarios(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive candidate FAIR loss event scenarios from a committed snapshot.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot (see
            ``core/snapshot.py``).

    Returns:
        A list of scenario definitions (threat event x asset x vulnerability
        pairing) ready to be parameterized by :func:`parameterize_scenario`.
        Shape is internal to the engine, not schema-governed.

    Must never:
        Read anything from the snapshot beyond what
        ``schema/aggregated_assets.schema.json`` defines, or branch on
        which connector produced a given finding.
    """
    raise NotImplementedError


def parameterize_scenario(scenario: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach Open FAIR parameters (frequency, vulnerability, loss magnitude
    distributions) to a scenario, using snapshot data and named assumptions.

    Args:
        scenario: One scenario from :func:`build_loss_event_scenarios`.
        snapshot: The committed snapshot the scenario was derived from.

    Returns:
        The scenario augmented with FAIR distribution parameters (e.g.
        threat event frequency, vulnerability/control resistance, primary
        and secondary loss magnitude distributions).

    Must never:
        Use a bare numeric literal for any parameter — every constant must
        come from ``core.assumptions``, keyed appropriately (e.g. by
        control category, backup posture, or regulatory regime).
    """
    raise NotImplementedError


def run_monte_carlo(parameterized_scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Propagate uncertainty through all parameterized scenarios via Monte
    Carlo simulation to produce a joint loss distribution.

    Args:
        parameterized_scenarios: Output of :func:`parameterize_scenario`
            for every scenario in scope.

    Returns:
        Simulation output sufficient to derive Expected Annual Loss, Value
        at Risk at any percentile, and per-scenario contribution to the
        total — shape is internal to the engine.

    Must never:
        Use an iteration count other than
        ``core.assumptions.MONTE_CARLO_ITERATIONS``, or a fixed seed that
        isn't recorded alongside the result (the same snapshot + same
        assumptions must be reproducible on rerun).
    """
    raise NotImplementedError


def compute_risk_figure(snapshot: dict[str, Any]) -> RiskFigure:
    """Run the full engine pipeline against a committed snapshot.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot. Must have
            already passed all 5 quality gates in ``core/snapshot.py`` —
            this function does not re-validate.

    Returns:
        A :class:`RiskFigure` with Expected Annual Loss, Value at Risk, and
        the ranked top loss-event contributors.

    Must never:
        Call an ML model or an LLM at any point in this pipeline. Must
        never return a figure without the ``top_contributors`` breakdown —
        a bottom-line number with no explanation of what drives it cannot
        be defended or acted on. See repo-root ``CLAUDE.md`` principle 1.
    """
    raise NotImplementedError
