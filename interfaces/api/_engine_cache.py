"""Remembered engine output for committed snapshots, shared by the API's read routes.

A committed snapshot is immutable and its ``snapshot_id`` is a hash of its
content (principle 5), and the engine's default seed is derived from that
same content, so ``core.engine`` run twice on one committed snapshot returns
the same figure both times. This module lets a route compute that figure
once per ``snapshot_id`` instead of once per request: a cached response is
identical to a recomputed one, and a new current snapshot has a new id, so
nothing here can ever serve a figure for a snapshot that is not the one
asked about.

Keys must only ever be built from a snapshot loaded from the store. The
optimizer and the what-if routes run the engine on modified *copies* of a
snapshot that keep the original ``snapshot_id``; those must never be cached
here, which is why this lives in ``interfaces/api/`` beside the routes that
load committed snapshots, and not in ``core/``.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import TypeVar

T = TypeVar("T")

#: Most remembered responses kept at once, across every kind of key. A
#: memory bound (a handful of routes, times the current snapshot plus its
#: history), not a modelling constant.
DEFAULT_MAX_ENTRIES = 128


class EngineCache:
    """A bounded, thread-safe, single-flight memo of computed responses.

    Single-flight: when several requests miss the same key at once, one
    computes and the rest wait for its result, so a cold page that fires
    six requests (or two tabs opening the same page) never runs the same
    simulation twice.
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[Hashable, object] = OrderedDict()
        self._lock = threading.Lock()
        self._key_locks: dict[Hashable, threading.Lock] = {}

    def get_or_compute(
        self,
        key: Hashable,
        compute: Callable[[], T],
        *,
        cacheable: Callable[[T], bool] | None = None,
    ) -> T:
        """Return the remembered value for ``key``, computing it on a miss.

        Args:
            key: Must include the ``snapshot_id`` of a committed snapshot
                (and anything else the value depends on).
            compute: Produces the value. An exception propagates and nothing
                is remembered, so an error response is never cached.
            cacheable: Optional check on a freshly computed value; when it
                returns False the value is returned but not remembered.

        Returns:
            The remembered or freshly computed value.
        """
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]  # type: ignore[return-value]
            key_lock = self._key_locks.setdefault(key, threading.Lock())

        with key_lock:
            with self._lock:
                if key in self._entries:
                    self._entries.move_to_end(key)
                    return self._entries[key]  # type: ignore[return-value]
            try:
                value = compute()
            finally:
                with self._lock:
                    self._key_locks.pop(key, None)
            if cacheable is None or cacheable(value):
                with self._lock:
                    self._entries[key] = value
                    self._entries.move_to_end(key)
                    while len(self._entries) > self._max_entries:
                        self._entries.popitem(last=False)
            return value

    def clear(self) -> None:
        """Forget every remembered value (for tests)."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


#: The process-wide cache the API routes share.
ENGINE_CACHE = EngineCache()
