# Build log — 24 to 26 September 2026

A record of what was built between the LoanEase sandbox hand-off and the hosted, daily-refreshing
platform: what changed, why, what broke, and what is still open. Written for the team and for anyone
picking the project up (or rebuilding it for the finals) without the original conversation.

Related documents: `docs/CONNECTORS.md` (connector catalog), `docs/OPERATIONS.md` (running,
hosting, cost, runbooks), `docs/DASHBOARD_WIRING.md` (dashboard ↔ API), `docs/ASSUMPTIONS.md` (modelling
constants and honesty notes), `infra/terraform/manifest.yaml` (planted vulnerabilities).

## 1. Where we started

- **`loanease-sim`**: a deliberately vulnerable AWS sandbox (account `627984120842`, `ap-south-1`) built
  to generate real telemetry. Because of an 8 vCPU Free Plan limit it is 4 instances in one public subnet
  with no NAT: portal, DB, endpoint and one bastion that also hosts Wazuh (manager only) and Greenbone.
  Six vulnerabilities were planted and verified (V-01 to V-06).
- **`ps105`** (this repo): the platform. The hand-off's guess that `core/snapshot.py` was the blocker was
  wrong: the quality gates, snapshot store, engine and optimizer already existed. Its second guess was also
  wrong: none of the three main connectors read local files. Wazuh and Greenbone call live APIs; Prowler reads
  an S3 object.

## 2. What was built

### Data sources (details in `docs/CONNECTORS.md`)

- **Prowler** now reads real `json-asff` output (the flat format it was written for does not exist). 119 findings in the
  first run, 121 in the current snapshot.
- **IAM connector (PMapper):** implemented; findings attach to the account asset because principals are free text.
- **Asset inventory:** the CMDB connector can read a JSON file, produced from `ec2:DescribeInstances` by
  `infra/inventory/export_ec2_inventory.py`.
- **Wazuh:** file mode (`WAZUH_EXPORT_PATH`), a bundle builder, real agent status, IP taken from alerts, and
  never-connected registrations skipped. The API + indexer mode remains in code but the sandbox has no indexer.
- **Greenbone:** file mode reading a report XML or a GSA CSV. gvmd publishes no port, so the live API cannot be
  reached. 92 findings on 5 hosts, including V-01 (Werkzeug banner) and V-02 (PostgreSQL detections).
- **ScoutSuite:** ran for the first time and the connector was corrected against real output; findings are evidence
  only (see decisions).

### Engine and schema

- **Human-declared services** (`core/declared/loanease_sandbox_services.json`, loader `core/declared_services.py`):
  criticality tier and backup posture per service, linked to assets. Manually declared and labelled as such.
  Without them every finding got the same generic loss magnitude.
- **Severity-aware exploit probability:** findings with no EPSS score now scale the baseline probability by their own
  severity (`UNSCORED_EXPLOIT_PROBABILITY_SCALE_BY_CRITICALITY`, a placeholder in `core/assumptions.py`). Before,
  a critical misconfiguration and an informational hygiene check scored identically.
- **`counts_toward_loss`** (schema, engine): an optional finding marker for corroborating evidence.

### Pipeline and hosting (details in `docs/OPERATIONS.md`)

- GitHub Actions workflow `Scheduled ingest` (daily plus manual, with `skip_scanners` and `refresh_host_data`),
  helper scripts, and least-privilege IAM (OIDC role, bastion role, read-only API user) in a new Terraform module.
- Snapshots published to S3 (`current.json` + `history/`); the API syncs them and can issue short-lived signed URLs.
- On-demand host refresh through AWS Systems Manager (no SSH, no bastion cron): Wazuh and Greenbone exports run on
  the bastion and upload to S3.
- `infra/Dockerfile.api`; a `riskctl` console command; Terraform and the sandbox's `manifest.yaml` moved into
  the repo under `infra/terraform/`.
- Dashboard: a snapshot-age indicator and stale-snapshot notice (`ProvenanceStrip.tsx`, `format.ts`).

### Quality work

- Test suite grew to 343 tests (339 pass; the 4 failures are Windows-only, see `docs/OPERATIONS.md`).
  `ruff format`, `ruff check` and `mypy --strict` are clean; the dashboard production build type-checks.
- CI fixes: `ruff format`, and the semgrep finding on the intentionally public sandbox subnet.
- Fixtures state whether they are real captures or synthetic; synthetic ones use documentation IP ranges.

## 3. Decisions and why

| Decision | Reason |
|---|---|
| **File-based sources for Wazuh, Greenbone, IAM, CMDB** | The live APIs are not reachable in this sandbox (no Wazuh indexer, no published gvmd port). The operator-produces-the-file pattern already existed for Prowler. Live modes remain in code. |
| **Use ASFF, not OCSF, for Prowler** | OCSF's `created_time_dt` is a naive local-time string, 5.5 h off UTC; it would mis-date every finding. |
| **No database; snapshots in S3** | ~90–100 KB immutable JSON per day. The existing store layout already fits object storage. AWS cost of this is a fraction of a cent a month. |
| **SSM, not SSH and not a bastion cron** | The bastion only allows the operator's IP, so GitHub cannot SSH. SSM runs one fixed script on one tagged instance, and lets both the daily run and a manual click trigger it. |
| **Findings from PMapper and ScoutSuite attach to the account asset** | PMapper principals are free text; ScoutSuite ids are internal paths. Per-resource assets would never match Prowler's ARNs and would trip the asset-count gate. |
| **ScoutSuite findings do not count toward loss** | It overlaps Prowler; counting both raised the expected annual loss by about ₹32M for issues Prowler already reports. Dropping the findings and showing the scanner as "reporting" would have implied it found nothing, so they stay as evidence with an explicit marker. Also excludes ScoutSuite-only issues. Logged in `docs/ASSUMPTIONS.md`. |
| **No third-party GitHub actions for AWS login** | The repo pins actions by commit SHA and one cannot be verified offline; plain OIDC needs none. |
| **Bastion failure tolerated on scheduled runs** | A missing host export must not block the daily snapshot. The stale input is then handled honestly. |
| **A separate Terraform module for pipeline IAM** | Keeps real least-privilege IAM apart from the deliberately vulnerable planted IAM. |

## 4. Incidents and what they taught us

| What happened | Cause | Outcome |
|---|---|---|
| A Terraform plan would have removed the DB volume's `Backup=true` tag | tag applied by a separate resource; the instance resource kept trying to reset it | caught by reading the plan; fixed with `ignore_changes`; verified the tag and DLM policy survived |
| Workflow login `AccessDenied` | GitHub's OIDC `sub` claim now embeds numeric owner/repo ids | trust rule accepts both forms; claims are now logged |
| Greenbone export would have been rejected | nested `<detection><result>` elements read as findings (19 of 111); a bug introduced when the reader was widened | reader restricted to real findings; tested |
| Wazuh agents looked unidentified | `agent_control` shows `IP: any` | IP taken from the agent's alerts, only when consistent |
| A phantom agent (`ospd-openvas.local`) | never-connected registration, likely from Greenbone probing the open `authd` service | not counted as EDR coverage; still evidence for the `authd` finding |
| ScoutSuite connector rejected a real report | assumed a trailing `;`; assumed ARN-like ids | corrected and re-verified on real output before enabling |
| Local `ai/` tests failed | the tests read `./data/snapshots`, and an earlier "clean tree" comparison missed that folder because it is gitignored | they pass with an empty store; CI is unaffected |
| Local `test_snapshot_store` tests failed | `sha256:` file names are illegal on NTFS | Linux/CI pass; documented |
| Fetching from GitHub failed in an automated shell | credentials not present there | do fetch and push from your own terminal |

## 5. Real results

**Snapshots in S3** (all built from real inputs): `dfa6ee2…` (24 Sep, first ingest), `77727443…`,
`d1c53153…` and `1993a3c…` (current, 26 Sep). Current snapshot: 55 assets, 4 services, 20 endpoints, 215 open
findings, Wazuh + Greenbone + Prowler + IAM + CMDB reporting; ScoutSuite absent from that snapshot because it
predates the ScoutSuite fix.

**Figures** (recomputed by the engine, so they vary by about ±1% with the random seed): expected annual loss about
₹13.1 crore, value at risk (95th percentile) about ₹24.3 crore.

**Read these numbers carefully.** Loss magnitudes and probabilities are still placeholders (see
`docs/ASSUMPTIONS.md`). The 215 open findings are 121 from Prowler (mostly generic hygiene checks), 92 from Greenbone
and 2 from PMapper, and 79 of the Greenbone findings are informational detections that the engine still counts as loss
events at a reduced weight. The figure shows where the model is going, not a calibrated loss estimate.

**Planted vulnerabilities in the platform** (see `infra/terraform/manifest.yaml`): V-01, V-02 and the real `authd`
finding come from Greenbone; V-03 and V-04 from Prowler; V-05 is absent by design (its check passes until
2026-12-23, and a PASS is not a finding); V-06 is carried into the figure through the declared backup posture.
PMapper did **not** corroborate V-03 to V-05 (its checks only evaluate principals already flagged as admin); it found a
real, separate problem: the `tf-bootstrap` admin user has no MFA.

**Cost:** about $18.3 gross for September, covered by credits; about $4 per day with all four instances running.

## 6. Security notes

- Secrets are never committed (`.env`, `*.tfstate`, `tfplan`, `terraform.tfvars` are ignored; the S3 bucket blocks
  all public access; signed snapshot links are locked behind `SNAPSHOT_LINKS_TOKEN`).
- Two credentials were exposed in chat during setup: the read-only API key (deleted and re-issued) and the
  Greenbone admin password. **Change the Greenbone password.** The `tf-bootstrap` admin key was also shared earlier
  in the project; rotating it is recommended.
- Snapshots contain real sandbox telemetry (IPs, ARNs, the account id): keep them out of git.

## 7. Open items and known gaps

**Not done yet**

- Deploy the API (Render or Fly) and the dashboard (Vercel), set the keep-alive pinger, and run a full workflow once to
  confirm the ScoutSuite step in GitHub's environment.
- Attack graph data: no connector supplies `network_topology` / `segment_id`.
- The daily workflow has run manually only; the schedule has not yet fired on its own.

**Known limitations to state honestly**

- Wazuh EDR data is not joined to the cloud (`cloud:`) versions of the same machines, because the LLM identity merge
  needs `TYPESAFE_API_KEY`. EDR therefore does not reduce the loss on the assets that carry Prowler's findings.
- The threat-intel (EPSS/KEV), Nessus and nmap connectors are stubs. EPSS is always null, so V-01's live EPSS score
  (a manifest note) is not looked up.
- Greenbone V-01 arrives as an informational banner with no CVE attached. The link to CVE-2023-25577 exists only in
  the manifest.
- Wazuh and Greenbone run from exports, not live APIs. Greenbone exports the latest existing scan; it does not rescan.
- Compliance: most controls are `unknown` and no framework has a weighted score; the DPDP library has no controls.
- The overlap between Prowler and ScoutSuite is handled by exclusion, not de-duplication. A cross-scanner mapping
  (shared control ids cover only about 10 of 24 flagged ScoutSuite findings) is the right long-term fix.
- The `optimize_investment` assistant tool and `riskctl optimize` remain stubs (the dashboard calls the optimizer
  directly).

**After the demo**: shut down (checklist in `docs/OPERATIONS.md`), rotate keys, and write down the by-hand rebuild
steps for the finals.
