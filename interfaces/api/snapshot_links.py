"""Short-lived signed download links for published snapshots.

The scheduled-ingest workflow publishes the snapshot store to S3. This module lets a client
(the dashboard's server side, an analyst's script) fetch a snapshot's raw JSON *directly from
S3* through a pre-signed URL, without the API relaying or storing the bytes:

    GET /snapshots                          list published snapshots (newest first)
    GET /snapshots/{snapshot_id}/download-url   a signed URL for one snapshot ("current" allowed)

A signed URL is a bearer credential and snapshots hold real telemetry (IPs, ARNs, account id),
so this is deliberately locked down:

* Secure by default: unless ``SNAPSHOT_LINKS_TOKEN`` is set, every route refuses (403). When it
  is set, the caller must send it as ``X-Suraksha-Token`` (compared in constant time).
* Only snapshot objects can be signed. ``snapshot_id`` must be ``current`` or match
  ``sha256:<64 hex>``; it is mapped to a key here and never used as a raw path, so a caller
  cannot sign an arbitrary key in the bucket.
* Links expire quickly (default 5 minutes, hard cap 1 hour).

Needs only ``s3:ListBucket`` / ``s3:GetObject`` on the snapshot prefix, which the read-only
``suraksha-api-reader`` user already has. For a *browser* to fetch a signed URL directly, the
bucket also needs a CORS rule allowing GET from the dashboard's origin (see the API README).
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_BUCKET_ENV = "SNAPSHOT_S3_BUCKET"
_PREFIX_ENV = "SNAPSHOT_S3_PREFIX"
_TOKEN_ENV = "SNAPSHOT_LINKS_TOKEN"
_EXPIRY_ENV = "SNAPSHOT_URL_EXPIRY_SECONDS"
_TOKEN_HEADER = "X-Suraksha-Token"

#: How long a signed link lives unless overridden. Operational security setting, not a
#: modelling constant: long enough to start a download, short enough that a leaked link is
#: nearly worthless.
DEFAULT_EXPIRY_SECONDS = 300
_MIN_EXPIRY_SECONDS = 30
_MAX_EXPIRY_SECONDS = 3600

_CURRENT = "current"
_SNAPSHOT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


def _prefix() -> str:
    prefix = os.environ.get(_PREFIX_ENV, "snapshots/")
    return prefix if prefix.endswith("/") else prefix + "/"


def _expiry_seconds() -> int:
    raw = os.environ.get(_EXPIRY_ENV)
    seconds = int(raw) if raw else DEFAULT_EXPIRY_SECONDS
    return max(_MIN_EXPIRY_SECONDS, min(seconds, _MAX_EXPIRY_SECONDS))


def _client() -> Any:
    # SigV4 with an explicit region: the bucket's region must match or S3 answers a redirect
    # that a pre-signed URL cannot follow.
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
    return boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))


def key_for(snapshot_id: str, prefix: str) -> str:
    """Map a ``snapshot_id`` to its S3 key, or raise ``ValueError`` if it is not valid.

    Must never:
        Build a key from anything but ``current`` or a strictly-validated content-hash id.
    """
    if snapshot_id == _CURRENT:
        return f"{prefix}current.json"
    if _SNAPSHOT_ID.fullmatch(snapshot_id):
        return f"{prefix}history/{snapshot_id}.json"
    raise ValueError("snapshot_id must be 'current' or 'sha256:<64 hex characters>'")


def list_snapshots(bucket: str, prefix: str, client: Any) -> list[dict[str, Any]]:
    """List published history snapshots, newest first.

    Returns:
        ``{"snapshot_id", "last_modified", "size_bytes"}`` per object under
        ``<prefix>history/``. ``last_modified`` is when the object reached S3, which is when
        the snapshot was published, not the snapshot's own ``observed_at``.
    """
    history = f"{prefix}history/"
    found: list[dict[str, Any]] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=history):
        for obj in page.get("Contents", []):
            name = obj["Key"][len(history) :]
            snapshot_id = name[: -len(".json")] if name.endswith(".json") else ""
            if _SNAPSHOT_ID.fullmatch(snapshot_id):
                found.append(
                    {
                        "snapshot_id": snapshot_id,
                        "last_modified": obj["LastModified"].isoformat(),
                        "size_bytes": obj["Size"],
                    }
                )
    return sorted(found, key=lambda item: item["last_modified"], reverse=True)


def presign_snapshot(
    bucket: str, prefix: str, snapshot_id: str, expires_seconds: int, client: Any
) -> dict[str, Any]:
    """Return a signed GET URL for one snapshot object.

    Raises:
        ValueError: If ``snapshot_id`` is not valid (see :func:`key_for`).
        LookupError: If that snapshot does not exist in the bucket.
    """
    key = key_for(snapshot_id, prefix)
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise LookupError(snapshot_id) from exc
        raise
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key, "ResponseContentType": "application/json"},
        ExpiresIn=expires_seconds,
    )
    return {"snapshot_id": snapshot_id, "url": url, "expires_in_seconds": expires_seconds}


def register_snapshot_link_routes(app: Any) -> None:
    """Register ``/snapshots`` and ``/snapshots/{snapshot_id}/download-url`` on ``app``."""
    from fastapi import Header, HTTPException

    def authorize(supplied: str | None) -> tuple[str, str]:
        bucket = os.environ.get(_BUCKET_ENV)
        if not bucket:
            raise HTTPException(status_code=503, detail="snapshot storage is not configured")
        expected = os.environ.get(_TOKEN_ENV)
        if not expected:
            raise HTTPException(
                status_code=403, detail=f"{_TOKEN_ENV} is not set; signed links are disabled"
            )
        if supplied is None or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail=f"missing or invalid {_TOKEN_HEADER}")
        return bucket, _prefix()

    def list_route(
        x_suraksha_token: str | None = Header(default=None, alias=_TOKEN_HEADER),
    ) -> dict[str, Any]:
        bucket, prefix = authorize(x_suraksha_token)
        return {"snapshots": list_snapshots(bucket, prefix, _client())}

    def url_route(
        snapshot_id: str,
        x_suraksha_token: str | None = Header(default=None, alias=_TOKEN_HEADER),
    ) -> dict[str, Any]:
        bucket, prefix = authorize(x_suraksha_token)
        try:
            return presign_snapshot(bucket, prefix, snapshot_id, _expiry_seconds(), _client())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="no such snapshot") from exc

    app.get("/snapshots")(list_route)
    app.get("/snapshots/{snapshot_id}/download-url")(url_route)
