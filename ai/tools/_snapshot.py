"""Shared "load the current committed snapshot" helper for ``ai/tools/*``.

Not itself a registered tool — every tool wrapper that needs the current
snapshot imports :func:`current_snapshot_or_unavailable` from here rather
than reading ``SNAPSHOT_STORE_PATH`` and calling
``core.snapshot_store.load_current_snapshot`` inline, so "no snapshot
committed yet" is reported identically (as ``NotImplementedError``, which
``ai.tool_registry.execute_tool`` turns into a structured "unavailable"
result — see repo-root ``CLAUDE.md`` principles 1 and 2) across every tool.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.snapshot_store import load_current_snapshot

#: Matches SNAPSHOT_STORE_PATH's default in .env.example.
_DEFAULT_SNAPSHOT_STORE_PATH = "./data/snapshots"


def current_snapshot_or_unavailable() -> dict[str, Any]:
    """Return the current committed snapshot.

    Returns:
        The current committed, schema-shaped aggregated snapshot.

    Raises:
        NotImplementedError: If no snapshot has ever been committed —
            dispatches to ``ai.tool_registry.execute_tool``'s
            ``status="unavailable"`` path, never a fabricated or empty
            result.
    """
    store_path = Path(os.environ.get("SNAPSHOT_STORE_PATH", _DEFAULT_SNAPSHOT_STORE_PATH))
    snapshot = load_current_snapshot(store_path)
    if snapshot is None:
        raise NotImplementedError("no snapshot has been committed yet")
    return snapshot
