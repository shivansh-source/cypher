"""Tests for core/snapshot_store.py's save/load persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.snapshot_store import load_current_snapshot, save_snapshot

_SNAPSHOT: dict[str, Any] = {
    "snapshot_id": "sha256:abc123",
    "observed_at": "2026-09-23T00:00:00+00:00",
    "valid_from": "2026-09-23T00:00:00+00:00",
    "valid_to": None,
    "assets": [],
}


def test_load_current_snapshot_returns_none_when_store_missing(tmp_path: Path) -> None:
    """A store directory that has never been written to has no current snapshot."""
    assert load_current_snapshot(tmp_path / "does-not-exist") is None


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """A saved snapshot must be loadable back as current, unchanged."""
    save_snapshot(tmp_path, _SNAPSHOT)

    loaded = load_current_snapshot(tmp_path)

    assert loaded == _SNAPSHOT


def test_save_writes_immutable_history_file(tmp_path: Path) -> None:
    """Every save must append an immutable history file keyed by snapshot_id."""
    save_snapshot(tmp_path, _SNAPSHOT)

    history_file = tmp_path / "history" / f"{_SNAPSHOT['snapshot_id']}.json"
    assert history_file.exists()


def test_save_supersedes_current_but_keeps_prior_history(tmp_path: Path) -> None:
    """Saving a second snapshot must update current.json but keep the first snapshot's history file."""
    first = dict(_SNAPSHOT)
    save_snapshot(tmp_path, first)

    second = {**_SNAPSHOT, "snapshot_id": "sha256:def456"}
    save_snapshot(tmp_path, second)

    assert load_current_snapshot(tmp_path) == second
    assert (tmp_path / "history" / "sha256:abc123.json").exists()
    assert (tmp_path / "history" / "sha256:def456.json").exists()
