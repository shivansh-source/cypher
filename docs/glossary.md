# Glossary

**Open FAIR** — Factor Analysis of Information Risk. An open standard for
quantifying information risk in financial terms, decomposing risk into
threat event frequency, vulnerability, and loss magnitude components.

**EAL (Expected Annual Loss)** — The mean of the simulated annual loss
distribution for a given scope (asset, service, or the whole estate),
expressed in INR.

**VaR (Value at Risk)** — The loss amount that will not be exceeded with a
given probability (e.g. VaR95 = the loss level exceeded only 5% of the
time) over a one-year horizon, expressed in INR. See
`core.assumptions.VALUE_AT_RISK_PERCENTILE`.

**Monte Carlo simulation** — Repeated random sampling from the FAIR model's
input distributions to produce a full loss distribution rather than a
single point estimate, from which EAL and VaR are derived.

**EPSS (Exploit Prediction Scoring System)** — A score (0-1) estimating the
probability a given CVE will be exploited in the wild in the near future.

**KEV (Known Exploited Vulnerabilities)** — CISA's catalog of
vulnerabilities with confirmed evidence of active exploitation.

**Snapshot** — An immutable, bitemporal, schema-shaped aggregation of
telemetry from all connectors at a point in time. See
`schema/aggregated_assets.schema.json` and `core/snapshot.py`.

**Bitemporal** — Tracking both when a fact was observed (`observed_at`) and
the period over which it is asserted to hold (`valid_from`/`valid_to`),
distinct from each other.

**Quality gate** — One of 5 automated checks a candidate snapshot must pass
before becoming current. See `core/snapshot.py` and
`.claude/commands/validate-snapshot.md`.

**scan_scope** — The record of which scanners actually ran and covered
which assets in a snapshot, used to distinguish "not scanned" from
"scanned and clean" or "scanned and remediated".

**Control** — A specific security investment (a patch, a configuration
change, an enforced policy) that can be evaluated for its effect on risk.
See `core.optimizer.Control`.

**Portfolio** — A candidate set of controls being evaluated together for
budget allocation. See `core.optimizer.recommend_portfolio` and repo-root
`CLAUDE.md` principle 7 on why portfolios must be jointly re-simulated.

**Control library** — Versioned, effective-dated definitions of controls
for a given regulatory/industry framework. See
`governance/control_library/`.

**RBI Directions, 2026** — The entity-specific cybersecurity directions
issued by the Reserve Bank of India that replaced the repealed 2016 Cyber
Security Framework on 31 July 2026. See
`governance/control_library/rbi_2026_directions.yaml`.

**SEBI CSCRF / CCI** — SEBI's Cybersecurity and Cyber Resilience Framework
and its associated Cyber Capability Index, applicable to SEBI-regulated
market infrastructure and intermediaries.

**numeric_guard** — The verification step (`ai/numeric_guard.py`) that
checks every number in LLM-generated text against real engine output
before it is shown to a user.

**Manual attestation** — Evidence for a compliance control that cannot be
derived automatically from findings (e.g. a policy sign-off), recorded in
`governance/manual_attestation.json` with an explicit expiry.
