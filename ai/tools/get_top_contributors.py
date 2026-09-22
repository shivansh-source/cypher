"""Tool: report the top contributors to current expected annual loss.

This function does not compute anything itself; it delegates to
``core.engine.compute_risk_figure`` and returns its
``top_contributors`` field with provenance. See repo-root ``CLAUDE.md``
principles 1 and 2.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable
from core.engine import compute_risk_figure


def get_top_contributors(limit: int = 10) -> dict[str, Any]:
    """Return the top loss-event scenarios ranked by contribution to EAL.

    Args:
        limit: Maximum number of contributors to return, largest first.

    Returns:
        A structured dict containing up to ``limit`` entries from a
        ``core.engine.RiskFigure.top_contributors``, plus the
        ``snapshot_id`` the figure was computed from.

    Must never:
        Re-rank, filter, or otherwise reinterpret the contributors beyond
        truncating to ``limit`` — the ranking comes entirely from
        ``core.engine``.
    """
    snapshot = current_snapshot_or_unavailable()
    risk_figure = compute_risk_figure(snapshot)
    return {
        "snapshot_id": risk_figure.snapshot_id,
        "top_contributors": [asdict(c) for c in risk_figure.top_contributors[:limit]],
    }
