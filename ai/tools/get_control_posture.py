"""Tool: report current control posture for an asset or the whole estate.

This function does not compute anything itself; it reads posture fields
already present in the current committed snapshot
(``assets[].edr``, ``assets[].identity_access``, ``assets[].network``,
``services[].backup``). See repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable

#: Same cap as get_exposure.py's MAX_NARRATED_CONTRIBUTORS. Every asset's full posture is
#: large enough, uncapped across a real estate's worth of assets, to exceed Groq's free-tier
#: tokens-per-minute limit on its own — this tool only needs a representative sample to
#: narrate posture, not every asset verbatim.
DEFAULT_ESTATE_LIMIT = 10


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


def get_control_posture(asset_id: str | None = None, limit: int | None = None) -> dict[str, Any]:
    """Return current control posture data for an asset or the whole estate.

    Args:
        asset_id: Optional single asset to scope to; None means summarize
            across the current snapshot's full asset population.
        limit: Maximum number of assets to return when ``asset_id`` is None
            (ignored when scoped to one asset). Defaults to
            ``DEFAULT_ESTATE_LIMIT``.

    Returns:
        A structured dict of posture fields as recorded in the current
        snapshot, plus the ``snapshot_id`` they came from. When scoping to
        the whole estate, ``assets`` is truncated to ``limit`` (the
        snapshot's own asset order, not re-ranked) and ``total_asset_count``
        reports how many assets the estate actually has.

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
    resolved_limit = limit if limit is not None else DEFAULT_ESTATE_LIMIT
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "total_asset_count": len(assets),
        "assets": [_asset_posture(asset, services_by_id) for asset in assets[:resolved_limit]],
    }
