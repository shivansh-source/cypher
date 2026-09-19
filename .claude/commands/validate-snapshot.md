---
description: Validate a candidate aggregated snapshot before it becomes current
---

# Validate a candidate snapshot

Use this before promoting any newly aggregated snapshot to "current". A
snapshot that fails validation must never become current — the previous
snapshot stays current instead (fail-safe, never fail-open).

1. Confirm the candidate file validates against
   `schema/aggregated_assets.schema.json` structurally (required fields
   present, types correct, `snapshot_id`/`observed_at`/`valid_from`/
   `valid_to`/`scan_scope` all populated).
2. Run all 5 quality gates from `core/snapshot.py` against the candidate,
   comparing to the current snapshot where the gate requires a delta:
   - asset-count delta within tolerance
   - no findings attributed to a scanner marked unreachable in `scan_scope`
   - every finding has criticality present or explicitly marked unknown
     (never silently defaulted)
   - every finding has non-null provenance
   - no ordinal value (e.g. "High"/"Medium"/"Low") stored in a field typed
     as numeric
3. Report each gate's pass/fail individually — do not collapse to a single
   pass/fail without saying which gate(s) failed.
4. If all gates pass, call `core.snapshot.commit_snapshot` and report the
   new `snapshot_id`. If any gate fails, do not commit — report which
   gate(s) failed, why, and that the previous snapshot remains current.
5. Never modify the candidate data to force a gate to pass. If the data is
   wrong, the fix belongs in the connector that produced it
   (`infra/connectors/`), not in the validation step.
