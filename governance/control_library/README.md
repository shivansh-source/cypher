# `governance/control_library/`

Versioned, effective-dated definitions of controls for each regulatory /
industry framework Su₹aksha maps findings against. `governance/mapper.py`
reads these files; `core/` never reads them directly (compliance mapping is
governance's job, not the engine's — see repo-root `CLAUDE.md` principle 6).

## Every file must be versioned and effective-dated

Frameworks change. RBI's 2016 Cyber Security Framework was repealed 31 July
2026 and replaced by entity-specific Directions, 2026 — a control library
file that doesn't carry its own `version` and `effective_from`/
`effective_to` has no way to express that change, and
`governance/mapper.py` has no way to reject a stale version. See repo-root
`CLAUDE.md` principle 8.

Every file in this directory follows the same top-level shape:

```yaml
framework: <stable key, matches the filename stem>
version: <version identifier for this framework as issued by its regulator/body>
effective_from: <ISO 8601 date this version took effect>
effective_to: <ISO 8601 date this version was/will be superseded, or null if current>
supersedes: <framework+version key this replaces, or null>
controls:
  - control_id: <stable id, unique within this framework+version>
    title: <short human-readable title>
    description: <what this control requires>
    maps_to_finding_types: [<finding "type" values from the aggregated schema this control is evidenced by>]
```

## Files

| File | Framework |
|---|---|
| `cis_controls.yaml` | CIS Critical Security Controls |
| `nist_csf.yaml` | NIST Cybersecurity Framework |
| `iso_27001.yaml` | ISO/IEC 27001 Annex A controls |
| `rbi_2026_directions.yaml` | RBI entity-specific Directions, 2026 (supersedes the repealed 2016 Cyber Security Framework) |
| `sebi_cscrf_cci.yaml` | SEBI Cybersecurity and Cyber Resilience Framework / Cyber Capability Index |

Every file here is currently a skeleton with placeholder values — see the
`TODO` comments inline. None should be treated as legally authoritative
without review against the actual current text of each framework.
