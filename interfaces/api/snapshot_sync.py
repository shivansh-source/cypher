"""Keep the API host's local snapshot store in step with the one published to S3.

The daily ``scheduled-ingest`` workflow commits snapshots and publishes the snapshot store
(``current.json`` + ``history/``) under an S3 prefix. An API host has no shared disk, so it
pulls that prefix into ``SNAPSHOT_STORE_PATH`` at start-up and then periodically. Everything
else (``core.snapshot_store``'s readers) keeps reading a plain local directory unchanged.

Inactive unless ``SNAPSHOT_S3_BUCKET`` is set, so local development is unaffected. The
download itself (:func:`sync_once`, download-only, history never rewritten) lives in
``interfaces/_snapshot_mirror.py``, shared with ``cypher plan``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from interfaces._snapshot_mirror import DEFAULT_PREFIX, s3_source_from_env, sync_once
from interfaces.api._http import snapshot_store_path

# Re-exported: callers and tests use snapshot_sync.sync_once / DEFAULT_PREFIX.
__all__ = ["DEFAULT_PREFIX", "configure_from_env", "sync_once", "sync_status"]

_INTERVAL_ENV = "SNAPSHOT_SYNC_INTERVAL_SECONDS"

#: How often the background thread re-checks S3. An operational polling interval (snapshots
#: change about once a day), not a modelling constant.
DEFAULT_INTERVAL_SECONDS = 300

_logger = logging.getLogger(__name__)
_status: dict[str, Any] = {"enabled": False, "last_success_at": None, "last_error": None}


def sync_status() -> dict[str, Any]:
    """The last sync outcome, for a health/diagnostics route (a copy, safe to mutate)."""
    return dict(_status)


def _run(bucket: str, prefix: str, dest: Path, interval_seconds: int) -> None:
    """Sync forever, recording each outcome; a failure never stops the loop."""
    while True:
        try:
            sync_once(bucket, prefix, dest)
            _status["last_success_at"] = datetime.now(UTC).isoformat()
            _status["last_error"] = None
        except Exception as exc:  # noqa: BLE001 - network/credential errors must not kill the API
            _status["last_error"] = f"{type(exc).__name__}: {exc}"
            _logger.warning("snapshot sync failed: %s", exc)
        time.sleep(interval_seconds)


def configure_from_env() -> bool:
    """Start syncing if ``SNAPSHOT_S3_BUCKET`` is set; otherwise do nothing.

    Runs one sync immediately (so the first request already sees data when S3 is reachable),
    then keeps a daemon thread polling. A failed first sync is recorded, not raised: the API
    still starts and serves whatever the local store holds, and the failure shows in
    :func:`sync_status`.

    Returns:
        Whether syncing was enabled.
    """
    source = s3_source_from_env()
    if source is None:
        return False
    bucket, prefix = source
    interval = int(os.environ.get(_INTERVAL_ENV, DEFAULT_INTERVAL_SECONDS))
    dest = snapshot_store_path()

    _status["enabled"] = True
    try:
        sync_once(bucket, prefix, dest)
        _status["last_success_at"] = datetime.now(UTC).isoformat()
    except Exception as exc:  # noqa: BLE001 - a failed first sync must not stop the API starting
        _status["last_error"] = f"{type(exc).__name__}: {exc}"
        _logger.warning("initial snapshot sync failed: %s", exc)

    threading.Thread(
        target=_run, args=(bucket, prefix, dest, interval), name="snapshot-sync", daemon=True
    ).start()
    return True
