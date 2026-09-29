# `governance/control_library/`

Versioned, effective-dated, **sourced** definitions of controls for each
regulatory/industry framework Cypher maps findings against.
`governance/library_loader.py` reads these files; `core/` never reads them
directly (compliance mapping is governance's job, not the engine's — see
repo-root `CLAUDE.md` principle 6).

## Sourcing rules

Every populated regulatory fact in these files must trace back to a source
actually retrieved during the research session that wrote it — never
recalled from a model's training data. Priority, highest first:

1. The regulator's own published document (a circular, a Directions PDF, a
   standard's own reference page).
2. Official secondary summaries from recognized bodies (e.g. DSCI briefs).
3. Reputable law firm / Big 4 compliance summaries, as a last resort.

Every control entry carries `source` (the citation), `confidence`
(`high`/`medium`/`low` — see below), and `verified_by_human: false` (this
project's own human reviewer flips this after checking the entry against
its source; nothing in this codebase sets it to `true` programmatically).
An entry that couldn't be verified at all says so explicitly in its
`description`/`source` rather than guessing.

**Confidence levels:**
- `high` — read directly from the primary regulatory document.
- `medium` — from a secondary/tertiary source, or the primary source was
  ambiguous, or (for ISO 27001, whose full text is paywalled) cross-checked
  against at least two independent public summaries.
- `low` — the underlying fact itself, or this specific mapping to it,
  could not be reliably sourced this session. See
  `rbi_2026_directions.yaml`'s top-of-file warning and
  `sebi_cscrf_cci.yaml`'s coverage warning for examples of what "low" looks
  like in practice — including a file that could only source 4 of a
  framework's 23 defined parameters, and one where the regulation's own
  existence could not be confirmed against any primary source.

## Every file must be versioned and effective-dated

Frameworks change. RBI's 2016 Cyber Security Framework was repealed 31 July
2026 and replaced by entity-specific Directions, 2026 — a control library
file that doesn't carry its own `version` and `effective_from`/
`effective_to` has no way to express that change, and
`governance/library_loader.py` has no way to reject a stale version. See
repo-root `CLAUDE.md` principle 8.

## File shape

```yaml
framework: <stable key, matches the filename stem>
version: <version identifier for this framework as issued by its regulator/body>
effective_from: <ISO 8601 date this version took effect>
effective_to: <ISO 8601 date this version was/will be superseded, or null if current>
supersedes: <framework+version key this replaces, or null>

sources:                                # bibliography for the whole file
  - url_or_citation: <string>
    retrieved: <ISO 8601 date this session actually retrieved/read it>
    covers: <what part of this file it supports>

controls:
  - id: <stable snake_case id, unique within this file>
    framework_ref: <the framework's own reference, e.g. "A.9.4.2", "PR.AC-7", "6.5">
    parameter_name: <short human-readable title>
    weight: <float|null>                # for weighted composite scores (e.g. SEBI's CCI); null if not weighted or not found
    description: <1-2 sentences, our own words — never verbatim copyrighted standard text>
    maturity_bands: <list|null>         # per-control maturity tiers, if the framework defines them at that granularity

    source: <citation for this specific entry>
    confidence: high | medium | low
    verified_by_human: false            # always false until a human reviews it

    telemetry_check:
      derivable_from_telemetry: <bool>
      source_field: <human-readable schema path(s) — documentation only, NOT executed>
      logic: <human-readable rule — documentation only, NOT executed>
      check_type: <name of an executable check in governance/mapper.py, or null>
      check_params: <parameters for check_type — this is what actually runs>

    manual_attestation_required: <bool>
    attestation_prompt: <string|null>
    attestation_validity_months: <int|null>   # overrides core.assumptions.DEFAULT_ATTESTATION_VALIDITY_MONTHS

penalty_provisions:                     # sourced statutory monetary penalties — see below
  - id: <stable snake_case id, unique within this file>
    statute: <the act/regulation creating this penalty power>
    provision_ref: <specific section/clause>
    description: <what triggers this penalty, our own words>

    penalty_amount_inr: <float|null>    # statutory ceiling, or null if no single figure applies
    penalty_formula: <string>           # human-readable, e.g. "greater of X or 2x gain, plus Y/day"
    currently_in_force: <bool>          # a provision can be enacted but not yet commenced
    in_force_from: <ISO 8601 date|null> # commencement date, if known

    source: <citation for this specific provision>
    confidence: high | medium | low
    verified_by_human: false
```

## Penalty provisions

`penalty_provisions` is a **separate, optional list**, distinct from
`controls`, that carries sourced statutory monetary fine/penalty amounts a
regulator can impose for non-compliance under this framework. It exists
because `core.assumptions.EXPECTED_REGULATORY_PENALTY_INR` needs a sourced,
versioned figure to be calibrated against, per repo-root `CLAUDE.md`'s
no-magic-numbers rule.

**This must never be confused with a compliance verdict.** A
`penalty_provision` is a fact about what a regulator *can* fine an entity
for a category of failure — it carries no `telemetry_check`, no
"met"/"not_met" status, and `governance/mapper.py` never reads it. Only
`core/`'s FAIR/Monte Carlo modelling (once implemented) is the intended
consumer, as an input to the "regulatory penalty" loss-magnitude factor —
never as a compliance signal (CLAUDE.md principle 6).

Not every framework has a direct statutory penalty of its own. CIS
Controls, NIST CSF, and ISO 27001 are voluntary frameworks — no regulator
fines an organization for failing a specific safeguard/subcategory/control
in them directly — so their files carry `penalty_provisions: []` (or omit
the key). Only frameworks backed by an actual Indian statute with monetary
penalty powers (RBI, SEBI, and the DPDP Act) carry populated entries. A
provision can also be enacted but not yet enforceable —
`currently_in_force: false` / `in_force_from` exists precisely for the DPDP
Act's phased commencement (see `dpdp_act_2023.yaml`).

`telemetry_check.check_type`/`check_params` is what `governance/mapper.py`
actually executes against a snapshot — `source_field`/`logic` are
human-readable documentation of the same rule, kept in sync by convention,
never parsed at runtime. See `governance/library_loader.KNOWN_CHECK_TYPES`
for the fixed set of check types mapper.py knows how to run, and
`governance/mapper.py`'s module docstring for how a missing/null field
always resolves to `"unknown"`, never `"not_met"`.

## Files

| File | Framework | Coverage this session |
|---|---|---|
| `cis_controls.yaml` | CIS Critical Security Controls v8.1 | 12 telemetry-derivable + 6 attestation-only controls; safeguard text not independently verified against a primary PDF (fetch failed) — confidence capped at medium |
| `nist_csf.yaml` | NIST Cybersecurity Framework 2.0 | 11 telemetry-derivable + 8 attestation-only subcategories; read directly from the primary NIST document — confidence high throughout |
| `iso_27001.yaml` | ISO/IEC 27001:2022 Annex A | 9 telemetry-derivable + 14 attestation-only controls; standard text is paywalled, IDs/titles cross-checked against 2+ public sources — confidence capped at medium |
| `rbi_2026_directions.yaml` | RBI entity-specific Directions, 2026 (NBFC-ML) | 5 telemetry-derivable + 5 attestation-only entries; **the regulation's own existence could not be confirmed against any RBI primary source** — every entry confidence: low, see the file's top-of-file warning. Carries 1 penalty provision (RBI Act s.58G, confidence: medium — general NBFC penalty power, not specific to the unconfirmed 2026 Directions) |
| `sebi_cscrf_cci.yaml` | SEBI CSCRF Annexure-K (Cyber Capability Index) | Framework metadata confirmed (primary, sebi.gov.in); **only 4 of the 23 defined parameters could be sourced at all**, none with a confirmed weight — see the file's coverage warning. Carries 1 penalty provision (SEBI Act s.15HB, confidence: high, fetched directly from sebi.gov.in) |
| `dpdp_act_2023.yaml` | Digital Personal Data Protection Act, 2023 | **Penalty schedule only** — no per-asset `controls` (see file's own explanation). 4 penalty provisions (security safeguard failure ₹250cr, breach notification failure ₹200cr, Significant Data Fiduciary breach ₹150cr, residual ₹50cr), confidence: medium (Gazette PDF unreachable this session, corroborated via multiple secondary sources). **All 4 currently NOT in force** — Section 33 (the penalty machinery) commences 2027-05-13 |

None of these files should be treated as legally authoritative without a
human review against the actual current text of each framework — that is
precisely what `verified_by_human: false` on every entry is flagging.
