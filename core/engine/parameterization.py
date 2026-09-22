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
)

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

    Starts from the finding's own EPSS score (or a baseline for non-CVE
    findings, which EPSS never scores), floored upward if CISA KEV lists it
    as actively exploited.
    """
    epss_score = finding.get("epss_score")
    exploit_probability = (
        epss_score if epss_score is not None else BASELINE_EXPLOIT_PROBABILITY_FOR_UNSCORED_FINDING
    )
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
    if identity_access.get("mfa_enforced") is True and "mfa_enforced" in CONTROL_RESISTANCE_STRENGTH:
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


def _describe_scenario(scenario: dict[str, Any], exposure_profile: str, criticality_tier: str) -> str:
    finding = scenario["finding"]
    identifier = finding.get("cve_id") or finding["finding_id"]
    return (
        f"{finding.get('type', 'finding')} {identifier} on {scenario['asset_id']} "
        f"({exposure_profile}, {criticality_tier}-tier service impact)"
    )


def parameterize_scenario(scenario: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach Open FAIR parameters (frequency, vulnerability, loss magnitude
    distributions) to a scenario, using snapshot data and named assumptions.

    Loss Event Frequency is derived as Threat Event Frequency (looked up by
    the asset's exposure profile) times Vulnerability (this finding's own
    exploit probability, discounted by the asset's observed controls) — see
    :func:`_exposure_profile` and :func:`_vulnerability_probability`. Loss
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

    Returns:
        The scenario augmented with FAIR distribution parameters (e.g.
        threat event frequency, vulnerability/control resistance, primary
        and secondary loss magnitude distributions).

    Must never:
        Use a bare numeric literal for any parameter — every constant must
        come from ``core.assumptions``, keyed appropriately (e.g. by
        control category, backup posture, or regulatory regime).
    """
    finding = scenario["finding"]
    asset = scenario["asset"]
    related_services = _related_services(scenario, snapshot)

    exposure_profile = _exposure_profile(asset, related_services)
    threat_event_frequency = BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR[exposure_profile]
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
        "vulnerability": vulnerability,
        "criticality_tier": criticality_tier,
        "backup_posture": backup_posture,
        "loss_event_frequency": loss_event_frequency,
        "loss_magnitude": loss_magnitude,
        "description": _describe_scenario(scenario, exposure_profile, criticality_tier),
    }
