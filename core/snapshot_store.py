"""Persistence for the current committed snapshot and its immutable history.

``core/snapshot.py`` owns snapshot lifecycle *logic* (the quality gates,
``validate_snapshot``, ``commit_snapshot``) and does no file I/O itself —
this module is the thin I/O adapter that writes a committed snapshot to
disk and reads the current one back. Kept in ``core/`` (rather than
``interfaces/``) so ``ai/tools/*`` — which may import ``core/`` but never
``interfaces/`` per repo-root ``CLAUDE.md``'s module ownership map — can
reach the current snapshot directly.

Layout under ``store_path`` (default ``SNAPSHOT_STORE_PATH``,
``./data/snapshots``):

    current.json           The current committed snapshot.
    history/{snapshot_id}.json
                            Every snapshot ever committed, exactly as
                            committed — including ones since superseded
                            (their ``valid_to`` is set, but the file itself
                            is never rewritten otherwise), matching
                            repo-root ``CLAUDE.md`` principle 5
                            (bitemporal, immutable snapshots).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CURRENT_FILENAME = "current.json"
_HISTORY_DIRNAME = "history"


def save_snapshot(store_path: Path, snapshot: dict[str, Any]) -> None:
    """Persist a just-committed snapshot as current, and append it to history.

    Args:
        store_path: Root directory of the snapshot store.
        snapshot: The committed snapshot (i.e. the return value of
            ``core.snapshot.commit_snapshot``), with ``snapshot_id`` set.

    Must never:
        Overwrite an existing history file for the same ``snapshot_id`` —
        history is append-only and immutable.
    """
    store_path.mkdir(parents=True, exist_ok=True)
    history_dir = store_path / _HISTORY_DIRNAME
    history_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    (store_path / _CURRENT_FILENAME).write_text(payload)

    history_file = history_dir / f"{snapshot['snapshot_id']}.json"
    if not history_file.exists():
        history_file.write_text(payload)


def load_current_snapshot(store_path: Path) -> dict[str, Any] | None:
    """Load the current committed snapshot, if one has ever been committed.

    Args:
        store_path: Root directory of the snapshot store.

    Returns:
        The current snapshot dict, or None if no snapshot has been
        committed yet (e.g. first run, or store directory doesn't exist).
    """
    current_file = store_path / _CURRENT_FILENAME
    if not current_file.exists():
        return None
    result: dict[str, Any] = json.loads(current_file.read_text())
    return result
