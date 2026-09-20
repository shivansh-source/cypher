"""Shared S3 helper for connectors that persist/read raw tool output.

This module is an implementation detail of individual connectors' ``fetch()``
methods, never a connector in its own right: it owns no ``Connector``
subclass, produces no schema-shaped output, and is never registered in
``scan_scope``. Two usage patterns exist in this codebase:

* Connectors that call a live tool API (``wazuh_connector.py``,
  ``greenbone_connector.py``) use :func:`write_raw` to persist what they
  fetched, purely for auditability — write-only from their perspective.
* Connectors whose tool already ran as a one-shot CI scan and pushed its
  output to S3 out-of-band (``prowler_connector.py``,
  ``scoutsuite_connector.py``) use :func:`read_latest` /
  :func:`read_latest_text` as their *entire* ``fetch()`` implementation —
  they never call a live API themselves.

Every function here builds its own ``boto3.client("s3", ...)`` per call
(no shared/global client) specifically so tests can mock ``boto3.client``
with ``unittest.mock.patch`` without needing to reach into module-level
state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import boto3

from infra.connectors import _env

#: Name of the environment variable naming the S3 bucket every connector's
#: raw findings are written to/read from. Operational configuration, not a
#: modelling constant.
RAW_FINDINGS_BUCKET_ENV: str = "RAW_FINDINGS_BUCKET"

#: Name of the environment variable naming the AWS region used for the S3
#: client. Operational configuration, not a modelling constant.
AWS_REGION_ENV: str = "AWS_REGION"

#: Key prefix under which every connector's most recent raw payload is kept,
#: e.g. ``latest/prowler_connector.json``. Operational/layout constant.
_LATEST_KEY_PREFIX: str = "latest"

#: Timestamp format used for the auditability copy of each write, e.g.
#: ``wazuh_connector/20260920T120000Z.json``. Operational layout constant,
#: not a modelling constant.
_TIMESTAMP_FORMAT: str = "%Y%m%dT%H%M%SZ"


class ObjectStoreError(RuntimeError):
    """Raised when a connector cannot write to or read from the raw-findings
    object store.

    Always names the connector involved and the underlying cause (a missing
    environment variable, an S3 failure, a missing/unreadable object, or a
    stale object). Callers must never treat this as "no data" — it must
    propagate so the caller can record the connector under
    ``scan_scope.unreachable_scanners``.
    """


def _bucket_name(connector_name: str) -> str:
    """Read the raw-findings bucket name from the environment.

    Raises:
        ObjectStoreError: If ``RAW_FINDINGS_BUCKET`` is not set.
    """
    bucket = _env.get_optional(RAW_FINDINGS_BUCKET_ENV)
    if not bucket:
        raise ObjectStoreError(
            f"{connector_name}: environment variable {RAW_FINDINGS_BUCKET_ENV} is not set; "
            "cannot reach the raw-findings object store"
        )
    return bucket


def _latest_key(connector_name: str) -> str:
    return f"{_LATEST_KEY_PREFIX}/{connector_name}.json"


def write_raw(connector_name: str, payload: Any) -> None:
    """JSON-serialize ``payload`` and write it to S3 for auditability.

    Writes two objects to the bucket named by the ``RAW_FINDINGS_BUCKET``
    environment variable (region from ``AWS_REGION``): a timestamped key
    (``<connector_name>/<UTC timestamp>.json``) that is never overwritten,
    and ``latest/<connector_name>.json``, which :func:`read_latest` /
    :func:`read_latest_text` read back.

    Args:
        connector_name: The connector's stable ``name`` (matches
            ``Connector.name``), used to key both S3 objects.
        payload: Any JSON-serializable raw tool output.

    Must never:
        Swallow a missing bucket configuration or an S3 failure into a
        silent no-op — both are raised as :class:`ObjectStoreError` naming
        this connector, so a connector's ``fetch()`` can propagate them
        rather than returning as if the write (or the whole fetch) had
        succeeded.
    """
    bucket = _bucket_name(connector_name)
    region = _env.get_optional(AWS_REGION_ENV)
    body = json.dumps(payload).encode("utf-8")
    timestamp = datetime.now(UTC).strftime(_TIMESTAMP_FORMAT)
    timestamped_key = f"{connector_name}/{timestamp}.json"
    latest_key = _latest_key(connector_name)

    try:
        client = boto3.client("s3", region_name=region)
        client.put_object(Bucket=bucket, Key=timestamped_key, Body=body)
        client.put_object(Bucket=bucket, Key=latest_key, Body=body)
    except Exception as exc:
        raise ObjectStoreError(
            f"{connector_name}: failed to write raw findings to "
            f"s3://{bucket}/{latest_key} (region={region!r}): {exc}"
        ) from exc


def read_latest_text(connector_name: str, staleness_threshold_seconds: int) -> str:
    """Read ``latest/<connector_name>.json`` from S3 as raw decoded text.

    This is the primitive :func:`read_latest` builds on; connectors whose
    raw payload is not plain JSON (e.g. ``scoutsuite_connector.py``'s
    JS-wrapped output) call this directly and parse the text themselves.

    Args:
        connector_name: The connector's stable ``name``, used to build the
            object key.
        staleness_threshold_seconds: Caller-supplied freshness tolerance.
            This must be a named constant in the *calling* connector's own
            module (staleness tolerance is legitimately per-tool), never a
            literal hardcoded here.

    Returns:
        The object's body, UTF-8 decoded.

    Raises:
        ObjectStoreError: If the bucket is not configured, the object is
            missing/unreadable, or the object's ``LastModified`` is older
            than ``staleness_threshold_seconds``.

    Must never:
        Return stale data silently, or fall back to an empty string to mean
        "not found" — both are data-quality failures a caller must be able
        to record under ``scan_scope.unreachable_scanners``.
    """
    bucket = _bucket_name(connector_name)
    region = _env.get_optional(AWS_REGION_ENV)
    key = _latest_key(connector_name)

    try:
        client = boto3.client("s3", region_name=region)
        response = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise ObjectStoreError(
            f"{connector_name}: failed to read s3://{bucket}/{key} (region={region!r}): {exc}"
        ) from exc

    last_modified = response.get("LastModified")
    if last_modified is not None:
        age_seconds = (datetime.now(UTC) - last_modified).total_seconds()
        if age_seconds > staleness_threshold_seconds:
            raise ObjectStoreError(
                f"{connector_name}: s3://{bucket}/{key} is stale "
                f"({age_seconds:.0f}s old, threshold {staleness_threshold_seconds}s) — "
                "treating this connector as unreachable rather than trusting outdated findings"
            )

    try:
        body_bytes = response["Body"].read()
    except Exception as exc:
        raise ObjectStoreError(
            f"{connector_name}: could not read the body of s3://{bucket}/{key}: {exc}"
        ) from exc

    try:
        text: str = body_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ObjectStoreError(f"{connector_name}: s3://{bucket}/{key} is not valid UTF-8: {exc}") from exc
    return text


def read_latest(connector_name: str, staleness_threshold_seconds: int) -> Any:
    """Read and JSON-parse ``latest/<connector_name>.json`` from S3.

    Args:
        connector_name: The connector's stable ``name``.
        staleness_threshold_seconds: Caller-supplied freshness tolerance;
            see :func:`read_latest_text`.

    Returns:
        The object's body, parsed with ``json.loads``.

    Raises:
        ObjectStoreError: Under the same conditions as
            :func:`read_latest_text`, plus if the body is not valid JSON.
    """
    text = read_latest_text(connector_name, staleness_threshold_seconds)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ObjectStoreError(
            f"{connector_name}: latest/{connector_name}.json is not valid JSON: {exc}"
        ) from exc
