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
| `prowler_connector.py` | Prowler (CSPM) | `assets[].findings` (misconfigurations) |
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
