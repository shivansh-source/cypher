"""The Open FAIR + Monte Carlo risk quantification engine.

This is the only place in the codebase that produces a rupee-denominated
risk figure. It is deterministic given its inputs (a committed snapshot,
the named assumptions in ``core/assumptions.py``, and a fixed random seed
for the Monte Carlo simulation) — it never calls an ML model or an LLM. See
repo-root ``CLAUDE.md`` principle 1.

The engine reads only ``schema/aggregated_assets.schema.json``-shaped data.
It must never contain a branch keyed on which connector produced a given
finding — see principle 3.

Split across submodules by pipeline stage, each independently testable:

- ``models`` — ``LossEventContribution``, ``RiskFigure``, ``LossExceedanceCurve``.
- ``scenarios`` — ``build_loss_event_scenarios``: snapshot -> candidate scenarios.
- ``attack_graph`` — ``build_attack_graph``: snapshot network topology -> nodes/edges (structure only).
- ``attack_graph_inference`` — ``compute_graph_reachability``: bounded, simulated Bayesian
  inference -> per-asset attack routes (entry point, reach, share), consumed by
  ``parameterization``.
- ``parameterization`` — ``parameterize_scenario``: scenario -> FAIR distribution parameters.
- ``simulation`` — ``run_monte_carlo``: parameterized scenarios -> joint loss distribution.
- ``risk_figure`` — ``compute_risk_figure``: wires the above into one ``RiskFigure``;
  ``compute_loss_exceedance_curve`` reads the same simulation as a curve;
  ``expected_annual_loss_by_asset`` rolls a figure up by asset.

Every name below is re-exported here so existing call sites
(``from core.engine import compute_risk_figure``, etc.) are unaffected by
this internal split.
"""

from __future__ import annotations

from core.engine.models import (
    LossEventContribution,
    LossExceedanceCurve,
    LossExceedancePoint,
    RiskFigure,
)
from core.engine.parameterization import parameterize_scenario
from core.engine.risk_figure import (
    compute_loss_exceedance_curve,
    compute_risk_figure,
    expected_annual_loss_by_asset,
)
from core.engine.scenarios import build_loss_event_scenarios
from core.engine.simulation import run_monte_carlo

__all__ = [
    "LossEventContribution",
    "LossExceedanceCurve",
    "LossExceedancePoint",
    "RiskFigure",
    "build_loss_event_scenarios",
    "compute_loss_exceedance_curve",
    "compute_risk_figure",
    "expected_annual_loss_by_asset",
    "parameterize_scenario",
    "run_monte_carlo",
]
