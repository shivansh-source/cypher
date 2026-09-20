# `governance/control_library/`

Versioned, effective-dated, **sourced** definitions of controls for each
regulatory/industry framework Su₹aksha maps findings against.
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
```

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
| `rbi_2026_directions.yaml` | RBI entity-specific Directions, 2026 (NBFC-ML) | 5 telemetry-derivable + 5 attestation-only entries; **the regulation's own existence could not be confirmed against any RBI primary source** — every entry confidence: low, see the file's top-of-file warning |
| `sebi_cscrf_cci.yaml` | SEBI CSCRF Annexure-K (Cyber Capability Index) | Framework metadata confirmed (primary, sebi.gov.in); **only 4 of the 23 defined parameters could be sourced at all**, none with a confirmed weight — see the file's coverage warning |

None of these files should be treated as legally authoritative without a
human review against the actual current text of each framework — that is
precisely what `verified_by_human: false` on every entry is flagging.
