# `schema/`

This directory is the one shared contract in the whole system. Every
connector in `infra/connectors/` normalizes its tool's raw output into the
shape defined by `aggregated_assets.schema.json`, and `core/` reads only
that shape. Nothing downstream of aggregation may know which tool a piece
of data came from — see `CLAUDE.md` principle 3 at the repo root.

## Files

- **`aggregated_assets.schema.json`** — the JSON Schema itself. Treat
  changes to this file as a bigger deal than changes anywhere else in the
  repo: every connector and every consumer in `core/` and `governance/`
  depends on it. Fields marked with a `TODO` comment in their
  `description` are known-open design questions, not implementation gaps —
  resolve them deliberately, not incidentally while building a connector.
- **`sample_aggregated.json`** — a small, fully schema-valid fixture with
  illustrative (not real) data, covering: a critical internet-facing
  finding with EPSS/KEV data, a finding with unknown criticality, a service
  with good backup posture and one with none, and an unreachable scanner in
  `scan_scope`. Used by `.claude/commands/run-engine.md` to exercise the
  engine without a live connector.

## Field notes worth calling out explicitly

- **`scan_scope`** exists so that "no finding reported" can be told apart
  from "the scanner that would have found it never ran". Any consumer that
  treats absence-of-finding as evidence of remediation without checking
  `scan_scope.unreachable_scanners` first is making a fail-open assumption
  this schema was designed to prevent.
- **`snapshot_id`** is a content hash of the normalized payload, not a
  sequence number or timestamp. It's what makes snapshots content-addressed
  and lets the system detect "nothing material changed" without a manual
  diff.
- **`valid_from` / `valid_to` / `observed_at`** are the bitemporal fields.
  `observed_at` is when the pipeline ran; `valid_from`/`valid_to` describe
  the period the snapshot's facts are asserted to hold. Snapshots are never
  mutated after creation — `valid_to` is the only field ever set after the
  fact, and only when a later snapshot supersedes this one.
- **`findings[].criticality`** distinguishes `null` (never evaluated — a
  defect) from the literal string `"unknown"` (evaluated, scanner couldn't
  determine severity). Quality gate 3 in `core/snapshot.py` should reject
  the former and accept the latter.
- **`findings[].provenance`** is mandatory on every finding (quality gate
  4). `raw_source_id` is kept for auditability/debugging only and must
  never be read by `core/` or `governance/` — if a downstream module
  needs `provenance.connector` to decide behavior, that's principle 3 being
  violated.

## Adding a new connector

See `.claude/commands/add-connector.md` — it walks through fitting a new
tool's data into this schema without drifting from it.
