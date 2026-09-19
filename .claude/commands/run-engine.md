---
description: Run the FAIR + Monte Carlo engine against a sample aggregated snapshot
---

# Run the engine against a sample

Use this to sanity-check the engine end to end against
`schema/sample_aggregated.json` without needing a live connector.

1. Confirm `schema/sample_aggregated.json` validates against
   `schema/aggregated_assets.schema.json`. If it doesn't, fix the sample
   first — the engine must never run against a shape the schema wouldn't
   accept in production.
2. Load the sample through `core.snapshot.validate_snapshot`, then
   `core.snapshot.commit_snapshot`. If any of the 5 quality gates fail, stop
   and report which one — do not force a commit past a failing gate.
3. Run `core.engine` against the committed snapshot to produce EAL and VaR.
4. Report the figures along with the top loss-event contributors
   (`core.engine` should expose this; if it only returns a bottom line,
   that's a gap worth flagging, not working around).
5. Cross-check every constant the engine used against
   `core/assumptions.py` — there should be no numeric literal in the run
   path that isn't named and justified there.

Do not hand-wave a result if the engine isn't implemented yet. Say plainly
what ran and what's still a stub.
