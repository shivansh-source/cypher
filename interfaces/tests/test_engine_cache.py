"""Tests for interfaces/api/_engine_cache.py and interfaces/api/_cache_warmer.py (pure logic)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from core.snapshot_store import save_snapshot
from interfaces.api._cache_warmer import warm_once
from interfaces.api._engine_cache import EngineCache


def test_computes_once_per_key_and_recomputes_for_a_new_key() -> None:
    cache = EngineCache()
    calls: list[str] = []

    def compute(value: str) -> str:
        calls.append(value)
        return value.upper()

    assert cache.get_or_compute(("figure", "sha256:a"), lambda: compute("a")) == "A"
    assert cache.get_or_compute(("figure", "sha256:a"), lambda: compute("a")) == "A"
    assert cache.get_or_compute(("figure", "sha256:b"), lambda: compute("b")) == "B"
    assert calls == ["a", "b"]


def test_evicts_the_least_recently_used_entry() -> None:
    cache = EngineCache(max_entries=2)
    cache.get_or_compute("a", lambda: 1)
    cache.get_or_compute("b", lambda: 2)
    cache.get_or_compute("a", lambda: 99)  # touch "a", so "b" is now the oldest
    cache.get_or_compute("c", lambda: 3)

    assert len(cache) == 2
    assert cache.get_or_compute("a", lambda: 99) == 1
    assert cache.get_or_compute("b", lambda: 22) == 22  # evicted, so recomputed


def test_an_exception_is_never_remembered() -> None:
    cache = EngineCache()

    def fail() -> int:
        raise RuntimeError("engine failed")

    with pytest.raises(RuntimeError):
        cache.get_or_compute("k", fail)
    assert cache.get_or_compute("k", lambda: 7) == 7


def test_a_value_failing_cacheable_is_returned_but_not_remembered() -> None:
    cache = EngineCache()
    result = cache.get_or_compute(
        "k", lambda: {"snapshot_id": "sha256:newer"}, cacheable=lambda r: r["snapshot_id"] == "x"
    )
    assert result == {"snapshot_id": "sha256:newer"}
    assert len(cache) == 0


def test_concurrent_misses_on_one_key_compute_once() -> None:
    cache = EngineCache()
    calls = 0
    calls_lock = threading.Lock()

    def slow() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return "figure"

    results: list[str] = []
    threads = [
        threading.Thread(target=lambda: results.append(cache.get_or_compute("k", slow)))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["figure"] * 8
    assert calls == 1


def _snapshot(snapshot_id: str) -> dict[str, Any]:
    return {"snapshot_id": snapshot_id, "observed_at": "2026-09-29T06:00:00Z"}


def test_warm_once_runs_handlers_only_for_a_new_current_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    calls: list[str] = []
    handlers = [lambda: calls.append("exposure"), lambda: calls.append("plan")]

    assert warm_once(handlers, None) is None  # nothing committed yet
    assert calls == []

    save_snapshot(tmp_path, _snapshot("sha256:one"))
    assert warm_once(handlers, None) == "sha256:one"
    assert warm_once(handlers, "sha256:one") == "sha256:one"  # unchanged: no rerun
    assert calls == ["exposure", "plan"]

    save_snapshot(tmp_path, _snapshot("sha256:two"))
    assert warm_once(handlers, "sha256:one") == "sha256:two"
    assert calls == ["exposure", "plan", "exposure", "plan"]


def test_warm_once_survives_a_failing_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    save_snapshot(tmp_path, _snapshot("sha256:one"))
    calls: list[str] = []

    def broken() -> None:
        raise ValueError("bad snapshot")

    assert warm_once([broken, lambda: calls.append("next")], None) == "sha256:one"
    assert calls == ["next"]
