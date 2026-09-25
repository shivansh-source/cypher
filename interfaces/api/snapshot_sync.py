"""Keep the API host's local snapshot store in step with the one published to S3.

The daily ``scheduled-ingest`` workflow commits snapshots and publishes the snapshot store
(``current.json`` + ``history/``) under an S3 prefix. An API host has no shared disk, so it
pulls that prefix into ``SNAPSHOT_STORE_PATH`` at start-up and then periodically. Everything
else (``core.snapshot_store``'s readers) keeps reading a plain local directory unchanged.

Inactive unless ``SNAPSHOT_S3_BUCKET`` is set, so local development is unaffected.

Download-only by design: this module never uploads or deletes anything, and never rewrites a
history file that already exists locally (history is immutable, repo-root ``CLAUDE.md``
principle 5).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3

from interfaces.api._http import snapshot_store_path

_BUCKET_ENV = "SNAPSHOT_S3_BUCKET"
_PREFIX_ENV = "SNAPSHOT_S3_PREFIX"
_INTERVAL_ENV = "SNAPSHOT_SYNC_INTERVAL_SECONDS"

#: Key prefix the workflow publishes the snapshot store under.
DEFAULT_PREFIX = "snapshots/"

#: How often the background thread re-checks S3. An operational polling interval (snapshots
#: change about once a day), not a modelling constant.
DEFAULT_INTERVAL_SECONDS = 300

_CURRENT_FILENAME = "current.json"

_logger = logging.getLogger(__name__)
_status: dict[str, Any] = {"enabled": False, "last_success_at": None, "last_error": None}


def sync_status() -> dict[str, Any]:
    """The last sync outcome, for a health/diagnostics route (a copy, safe to mutate)."""
    return dict(_status)


def sync_once(bucket: str, prefix: str, dest: Path, client: Any | None = None) -> int:
    """Download new snapshot-store objects from ``s3://bucket/prefix`` into ``dest``.

    Args:
        bucket: Source bucket.
        prefix: Key prefix of the published snapshot store (e.g. ``"snapshots/"``).
        dest: Local snapshot store root.
        client: An S3 client (defaults to ``boto3.client("s3")``); injectable for tests.

    Returns:
        How many objects were downloaded.

    Must never:
        Overwrite an existing ``history/`` file (immutable), write outside ``dest``, or leave
        a half-written file in place (each download lands in a temp file, then is renamed).
        ``current.json`` is downloaded last, so it can never reference a history entry that
        has not arrived yet.
    """
    s3 = client if client is not None else boto3.client("s3")
    root = dest.resolve()

    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    relative = [key[len(prefix) :] for key in keys if key[len(prefix) :] and not key.endswith("/")]
    relative.sort(key=lambda rel: rel == _CURRENT_FILENAME)  # current.json last

    downloaded = 0
    for rel in relative:
        target = (root / rel).resolve()
        if root not in target.parents:
            raise ValueError(f"refusing to write outside the snapshot store: {rel!r}")
        if target.exists() and rel != _CURRENT_FILENAME:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        s3.download_file(bucket, prefix + rel, str(partial))
        os.replace(partial, target)
        downloaded += 1
    return downloaded


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
    bucket = os.environ.get(_BUCKET_ENV)
    if not bucket:
        return False
    prefix = os.environ.get(_PREFIX_ENV, DEFAULT_PREFIX)
    if not prefix.endswith("/"):
        prefix += "/"
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
