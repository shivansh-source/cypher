"""Mirror the snapshot store the ``scheduled-ingest`` workflow publishes to S3 into a local directory.

Shared by the hosted API (``interfaces/api/snapshot_sync.py``, which re-syncs on a timer) and
the CLI (``cypher plan``, which syncs once before reading its baseline). Everything else keeps
reading a plain local directory through ``core.snapshot_store``.

Configured by ``SNAPSHOT_S3_BUCKET`` (the bucket the workflow publishes to) and optionally
``SNAPSHOT_S3_PREFIX``; with no bucket set nothing here touches the network.

Download-only by design: this module never uploads or deletes anything, and never rewrites a
history file that already exists locally (history is immutable, repo-root ``CLAUDE.md``
principle 5).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import boto3

BUCKET_ENV = "SNAPSHOT_S3_BUCKET"
PREFIX_ENV = "SNAPSHOT_S3_PREFIX"

#: Key prefix the workflow publishes the snapshot store under.
DEFAULT_PREFIX = "snapshots/"

_CURRENT_FILENAME = "current.json"


def s3_source_from_env() -> tuple[str, str] | None:
    """``(bucket, prefix)`` from the environment, prefix ending in ``/``; None if no bucket is set."""
    bucket = os.environ.get(BUCKET_ENV)
    if not bucket:
        return None
    prefix = os.environ.get(PREFIX_ENV) or DEFAULT_PREFIX
    if not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


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
