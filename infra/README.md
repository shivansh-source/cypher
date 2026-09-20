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
| `iam_connector.py` | IAM provider (Entra/AWS IAM/Okta) | `assets[].identity_access` |
| `cmdb_connector.py` | CMDB | `services[]`, canonical asset identity |
| `nmap_connector.py` | nmap | `assets[].network`, `endpoints[]` |
| `threat_intel_connector.py` | EPSS + CISA KEV | enrichment of existing `findings[].epss_score` / `.kev_listed` |

`cmdb_connector.py` is special: it is the canonical source of asset
identity, and every other connector's `resolve_asset_id` must resolve
against the identity scheme it defines. `threat_intel_connector.py` is also
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
`normalize()` produces. It exists only because `cmdb_connector.py` — the
codebase's intended canonical source of asset identity — is still an
unimplemented stub with its own unresolved TODO on identity keys. Each
connector's `resolve_asset_id` reads its own `_identity_hint.value` and
mints a placeholder `host:`/`cloud:`-prefixed asset_id from it.
`Connector.run()` strips every `_`-prefixed key before returning, so
`_identity_hint` never reaches a schema-shaped snapshot (schema's
`additionalProperties: false` would reject it if it did). This is an
explicitly-flagged placeholder, not a permanent identity scheme — once
`cmdb_connector.py` is implemented, every connector's `resolve_asset_id`
should resolve against its identity scheme instead.

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
