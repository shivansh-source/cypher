"""Tool: run a hypothetical what-if scenario through the real engine.

This function does not compute anything itself; it delegates to
``core.optimizer.apply_controls_to_snapshot`` and
``core.engine.compute_risk_figure`` to produce a real, jointly-simulated
hypothetical figure. See repo-root ``CLAUDE.md`` principles 1, 2, and 7.
"""

from __future__ import annotations

from typing import Any


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
        plus the ``snapshot_id`` used.

    Must never:
        Estimate the effect of the hypothetical controls via any means
        other than an actual call into
        ``core.optimizer.apply_controls_to_snapshot`` followed by
        ``core.engine.compute_risk_figure`` — never a summed-delta shortcut,
        even for a "quick" what-if question. See principle 7.
    """
    raise NotImplementedError
