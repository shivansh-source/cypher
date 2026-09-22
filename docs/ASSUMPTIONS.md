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

- **Assumption:** `mfa_enforced: 0.4`, `edr_active: 0.5`. Only these two
  categories are populated — `patch_current` and `network_segmentation`
  stay unset because no connector currently exposes a per-asset signal for
  either; `core/engine/` cannot use a value nothing feeds.
- **Justification:** PLACEHOLDER — illustrative only. This is exactly the
  number the SIH105 Notion doc's lab phase (page 11, "Experimental
  Protocol and Lab Validation") is designed to measure: a graded
  attacker-capability sweep with a control on vs. off, paired with common
  random numbers, gives the shift in success rate as the control's real
  efficacy in these same units.
- **Sensitivity:** Not yet run as a formal study, but the mechanism is
  directly observable: `core/tests/test_engine.py::test_parameterize_scenario_uses_only_named_assumptions`
  demonstrates that raising these values measurably lowers a scenario's
  `vulnerability`. A proper sweep (vary each value, plot resulting EAL/VaR)
  is still TODO.
- **Known limitations:** Control strength is unlikely to be a single
  scalar in reality — the same control can resist different threat event
  types with very different effectiveness. TODO: revisit whether this
  needs to be per-(control, threat-event-type) rather than per-control.
  Also: these two values are now *shared latent factors* too (see
  `SHARED_CONTROL_HEALTH_PERT` below) — a change here changes both the
  per-scenario baseline and the correlation model at once.

### RTO multiplier by backup posture (`core.assumptions.RTO_MULTIPLIER_BY_BACKUP_POSTURE`)

- **Assumption:** `backup_tested_immutable: 1.0`, `backup_tested_no_immutable: 1.3`,
  `backup_untested: 1.8`, `no_backup: 3.0` — a multiplier on base loss
  magnitude, applied by `core/engine/`'s `parameterize_scenario` based on
  the worst backup posture among a scenario's related services.
- **Justification:** PLACEHOLDER — the ordering (worse posture ⇒ larger
  multiplier) is the defensible part; the specific magnitudes are
  illustrative only.
- **Sensitivity:** Not yet run as a formal study.
- **Known limitations:** Real recovery time depends heavily on factors not
  in this simple lookup (data volume, team readiness, whether the
  incident is ransomware requiring forensic hold before restore). TODO:
  revisit granularity once real backup test data is available.

### Cost per compromised record (`core.assumptions.COST_PER_RECORD_INR`)

- **Assumption:** PLACEHOLDER — not yet populated, and **not yet wired into
  `core/engine/` either**: `schema/aggregated_assets.schema.json` has no
  records-affected-count field on a finding or asset, so there is nothing
  to multiply this by yet. This is a schema gap, not just a calibration
  gap.
- **Justification:** PLACEHOLDER. Global studies (e.g. IBM's Cost of a Data
  Breach) are explicitly NOT to be used unadjusted — see
  `core/assumptions.py`.
- **Sensitivity:** N/A until wired in.
- **Known limitations:** Highly sensitive to data sensitivity
  classification, which itself may not be reliably known from the
  aggregated schema for every asset.

### Expected regulatory penalty (`core.assumptions.EXPECTED_REGULATORY_PENALTY_INR`)

- **Assumption:** PLACEHOLDER — not yet populated, and **not yet wired into
  `core/engine/` either**: the schema has no field naming which
  regulatory regime a service falls under, so there is nothing to key this
  lookup by yet. The SIH105 Notion doc's "Data Approach: Alternative
  (India-Calibrated via Incident Corpus)" page has real target figures
  (RBI-regulated: ₹25L–2cr breach, median ₹1cr; SEBI-regulated: ₹50L–5cr
  critical system failure) once that schema field exists.
- **Justification:** PLACEHOLDER. Must be calibrated against the current,
  effective-dated regulatory instrument (RBI's Directions, 2026, not the
  repealed 2016 framework — see repo-root `CLAUDE.md` principle 8), never
  a stale one.
- **Sensitivity:** N/A until wired in.
- **Known limitations:** Regulatory penalties in practice are often
  discretionary rather than fixed, making a point-value or even a simple
  distribution potentially misleading without legal review.

### Baseline threat event frequency (`core.assumptions.BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR`)

- **Assumption:** `internet_facing_critical_asset: {min: 6, most_likely: 12, max: 24}`,
  `internal_asset: {min: 1, most_likely: 2, max: 6}` events/year. Now a
  Beta-PERT three-point estimate per exposure profile (restructured from a
  single point value) since `run_monte_carlo` needs an actual distribution
  to sample, not a scalar — the frequency itself is uncertain, not only
  the loss magnitude.
- **Justification:** PLACEHOLDER — no source yet.
- **Sensitivity:** Not yet run as a formal study.
- **Known limitations:** Threat frequency is likely the single most
  sensitive input to the whole model and the hardest to calibrate without
  either real telemetry or a credible external benchmark specific to
  India's threat landscape and the organization's sector.

### Vulnerability inputs (`core.assumptions.BASELINE_EXPLOIT_PROBABILITY_FOR_UNSCORED_FINDING`, `core.assumptions.KEV_LISTED_MINIMUM_EXPLOIT_PROBABILITY`)

- **Assumption:** `0.05` baseline for a finding with no EPSS score (e.g. a
  misconfiguration, which EPSS never scores), floored to `0.5` if CISA KEV
  lists the finding as actively exploited.
- **Justification:** PLACEHOLDER for the exact values; the *direction* of
  each (unscored findings shouldn't silently outrank scored ones; KEV
  listing is real evidence of active exploitation, not a modelled
  estimate, and should never round down) is defensible on its face.
- **Sensitivity:** Not yet run as a formal study.
- **Known limitations:** SIH105 Notion doc page 5 (Conflict Register, item
  **C1**) records this as genuinely unresolved: whether EPSS should scale
  Threat Event Frequency (this project's current implementation) or be
  read as a vulnerability proxy directly is an open, sensitivity-testable
  modelling choice, not a settled one. See `core/engine/`'s
  `_exploit_probability`/`_vulnerability_probability`.

### Primary loss magnitude by criticality tier (`core.assumptions.BASE_LOSS_MAGNITUDE_BY_CRITICALITY_INR`)

- **Assumption:** Beta-PERT ranges per tier, e.g. `critical: {min: 50L, most_likely: 2cr, max: 8cr}`,
  down to `low: {min: 50k, most_likely: 2L, max: 10L}`; `unknown` is
  deliberately mid-range (matching `medium`), not the lowest tier, so an
  unclassified service is never silently treated as trivial.
- **Justification:** PLACEHOLDER — ordering (critical > high > medium >
  low > unknown) is the defensible part; magnitudes are illustrative only.
  The SIH105 Notion doc's "Data Approach: Current (US-Calibrated Fallback)"
  page has a real, citable source for this — the Cyentia Institute's IRIS
  study publishes log-normal loss distribution parameters (μ, σ) by
  industry and revenue band — but wiring it in requires a `sector`/
  `revenue_band` field the schema doesn't carry yet (we only have
  `criticality`). Not yet decomposed into FAIR's own primary loss forms
  (productivity, response, replacement, competitive advantage,
  fines/judgments, reputation).
- **Sensitivity:** Not yet run as a formal study.
- **Known limitations:** Blended into one number per tier rather than
  FAIR-MAM's structured cost-category breakdown; see "Known gaps" below.

### Shared latent control-health factors (`core.assumptions.SHARED_CONTROL_HEALTH_PERT`)

- **Assumption:** `mfa_enforced: {min: 0.5, most_likely: 1.0, max: 1.05}`,
  `edr_active: {min: 0.4, most_likely: 1.0, max: 1.05}` — a per-simulated-year
  multiplier on the control's assumed resistance strength (1.0 = performed
  exactly as assumed; below 1.0 = degraded that year).
- **Justification:** PLACEHOLDER. This constant is the engine's resolution
  of the SIH105 Notion doc's Conflict Register item **C3** ("scenario
  independence in aggregation"): `core/engine/`'s `run_monte_carlo`
  samples one value per control category per Monte Carlo iteration and
  applies it to every scenario relying on that control that iteration,
  which induces genuine positive correlation between scenarios sharing
  infrastructure — the actual defect naive independent summation has.
  Team decision recorded 2026-09-21 in a comment on Notion page 5
  (referencing `C3_Scenario_Aggregation_Resolution.md`, "Option C,
  Approach 2 — Shared Latent Factor Modeling").
- **Sensitivity:** `core/tests/test_engine.py::test_run_monte_carlo_shared_control_induces_positive_correlation`
  confirms the mechanism produces measurably higher correlation between
  scenarios sharing a control than scenarios that don't, at the same seed.
  A formal sensitivity sweep on the health distribution's own width is
  still TODO.
- **Known limitations:** Only categories also present in
  `CONTROL_RESISTANCE_STRENGTH` participate — a category missing from
  either dict falls back to being treated as independent, which is a
  known simplification, not a claim that no correlation exists there. The
  source document's own literal pseudocode (an additive rupee-denominated
  "shared_risk" term with an undefined `compute_additional_exposure`
  function) was not implementable as written; this implements the
  mathematically sound version of the same idea instead — see
  `SHARED_CONTROL_HEALTH_PERT`'s docstring in `core/assumptions.py` for
  the full reasoning.

### Beta-PERT confidence factor (`core.assumptions.PERT_CONFIDENCE_FACTOR`)

- **Assumption:** `4.0` — the standard default shape parameter for
  converting a (min, most_likely, max) three-point estimate into a
  Beta-PERT distribution.
- **Justification:** Matches the published FAIR worked example
  `core/tests/test_engine.py::test_run_monte_carlo_matches_published_fair_worked_example`
  reproduces, and is the conventional default across PERT-based
  risk-analysis tooling generally.
- **Sensitivity:** Not yet run as a formal study.
- **Known limitations:** None yet identified; revisit per-factor if expert
  elicitation justifies a sharper or flatter distribution for a specific
  factor.

### Monte Carlo iterations and VaR percentile (`core.assumptions.MONTE_CARLO_ITERATIONS`, `core.assumptions.VALUE_AT_RISK_PERCENTILE`)

- **Assumption:** `10_000` iterations, `0.95` VaR percentile.
- **Justification:** Both match the published FAIR worked example the
  golden test (`test_run_monte_carlo_matches_published_fair_worked_example`)
  reproduces — chosen so the engine's own convergence could be checked
  against a known-good external result at this exact count, not because
  10,000 has been separately verified as sufficient for this
  organization's actual scenario population.
- **Sensitivity:** The golden test itself is evidence at this specific
  count (mean and VaR95 both converge to the published figures within
  <1% at 1,000,000 iterations too — see the test's docstring). A proper
  convergence study (does VaR stop moving materially beyond N iterations,
  for this organization's real scenario count) is still TODO.
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
- `core/engine/`'s `build_loss_event_scenarios` only produces a scenario
  for a discrete, evidenced finding — risk implied purely by posture (e.g.
  weak IAM with no associated finding, ransomware exposure from backup
  posture alone) isn't modelled as its own scenario yet. Every scenario is
  traceable to concrete evidence, at the cost of not covering every FAIR
  threat-event type the schema's other fields could in principle support.
- Two assumption constants exist but are not yet wired into the engine at
  all, because the schema has nothing to key them by: `COST_PER_RECORD_INR`
  (needs a records-affected-count field) and `EXPECTED_REGULATORY_PENALTY_INR`
  (needs a regulatory-regime field per service). These are schema gaps,
  not calibration gaps — see the SIH105 Notion doc's Data Approach pages
  for the real target figures once the schema supports them.
- SIH105 Notion doc page 5's Conflict Register item **C1** (probability
  vs. frequency — should EPSS scale Threat Event Frequency or act as a
  vulnerability proxy?) is explicitly recorded as unresolved. This
  project's `_exploit_probability`/`_vulnerability_probability` currently
  reads EPSS as contributing to vulnerability alongside control
  resistance; revisit if C1 is formally resolved in favour of the
  frequency-modifier interpretation.
- Insider threat, supply-chain/third-party risk (FAIR-TAM), and control
  decay over time are named, deliberately deferred gaps — none are
  modelled by any scenario or assumption in this file yet. See the SIH105
  Notion doc's Gap2/Gap3 resolution documents for the team's phased plan.
