# Connectors

Su₹aksha does not know which security tool a finding came from. Every connector in
`infra/connectors/` turns one tool's output into the shared contract
(`schema/aggregated_assets.schema.json`); the engine, the quality gates and the compliance
mapper read only that contract. Adding a customer's tool means writing one connector. Nothing in
`core/` or `governance/` changes.

Written for: engineers maintaining or extending the platform, and anyone who needs an honest
account of what data each connector produces today. Status as of **2026-09-26**.

## Status vocabulary

| Status | Meaning |
|---|---|
| **Live** | Code and tests done, and real data from the LoanEase sandbox is in the current snapshot. |
| **Ready** | Code and tests done and checked against real tool output, but not yet in a published snapshot. |
| **Planned** | A stub (`NotImplementedError`) or roadmap item. Nothing works yet. |

"Live" describes *this sandbox*. Wazuh and Greenbone run from exported files today, not live APIs
(see each entry).

## Catalog

| Connector | Category | Status | Input | Findings / data it emits | Asset identity |
|---|---|---|---|---|---|
| `prowler_connector` | CSPM (AWS) | **Live** | S3 object `latest/prowler_connector.json`, Prowler 5.43 `json-asff` output, unmodified | `misconfiguration` findings for every `FAILED` check (121 in the current snapshot; 119 in the first run) | one asset per resource: `cloud:<resource ARN, lowercased>` |
| `iam_connector` | Identity (AWS IAM) | **Live** | local file `IAM_PMAPPER_OUTPUT_PATH` = `pmapper analysis --output-type json` | `misconfiguration` findings (2 in the sandbox, both about `tf-bootstrap`) | one account asset: `cloud:aws-account:<account id>` |
| `cmdb_connector` | Asset inventory | **Live** (via EC2 export) | `CMDB_EXPORT_PATH` JSON from `infra/inventory/export_ec2_inventory.py`, **or** a REST CMDB (`CMDB_BASE_URL` + `CMDB_API_TOKEN`) | `endpoints[]` (hostnames, private IPs, instance and volume ARNs) with canonical id `cmdb:<id>` | canonical `cmdb:<name>` |
| `wazuh_connector` | SIEM / EDR | **Live** (file mode) | `WAZUH_EXPORT_PATH` bundle from `infra/inventory/build_wazuh_bundle.py` (alerts file + `agent_control -l`), **or** the Wazuh manager API + indexer | `assets[].edr` per agent: installed, healthy, recent alerts (4 agents in the sandbox) | `host:<agent IP>`, or `host:<name>` if no usable IP |
| `greenbone_connector` | Vulnerability scanner | **Live** (file mode) | `GREENBONE_EXPORT_PATH`: a GMP report XML (`infra/bastion/export_greenbone_report.sh`) or a GSA "CSV Results" export, **or** GMP over TLS | `cve`-typed findings incl. Log-severity detections (92 findings on 5 hosts) | `host:<IP>` |
| `scoutsuite_connector` | CSPM (AWS) | **Ready** (becomes Live on the next full run) | S3 object `latest/scoutsuite_connector.json` = ScoutSuite 5.14.0 `scoutsuite_results_*.js` | 48 findings in the sandbox, all with `counts_toward_loss: false` (evidence only) | one account asset: `cloud:aws-account:<account id>` |
| `network_topology_connector` | Network exposure / attack-graph topology | **Live** | `NETWORK_TOPOLOGY_EXPORT_PATH` JSON from `infra/inventory/export_network_topology.py` (read-only `ec2:Describe{Vpcs,Subnets,Instances,SecurityGroups}`) | `assets[].network` (`segment_id`, `internet_facing`) plus the top-level `network_topology` object; feeds `core/engine/attack_graph*.py`, which changes EAL/VaR | attaches to whichever of `host:<ip>` / `cloud:<instance ARN>` another connector already created (see "Identity" below) |
| `threat_intel_connector` | EPSS + CISA KEV enrichment | **Planned** | none | none. Until built, `epss_score` and `kev_listed` are always null and exploit probability falls back to the baseline | n/a |
| `nessus_connector` | Vulnerability scanner | **Planned** | none | none | n/a |
| `nmap_connector` | Network exposure | **Planned** | none | none. No connector yet supplies `network_topology` or `segment_id` (the attack graph is therefore empty) | n/a |

**Roadmap examples** a customer could ask for and that fit the same contract: Okta / Entra ID (identity),
CrowdStrike / Defender (EDR), Splunk / Sentinel (SIEM), ServiceNow (CMDB), Tenable / Qualys (vulnerability
scanning). None of these exist in code.

## How a connector works

Every connector subclasses `infra/connectors/base.py::Connector` and implements three steps, always
in this order:

1. `fetch()` returns the tool's raw output, parsed but untransformed. **A failed fetch must raise**,
   never return an empty list. `ingest` records the connector as `unreachable`, so absence of data
   is never read as "scanned, found nothing".
2. `normalize(raw)` maps it into schema-shaped fragments. All tool-specific vocabulary (severity
   scales, identifiers) ends here.
3. `resolve_asset_id(fragment)` attaches a stable asset id. Fragments carry a private `_identity_hint`
   that `Connector.run()` strips before anything reaches a snapshot.

Rules every connector obeys (they were each enforced by a real bug we hit):

- **Never fabricate.** No invented timestamps, criticalities, CVE ids or `raw_source_id` values. Missing
  data raises an error, or is the explicit literal `"unknown"` where the schema allows it.
- **Report what the tool reported.** Severity comes from the tool; the map is a direct rename, kept in
  the connector.
- **The engine never learns the source.** No `if source == "prowler"` anywhere outside `infra/connectors/`.

### The "file source" pattern

Tools whose live API is unreachable in a given deployment (Wazuh without an indexer, Greenbone with
no published gvmd port) also read an **operator-produced export file**. When the `*_EXPORT_PATH`
variable is set, the connector reads the file instead of calling the API, and does not write it back to
the object store (the file is its own audit artifact). A missing, unparseable or empty file raises a
named error. An export with zero results is rejected rather than treated as a clean scan.

## Identity: placeholder schemes and the duplicate-asset caveat

There is no real cross-tool identity resolution yet. Connectors mint placeholder ids:

| Scheme | Minted by | Example |
|---|---|---|
| `cloud:<ARN>` | Prowler | `cloud:arn:aws:ec2:ap-south-1:627984120842:instance/i-06d5...` |
| `cloud:aws-account:<id>` | PMapper, ScoutSuite | `cloud:aws-account:627984120842` |
| `host:<ip or name>` | Wazuh, Greenbone | `host:10.20.1.129` |
| `cmdb:<name>` | CMDB | `cmdb:loanease-db` (in `endpoints[]`, not `assets[]`) |

The **same machine therefore appears twice**: as a `host:` asset (Wazuh EDR, Greenbone findings) and as a
`cloud:` ARN asset (Prowler findings). A Jev (LLM) merge step can join them using CMDB evidence
(`interfaces/cli/riskctl.py::_resolve_identities`), but it needs `TYPESAFE_API_KEY`, which is not set.
Until it is, EDR posture does not attach to the ARN assets where Prowler's findings live, so Wazuh
improves coverage and the asset views but not the loss figure.

## Freshness rules (what makes a scanner "not reporting")

| Input | Rule | Where enforced |
|---|---|---|
| Prowler object | reject if the S3 object is over 24h old | `prowler_connector.py` |
| ScoutSuite object | reject if over 24h old | `scoutsuite_connector.py` |
| PMapper file | drop if over 48h old | `.github/scripts/fetch-input.sh` (workflow) |
| Wazuh bundle | drop if over 30h old | workflow |
| Greenbone report | any age accepted (findings carry their own scan timestamp) | workflow |

A dropped or missing input leaves that connector unconfigured, so `ingest` records it under
`scan_scope.unreachable_scanners` and the dashboard shows a coverage caveat.

## Real-output findings (why fixtures say "real" or "synthetic")

Each connector was first written against an assumed format and then corrected against real output.
Tests state which fixtures are real and which are synthetic.

- **Prowler:** the flat `CheckID`/`Status` shape was assumed; the real files are ASFF
  (`GeneratorId`, `Compliance.Status`, `Severity.Label`, `Resources[].Id`, `FirstObservedAt`). The OCSF
  format was rejected because its `created_time_dt` is a naive local-time string (5.5 h off from UTC).
- **PMapper:** real top-level keys are `account` and `date_and_time` (not the names in the source read).
  Principals appear only as free-text bullets in `description`, so findings attach to the account asset.
- **Greenbone:** a report nests `<result>` elements inside `<detection>` blocks that are *not* findings
  (19 of 111 in the sandbox report). Only results directly under a `<results>` element are findings.
- **Wazuh:** `agent_control -l` prints `IP: any` for agents. The real IP comes from the agent's own
  alerts, used only when every alert agrees. An agent that never connected is not an installed agent.
- **ScoutSuite:** the real file has no trailing `;`, and its resource ids are internal dotted paths, not
  ARNs, which is why findings attach to the account asset (44 unmatched assets would have failed the
  asset-count gate).

## Findings that don't count toward loss

The schema has an optional finding field `counts_toward_loss` (absent means true). `false` keeps a
finding in the snapshot as evidence (visible, usable for compliance) but the engine does not turn it
into a loss-event scenario. ScoutSuite sets it because it overlaps Prowler and counting both raised the
expected annual loss by about ₹32M for issues Prowler already reports. This is a modelling judgement
recorded in `docs/ASSUMPTIONS.md`. It is not a remediation claim, and it also excludes ScoutSuite-only
issues.

## Network topology: what `internet_facing` means, and why `segment_reachability` is empty

`network_topology_connector.py` observes two real, non-guessed facts per EC2 instance:

- **`segment_id` = the instance's actual VPC subnet id.** A subnet is a real, observable
  boundary, not a judgement call. The sandbox has exactly one subnet, so all four instances
  share one segment — which the engine reads as "mutually reachable within the segment",
  matching the sandbox's real, deliberate lack of internal network segmentation.
- **`internet_facing` = "this instance's security group has an ingress rule naming an address
  outside the VPC's own CIDR block"** (checked with `ipaddress.subnet_of`, not a literal
  `0.0.0.0/0` string match). In this sandbox every rule is scoped to the operator's single home
  IP, none to `0.0.0.0/0` — but that IP is still genuinely outside the VPC, so traffic to reach
  it still crosses the public internet. Under this definition the portal and bastion are
  internet-facing (their security groups admit that external IP); the DB and endpoint are not
  (their only inbound sources are the VPC's own CIDR or another security group, i.e. reachable
  only by first pivoting through something already inside the VPC). A rule that only references
  another security group is never counted as internet-facing by itself, for the same reason.

`segment_reachability` (edges *between* different segments) is left empty here on purpose: real
cross-subnet reachability needs route-table and NACL analysis this connector does not attempt,
and the schema is explicit that an unlisted pair means "no assumed reachability" — an honest
empty answer, not a gap to paper over with a guess.

**Measured real effect** (current snapshot, common-random-numbers seed): merging this connector's
real output turned the attack graph from 0 edges to 56 real same-segment edges, made the portal
and bastion the graph's entry points, and made the DB and endpoint asset entries reachable
through them — which raised Expected Annual Loss from about ₹14.49 Cr to ₹25.9 Cr and VaR (95th
percentile) from about ₹26.4 Cr to ₹42.4 Cr. This is a large, real change driven entirely by
observed AWS data (which hosts are reachable from where), not a new assumption.

## Adding a connector

1. Get **real output** from the tool first. Do not code against documentation alone; every connector here
   was wrong about something until it saw real data.
2. Subclass `Connector`; set `name` to the module name; implement `fetch`, `normalize`, `resolve_asset_id`.
3. Emit only schema fields. Map severity with a direct-rename dict local to the connector.
4. Give findings `provenance.connector` and a `provenance.raw_source_id` taken from the tool (never
   invented), and a real `first_seen_at`.
5. Add tests under `infra/tests/` with a fixture in the tool's real shape (label it real or synthetic) and a
   `jsonschema.validate` of a snapshot built from the output.
6. Register it in `interfaces/cli/riskctl.py::ingest_command` with its own error class and document its
   env vars in `.env.example`.
7. Add a row to the catalog above.
