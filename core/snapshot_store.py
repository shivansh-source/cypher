"""Persistence for the current committed snapshot and its immutable history.

``core/snapshot.py`` owns snapshot lifecycle *logic* (the quality gates,
``validate_snapshot``, ``commit_snapshot``) and does no file I/O itself —
this module is the thin I/O adapter that writes a committed snapshot to
disk and reads the current one (and the history behind it) back. Kept in
``core/`` (rather than ``interfaces/``) so ``ai/tools/*`` — which may import ``core/`` but never
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
from datetime import UTC, datetime
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


def _observed_at(snapshot: dict[str, Any]) -> datetime:
    """Parse ``observed_at``, reading a timestamp with no offset as UTC.

    Normalizing to aware datetimes keeps a naive and an offset timestamp
    comparable instead of raising mid-sort.
    """
    parsed = datetime.fromisoformat(snapshot["observed_at"])
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def load_snapshot_history(store_path: Path) -> list[dict[str, Any]]:
    """Load every snapshot ever committed, oldest first.

    Args:
        store_path: Root directory of the snapshot store.

    Returns:
        Every file under ``history/``, exactly as committed, ordered by
        ``observed_at`` ascending (ties broken by ``snapshot_id`` so the
        order is stable). Empty if nothing has been committed yet.

    Raises:
        ValueError: If a history file's ``observed_at`` is not an ISO 8601
            timestamp — history is audit data, so a malformed entry is
            reported rather than silently dropped or misordered.
    """
    history_dir = store_path / _HISTORY_DIRNAME
    if not history_dir.is_dir():
        return []
    snapshots: list[dict[str, Any]] = [
        json.loads(path.read_text()) for path in sorted(history_dir.glob("*.json"))
    ]
    return sorted(
        snapshots,
        key=lambda snapshot: (_observed_at(snapshot), snapshot["snapshot_id"]),
    )


def load_predecessor_snapshot(store_path: Path, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Load the committed snapshot that ``snapshot`` superseded, if any.

    Args:
        store_path: Root directory of the snapshot store.
        snapshot: A committed snapshot present in the store's history.

    Returns:
        Among every other history entry observed at or before ``snapshot``,
        the one committed most recently, or None if there is none. Commit
        order is read from each history file's modification time, which
        :func:`save_snapshot` sets once and never rewrites; it breaks ties
        between snapshots with the same ``observed_at``, which a strict
        "observed earlier" rule would silently treat as "no predecessor".
    """
    history_dir = store_path / _HISTORY_DIRNAME
    if not history_dir.is_dir():
        return None
    observed_at = _observed_at(snapshot)
    candidates: list[tuple[datetime, float, dict[str, Any]]] = []
    for path in history_dir.glob("*.json"):
        candidate: dict[str, Any] = json.loads(path.read_text())
        if candidate["snapshot_id"] == snapshot["snapshot_id"]:
            continue
        candidate_observed_at = _observed_at(candidate)
        if candidate_observed_at <= observed_at:
            candidates.append((candidate_observed_at, path.stat().st_mtime, candidate))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]
