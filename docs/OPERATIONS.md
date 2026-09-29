# Operations

How the platform runs end to end: the daily pipeline, where each piece lives, how to run it by hand,
what it costs, how to shut it down and rebuild it, and the failures we have already hit.

Written for: whoever operates the demo environment or rebuilds it (for example for the finals, in a
different AWS account). Status as of **2026-09-26**. API and dashboard hosting is *designed and
configured in the repo but not yet deployed* (Render/Fly and Vercel steps are in "Hosting").

## 1. Architecture

```
                    scan job (GitHub Actions)                      bastion (EC2, Wazuh + Greenbone)
                    ─────────────────────────                      ────────────────────────────────
  AWS account ──►   Prowler ─────────► S3 latest/prowler_connector.json
  (read-only)       ScoutSuite ──────► S3 latest/scoutsuite_connector.json
                    PMapper ─────────► S3 inputs/pmapper.json
                                                                   refresh_host_data.sh  (run by SSM)
                    ingest job (GitHub Actions)  ◄── SSM ────────►   Wazuh export  ──► S3 inputs/wazuh_bundle.json
                    ───────────────────────────                       Greenbone export► S3 inputs/greenbone_report.xml
                    download inputs ◄── S3
                    EC2 inventory (built in the job, from AWS)
                    riskctl ingest  (5 quality gates)
                    publish ────────► S3 snapshots/current.json + snapshots/history/<id>.json
                                              │
                                              ▼
                    API host (FastAPI) syncs snapshots/ from S3 ──► dashboard (Next.js, Vercel)
```

- **A snapshot is immutable and content-addressed** (`sha256:<hash>`). `current.json` points at the newest;
  every snapshot ever committed stays in `history/`.
- **Fail-safe:** if any of the 5 quality gates rejects a candidate, the previous snapshot stays current
  and the workflow run fails visibly. Nothing is ever committed half-built.
- **Nothing is faked.** A missing or stale input leaves its connector unconfigured, so that scanner is
  recorded as `unreachable` and the dashboard shows a coverage caveat.
- **No database.** Snapshots are ~90–100 KB of JSON, one per day; S3 objects with the existing
  `current.json` + `history/` layout are enough.

## 2. Where things live

| Thing | Location |
|---|---|
| Pipeline workflow | `.github/workflows/scheduled-ingest.yml` (helper scripts in `.github/scripts/`) |
| Connectors, inventory and bundle builders | `infra/connectors/`, `infra/inventory/` |
| Bastion scripts | `infra/bastion/` (installed at `/opt/suraksha/` on the bastion) |
| Terraform (the sandbox and pipeline IAM) | `infra/terraform/` (state in S3, see below) |
| Manual, human-declared business context | `core/declared/loanease_sandbox_services.json` |
| API + snapshot sync + signed links | `interfaces/api/` (`snapshot_sync.py`, `snapshot_links.py`) |
| API container | `infra/Dockerfile.api` |
| Dashboard | `interfaces/dashboard/` |
| Ground truth of the planted vulnerabilities | `infra/terraform/manifest.yaml` |

AWS account `627984120842`, region `ap-south-1`.

**S3 buckets**

- `loanease-raw-findings-f00321` (created by hand, **not** in Terraform; all public access blocked):
  - `latest/prowler_connector.json`, `latest/scoutsuite_connector.json`: what those connectors read.
  - `inputs/pmapper.json`, `inputs/wazuh_bundle.json`, `inputs/greenbone_report.xml` (or `.csv`).
  - `snapshots/current.json`, `snapshots/history/<snapshot_id>.json`.
- `loanease-tfstate-d07f64`: Terraform state (`dev/terraform.tfstate`), native lockfile, no DynamoDB.

## 3. The workflow (`Scheduled ingest`)

**Triggers**

- **Daily at 21:00 UTC** (02:30 IST), from `main` only.
- **Manual ("the button"):** Actions → *Scheduled ingest* → *Run workflow*, with two options:

| Option | What it does |
|---|---|
| `skip_scanners` | Skip Prowler, ScoutSuite and PMapper and reuse their last exports. Fast (minutes), but Prowler's and ScoutSuite's objects must be under 24 h old or they count as unreachable and the asset-count gate will reject the snapshot. |
| `refresh_host_data` | First have the bastion re-export Wazuh and Greenbone data via SSM. |

**Which boxes to tick:** first test → both. Everything fresh → only `refresh_host_data` (about 20–30 minutes).
Re-ingest what is already in S3 → neither. Scheduled runs always refresh host data, but a bastion failure on a
schedule is tolerated (it never blocks the daily snapshot); on a manual run it fails loudly.

**Jobs**

1. `scan` (60 min timeout): assume the AWS role by OIDC → install Prowler 5.43.0 and PMapper 1.1.5 (patched for
   Python ≥ 3.10) → Prowler (`json-asff`, all FAILs kept) → upload → PMapper (`graph create` with the
   sandbox's disabled opt-in regions excluded, then `analysis`) → upload → ScoutSuite 5.14.0 in its own venv
   (`continue-on-error`) → upload. Each upload is validated first, never uploading an empty file.
2. `ingest` (30 min timeout): OIDC login → refresh the bastion via SSM (if scheduled or ticked) → sync
   `snapshots/` down → build the EC2 inventory → fetch inputs (missing or stale ones left unset) → `riskctl ingest`
   → **fail the run if a gate rejected the candidate** → sync `snapshots/` back up (never `--delete`) →
   write a summary (snapshot id, counts, reachable and unreachable scanners).

Only one run at a time (concurrency group `suraksha-ingest`); a second waits for the first. Cancel the running
one if it is stuck.

**Repository variables** (Settings → Secrets and variables → Actions → *Variables*, not secrets):
`AWS_ROLE_ARN` = `arn:aws:iam::627984120842:role/gha-suraksha-ingest`, `RAW_FINDINGS_BUCKET` =
`loanease-raw-findings-f00321`.

No third-party actions are used except the two SHA-pinned `actions/checkout` and `actions/setup-python`;
the AWS login is plain OIDC via `.github/scripts/aws-oidc-login.sh`.

## 4. The bastion and on-demand refresh

The bastion (`loanease-bastion-scanner`, `m7i-flex.large`, 100 GB) runs the Wazuh manager and the
Greenbone Community stack. Its security group allows SSH only from the operator's IP, so GitHub cannot
SSH in. Instead the workflow calls **AWS Systems Manager**:

- SSM document `SurakshaRefreshHostData` runs exactly one command: `/opt/suraksha/refresh_host_data.sh`.
- The GitHub role may run only that document, only on the instance tagged `Name=loanease-bastion-scanner`.
- `refresh_host_data.sh` runs `export_host_data.sh` (Wazuh alerts + `agent_control -l` → bundle → S3) and
  `export_greenbone_report.sh` (`gvm-cli` through the `gvm-tools` container's gvmd socket; latest report of
  task `loanease-full-scan`, all severities; **no rescan** → S3). One failing does not stop the other.

**One-time setup on the bastion** (already done): AWS CLI v2, the four files in `/opt/suraksha/`,
`/etc/default/suraksha-export` (bucket name), and a root-only `/opt/suraksha/gvm.pass` holding the Greenbone
login. Full commands: `infra/bastion/README.md`.

## 5. IAM (all least-privilege, in `infra/terraform/modules/pipeline`)

| Identity | Can |
|---|---|
| Role `gha-suraksha-ingest` | be assumed only by repo `shivansh-source/ps105`'s `main` branch via GitHub OIDC (both the plain-name and the numeric-ID `sub` forms are trusted); SecurityAudit + ViewOnlyAccess; read/write `inputs/`, `snapshots/`, `latest/`; run the one SSM document |
| Role `suraksha-bastion-exporter` (+ instance profile) | `s3:PutObject` on `inputs/*`; SSM agent registration |
| User `suraksha-api-reader` | list + read `snapshots/*` only; **access key created by hand** so its secret never enters Terraform state |

The planted-vulnerability IAM (`loan-ops-analyst`, `loan-ops-no-mfa`, `loan-ops-stale-key`) is in a
separate module (`modules/iam`) on purpose.

## 6. Terraform

- Code: `infra/terraform/environments/dev` + `modules/{network,compute,iam,backup,pipeline}`. Backend and profile:
  `loanease-tfstate-d07f64`, profile `loanease-sandbox`.
- Use: `terraform init`, `terraform plan -out=tfplan`, **read the plan**, `terraform apply tfplan`. Create
  `terraform.tfvars` with `my_ip_cidr = "<your public ip>/32"`; re-run when your IP changes (SSH and HTTP rules
  use it).
- **Gotcha, already fixed:** the DB instance's root volume has a `Backup=true` tag applied by a separate resource
  (`aws_ec2_tag`). Without `ignore_changes = [root_block_device[0].tags]` every plan tried to strip it, which would have
  silently removed the DB from the backup policy and falsified planted item V-06.
- Never commit `*.tfstate*`, `tfplan`, `terraform.tfvars`, or keys. Semgrep flags the public subnet; it is
  intentional and suppressed with a `nosemgrep` comment next to a justification.

## 7. Hosting (designed; not yet deployed)

**API** (Render or Fly, from `infra/Dockerfile.api`). Set:

| Variable | Value |
|---|---|
| `SNAPSHOT_S3_BUCKET` | `loanease-raw-findings-f00321` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | the `suraksha-api-reader` key, `ap-south-1` |
| `CORS_ALLOWED_ORIGINS` | the dashboard's public origin |
| `SNAPSHOT_LINKS_TOKEN` | a long random string (signed-link routes refuse without it) |
| `GROQ_API_KEY` | only if the chat assistant should answer |

On start the API pulls `snapshots/` from S3 into its local store (history is never overwritten; `current.json` is
fetched last) and re-checks every 5 minutes. `GET /health/snapshot-sync` reports the last outcome.
`GET /snapshots` and `GET /snapshots/{id}/download-url` return short-lived signed S3 URLs (default 5 minutes)
so a client can read raw snapshot JSON directly from S3. Browsers need a CORS rule on the bucket (command in
`interfaces/api/README.md`).

**Dashboard** (Vercel): root directory `interfaces/dashboard`; set `NEXT_PUBLIC_API_BASE_URL` to the API's
`https://` URL **before building** (`NEXT_PUBLIC_*` is inlined at build time); leave `NEXT_PUBLIC_DEMO_MODE`
unset. Free API hosts sleep when idle: add a pinger on `/health` every 10 minutes and warm the site before a demo.

## 8. Running things by hand

```bash
# Refresh Wazuh + Greenbone on the bastion (as root there)
sudo /opt/suraksha/refresh_host_data.sh

# See what is in S3
aws s3 ls s3://loanease-raw-findings-f00321/snapshots/ --recursive --profile loanease-sandbox
aws s3 sync s3://loanease-raw-findings-f00321/snapshots/ ./snapshots-copy --profile loanease-sandbox

# Run the engine on a snapshot file
riskctl run-engine ./snapshots-copy/current.json

# Run the API locally against a synced store
SNAPSHOT_STORE_PATH=./snapshots-copy uvicorn --factory interfaces.api.app:create_app --port 8000
```

## 9. Cost (measured 2026-09-26)

- Gross usage for September: about **$18.3**, fully covered by AWS Free Plan credits (net bill $0.00).
  By service: EC2 compute $14.69, public IPv4 $2.22, disks and other EC2 $1.41, S3 and the rest under a cent.
- Burn with all four instances running: about **$4 per day** (about $115–120 a month).
- The budgets (`$5`, `$20`, `$50`) track cost *after* credits, so they stay at $0 and will not warn while credits
  last. To get an early warning, create a budget on gross usage (credits excluded).
- Anything added by the pipeline (S3, SSM, Actions runs) costs cents.

## 10. Shutting down and rebuilding

**Shut down** (for example after the demo):

1. Download `snapshots/` and `inputs/` from S3. Save the Greenbone report and password somewhere private.
2. Disable the workflow (Actions → Scheduled ingest → ⋯ → Disable).
3. Stop the four instances. Disks (~136 GB) keep costing about $0.35/day; auto-assigned public IPs are released.
4. Check Billing a day later. Change the Greenbone admin password (it was typed into a chat during setup) and rotate
   the `tf-bootstrap` admin key.

**Rebuild** (for example in a new account for the finals). Terraform only recreates what is in code. These parts were
done by hand and must be redone:

- Greenbone: Docker + the Community compose stack, the ~35 GB feed import, a target for the subnet and the
  `loanease-full-scan` task, the admin password.
- Wazuh: manager install, agent enrollment on the other hosts, `ossec.conf` edits (vulnerability-detection module
  disabled because it downloaded a 16 GB feed with nowhere to send it; the endpoint agent deliberately under-tuned:
  FIM, rootcheck and SCA off).
- The raw-findings bucket, the OIDC provider, and the bastion setup in section 4.
- In the pipeline module: the GitHub owner and repo numeric IDs (`github_owner_id`, `github_repo_id`) for the trust rule.
- Update `core/declared/loanease_sandbox_services.json`: it links services to instance and volume ARNs and `host:` ids,
  which change in a new account.
- The account is on the Free Plan with an **8 vCPU limit**; the four-instance layout uses all of it.

## 11. Troubleshooting (all seen for real)

| Symptom | Cause | Fix |
|---|---|---|
| `AccessDenied` on `AssumeRoleWithWebIdentity` | GitHub's OIDC `sub` claim now includes numeric ids (`repo:owner@<id>/repo@<id>:ref:...`); the trust rule expected the plain name | trust rule now allows both; `aws-oidc-login.sh` prints the claims to diagnose |
| "Waiting for Scheduled ingest #N to complete" | one-run-at-a-time concurrency group | wait, or cancel the stuck run |
| Candidate rejected: asset count changed >50% | a large source dropped out (for example a stale Prowler object), or a source added many new assets | gate is doing its job; run a full scan, or fix the source |
| Wazuh shows "not reporting" the next day | its bundle is older than 30 h | refresh via the button, or check the SSM step |
| SSH to the bastion times out | security group allows only the operator IP, which changed | update `my_ip_cidr` and apply |
| `refresh-bastion.sh` finds no instance / command fails | SSM agent not registered, or bastion stopped | check `aws ssm describe-instance-information`; start the instance |
| Greenbone export "Failed to authenticate" | wrong password file or username | rewrite `/opt/suraksha/gvm.pass`; set `GREENBONE_USERNAME` |
| `pip install` fails in WSL | WSL Python is 3.10; the project needs 3.11+ | use a `uv`-managed 3.12 venv |
| 4 `test_snapshot_store` tests fail on Windows | history files are named `sha256:<hash>.json`; NTFS cannot create `:` | run tests on Linux/CI (they pass) |
| 5 `ai/` tests fail locally | a real `data/snapshots/` exists and the tests expect none | run with `SNAPSHOT_STORE_PATH=<empty dir>` |
| Dashboard dev server returns 500 on every page (Turbopack, Google fonts) | a Turbopack dev-mode font-loader failure on this Windows setup | use `next build && next start` (the production build works and is what Vercel runs) |
| `git fetch` says "Repository not found" from an automated shell | credentials not available in that shell | fetch/push from your own terminal |

## Accounts and sign-in (Supabase)

Users register on the dashboard (organisation name, email, password), pick their
tools, then reach the dashboard. Accounts, organisations and tool selections live
in Supabase Postgres; passwords are held only by Supabase Auth.

One-time setup:

1. Create a Supabase project. Under **Authentication → Providers → Email**, turn
   **Confirm email** off (sign-up then logs the user straight in) and set the
   minimum password length to 10.
2. Run `infra/supabase/migrations/0001_auth.sql` in the SQL editor (or
   `supabase db push`). It creates `organizations`, `profiles`, `org_tools`, their
   row-level-security policies, the sign-up trigger that creates the org, and the
   `save_org_setup` function.
3. Dashboard `.env.local`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   (both public by design).
4. API `.env`: `SUPABASE_JWT_SECRET` (legacy HS256 projects) or `SUPABASE_URL`
   (asymmetric signing keys). Server-side only. With neither set, every protected
   route answers 503; `AUTH_DISABLED=1` skips the check for local development only.

Not yet per-organisation: the snapshot store is still one global store, and the
saved tool selection records the org's estate but does not gate `cypher ingest`.
