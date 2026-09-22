"""Deriving candidate FAIR loss event scenarios from a committed snapshot."""

from __future__ import annotations

from typing import Any


def build_loss_event_scenarios(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive candidate FAIR loss event scenarios from a committed snapshot.

    The unit of analysis is one active (not yet remediated) finding on one
    asset — a scenario is "this specific vulnerability, on this specific
    asset, being exploited." A remediated finding (``remediated_at`` set)
    produces no scenario: the schema's absence-of-finding discipline (see
    ``schema/README.md`` on ``scan_scope``) already distinguishes "never
    found" from "found and fixed," and only the latter applies here — a
    fixed finding is not a live loss-event path.

    This is a deliberate scope limitation, not an oversight: threat paths
    that don't originate from a discrete finding (e.g. credential-stuffing
    risk implied purely by weak IAM posture with no associated finding, or
    ransomware risk implied purely by backup posture) are not yet modelled
    as their own scenarios. Every scenario this function produces is
    traceable to one concrete, evidenced finding, which keeps the eventual
    risk figure defensible at the cost of not yet covering every FAIR
    threat-event type the schema's other fields (``edr``, ``identity_access``,
    ``network``, ``services[].backup``) could in principle support.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot (see
            ``core/snapshot.py``).

    Returns:
        A list of scenario definitions (threat event x asset x vulnerability
        pairing) ready to be parameterized by
        :func:`core.engine.parameterization.parameterize_scenario`. Each
        element carries ``scenario_id`` (``"{asset_id}::{finding_id}"``),
        ``asset_id``, ``finding`` (the raw schema-shaped finding dict),
        ``asset`` (the raw schema-shaped asset dict, for the asset's
        ``edr``/``identity_access``/``network`` context), and
        ``service_ids`` (the asset's ``service_ids``, for looking up
        service criticality/backup posture during parameterization). Shape
        beyond these keys is internal to the engine, not schema-governed.

    Must never:
        Read anything from the snapshot beyond what
        ``schema/aggregated_assets.schema.json`` defines, or branch on
        which connector produced a given finding.
    """
    scenarios: list[dict[str, Any]] = []
    for asset in snapshot["assets"]:
        for finding in asset["findings"]:
            if finding.get("remediated_at") is not None:
                continue
            scenarios.append(
                {
                    "scenario_id": f"{asset['asset_id']}::{finding['finding_id']}",
                    "asset_id": asset["asset_id"],
                    "finding": finding,
                    "asset": asset,
                    "service_ids": asset.get("service_ids", []),
                }
            )
    return scenarios
