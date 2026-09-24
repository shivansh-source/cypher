"""Human-declared business context: ``services[]`` and asset-to-service links.

No scanner can observe "this system is customer-facing, therefore high
impact" or "this database's restores have never been tested" — those are
business facts a person states. This module loads such a declaration file and
applies it to a candidate snapshot's ``services[]`` and ``assets[].service_ids``.

Every declared service is *manually declared*, never connector-observed. The
declaration file must say so itself (``declared_by``, ``declared_at``,
``basis``) so a reader of the file can never mistake it for scan output.

Declaration file shape::

    {
      "declared_by": "...", "declared_at": "<ISO date-time>", "basis": "...",
      "services": [<schema services[] item>, ...],
      "asset_links": {"<service_id>": ["<asset_id>", ...]}
    }

Each ``services`` item must already be shaped exactly like
``schema/aggregated_assets.schema.json``'s ``services[]`` item (this module
adds nothing to it and never infers a field). ``asset_links`` lives outside
those items because the schema gives ``services[]`` no asset list — the link
is stored on ``assets[].service_ids``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REQUIRED_TOP_LEVEL = ("declared_by", "declared_at", "basis", "services", "asset_links")
_REQUIRED_SERVICE_KEYS = ("service_id", "name", "criticality", "backup")


class DeclaredServicesError(RuntimeError):
    """Raised when a declaration file is missing, unparseable, or inconsistent."""


@dataclass(frozen=True)
class DeclaredServices:
    """A parsed, internally consistent declaration.

    Attributes:
        services: Schema-shaped ``services[]`` items, exactly as declared.
        asset_links: service_id -> asset_ids that service supports.
    """

    services: list[dict[str, Any]]
    asset_links: dict[str, list[str]]


def load_declared_services(path: Path) -> DeclaredServices:
    """Read and validate a declaration file.

    Args:
        path: Path to the declaration JSON.

    Returns:
        The declared services and asset links.

    Raises:
        DeclaredServicesError: If the file cannot be read or parsed, lacks a
            required key (including the provenance keys ``declared_by`` /
            ``declared_at`` / ``basis``), repeats a ``service_id``, or links
            an asset to a service that was not declared.

    Must never:
        Fill in a missing field on a service — an incomplete declaration is
        an error, not something to default.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclaredServicesError(f"could not read declared services at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DeclaredServicesError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise DeclaredServicesError(f"{path}: expected a JSON object")
    for key in _REQUIRED_TOP_LEVEL:
        if not document.get(key):
            raise DeclaredServicesError(f"{path}: missing or empty required key {key!r}")

    services = document["services"]
    asset_links = document["asset_links"]
    if not isinstance(services, list) or not isinstance(asset_links, dict):
        raise DeclaredServicesError(f"{path}: 'services' must be a list, 'asset_links' an object")

    declared_ids: set[str] = set()
    for service in services:
        for key in _REQUIRED_SERVICE_KEYS:
            if not isinstance(service, dict) or key not in service:
                raise DeclaredServicesError(f"{path}: a service is missing required key {key!r}")
        service_id = str(service["service_id"])
        if service_id in declared_ids:
            raise DeclaredServicesError(f"{path}: duplicate service_id {service_id!r}")
        declared_ids.add(service_id)

    for service_id in asset_links:
        if service_id not in declared_ids:
            raise DeclaredServicesError(
                f"{path}: asset_links references undeclared service {service_id!r}"
            )

    return DeclaredServices(
        services=services,
        asset_links={sid: [str(a) for a in assets] for sid, assets in asset_links.items()},
    )


def apply_declared_services(
    declared: DeclaredServices, assets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Attach declared ``service_ids`` to the assets that were actually observed.

    Args:
        declared: The parsed declaration.
        assets: The candidate snapshot's ``assets[]``. Modified in place.

    Returns:
        ``(services, unmatched_asset_ids)``: the declared ``services[]`` to
        put in the snapshot, and every declared asset_id that matched no
        observed asset (a caller should report these — the declaration named
        something no connector saw this run).

    Must never:
        Create an asset. A declared asset no connector observed stays
        unmatched; inventing it would fabricate an asset with no telemetry.
    """
    by_id = {asset["asset_id"]: asset for asset in assets}
    unmatched: list[str] = []
    for service_id, asset_ids in declared.asset_links.items():
        for asset_id in asset_ids:
            asset = by_id.get(asset_id)
            if asset is None:
                unmatched.append(asset_id)
                continue
            linked: list[str] = asset.setdefault("service_ids", [])
            if service_id not in linked:
                linked.append(service_id)
    return declared.services, unmatched
