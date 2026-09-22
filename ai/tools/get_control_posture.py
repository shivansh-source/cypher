"""Tool: report current control posture for an asset or the whole estate.

This function does not compute anything itself; it reads posture fields
already present in the current committed snapshot
(``assets[].edr``, ``assets[].identity_access``, ``assets[].network``,
``services[].backup``). See repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable


def _asset_posture(
    asset: dict[str, Any], services_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Reshape one asset's raw posture fields, as recorded, no inference."""
    return {
        "asset_id": asset["asset_id"],
        "edr": asset.get("edr"),
        "identity_access": asset.get("identity_access"),
        "network": asset.get("network"),
        "services_backup": [
            {"service_id": sid, "backup": services_by_id[sid].get("backup")}
            for sid in asset.get("service_ids", [])
            if sid in services_by_id
        ],
    }


def get_control_posture(asset_id: str | None = None) -> dict[str, Any]:
    """Return current control posture data for an asset or the whole estate.

    Args:
        asset_id: Optional single asset to scope to; None means summarize
            across the current snapshot's full asset population.

    Returns:
        A structured dict of posture fields as recorded in the current
        snapshot, plus the ``snapshot_id`` they came from.

    Must never:
        Infer or estimate a posture value not explicitly present in the
        snapshot (e.g. must not guess ``mfa_enforced`` when the field is
        null — report it as null/unknown instead).
    """
    snapshot = current_snapshot_or_unavailable()
    services_by_id = {service["service_id"]: service for service in snapshot.get("services", [])}
    assets = snapshot["assets"]
    if asset_id is not None:
        assets = [asset for asset in assets if asset["asset_id"] == asset_id]
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "assets": [_asset_posture(asset, services_by_id) for asset in assets],
    }
