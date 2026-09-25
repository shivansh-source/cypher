"""Tool: run a hypothetical what-if scenario through the real engine.

This function does not compute anything itself; it delegates to
``core.optimizer.compare_hypothetical`` (which applies the controls via
``core.optimizer.apply_controls_to_snapshot`` and runs
``core.engine.compute_risk_figure`` on the result) to produce a real,
jointly-simulated hypothetical figure. See repo-root ``CLAUDE.md``
principles 1, 2, and 7.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable
from core.optimizer import Control, compare_hypothetical


def _to_control(raw: dict[str, Any]) -> Control:
    """Build a ``core.optimizer.Control`` from one untrusted tool argument."""
    if not isinstance(raw, dict) or not raw.get("control_id") or not raw.get("control_category"):
        raise ValueError("every hypothetical control needs a control_id and a control_category")
    affected = raw.get("affected_asset_ids")
    if not isinstance(affected, list) or not all(isinstance(a, str) for a in affected):
        raise ValueError(
            f"hypothetical control {raw.get('control_id')!r} needs affected_asset_ids as a "
            "list of asset_id strings — call get_control_posture to find them"
        )
    finding_id = raw.get("finding_id")
    service_id = raw.get("service_id")
    return Control(
        control_id=str(raw["control_id"]),
        control_category=str(raw["control_category"]),
        estimated_cost_inr=float(raw.get("estimated_cost_inr") or 0.0),
        affected_asset_ids=list(affected),
        finding_id=str(finding_id) if finding_id else None,
        service_id=str(service_id) if service_id else None,
    )


def simulate_scenario(hypothetical_controls: list[dict[str, Any]]) -> dict[str, Any]:
    """Simulate the effect of a hypothetical set of controls on current risk.

    Args:
        hypothetical_controls: Structured control descriptions (matching
            ``core.optimizer.Control``) representing a "what if we did X"
            question from the user — not necessarily anything under
            active consideration in a real budget.

    Returns:
        A structured dict with the baseline and post-hypothetical
        ``core.engine.RiskFigure`` fields (via a real joint re-simulation),
        the changes between them as ``core.optimizer`` computed them, plus
        the ``snapshot_id`` used. The baseline is re-simulated on the same
        random draws as the hypothetical, so it can differ slightly from
        ``get_exposure``'s figure for the same snapshot.

    Raises:
        ValueError: If a control is malformed, targets no or unknown
            assets, or has a category the optimizer cannot apply.

    Must never:
        Estimate the effect of the hypothetical controls via any means
        other than an actual call into
        ``core.optimizer.apply_controls_to_snapshot`` followed by
        ``core.engine.compute_risk_figure`` — never a summed-delta shortcut,
        even for a "quick" what-if question. See principle 7.
    """
    snapshot = current_snapshot_or_unavailable()
    controls = [_to_control(raw) for raw in hypothetical_controls]
    comparison = compare_hypothetical(snapshot, controls)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "hypothetical_controls": [asdict(control) for control in comparison.controls],
        "baseline": asdict(comparison.baseline_risk_figure),
        "hypothetical": asdict(comparison.hypothetical_risk_figure),
        "expected_annual_loss_change_inr": comparison.expected_annual_loss_change_inr,
        "value_at_risk_change_inr": comparison.value_at_risk_change_inr,
    }
