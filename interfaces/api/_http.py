"""HTTP plumbing shared by every route module in ``interfaces/api/``.

Nothing here computes anything: it turns "there is no figure" and "the
request was wrong" into the status codes the dashboard contract in
``interfaces/dashboard/README.md`` relies on — 404/409/501 mean *nothing to
show*, never a zero; any other non-2xx is a real failure.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ai.tool_registry import ToolExecution
from core.snapshot_store import load_current_snapshot

#: Matches SNAPSHOT_STORE_PATH's default in .env.example.
_DEFAULT_SNAPSHOT_STORE_PATH = "./data/snapshots"

#: The ``detail`` of every 404 raised because nothing has been committed.
NO_SNAPSHOT_DETAIL = (
    "No snapshot has been committed yet. Run `cypher ingest` so a candidate "
    "snapshot can pass the five quality gates and become current."
)


def snapshot_store_path() -> Path:
    """The snapshot store root, from ``SNAPSHOT_STORE_PATH``."""
    return Path(os.environ.get("SNAPSHOT_STORE_PATH", _DEFAULT_SNAPSHOT_STORE_PATH))


def current_snapshot_or_404() -> dict[str, Any]:
    """Return the current committed snapshot, or raise HTTP 404 if there is none.

    Must never:
        Fall back to a sample fixture, an empty snapshot, or a previously
        superseded one — no committed snapshot means there is nothing to
        show, and the caller must be told exactly that.
    """
    from fastapi import HTTPException

    snapshot = load_current_snapshot(snapshot_store_path())
    if snapshot is None:
        raise HTTPException(status_code=404, detail=NO_SNAPSHOT_DETAIL)
    return snapshot


def execution_to_response(execution: ToolExecution) -> dict[str, Any]:
    """Turn a tool execution into a JSON body, or raise the matching HTTP error.

    ``ok`` becomes the body; ``unavailable`` (the computation cannot run
    yet) becomes 501; ``error`` (it ran and rejected the request or
    failed) becomes 400 carrying the tool's own detail.
    """
    from fastapi import HTTPException

    if execution.status == "ok":
        return execution.result or {}
    if execution.status == "unavailable":
        raise HTTPException(status_code=501, detail=execution.detail)
    raise HTTPException(status_code=400, detail=execution.detail)
