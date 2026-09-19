---
description: Add a new connector without drifting from the shared schema contract
---

# Add a new connector

Every connector's only job is: fetch raw tool output → normalize it into
`schema/aggregated_assets.schema.json` → attach it to a resolved
`asset_id`. Nothing downstream of `infra/connectors/` may ever learn which
tool a piece of data came from — if it needs to, normalization happened in
the wrong place. Read `core.CLAUDE.md` principle 3 before starting.

1. Read `schema/aggregated_assets.schema.json` and `schema/README.md` in
   full before writing anything. Identify exactly which top-level section(s)
   the new tool's data belongs under (`services`, `assets.findings`,
   `assets.threat_intel`, `assets.edr`, `assets.identity_access`,
   `assets.network`, `endpoints`). Do not invent a new top-level section
   without updating the schema first and flagging that as a schema change,
   not a connector change.
2. Subclass `infra.connectors.base` (see its docstring for the fetch →
   normalize → attach contract). Do not bypass the base class's interface
   even if the tool's raw output would be more convenient to pass through
   directly.
3. Write normalization logic that maps every field the tool provides to the
   matching schema field, and nothing else — do not smuggle
   tool-specific fields into the output as extras "just in case". If a
   piece of data doesn't fit the schema, that's a schema gap to raise, not
   a reason to add a side channel.
4. Resolve the asset_id using whatever identity-resolution mechanism the
   codebase already uses (check `infra/connectors/cmdb_connector.py` and
   sibling connectors for the established pattern) — do not invent a new
   identity key per connector.
5. Add a fixture of real (or realistic, anonymized) raw output from the
   tool and a test asserting the normalized output validates against
   `schema/aggregated_assets.schema.json`.
6. Update `schema/README.md` if the connector reveals a field description
   that was missing or unclear — the schema doc should stay accurate to
   what real tools actually produce.
