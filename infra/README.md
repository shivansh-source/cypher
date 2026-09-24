# `infra/`

Connectors that pull raw output from security tools and normalize it into
the shared contract at `schema/aggregated_assets.schema.json`. See
`infra/connectors/base.py` for the fetch → normalize → attach contract
every connector obeys, and `.claude/commands/add-connector.md` for the
workflow to follow when adding a new one.

## Connectors in this repo

| Connector | Source tool | Schema sections populated |
|---|---|---|
| `nessus_connector.py` | Tenable Nessus | `assets[].findings` (CVEs) |
| `greenbone_connector.py` | Greenbone (OpenVAS/GVM) | `assets[].findings` (CVEs) |
| `prowler_connector.py` | Prowler (CSPM) | `assets[].findings` (misconfigurations) |
| `scoutsuite_connector.py` | ScoutSuite (CSPM) | `assets[].findings` (misconfigurations) |
| `wazuh_connector.py` | Wazuh (EDR/SIEM) | `assets[].edr`, optionally `assets[].findings` |
| `iam_connector.py` | AWS IAM via PMapper (`IAM_PMAPPER_OUTPUT_PATH`, a `pmapper analysis --output-type json` file) | `assets[].findings`, attached to the account-level asset |
| `cmdb_connector.py` | CMDB REST API, or a JSON inventory file (`CMDB_EXPORT_PATH`, e.g. from `infra/inventory/export_ec2_inventory.py`) | `endpoints[]`, canonical asset identity |
| `nmap_connector.py` | nmap | `assets[].network`, `endpoints[]` |
| `threat_intel_connector.py` | EPSS + CISA KEV | enrichment of existing `findings[].epss_score` / `.kev_listed` |

`cmdb_connector.py` is special: it is the canonical source of asset
identity, and (as of its implementation) the target every other
connector's placeholder id gets reconciled against — see "Identity
resolution via Jev" below. Unlike every other connector, its own
`resolve_asset_id` needs no placeholder scheme at all: CMDB *is* the
identity authority, so it computes the final `cmdb:<id>` asset id directly
at normalize time. It normalizes into `endpoints[]` only; `services[]`
normalization remains an unimplemented, explicitly documented gap (see the
module's own docstring — that mismatch is a distinct, already-flagged open
schema question, not part of identity resolution).
`threat_intel_connector.py` is also
special: it enriches findings already produced by another connector
(matching on `cve_id`) rather than producing standalone findings from a
scan of its own.

`greenbone_connector.py` plays the role `nessus_connector.py` plays
elsewhere (both populate CVE findings from a vulnerability scanner) — this
deployment's actual tool stack runs Greenbone, not Nessus. Both connector
files exist in this repo, but only `greenbone_connector.py` is currently
wired into `interfaces/cli/riskctl.py`'s `ingest_command`; `nessus_connector.py`
remains an unimplemented stub, kept for reference/future deployments that
do run Nessus instead.

## Raw findings object store (`_object_store.py`)

`wazuh_connector.py` and `greenbone_connector.py` call live tool APIs
directly and, on success, persist their raw payload to S3 via
`_object_store.write_raw` purely for auditability (write-only from their
perspective). `prowler_connector.py` and `scoutsuite_connector.py` never
call a live API at all: Prowler and ScoutSuite already ran as one-shot CLI
scans in CI and pushed their raw output to S3 out-of-band, so those two
connectors' entire `fetch()` implementation is
`_object_store.read_latest`/`read_latest_text`.

Layout in the bucket named by the `RAW_FINDINGS_BUCKET` env var (region
from `AWS_REGION`):

- `latest/<connector_name>.json` — the most recent raw payload for that
  connector, overwritten on every successful `write_raw` call. This is
  what `read_latest`/`read_latest_text` read back, and what a stale-check
  (a per-connector `STALENESS_THRESHOLD_SECONDS`/similar constant) guards.
- `<connector_name>/<UTC timestamp>.json` — an append-only, never-overwritten
  audit trail of every raw payload a connector has ever written.

A missing bucket configuration, a missing/unreadable object, or a stale
`latest/` object all raise `ObjectStoreError` — never a silent empty
result — so the calling connector can propagate a specific error for
`scan_scope.unreachable_scanners` to record.

## The `_identity_hint` bridging convention

`wazuh_connector.py`, `prowler_connector.py`, `greenbone_connector.py`, and
`scoutsuite_connector.py` each attach a private, non-schema
`_identity_hint: {"kind": ..., "value": ...}` key to every fragment
`normalize()` produces. Each connector's `resolve_asset_id` reads its own
`_identity_hint.value` and mints a placeholder `host:`/`cloud:`-prefixed
asset_id from it. `Connector.run()` strips every `_`-prefixed key before
returning, so `_identity_hint` never reaches a schema-shaped snapshot
(schema's `additionalProperties: false` would reject it if it did).

`cmdb_connector.py` is now implemented, but these four connectors still
mint their own placeholder ids rather than resolving against CMDB's
identity scheme directly — connectors must never import `ai/` (see
repo-root `CLAUDE.md`'s module ownership map), and reconciling a
placeholder id against CMDB now requires a Jev call (see below), so that
reconciliation cannot happen inside `resolve_asset_id` itself. Instead,
`interfaces/cli/riskctl.py`'s `ingest_command` reconciles placeholder ids
against CMDB's canonical ids as a step *after* every connector has run.
An asset whose placeholder id cannot be matched to a CMDB record with
sufficient confidence keeps its placeholder id — this remains a
legitimate, if less resolved, terminal state, not a defect.

## Identity resolution via Jev

`cmdb_connector.py` normalizes every identifier CMDB has on file for an
asset (hostnames, IPs, cloud instance ids) into `endpoints[]` entries, each
carrying `resolved_asset_id` set to that asset's canonical `cmdb:<id>` id —
see the module's own docstring. `infra/connectors/_identity_resolution.py`
(a private, non-connector helper, like `_object_store.py`/`_env.py`) then:

1. Finds every placeholder asset id (from the other four connectors) that
   shares at least one identifier value with a CMDB canonical asset
   (`find_candidate_merges`) — never a blind pairwise comparison of every
   asset against every other.
2. Renders each candidate's evidence into a human-readable state string
   (`render_evidence_state`), distinguishing same-kind evidence (e.g. a
   shared cloud instance id — strong) from cross-kind evidence (e.g. a
   hostname-shaped placeholder matching a CMDB IP record — weak).

`interfaces/cli/riskctl.py`'s `ingest_command` is the only place that
actually calls Jev (`ai.jev_transport.JevTransport`, TypeSafe AI's "System
One" model — see that module's docstring for why it's not chat-shaped):
one `TypedQuestion` per candidate, asking whether the two ids name the same
real-world asset. `infra.connectors._identity_resolution.MERGE_CONFIDENCE_THRESHOLD`
(documented in `docs/ASSUMPTIONS.md`) is then applied: at or above it, the
placeholder asset is merged into the canonical one (findings concatenated,
never dropped); below it, the two stay separate. **Every** decision —
merged or not — is recorded append-only, with its full evidence trail and
Jev's confidence, via `record_merge_decision` to
`IDENTITY_RECONCILIATION_STORE_PATH` (`.env.example`), so a below-threshold
non-merge is never silently lost — it is exactly the record a human
reconciling identities later needs. If `TYPESAFE_API_KEY` is not
configured, identity resolution is skipped entirely (echoed, not silent)
and every asset keeps whatever id it already had; this never blocks
`ingest_command`'s quality gates or commit.

## `docker-compose.yml`

A skeleton only. Nothing here is wired up — see the `TODO` comments inline.
Do not deploy this as-is; it has no real secret management and no built
images. It composes three kinds of services: the FastAPI backend (`api`),
the Next.js frontend (`dashboard`, under `interfaces/dashboard/`), and
persistence/scheduling (`db`, `connector-scheduler`). `dashboard` talks to
`api` over HTTP only.

## Design notes

- Connectors must never special-case downstream behavior based on the
  source tool once data has left `infra/connectors/` — see repo-root
  `CLAUDE.md` principle 3.
- A connector that cannot reach its tool must raise, not return an empty
  result — the aggregation pipeline needs the failure to record the
  connector under `scan_scope.unreachable_scanners` (see
  `schema/README.md`).


## Other folders

- `infra/inventory/` — operator-run helpers that produce connector input files
  (currently `export_ec2_inventory.py`, the AWS stand-in for a CMDB).
- `infra/terraform/` — the LoanEase sandbox that generates the telemetry; see
  its own `README.md` and `manifest.yaml`.
