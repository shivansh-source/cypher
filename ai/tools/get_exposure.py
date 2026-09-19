"""Tool: report current risk exposure (EAL/VaR) for the whole estate or a scope.

This function does not compute anything itself; it delegates to
``core.engine.compute_risk_figure`` against the current committed snapshot
and returns structured output with provenance (which snapshot_id the figure
came from). See repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

from typing import Any


def get_exposure(scope: str | None = None) -> dict[str, Any]:
    """Return the current Expected Annual Loss and Value at Risk.

    Args:
        scope: Optional filter (e.g. a service_id or asset_id) to restrict
            the figure to a subset of the estate. None means the whole
            current snapshot.

    Returns:
        A structured dict containing the relevant fields of a
        ``core.engine.RiskFigure``, plus the ``snapshot_id`` it was
        computed from, so the caller (``ai/llm_client.py``'s narration
        path) has ground truth to verify against via
        ``ai.numeric_guard``.

    Must never:
        Compute or approximate a figure itself — this function's entire
        body is a call into ``core.engine`` (and, for scoping, whatever
        snapshot-filtering utility exists there) plus reshaping the result.
    """
    raise NotImplementedError
