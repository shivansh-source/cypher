"""Fill ``interfaces.api._engine_cache`` for each new current snapshot, off the request path.

The figures behind the dashboard's pages are remembered per ``snapshot_id``,
but the first request for a new snapshot still pays for them (the priority
plan alone is several seconds of Monte Carlo). A daemon thread watches the
store's current snapshot and, whenever its id changes (start-up, a
``cypher ingest``, an S3 sync), calls the read routes' own handlers once, so
the cache holds exactly what those routes would compute.

Off when ``ENGINE_CACHE_WARMUP=0``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from core.snapshot_store import load_current_snapshot
from interfaces.api._http import snapshot_store_path

_ENABLED_ENV = "ENGINE_CACHE_WARMUP"

#: How often the warmer checks whether the current snapshot changed. An
#: operational polling interval (snapshots change about once a day), not a
#: modelling constant.
POLL_INTERVAL_SECONDS = 30

_logger = logging.getLogger(__name__)


def warm_once(handlers: Sequence[Callable[[], Any]], last_snapshot_id: str | None) -> str | None:
    """Run every handler once if the current snapshot is new.

    Args:
        handlers: Zero-argument route handlers whose results are cached.
        last_snapshot_id: The id warmed last time, or None.

    Returns:
        The current snapshot's id (or None when there is none), for the next call.

    Must never:
        Raise: a failing handler is logged and the rest still run, because a
        warm-up failure must not stop the API, and the route will report the
        same failure properly when a user asks.
    """
    try:
        current = load_current_snapshot(snapshot_store_path())
    except Exception as exc:  # noqa: BLE001 - an unreadable store is the routes' to report
        _logger.warning("cache warm-up could not read the snapshot store: %s", exc)
        return last_snapshot_id
    if current is None or current["snapshot_id"] == last_snapshot_id:
        return None if current is None else last_snapshot_id
    for handler in handlers:
        try:
            handler()
        except Exception as exc:  # noqa: BLE001 - see Must never
            _logger.warning("cache warm-up handler failed: %s", exc)
    return str(current["snapshot_id"])


def start_cache_warmer(handlers: Sequence[Callable[[], Any]]) -> bool:
    """Start the warm-up daemon thread unless ``ENGINE_CACHE_WARMUP=0``.

    Returns:
        Whether the thread was started.
    """
    if os.environ.get(_ENABLED_ENV) == "0":
        return False

    def run() -> None:
        last: str | None = None
        while True:
            last = warm_once(handlers, last)
            time.sleep(POLL_INTERVAL_SECONDS)

    threading.Thread(target=run, name="engine-cache-warmer", daemon=True).start()
    return True
