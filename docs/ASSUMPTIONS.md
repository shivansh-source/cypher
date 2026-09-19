# Assumptions — the honesty artifact

Every rupee figure Su₹aksha produces is only as credible as the assumptions
behind it. This document exists so that no number leaves the system without
a visible trail back to the judgement calls that produced it. It must be
kept in lockstep with `core/assumptions.py` — every named constant there
should have a corresponding entry here, and vice versa.

## How to read this document

Each assumption entry has four parts:

- **Assumption** — what the constant represents and its current
  (placeholder) value.
- **Justification** — the source or reasoning behind the value, or
  "PLACEHOLDER — not yet calibrated" if none exists yet.
- **Sensitivity** — how much the headline EAL/VaR figures move when this
  assumption is varied within a plausible range. Empty until the engine
  exists and a sensitivity analysis can actually be run.
- **Known limitations** — ways this assumption could be wrong or misused,
  and what evidence would change it.

## Assumption entries

### Control resistance strength (`core.assumptions.CONTROL_RESISTANCE_STRENGTH`)

- **Assumption:** PLACEHOLDER — not yet populated.
- **Justification:** PLACEHOLDER.
- **Sensitivity:** TODO — run once `core/engine.py` is implemented.
- **Known limitations:** Control strength is unlikely to be a single
  scalar in reality — the same control can resist different threat event
  types with very different effectiveness. TODO: revisit whether this
  needs to be per-(control, threat-event-type) rather than per-control.

### RTO multiplier by backup posture (`core.assumptions.RTO_MULTIPLIER_BY_BACKUP_POSTURE`)

- **Assumption:** PLACEHOLDER — not yet populated.
- **Justification:** PLACEHOLDER.
- **Sensitivity:** TODO.
- **Known limitations:** Real recovery time depends heavily on factors not
  in this simple lookup (data volume, team readiness, whether the
  incident is ransomware requiring forensic hold before restore). TODO:
  revisit granularity once real backup test data is available.

### Cost per compromised record (`core.assumptions.COST_PER_RECORD_INR`)

- **Assumption:** PLACEHOLDER — not yet populated.
- **Justification:** PLACEHOLDER. Global studies (e.g. IBM's Cost of a Data
  Breach) are explicitly NOT to be used unadjusted — see
  `core/assumptions.py`.
- **Sensitivity:** TODO.
- **Known limitations:** Highly sensitive to data sensitivity
  classification, which itself may not be reliably known from the
  aggregated schema for every asset.

### Expected regulatory penalty (`core.assumptions.EXPECTED_REGULATORY_PENALTY_INR`)

- **Assumption:** PLACEHOLDER — not yet populated.
- **Justification:** PLACEHOLDER. Must be calibrated against the current,
  effective-dated regulatory instrument (RBI's Directions, 2026, not the
  repealed 2016 framework — see repo-root `CLAUDE.md` principle 8), never
  a stale one.
- **Sensitivity:** TODO.
- **Known limitations:** Regulatory penalties in practice are often
  discretionary rather than fixed, making a point-value or even a simple
  distribution potentially misleading without legal review.

### Baseline threat event frequency (`core.assumptions.BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR`)

- **Assumption:** PLACEHOLDER — not yet populated.
- **Justification:** PLACEHOLDER.
- **Sensitivity:** TODO.
- **Known limitations:** Threat frequency is likely the single most
  sensitive input to the whole model and the hardest to calibrate without
  either real telemetry or a credible external benchmark specific to
  India's threat landscape and the organization's sector.

### Monte Carlo iterations and VaR percentile (`core.assumptions.MONTE_CARLO_ITERATIONS`, `core.assumptions.VALUE_AT_RISK_PERCENTILE`)

- **Assumption:** PLACEHOLDER — not yet set.
- **Justification:** Iteration count should be set via a convergence
  study, not intuition; VaR percentile is a reporting/stakeholder decision,
  not a statistical one.
- **Sensitivity:** TODO — a convergence plot (VaR estimate vs. iteration
  count) should be produced and referenced here once the engine exists.
- **Known limitations:** None yet identified.

## Known limitations of the model overall

- No organization-specific loss history has been used to calibrate any
  assumption above; every value is currently a placeholder.
- The Open FAIR + Monte Carlo approach models uncertainty in the
  *parameters*, but the *structure* of the model (which threat events
  matter, how loss magnitude is decomposed) is itself a judgement call not
  captured by any sensitivity analysis on the numeric constants alone.
- Control overlap is handled by joint re-simulation (see repo-root
  `CLAUDE.md` principle 7), but the underlying control-resistance
  assumptions still treat each control's effect somewhat independently
  before combination — a truly joint control-interaction model is a
  further refinement not yet attempted.
