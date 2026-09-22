"""The single home for every tunable modelling constant used anywhere in the
engine or optimizer.

No numeric literal representing a modelling judgement call may appear
anywhere else in the codebase — see repo-root ``CLAUDE.md``. Every constant
below carries three things:

    ASSUMPTION  — what the constant represents and the value chosen.
    JUSTIFICATION — why this value, and its source (industry benchmark,
        regulatory guidance, expert elicitation, prior incident data, etc).
    CALIBRATION — what would be required to replace this placeholder with
        an organization-specific, defensible value (e.g. "requires N
        months of incident cost data" or "requires a workshop with the
        CISO and Finance to elicit a distribution instead of a point
        value").

Every value in this module is a PLACEHOLDER pending real calibration. None
of them should be treated as production-ready, and none should be cited to
a regulator or auditor without the calibration step described.

This module intentionally contains no logic — only named, documented
constants. Anything that transforms these constants into a risk figure
belongs in ``core/engine/`` or ``core/optimizer.py``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Control resistance strength
# ---------------------------------------------------------------------------
# ASSUMPTION: relative strength (0-1) each control category contributes
# toward resisting a threat event from becoming a loss event, keyed by
# control category name as used in governance/control_library/. Only the
# two categories core/engine/ can currently observe directly from
# schema/aggregated_assets.schema.json (assets[].identity_access.mfa_enforced,
# assets[].edr.agent_installed/agent_healthy) are populated; "patch_current"
# and "network_segmentation" stay unpopulated until a connector exposes a
# per-asset signal for them, rather than guessing a value nothing reads yet.
# JUSTIFICATION: PLACEHOLDER — no source yet. This is exactly the number the
# lab described in the SIH105 Notion doc (page 11, "Experimental Protocol
# and Lab Validation") is designed to measure: a graded attacker-capability
# sweep with a control on vs off, common-random-number paired, gives the
# shift in success rate as the control's efficacy in the same units used
# here. Until that lab runs, these are illustrative placeholders only.
# CALIBRATION: requires Open FAIR-style control-strength elicitation per
# control category, ideally cross-checked against the organization's own
# incident history (how often did this control actually stop an event?),
# or — see JUSTIFICATION — the lab's capability-sweep measurement.
CONTROL_RESISTANCE_STRENGTH: dict[str, float] = {
    "mfa_enforced": 0.4,
    "edr_active": 0.5,
    # "patch_current": 0.0,         # TODO: no per-asset patch-currency signal in schema yet
    # "network_segmentation": 0.0,  # TODO: no per-asset segmentation signal in schema yet
}

# ---------------------------------------------------------------------------
# Recovery time multipliers by backup posture
# ---------------------------------------------------------------------------
# ASSUMPTION: multiplier applied to a service's baseline downtime-loss
# estimate depending on its backup posture, keyed by a posture label the
# engine derives from ``services[].backup`` in the aggregated schema.
# 1.0 means "no additional penalty beyond the base estimate"; values above
# 1.0 scale up loss magnitude as recovery confidence worsens.
# JUSTIFICATION: PLACEHOLDER — no source yet. Relative ordering (worse
# posture => larger multiplier) is the defensible part; the specific
# magnitudes are illustrative only.
# CALIBRATION: requires RTO/RPO data from real backup test results (not
# vendor SLAs) across services of varying criticality.
RTO_MULTIPLIER_BY_BACKUP_POSTURE: dict[str, float] = {
    "backup_tested_immutable": 1.0,
    "backup_tested_no_immutable": 1.3,
    "backup_untested": 1.8,
    "no_backup": 3.0,
}

# ---------------------------------------------------------------------------
# Cost per compromised record
# ---------------------------------------------------------------------------
# ASSUMPTION: expected direct cost (INR) per record compromised in a data
# breach loss event, potentially segmented by data sensitivity class.
# JUSTIFICATION: PLACEHOLDER — no source yet. Not yet wired into
# core/engine/'s parameterize_scenario either: schema/aggregated_assets.schema.json
# has no records-affected-count field on a finding or asset, so there is
# nothing to multiply this by yet. Wiring this in requires a schema
# addition, not just a value here.
# CALIBRATION: requires an India-specific breach cost study (global
# studies such as IBM's Cost of a Data Breach are not India-calibrated and
# must not be used unadjusted) or the organization's own past incident
# costs.
COST_PER_RECORD_INR: dict[str, float] = {
    # "pii_standard": 0.0,      # TODO: calibrate
    # "pii_sensitive": 0.0,     # TODO: calibrate
    # "financial_account": 0.0, # TODO: calibrate
}

# ---------------------------------------------------------------------------
# Expected regulatory penalty
# ---------------------------------------------------------------------------
# ASSUMPTION: statutory penalty CEILINGS (INR) sourced from
# governance/control_library/*.yaml `penalty_provisions`, keyed by the
# `penalty_provisions[].id` that sources each figure. These are the maximum
# amount a regulator is empowered to impose per provision — NOT a
# probability-weighted expected value. Real imposed RBI penalties, for
# example, are typically far below the statutory ceiling (recent orders
# against named NBFCs ran ₹2.7-8.1 lakh against a ₹10 lakh/violation
# ceiling — see rbi_2026_directions.yaml's penalty_provisions source note).
# JUSTIFICATION: each figure traces to a specific statute/section, sourced
# and dated in the corresponding control library file — see
# governance/control_library/rbi_2026_directions.yaml,
# governance/control_library/sebi_cscrf_cci.yaml, and
# governance/control_library/dpdp_act_2023.yaml for full citations and
# confidence levels. RBI's 2016 Cyber Security Framework was repealed 31
# July 2026 and replaced by entity-specific Directions, 2026 — the RBI
# figure below is keyed to the general RBI Act penalty power (Section 58G),
# not to the 2026 Directions specifically, since no Directions-specific
# penalty clause could be confirmed (see rbi_2026_directions.yaml's
# top-of-file warning).
# Not yet wired into core/engine/'s parameterize_scenario: these are
# keyed by penalty_provisions[].id (a specific statute/section), but
# schema/aggregated_assets.schema.json has no field naming which of these
# provisions' regulatory regime a given service falls under, so there is
# nothing to select a key with yet. Wiring this in requires a schema
# addition, not just the values now present here.
# CALIBRATION: converting a statutory ceiling into a true probability-
# weighted "expected regulatory penalty" requires (1) the probability that
# a given control failure is actually detected and enforced by the
# regulator at all, and (2) the distribution of actually-imposed amounts
# conditional on enforcement (see the RBI example above) — neither of
# which is captured by using the ceiling as a point estimate. Treat these
# as upper-bound inputs to a Monte Carlo draw, never as the loss figure
# itself, until that calibration work is done.
EXPECTED_REGULATORY_PENALTY_INR: dict[str, float] = {
    # RBI Act, 1934, Section 58G(1)(b) — ceiling only; also carries a
    # ₹1,00,000/day continuing-default penalty not represented here.
    # See governance/control_library/rbi_2026_directions.yaml:
    #   penalty_provisions[id=rbi_nbfc_58g_noncompliance]
    "rbi_nbfc_58g_noncompliance": 1_000_000.0,
    # SEBI Act, 1992, Section 15HB — ceiling, confirmed directly against
    # sebi.gov.in. See governance/control_library/sebi_cscrf_cci.yaml:
    #   penalty_provisions[id=sebi_15hb_noncompliance]
    "sebi_15hb_noncompliance": 10_000_000.0,
    # DPDP Act, 2023, Schedule item 1 (s.8(5) security safeguards) — ceiling.
    # NOT CURRENTLY IN FORCE: Section 33 (the penalty machinery) commences
    # 2027-05-13. Do not use this figure for a present-day loss estimate
    # without accounting for currently_in_force=false. See
    # governance/control_library/dpdp_act_2023.yaml:
    #   penalty_provisions[id=dpdp_security_safeguard_failure]
    "dpdp_security_safeguard_failure": 2_500_000_000.0,
}

# ---------------------------------------------------------------------------
# Baseline threat event frequencies
# ---------------------------------------------------------------------------
# ASSUMPTION: baseline annual frequency (events/year) of a threat actor
# attempting a given threat event type against an asset of a given exposure
# profile, before any control resistance is applied. Expressed as a
# Beta-PERT three-point estimate (min/most_likely/max) rather than a single
# point value — the frequency itself is uncertain, not just the loss
# magnitude, and core/engine/'s run_monte_carlo already expects this
# scenario-level structure (see its docstring). An asset counts as
# "internet_facing_critical_asset" when assets[].network.internet_facing is
# true and at least one of its related services[].criticality is "critical"
# or "high"; every other asset is "internal_asset".
# JUSTIFICATION: PLACEHOLDER — no source yet.
# CALIBRATION: requires either the organization's own telemetry (attempted
# intrusion counts) over a representative period, or a documented external
# benchmark appropriate to the organization's sector and size — never an
# arbitrary round number.
BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR: dict[str, dict[str, float]] = {
    "internet_facing_critical_asset": {"min": 6.0, "most_likely": 12.0, "max": 24.0},
    "internal_asset": {"min": 1.0, "most_likely": 2.0, "max": 6.0},
}

# ---------------------------------------------------------------------------
# Vulnerability (probability a threat event becomes a loss event)
# ---------------------------------------------------------------------------
# ASSUMPTION: baseline exploit probability used for a finding that has no
# EPSS score (EPSS only scores CVE-backed findings; a misconfiguration
# finding's epss_score is null per schema/aggregated_assets.schema.json).
# JUSTIFICATION: PLACEHOLDER — no source yet. Chosen well below a typical
# scored CVE's EPSS value so that an unscored finding doesn't silently
# outrank a scored one just because EPSS couldn't be computed for it.
# CALIBRATION: requires either an EPSS-equivalent scoring method for
# non-CVE finding types, or an empirical exploitation-rate study for
# misconfiguration-class findings specifically.
BASELINE_EXPLOIT_PROBABILITY_FOR_UNSCORED_FINDING: float = 0.05

# ASSUMPTION: floor applied to a finding's exploit probability when
# CISA KEV lists it — a KEV listing means active exploitation has already
# been observed in the wild, which should never be allowed to round down to
# a low probability just because the finding's own EPSS score is old or low.
# JUSTIFICATION: PLACEHOLDER — no source yet, but the direction (KEV floor
# should be materially higher than typical unscored/low-EPSS values) is
# defensible on its face: KEV listing is itself real-signal evidence of
# active exploitation, not a modelled estimate.
# CALIBRATION: requires a study of observed loss-event rates specifically
# for KEV-listed CVEs versus non-KEV CVEs of similar EPSS score.
KEV_LISTED_MINIMUM_EXPLOIT_PROBABILITY: float = 0.5

# ---------------------------------------------------------------------------
# Shared latent control-health factors (C3 scenario correlation)
# ---------------------------------------------------------------------------
# ASSUMPTION: per-simulated-year realized effectiveness of a control
# category, as a multiplier on its assumed CONTROL_RESISTANCE_STRENGTH
# value (1.0 = performed exactly as assumed; below 1.0 = degraded that
# year, e.g. an EDR fleet's detection engine missing an update, an
# identity provider outage). Expressed as a Beta-PERT three-point estimate.
# This is the model's resolution of the SIH105 Notion doc's Conflict
# Register item C3 ("scenario independence in aggregation"): rather than
# treating each scenario's control resistance as fixed and independent,
# core/engine/'s run_monte_carlo samples ONE value per control category
# per Monte Carlo iteration and applies it to every scenario relying on
# that control in that iteration — a shared latent factor, in the sense
# the C3 resolution document (see /outputs/C3_Scenario_Aggregation_Resolution.md,
# referenced from a comment on Notion page 5) uses the term. This induces
# genuine positive correlation between scenarios that share a control (a
# firewall/EDR/identity-system failure affects every scenario depending on
# it simultaneously, not just one), which is what makes the simulated tail
# heavier than naive independent summation — the actual defect C3 names.
# JUSTIFICATION: PLACEHOLDER — no source yet. Only categories also present
# in CONTROL_RESISTANCE_STRENGTH are used; a category missing here falls
# back to being treated as independent (no shared-factor adjustment),
# which is a known simplification, not a claim that no correlation exists.
# CALIBRATION: requires either the organization's own history of
# control-wide degradation events (an EDR engine failing fleet-wide, an
# identity provider outage) or expert elicitation of how often "the
# control behaves worse than assumed, for every asset relying on it at
# once" occurs in a given year.
SHARED_CONTROL_HEALTH_PERT: dict[str, dict[str, float]] = {
    "mfa_enforced": {"min": 0.5, "most_likely": 1.0, "max": 1.05},
    "edr_active": {"min": 0.4, "most_likely": 1.0, "max": 1.05},
}

# ---------------------------------------------------------------------------
# Primary loss magnitude by service criticality tier
# ---------------------------------------------------------------------------
# ASSUMPTION: base primary loss magnitude (INR), as a Beta-PERT three-point
# estimate, for a loss event materializing on a service of a given
# criticality tier, before the RTO_MULTIPLIER_BY_BACKUP_POSTURE scaling
# above is applied. Keyed by services[].criticality as populated in
# schema/aggregated_assets.schema.json (that field's allowed value set is
# itself still a schema TODO — see the schema file — so "unknown" exists
# here as a deliberately conservative fallback tier for any value not yet
# recognized, or for a scenario whose asset has no resolvable related
# service at all). "unknown" is deliberately mid-range (matching "medium"),
# not the lowest tier — an unknown criticality must never be silently
# treated as trivially low-impact just because it wasn't classified.
# JUSTIFICATION: PLACEHOLDER — no source yet. Ordering (critical > high >
# medium > low > unknown) is the defensible part; magnitudes are
# illustrative only, and deliberately do not yet decompose into FAIR's own
# primary loss forms (productivity, response, replacement, competitive
# advantage, fines/judgments, reputation) — see docs/ASSUMPTIONS.md.
# CALIBRATION: requires the organization's own business-impact-analysis
# figures per criticality tier (ideally decomposed into the FAIR primary
# loss forms above rather than one blended number per tier).
BASE_LOSS_MAGNITUDE_BY_CRITICALITY_INR: dict[str, dict[str, float]] = {
    "critical": {"min": 5_000_000.0, "most_likely": 20_000_000.0, "max": 80_000_000.0},
    "high": {"min": 1_000_000.0, "most_likely": 5_000_000.0, "max": 20_000_000.0},
    "medium": {"min": 200_000.0, "most_likely": 1_000_000.0, "max": 5_000_000.0},
    "low": {"min": 50_000.0, "most_likely": 200_000.0, "max": 1_000_000.0},
    "unknown": {"min": 200_000.0, "most_likely": 1_000_000.0, "max": 5_000_000.0},
}

# ---------------------------------------------------------------------------
# Monte Carlo simulation parameters
# ---------------------------------------------------------------------------
# ASSUMPTION: number of Monte Carlo iterations used to propagate uncertainty
# through the FAIR model into an EAL/VaR distribution.
# JUSTIFICATION: 10,000 matches the iteration count used in the published
# FAIR worked example this engine's golden test reproduces (see
# core/tests/test_engine.py::test_run_monte_carlo_matches_published_fair_worked_example),
# so the engine's own convergence can be checked against a known-good
# external result at this exact count. Still a PLACEHOLDER in the sense
# that it has not been separately verified as sufficient for this
# organization's own scenario population.
# CALIBRATION: requires a convergence study (does the VaR estimate stop
# moving materially beyond N iterations, for this organization's actual
# scenario count and distribution shapes?) rather than reusing the golden
# example's count indefinitely.
MONTE_CARLO_ITERATIONS: int = 10_000

# ASSUMPTION: percentile used to express Value at Risk (e.g. 0.95 for VaR95).
# JUSTIFICATION: 0.95 is the percentile reported in the published FAIR
# worked example this engine's golden test reproduces, and is also the
# most common convention in FAIR/actuarial reporting generally.
# CALIBRATION: a business/reporting decision, not a statistical one —
# confirm with stakeholders which percentile they expect to see; changing
# this without updating every report/UI label would silently misrepresent
# the figure.
VALUE_AT_RISK_PERCENTILE: float = 0.95

# ---------------------------------------------------------------------------
# Beta-PERT distribution shape
# ---------------------------------------------------------------------------
# ASSUMPTION: the confidence/shape factor (commonly called lambda) used to
# convert a (min, most_likely, max) three-point estimate into a Beta-PERT
# distribution for any FAIR factor expressed that way (loss event frequency,
# loss magnitude, etc). Higher values concentrate more probability mass
# around most_likely.
# JUSTIFICATION: 4 is the standard default confidence factor used across
# PERT-based risk-analysis tooling (including the published FAIR worked
# example this engine's golden test reproduces) when no source-specific
# reason to weight the most-likely estimate more or less heavily has been
# elicited.
# CALIBRATION: revisit per-factor if a subject-matter expert elicitation
# session justifies a sharper or flatter distribution than the default for
# a specific factor.
PERT_CONFIDENCE_FACTOR: float = 4.0

# ---------------------------------------------------------------------------
# Governance / attestation constants
# ---------------------------------------------------------------------------
# ASSUMPTION: how long a manual attestation stays current before it must be
# re-attested, in months, keyed by control_id for controls whose regulatory
# source specifies (or implies) a different cadence than the default.
# JUSTIFICATION: PLACEHOLDER — populate from a control's own framework text
# where it specifies a review/audit/testing cadence (e.g. "VAPT every six
# months", "BCP-DR test annually") as that research is done; entries left
# out use DEFAULT_ATTESTATION_VALIDITY_MONTHS below.
# CALIBRATION: read the specific clause of each regulatory source (see
# governance/control_library/*.yaml `source` fields) that governs review
# frequency for that control, rather than assuming a uniform cadence.
ATTESTATION_VALIDITY_MONTHS: dict[str, int] = {
    # "control_id": 6,  # e.g. VAPT/pentest-cadence controls
}

# ASSUMPTION: default attestation validity window (months) for any control
# not listed in ATTESTATION_VALIDITY_MONTHS above.
# JUSTIFICATION: 12 months matches the common annual audit/surveillance
# cadence shared by ISO 27001 surveillance audits, RBI/SEBI annual
# compliance certifications, and CIS/NIST self-assessment cycles — a
# reasonable default, not a researched value for any single framework.
# CALIBRATION: revisit once each framework's actual review cadence has been
# researched and recorded per-control above; this default should shrink in
# importance over time, not grow.
DEFAULT_ATTESTATION_VALIDITY_MONTHS: int = 12

# ASSUMPTION: how recent a backup test must be (days) for
# governance.mapper's `backup_tested_within_days` telemetry check to count
# it as "tested", independent of `core.engine`'s own RTO/RPO modelling.
# JUSTIFICATION: 90 days approximates a quarterly test cadence, a common
# baseline recommendation (e.g. in CIS Control 11) where the specific
# control's own source doesn't specify an exact figure.
# CALIBRATION: replace with the specific cadence named in each control's
# `source` document where one exists; this is a fallback, not a citation.
BACKUP_TEST_RECENCY_DAYS: int = 90

# ASSUMPTION: ports that, if open on an internet-facing asset, indicate weak
# network exposure control — used by governance.mapper's
# `no_dangerous_ports_on_internet_facing_assets` telemetry check (e.g. for
# ISO 27001's A.8.20 "Networks security").
# JUSTIFICATION: these are commonly targeted for direct exploitation or
# credential brute-forcing when reachable from the internet (SSH, Telnet,
# RDP, SMB, FTP, and common database ports that should never be
# internet-facing). This is a generic heuristic, not a substitute for an
# asset-specific expected-ports policy, and no control library entry treats
# it as authoritative regulatory text.
# CALIBRATION: replace with (or supplement via) an organization-specific
# expected-ports allowlist per asset once that data is available from a
# connector, rather than a single global blocklist.
DANGEROUS_INTERNET_FACING_PORTS: list[int] = [21, 22, 23, 445, 3306, 3389, 5432, 6379, 27017]

# ---------------------------------------------------------------------------
# Snapshot quality gate tolerances
# ---------------------------------------------------------------------------
# ASSUMPTION: maximum fractional change in total asset count, between a
# candidate snapshot and the previous committed one, that
# core.snapshot.check_asset_count_delta will still pass. 0.5 means the
# candidate's asset count may shrink or grow by up to 50% of the previous
# count before this gate fails it.
# JUSTIFICATION: PLACEHOLDER — no source yet. Deliberately loose rather than
# tight: the gate exists to catch a connector that failed partway through
# aggregation (asset count collapsing toward zero) or duplicated output
# (asset count spiking), not to police normal estate churn, and a false
# gate failure blocks every snapshot behind it (fail-safe means the
# previous snapshot stays current, which is itself a real availability
# cost if the tolerance is too tight for an organization's actual churn).
# CALIBRATION: requires the organization's actual asset churn rate (adds/
# decommissions per snapshot interval) to set a tolerance that only trips
# on a genuine aggregation defect, not routine change.
ASSET_COUNT_DELTA_TOLERANCE_FRACTION: float = 0.5
