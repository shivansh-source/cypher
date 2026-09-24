"""Tests for core/snapshot_store.py's save/load persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.snapshot_store import (
    load_current_snapshot,
    load_predecessor_snapshot,
    load_snapshot_history,
    save_snapshot,
)

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


def _snapshot_at(snapshot_id: str, observed_at: str) -> dict[str, Any]:
    return {**_SNAPSHOT, "snapshot_id": snapshot_id, "observed_at": observed_at}


def test_history_is_empty_for_a_store_never_written_to(tmp_path: Path) -> None:
    assert load_snapshot_history(tmp_path / "does-not-exist") == []


def test_history_is_ordered_by_observed_at_not_by_filename(tmp_path: Path) -> None:
    """Content-hash ids sort arbitrarily; history order must come from observed_at."""
    later = _snapshot_at("sha256:aaa", "2026-09-22T00:00:00Z")
    earlier = _snapshot_at("sha256:zzz", "2026-09-01T00:00:00+00:00")
    save_snapshot(tmp_path, earlier)
    save_snapshot(tmp_path, later)

    history = load_snapshot_history(tmp_path)

    assert [s["snapshot_id"] for s in history] == ["sha256:zzz", "sha256:aaa"]


def test_history_orders_naive_and_offset_timestamps_together(tmp_path: Path) -> None:
    save_snapshot(tmp_path, _snapshot_at("sha256:b", "2026-09-02T00:00:00"))
    save_snapshot(tmp_path, _snapshot_at("sha256:a", "2026-09-01T00:00:00Z"))

    assert [s["snapshot_id"] for s in load_snapshot_history(tmp_path)] == [
        "sha256:a",
        "sha256:b",
    ]


def test_predecessor_is_the_latest_snapshot_observed_before(tmp_path: Path) -> None:
    first = _snapshot_at("sha256:1", "2026-09-01T00:00:00Z")
    second = _snapshot_at("sha256:2", "2026-09-08T00:00:00Z")
    third = _snapshot_at("sha256:3", "2026-09-15T00:00:00Z")
    for snapshot in (first, second, third):
        save_snapshot(tmp_path, snapshot)

    assert load_predecessor_snapshot(tmp_path, third) == second
    assert load_predecessor_snapshot(tmp_path, first) is None


def test_predecessor_with_identical_observed_at_is_still_found(tmp_path: Path) -> None:
    """Two snapshots observed at the same instant: the other one is the predecessor."""
    first = _snapshot_at("sha256:1", "2026-09-01T00:00:00Z")
    second = _snapshot_at("sha256:2", "2026-09-01T00:00:00Z")
    save_snapshot(tmp_path, first)
    save_snapshot(tmp_path, second)

    assert load_predecessor_snapshot(tmp_path, second) == first
