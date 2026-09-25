"""Attaching Open FAIR distribution parameters to a loss event scenario.

Turns one scenario from :func:`core.engine.scenarios.build_loss_event_scenarios`
into the ``loss_event_frequency``/``loss_magnitude`` (and supporting) shape
that :mod:`core.engine.simulation` consumes.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from core.assumptions import (
    BASE_LOSS_MAGNITUDE_BY_CRITICALITY_INR,
    BASELINE_EXPLOIT_PROBABILITY_FOR_UNSCORED_FINDING,
    BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR,
    CONTROL_RESISTANCE_STRENGTH,
    KEV_LISTED_MINIMUM_EXPLOIT_PROBABILITY,
    RTO_MULTIPLIER_BY_BACKUP_POSTURE,
    UNSCORED_EXPLOIT_PROBABILITY_SCALE_BY_CRITICALITY,
)
from core.engine.attack_graph import GraphReachability

# Ordinal ranks used only to pick the worst-case tier/posture across an
# asset's several related services — not a modelling judgement value itself
# (those live in core.assumptions), just a fixed ordering over the labels
# that already exist there and in the schema.
_CRITICALITY_RANK: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}
_BACKUP_POSTURE_RANK: dict[str, int] = {
    "no_backup": 3,
    "backup_untested": 2,
    "backup_tested_no_immutable": 1,
    "backup_tested_immutable": 0,
}


def _related_services(scenario: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    services_by_id = {service["service_id"]: service for service in snapshot["services"]}
    return [
        services_by_id[service_id]
        for service_id in scenario["service_ids"]
        if service_id in services_by_id
    ]


def _exposure_profile(asset: dict[str, Any], related_services: list[dict[str, Any]]) -> str:
    """internet_facing_critical_asset if internet-facing and serving a critical/high service, else internal_asset."""
    internet_facing = bool((asset.get("network") or {}).get("internet_facing"))
    serves_high_value = any(
        service.get("criticality") in ("critical", "high") for service in related_services
    )
    if internet_facing and serves_high_value:
        return "internet_facing_critical_asset"
    return "internal_asset"


def _exploit_probability(finding: dict[str, Any]) -> float:
    """This finding's own exploit probability, before any control discount.

    Starts from the finding's own EPSS score (or, for non-CVE findings
    which EPSS never scores, a baseline scaled by the finding's own
    criticality), floored upward if CISA KEV lists it
    as actively exploited.
    """
    epss_score = finding.get("epss_score")
    if epss_score is not None:
        exploit_probability = epss_score
    else:
        scale = UNSCORED_EXPLOIT_PROBABILITY_SCALE_BY_CRITICALITY.get(
            str(finding.get("criticality")), 1.0
        )
        exploit_probability = min(BASELINE_EXPLOIT_PROBABILITY_FOR_UNSCORED_FINDING * scale, 1.0)
    if finding.get("kev_listed"):
        exploit_probability = max(exploit_probability, KEV_LISTED_MINIMUM_EXPLOIT_PROBABILITY)
    return float(exploit_probability)


def _active_control_resistances(asset: dict[str, Any]) -> dict[str, float]:
    """Which control categories are observed active on this asset, and their base resistance strength.

    Returned keyed by the same control-category names used in
    core.assumptions.CONTROL_RESISTANCE_STRENGTH, so
    core.engine.simulation can look up a matching SHARED_CONTROL_HEALTH_PERT
    entry per category when modelling C3 scenario correlation (see that
    constant's docstring).
    """
    active: dict[str, float] = {}
    identity_access = asset.get("identity_access") or {}
    if (
        identity_access.get("mfa_enforced") is True
        and "mfa_enforced" in CONTROL_RESISTANCE_STRENGTH
    ):
        active["mfa_enforced"] = CONTROL_RESISTANCE_STRENGTH["mfa_enforced"]
    edr = asset.get("edr") or {}
    if (
        edr.get("agent_installed") is True
        and edr.get("agent_healthy") is True
        and "edr_active" in CONTROL_RESISTANCE_STRENGTH
    ):
        active["edr_active"] = CONTROL_RESISTANCE_STRENGTH["edr_active"]
    return active


def _combine_resistances(resistances: dict[str, float] | list[float]) -> float:
    """1 - product of each control's own miss probability: the probability at least one control stops the event.

    Never summed — summing would let enough controls push resistance past
    100%, which is not a real probability.
    """
    values = resistances.values() if isinstance(resistances, dict) else resistances
    miss_probability = 1.0
    for resistance in values:
        miss_probability *= 1.0 - resistance
    return 1.0 - miss_probability


def _vulnerability_probability(finding: dict[str, Any], asset: dict[str, Any]) -> float:
    """Probability this specific finding becomes a loss event, net of observed controls."""
    exploit_probability = _exploit_probability(finding)
    combined_resistance = _combine_resistances(_active_control_resistances(asset))
    return float(np.clip(exploit_probability * (1.0 - combined_resistance), 0.0, 1.0))


def _worst_criticality_tier(related_services: list[dict[str, Any]]) -> str:
    """The highest-ranked criticality tier among an asset's related services, or 'unknown' if none resolve."""
    tiers: list[str] = [
        service["criticality"]
        for service in related_services
        if service.get("criticality") in _CRITICALITY_RANK
    ]
    if not tiers:
        return "unknown"
    return max(tiers, key=lambda tier: _CRITICALITY_RANK[tier])


def _single_service_backup_posture(service: dict[str, Any]) -> str:
    backup = service.get("backup") or {}
    if not backup.get("exists"):
        return "no_backup"
    if backup.get("last_tested_at") is None:
        return "backup_untested"
    if not backup.get("immutable_copy"):
        return "backup_tested_no_immutable"
    return "backup_tested_immutable"


def _worst_backup_posture(related_services: list[dict[str, Any]]) -> str:
    """The weakest backup posture among an asset's related services, or 'no_backup' if none resolve.

    Defaulting an unresolvable service to the worst posture (rather than
    the best) is deliberate: missing backup data must never be read as
    reassuring.
    """
    if not related_services:
        return "no_backup"
    postures = [_single_service_backup_posture(service) for service in related_services]
    return max(postures, key=lambda posture: _BACKUP_POSTURE_RANK[posture])


def _scale_pert(pert: dict[str, float], factor: float) -> dict[str, float]:
    return {key: value * factor for key, value in pert.items()}


def _describe_scenario(
    scenario: dict[str, Any],
    exposure_profile: str,
    criticality_tier: str,
    reachability: GraphReachability | None,
) -> str:
    finding = scenario["finding"]
    identifier = finding.get("cve_id") or finding["finding_id"]
    description = (
        f"{finding.get('type', 'finding')} {identifier} on {scenario['asset_id']} "
        f"({exposure_profile}, {criticality_tier}-tier service impact)"
    )
    # Stated in the description itself so the dashboard, which shows
    # top_contributors' descriptions as-is, surfaces why this figure moved
    # once topology became known — never a silent change to the numbers.
    if reachability is not None and not reachability.is_entry_point:
        if reachability.routes:
            routes = ", ".join(
                f"{route.entry_asset_id} {route.share:.0%} (p={route.reach_probability:.3f})"
                for route in reachability.routes
            )
            description += f"; reached via attack graph: {routes}"
        else:
            description += "; unreachable under the known network topology"
    return description


def _graph_threat_event_frequency(
    reachability: GraphReachability, finding_id: str
) -> dict[str, float]:
    """Attacks/year that reach this asset *and* find this finding workable, summed over routes.

    Each route contributes its entry point's own baseline rate times the
    probability a campaign from there reaches this asset given this
    finding's exploit works. Separate entry points are separate streams of
    campaigns, so their rates add — each keeps its own rate, rather than
    every route borrowing the busiest one.
    """
    total = {"min": 0.0, "most_likely": 0.0, "max": 0.0}
    for route in reachability.routes:
        rate = BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR[route.entry_exposure_profile]
        factor = route.reach_given_finding.get(finding_id, route.reach_probability)
        for key in total:
            total[key] += rate[key] * factor
    return total


def parameterize_scenario(
    scenario: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    graph_reachability: dict[str, GraphReachability] | None = None,
) -> dict[str, Any]:
    """Attach Open FAIR parameters (frequency, vulnerability, loss magnitude
    distributions) to a scenario, using snapshot data and named assumptions.

    Loss Event Frequency is derived as Threat Event Frequency times
    Vulnerability — see :func:`_exposure_profile` and
    :func:`_vulnerability_probability`. Vulnerability is this finding's own
    exploit probability, discounted by the asset's observed controls.

    When the attack graph (``graph_reachability``) covers this asset and
    the asset is reached only *through* the graph, Threat Event Frequency is
    no longer the asset's own "internal" rate. It becomes, summed over every
    route in (see :func:`_graph_threat_event_frequency`), each entry
    point's rate times the probability a campaign from there reaches this
    asset given this finding's exploit works. The "internal" rate was a
    rough proxy for being hard to reach; the graph now measures that
    directly, so using both would count the same difficulty twice. The
    chain is then: attacks/year at each entry point x P(they reach this
    asset) x P(this finding is exploited), summed across entry points.

    An internet-facing asset and an asset with unknown topology (absent
    from ``graph_reachability``) keep exactly the figures they had before
    the attack graph existed. Loss
    Magnitude is derived from the worst-case criticality tier among the
    asset's related services, scaled by the worst-case backup posture among
    them — see :func:`_worst_criticality_tier` and
    :func:`_worst_backup_posture`. Both stay as Beta-PERT three-point
    distributions throughout, matching what
    :func:`core.engine.simulation.run_monte_carlo` expects.

    Known gap: this does not yet incorporate
    ``core.assumptions.COST_PER_RECORD_INR`` or
    ``core.assumptions.EXPECTED_REGULATORY_PENALTY_INR`` — the schema
    carries no records-affected count or regulatory-regime field to key
    them by yet (see the JUSTIFICATION comment on each in
    ``core/assumptions.py``). Loss magnitude here is service-criticality
    driven only, not yet decomposed into every FAIR primary/secondary loss
    form.

    Args:
        scenario: One scenario from
            :func:`core.engine.scenarios.build_loss_event_scenarios`.
        snapshot: The committed snapshot the scenario was derived from.
        graph_reachability: ``{asset_id: GraphReachability}`` from
            :func:`core.engine.attack_graph_inference.compute_graph_reachability`,
            computed once per snapshot by the caller. None, or an asset
            absent from it, means no graph adjustment.

    Returns:
        The scenario augmented with FAIR distribution parameters (e.g.
        threat event frequency, vulnerability/control resistance, primary
        and secondary loss magnitude distributions), plus
        ``graph_reachability_applied`` and ``attack_routes`` (each route's
        entry point, share and reach probability) — and a ``description``
        that says so — so the graph's contribution to any figure is
        visible, never silent.

    Must never:
        Use a bare numeric literal for any parameter — every constant must
        come from ``core.assumptions``, keyed appropriately (e.g. by
        control category, backup posture, or regulatory regime).
    """
    finding = scenario["finding"]
    asset = scenario["asset"]
    related_services = _related_services(scenario, snapshot)

    exposure_profile = _exposure_profile(asset, related_services)
    reachability = (graph_reachability or {}).get(scenario["asset_id"])
    graph_reachability_applied = reachability is not None and not reachability.is_entry_point
    if reachability is not None and graph_reachability_applied:
        threat_event_frequency = _graph_threat_event_frequency(reachability, finding["finding_id"])
        attack_routes = [
            {
                "entry_asset_id": route.entry_asset_id,
                "share": route.share,
                "reach_probability": route.reach_probability,
            }
            for route in reachability.routes
        ]
    else:
        threat_event_frequency = BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR[exposure_profile]
        attack_routes = []
    exploit_probability = _exploit_probability(finding)
    active_control_resistances = _active_control_resistances(asset)
    vulnerability = _vulnerability_probability(finding, asset)
    loss_event_frequency = _scale_pert(threat_event_frequency, vulnerability)

    criticality_tier = _worst_criticality_tier(related_services)
    base_loss_magnitude = BASE_LOSS_MAGNITUDE_BY_CRITICALITY_INR[criticality_tier]
    backup_posture = _worst_backup_posture(related_services)
    rto_multiplier = RTO_MULTIPLIER_BY_BACKUP_POSTURE[backup_posture]
    loss_magnitude = _scale_pert(base_loss_magnitude, rto_multiplier)

    return {
        **scenario,
        "exposure_profile": exposure_profile,
        "threat_event_frequency": threat_event_frequency,
        "exploit_probability": exploit_probability,
        "active_control_resistances": active_control_resistances,
        "graph_reachability_applied": graph_reachability_applied,
        "attack_routes": attack_routes,
        "vulnerability": vulnerability,
        "criticality_tier": criticality_tier,
        "backup_posture": backup_posture,
        "loss_event_frequency": loss_event_frequency,
        "loss_magnitude": loss_magnitude,
        "description": _describe_scenario(
            scenario, exposure_profile, criticality_tier, reachability
        ),
    }
