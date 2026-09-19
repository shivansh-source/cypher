"""Tool: explain how a previously-shown number was derived.

This function does not compute anything itself; it looks up the
computation trail (scenario parameters, assumptions used, snapshot) behind
an already-produced figure. See repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

from typing import Any


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
    raise NotImplementedError
