"""Tool: explain how a previously-shown number was derived.

This function does not compute anything itself; it looks up the
computation trail (scenario parameters, assumptions used, snapshot) behind
an already-produced figure. See repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable
from core.engine import build_loss_event_scenarios, parameterize_scenario

#: Constants core.engine.parameterization.parameterize_scenario draws
#: from, by name, with a one-line description — see core/assumptions.py
#: for each constant's full ASSUMPTION/JUSTIFICATION/CALIBRATION text.
_ASSUMPTIONS_USED = {
    "BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR": (
        "Baseline annual attempt frequency for this asset's exposure profile."
    ),
    "BASELINE_EXPLOIT_PROBABILITY_FOR_UNSCORED_FINDING": (
        "Exploit probability used when this finding has no EPSS score."
    ),
    "KEV_LISTED_MINIMUM_EXPLOIT_PROBABILITY": (
        "Floor applied to exploit probability if this finding is CISA KEV-listed."
    ),
    "CONTROL_RESISTANCE_STRENGTH": (
        "Resistance strength of each control category observed active on this asset."
    ),
    "BASE_LOSS_MAGNITUDE_BY_CRITICALITY_INR": (
        "Base loss magnitude for this scenario's worst-case related-service criticality tier."
    ),
    "RTO_MULTIPLIER_BY_BACKUP_POSTURE": (
        "Multiplier applied for this scenario's worst-case related-service backup posture."
    ),
}


def explain_number(figure_reference: str) -> dict[str, Any]:
    """Return the derivation trail behind a previously-produced figure.

    Args:
        figure_reference: An identifier for a previously-computed figure
            (e.g. a scenario_id from a ``core.engine.LossEventContribution``,
            or a control_id from a ``core.optimizer.PortfolioRecommendation``)
            that the user is asking to have explained.

    Returns:
        A structured dict listing the FAIR parameters, the
        ``core.assumptions`` constants used (by name, with their
        justification text), and the snapshot data that fed into the
        referenced figure.

    Must never:
        Recompute the figure to "double check" it as part of explaining
        it, or produce an explanation for a figure_reference that doesn't
        correspond to a real prior computation.
    """
    snapshot = current_snapshot_or_unavailable()
    scenarios = build_loss_event_scenarios(snapshot)
    matches = [s for s in scenarios if s["scenario_id"] == figure_reference]
    if not matches:
        raise NotImplementedError(
            f"no active loss-event scenario found for figure_reference {figure_reference!r} "
            "(control_id-shaped references from the optimizer are not yet supported)"
        )
    scenario = matches[0]
    parameterized = parameterize_scenario(scenario, snapshot)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "scenario_id": scenario["scenario_id"],
        "asset_id": scenario["asset_id"],
        "finding": scenario["finding"],
        "parameters": {
            key: value for key, value in parameterized.items() if key not in ("finding", "asset")
        },
        "assumptions_used": _ASSUMPTIONS_USED,
    }
