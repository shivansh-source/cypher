"""Tool: report current risk exposure (EAL/VaR) for the whole estate or a scope.

This function does not compute anything itself; it delegates to
``core.engine.compute_risk_figure`` against the current committed snapshot
and returns structured output with provenance (which snapshot_id the figure
came from). See repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable
from core.engine import compute_risk_figure

#: Same default as get_top_contributors.py's `limit`. core.engine.RiskFigure's
#: top_contributors is the dashboard's contract and lists every loss-event scenario
#: uncapped — on an estate with many findings that is large enough, once serialized into
#: the conversation, to exceed Groq's free-tier tokens-per-minute limit on its own. This
#: tool only needs enough contributors to narrate what drives the figure; a caller that
#: wants the full ranked breakdown should use get_top_contributors instead.
MAX_NARRATED_CONTRIBUTORS = 10


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
        ``ai.numeric_guard``. ``top_contributors`` is truncated to
        ``MAX_NARRATED_CONTRIBUTORS`` (already ranked largest-first by
        ``core.engine``); use ``get_top_contributors`` for the full breakdown.

    Must never:
        Compute or approximate a figure itself — this function's entire
        body is a call into ``core.engine`` (and, for scoping, whatever
        snapshot-filtering utility exists there) plus reshaping the result.
    """
    # A blank scope (models sometimes send "" for an optional argument) means
    # the whole estate — filtering on it would silently drop every contributor.
    if scope is not None and not scope.strip():
        scope = None
    snapshot = current_snapshot_or_unavailable()
    risk_figure = compute_risk_figure(snapshot)
    result = asdict(risk_figure)
    if scope is not None:
        result["top_contributors"] = [
            c for c in result["top_contributors"] if c["asset_id"] == scope
        ]
        result["scope"] = scope
    result["top_contributors"] = result["top_contributors"][:MAX_NARRATED_CONTRIBUTORS]
    return result
