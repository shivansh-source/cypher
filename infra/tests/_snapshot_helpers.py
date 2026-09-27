"""Test-only helpers for building a minimal schema-shaped snapshot.

Mirrors the asset-defaulting behavior of
``interfaces/cli/cypher.py``'s ``ingest_command`` (default any section no
connector contributed to ``[]``/``{}``/the "no agent" ``edr`` shape) so each
connector test can validate its own output against
``schema/aggregated_assets.schema.json`` without depending on
``interfaces/`` (this file lives under ``infra/tests/``, not
``infra/connectors/``, so importing it imposes no restriction on the
connectors themselves).
"""

from __future__ import annotations

from typing import Any

_DEFAULT_EDR: dict[str, Any] = {
    "agent_installed": False,
    "agent_healthy": None,
    "detection_rules_active": None,
    "recent_alerts": None,
}


def default_asset(asset_id: str) -> dict[str, Any]:
    """Build a schema-complete ``assets[]`` entry with every section defaulted empty."""
    return {
        "asset_id": asset_id,
        "findings": [],
        "threat_intel": {},
        "edr": dict(_DEFAULT_EDR),
        "identity_access": {},
        "network": {},
    }


def merge_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge one connector's ``Connector.run()`` output into ``assets[]`` entries."""
    assets_by_id: dict[str, dict[str, Any]] = {}
    for fragment in fragments:
        asset_id: str = fragment["asset_id"]
        asset = assets_by_id.setdefault(asset_id, default_asset(asset_id))
        if "findings" in fragment:
            asset["findings"].extend(fragment["findings"])
        if "edr" in fragment:
            asset["edr"] = fragment["edr"]
        if "threat_intel" in fragment:
            asset["threat_intel"] = fragment["threat_intel"]
        if "identity_access" in fragment:
            asset["identity_access"] = fragment["identity_access"]
        if "network" in fragment:
            asset["network"] = fragment["network"]
    return list(assets_by_id.values())


def build_snapshot(assets: list[dict[str, Any]], reachable_scanners: list[str]) -> dict[str, Any]:
    """Build a minimal, fully schema-shaped candidate snapshot around ``assets``."""
    return {
        "snapshot_id": "sha256:test0000000000000000000000000000000000000000000000000000000000",
        "observed_at": "2026-09-20T00:00:00Z",
        "valid_from": "2026-09-20T00:00:00Z",
        "valid_to": None,
        "scan_scope": {
            "reachable_scanners": reachable_scanners,
            "unreachable_scanners": [],
            "coverage": [],
        },
        "services": [],
        "assets": assets,
        "endpoints": [],
    }
