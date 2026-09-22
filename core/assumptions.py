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
belongs in ``core/engine.py`` or ``core/optimizer.py``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Control resistance strength
# ---------------------------------------------------------------------------
# ASSUMPTION: relative strength (0-1) each control category contributes
# toward resisting a threat event from becoming a loss event, keyed by
# control category name as used in governance/control_library/.
# JUSTIFICATION: PLACEHOLDER — no source yet.
# CALIBRATION: requires Open FAIR-style control-strength elicitation per
# control category, ideally cross-checked against the organization's own
# incident history (how often did this control actually stop an event?).
CONTROL_RESISTANCE_STRENGTH: dict[str, float] = {
    # "mfa_enforced": 0.0,          # TODO: calibrate
    # "edr_active": 0.0,            # TODO: calibrate
    # "patch_current": 0.0,         # TODO: calibrate
    # "network_segmentation": 0.0,  # TODO: calibrate
}

# ---------------------------------------------------------------------------
# Recovery time multipliers by backup posture
# ---------------------------------------------------------------------------
# ASSUMPTION: multiplier applied to a service's baseline downtime-loss
# estimate depending on its backup posture, keyed by a posture label the
# engine derives from ``services[].backup`` in the aggregated schema.
# JUSTIFICATION: PLACEHOLDER — no source yet.
# CALIBRATION: requires RTO/RPO data from real backup test results (not
# vendor SLAs) across services of varying criticality.
RTO_MULTIPLIER_BY_BACKUP_POSTURE: dict[str, float] = {
    # "no_backup": 0.0,                    # TODO: calibrate
    # "backup_untested": 0.0,              # TODO: calibrate
    # "backup_tested_no_immutable": 0.0,   # TODO: calibrate
    # "backup_tested_immutable": 0.0,      # TODO: calibrate
}

# ---------------------------------------------------------------------------
# Cost per compromised record
# ---------------------------------------------------------------------------
# ASSUMPTION: expected direct cost (INR) per record compromised in a data
# breach loss event, potentially segmented by data sensitivity class.
# JUSTIFICATION: PLACEHOLDER — no source yet.
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
# profile, before any control resistance is applied.
# JUSTIFICATION: PLACEHOLDER — no source yet.
# CALIBRATION: requires either the organization's own telemetry (attempted
# intrusion counts) over a representative period, or a documented external
# benchmark appropriate to the organization's sector and size — never an
# arbitrary round number.
BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR: dict[str, float] = {
    # "internet_facing_critical_asset": 0.0,  # TODO: calibrate
    # "internal_asset": 0.0,                  # TODO: calibrate
}

# ---------------------------------------------------------------------------
# Monte Carlo simulation parameters
# ---------------------------------------------------------------------------
# ASSUMPTION: number of Monte Carlo iterations used to propagate uncertainty
# through the FAIR model into an EAL/VaR distribution.
# JUSTIFICATION: PLACEHOLDER — chosen for convergence stability, not
# calibrated to any external source.
# CALIBRATION: requires a convergence study (does the VaR estimate stop
# moving materially beyond N iterations?) rather than an arbitrary round
# number.
MONTE_CARLO_ITERATIONS: int = 0  # TODO: set and justify via convergence study

# ASSUMPTION: percentile used to express Value at Risk (e.g. 0.95 for VaR95).
# JUSTIFICATION: PLACEHOLDER — must match whatever percentile is disclosed
# to stakeholders; changing this without updating every report/UI label
# would silently misrepresent the figure.
# CALIBRATION: a business/reporting decision, not a statistical one —
# confirm with stakeholders which percentile they expect to see.
VALUE_AT_RISK_PERCENTILE: float = 0.0  # TODO: set (e.g. 0.95) and keep in sync with reporting

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
