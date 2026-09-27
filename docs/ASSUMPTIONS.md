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
- **Interaction with the attack graph:** the `internal_asset` rate is a
  rough stand-in for "hard to reach from outside." When the attack graph
  knows the real path to an internal asset (see the attack-graph entry
  below), that difficulty is carried by each route's reach probability
  instead, so the asset's rate is the sum, over the entry points that lead
  to it, of **each entry point's own** rate times its route's reach, not
  `internal_asset`. Using both would count the same difficulty twice.
  `internal_asset` still applies to any internal asset whose network
  segment is unknown.

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
- **Known limitations:** The random seed is derived from the scenarios'
  own content, so any change to any scenario reshuffles every simulated
  year. Two snapshots' figures therefore differ by sampling noise even for
  assets that did not change (seen at ~0.5% of an asset's contribution at
  10,000 iterations on `schema/sample_aggregated.json`). Compare snapshots
  with that in mind; the optimizer avoids it for its own comparisons with
  a shared seed (see `core.optimizer._derive_comparison_seed`).

### Bayesian attack graph (`core/engine/attack_graph.py`, `core/engine/attack_graph_inference.py`)

Not a single constant, but a modelling structure with its own
judgement calls, so it gets an entry.

- **Assumption:** Assets in the same network segment
  (`assets[].network.segment_id`) can reach each other; reachability
  between segments exists only where `network_topology.segment_reachability`
  lists it, one direction at a time. Internet-facing assets are the
  attacker's entry points. An asset's chance of falling once tried reuses
  the existing per-finding vulnerability (EPSS/KEV, less observed
  controls); it falls if at least one of its open findings works.
  Attack spread is **simulated**: in each sample, every open finding's
  exploit either works or not, and compromise spreads forward from the
  entry point along the graph's edges. **Findings that share a CVE share one
  draw** (a finding works when the shared uniform falls below its own
  vulnerability). Each finding keeps exactly its own probability, but an
  attacker whose exploit works on one host is correspondingly likely to
  have it work on the next.
  Each entry point with a path to an asset is simulated as its own
  **route**, over the same draws. A finding's attack rate is then
  `Σ over routes (entry point's own rate × P(route reaches the asset | this
  finding's exploit works))`; its vulnerability stays its own. Every
  route's **share** (`entry rate × reach`, normalized) is reported, and the
  description lists them ("reached via attack graph: asset-web-01 80%
  (p=0.263), …").
- **Justification:** Follows the SIH105 project doc's Conflict Register
  item **C5**: exact inference on a Bayesian attack graph is #P-complete, so
  every computation is scoped to one asset's bounded subgraph (nodes on
  some path from an entry point to it). Within it, simulation rather than
  an analytic propagation formula follows Homer et al. (2013), who show
  that formula-based propagation goes wrong in two ways that simulation
  avoids by construction. First, loops feed a node's own probability back
  into itself; a boolean forward spread can't. Second, shared weaknesses
  (the same CVE on several hops) are hidden correlations that independent
  per-hop factors miss; one shared draw per CVE captures them. Rates add
  across routes because separate entry points are separate streams of
  attack campaigns. This replaced the earlier "busiest entry point's rate
  for every route" rule, which overstated rate for a quiet second route.
- **Sensitivity:** On `schema/sample_aggregated.json` the headline EAL moves
  by about +0.4% (within sampling noise), while the internal HR database's
  own contribution rises from ~₹1.18 lakh to ~₹1.68 lakh: its only route in
  runs through a critical internet-facing server attacked 12 times a year
  (12 × 0.261 ≈ 3.1 attacks/year reach it), not the 2/year its "internal"
  label assumed. Direction depends on real topology; no formal sweep yet.
- **Known limitations:**
  - No per-hop measurement exists yet. The SIH105 lab (page 11) is
    designed to measure exactly this; until it runs, per-hop probabilities
    are the engine's own finding-based vulnerability, not observation.
  - Only *same-CVE* correlation is modelled. Other reasons an attacker who
    clears one hop is likelier to clear the next (skill, harvested
    credentials, a shared misconfiguration without a CVE) are not, so real
    end-to-end reach may still be *higher* than computed.
  - Routes are simulated one entry point at a time and their rates
    summed. A campaign that enters through two points at once isn't
    modelled as one event, so heavily overlapping routes can double-count
    slightly; routes through different perimeters are unaffected.
  - Reach is a simulation estimate, so it carries sampling noise (see the
    samples entry below). It is seeded from the snapshot (or the caller's
    seed), so the same input always gives the same figure.
  - Same-CVE correlation only changes the rate for a finding whose CVE
    also appears upstream. That conditional is estimated from the samples
    where the finding's exploit works, so it is noisier for low-probability
    findings. A finding whose CVE appears nowhere upstream uses the route's
    plain reach, which is exact by independence and adds no noise.
  - An asset with no open findings can't be compromised in the model, so it
    also can't act as a stepping stone, even if a real attacker could get
    through it by other means (e.g. stolen credentials).
  - Anything not covered by `network_topology` (paths through IAM, shared
    credentials, SaaS) is invisible to the graph.
  - Connectors don't populate `segment_id` or `network_topology` yet, so
    until one does, real snapshots behave exactly as before the graph
    existed.

### Attack graph samples (`core.assumptions.ATTACK_GRAPH_SAMPLES`)

- **Assumption:** `50_000` simulated attack campaigns per target asset.
- **Justification:** PLACEHOLDER. Gives a standard error of about ±0.002
  on a reach probability near 0.26, well inside the uncertainty of the
  per-hop probabilities themselves. On the sample fixture, all inference
  for a snapshot runs in well under a second.
- **Sensitivity:** On `schema/sample_aggregated.json`, reach for the HR
  database lands at 0.261–0.263 against a hand-calculated 0.261.
- **Known limitations:** Needs a convergence study on realistically sized
  bounded subgraphs, analogous to the one `MONTE_CARLO_ITERATIONS` needs.
  Rare events deep in a large graph would need more samples, or
  importance sampling, to estimate well.

### Identity-merge confidence threshold (`infra.connectors._identity_resolution.MERGE_CONFIDENCE_THRESHOLD`)

Not a `core.assumptions` constant — this one is deliberately kept in
`infra/connectors/_identity_resolution.py` instead, and is mirrored here
only because this document's role ("no numeric judgement call ships without
a visible ASSUMPTION/JUSTIFICATION/CALIBRATION trail") applies to it just
as much as to anything in `core/`. It governs the ingestion pipeline's
decision to collapse two observed identifiers into one asset *before*
`core/` ever sees a snapshot — it is not a FAIR risk-modelling parameter,
and changing it cannot change a rupee figure directly (though it can change
*which* asset a finding ends up attributed to, which changes the figure
indirectly).

- **Assumption:** `0.85`. Jev (`ai.jev_transport`, TypeSafe AI's "System
  One" model — see that module's docstring) must report at least this
  confidence that a placeholder asset id (e.g. `host:10.0.0.5`, minted by
  `wazuh_connector.py`/`greenbone_connector.py`/`prowler_connector.py`/
  `scoutsuite_connector.py` per `infra/README.md`'s `_identity_hint`
  convention) and a CMDB canonical asset id name the same real-world asset,
  before `interfaces/cli/cypher.py`'s `ingest_command` merges them. The
  boundary is inclusive: confidence exactly `0.85` merges. Below it, the
  candidate is left unmerged and the decision is recorded (with its full
  evidence trail) via
  `infra.connectors._identity_resolution.record_merge_decision` for later
  human review — see `IDENTITY_RECONCILIATION_STORE_PATH` in
  `.env.example`.
- **Justification:** PLACEHOLDER — no source yet. Chosen deliberately high
  because a false merge (two different real assets collapsed into one) is
  worse than a false non-merge (two records left for one real asset,
  correctable later): a false merge can make one asset's risk *look*
  smaller or differently exposed than it really is, by attributing its
  findings to a machine with different posture/exposure. A false
  non-merge only duplicates an asset's risk contribution until corrected —
  visible and self-correcting, not hidden.
- **Sensitivity:** Not yet measurable — there is no labeled set of known
  same-asset/different-asset pairs to score threshold choices against yet.
- **Known limitations:** The threshold is a single global cutoff applied to
  every candidate regardless of evidence kind (e.g. a shared cloud instance
  ID is much stronger evidence than a shared hostname string, per
  `infra.connectors._identity_resolution.EvidenceItem.same_kind`), rather
  than varying by evidence strength. `MERGE_CONFIDENCE_THRESHOLD`'s own
  module docstring block covers full CALIBRATION requirements.

### Corroborating-only findings (`infra.connectors.scoutsuite_connector.SCOUTSUITE_COUNTS_TOWARD_LOSS`, schema field `counts_toward_loss`)

- **Assumption:** ScoutSuite's findings are emitted with `counts_toward_loss: false`. They stay in the snapshot as evidence but the engine does not turn them into loss-event scenarios.
- **Justification:** PLACEHOLDER. ScoutSuite and Prowler are both AWS cloud-posture scanners with heavy overlap, and the engine counts each finding as a separate loss event, so counting both double-counts. On the LoanEase sandbox, counting ScoutSuite added about INR 32M (130.6M to 162.4M) to expected annual loss for issues Prowler already reports.
- **Effect on the figure:** ScoutSuite-only issues (ones Prowler does not cover) are also not counted, so this can under-count as well as prevent over-counting.
- **Calibration needed:** a cross-scanner mapping of equivalent checks (shared benchmark control ids cover only about 10 of 24 flagged ScoutSuite findings) so overlapping findings can be de-duplicated and unique ones counted.

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
- Multi-step (stepping-stone) attacks are modelled by the Bayesian attack
  graph only where a snapshot carries network segmentation; see that
  entry's known limitations. Without it, every asset is scored as if
  attacked directly, as before the graph existed.
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
