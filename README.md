# Cypher

**Cyber risk in rupees.** Cypher takes what an organisation's security tools
report (vulnerability scans, EDR alerts, cloud and IAM misconfigurations,
network exposure, backup posture) and turns it into two numbers a CFO, a
board or a regulator can act on:

- **Expected Annual Loss (EAL)**: what a year of cyber risk costs on average, in ₹.
- **Value at Risk (VaR, p95)**: what a bad year looks like, in ₹.

It then shows which assets and findings drive those numbers, which controls
would reduce them most for a given budget, what a Terraform change would do
to them *before* it is applied, and how the underlying findings map to Indian
regulatory frameworks (RBI Directions 2026, SEBI CSCRF/CCI, DPDP Act 2023)
and to CIS Controls, NIST CSF and ISO 27001.

Cypher was built for **Smart India Hackathon 2026, Problem Statement 26105**.
It was originally called *Su₹aksha*. You will still see `suraksha` in the
Python package name, AWS resource names and a few other identifiers that
deployed infrastructure depends on.

---

## Contents

- [How it works](#how-it-works)
- [Design principles](#design-principles)
- [What's in the box](#whats-in-the-box)
- [Quick start](#quick-start)
- [The `cypher` CLI](#the-cypher-cli)
- [Pricing a Terraform change before apply (`cypher plan`)](#pricing-a-terraform-change-before-apply-cypher-plan)
- [The daily pipeline](#the-daily-pipeline)
- [Project status](#project-status)
- [Repository layout](#repository-layout)
- [Configuration](#configuration)
- [Tests and CI](#tests-and-ci)
- [Where to read next](#where-to-read-next)

---

## How it works

```
 Security tools             Connectors               One shared shape
 ──────────────             ──────────               ────────────────
 Wazuh (EDR/SIEM)     ─┐
 Greenbone (vulns)    ─┤    infra/connectors/        schema/aggregated_assets
 Prowler (cloud)      ─┼──▶ fetch → normalize  ────▶ .schema.json
 ScoutSuite (cloud)   ─┤    → attach to asset        (candidate snapshot)
 PMapper (AWS IAM)    ─┤                                     │
 CMDB / EC2 inventory ─┘                                     ▼
                                                  ┌───────────────────────┐
                                                  │  5 quality gates      │  fail → previous
                                                  │  core/snapshot.py     │  snapshot stays
                                                  └──────────┬────────────┘  current
                                                             ▼ pass
                                                  immutable, bitemporal snapshot store
                                                             │
                                                             ▼
                        ┌──────────────────────────────────────────────────────────┐
                        │ core/engine: Open FAIR + Monte Carlo                     │
                        │ (+ bounded Bayesian attack graph for stepping-stone      │
                        │  attacks) → EAL, VaR, ranked contributors                │
                        └──┬─────────────────┬──────────────────┬──────────────────┘
                           ▼                 ▼                  ▼
                  core/optimizer      governance/         ai/ (Ask Cypher)
                  joint re-simulation control mapping    LLM picks tools and narrates;
                  of control          (findings and      numeric_guard checks every
                  portfolios          controls only)     number against engine output
                           │                 │                  │
                           └────────┬────────┴──────────────────┘
                                    ▼
                  interfaces/: FastAPI · Next.js dashboard · `cypher` CLI
```

1. **Connect.** Each connector wraps one tool and normalises its output into
   the one shared schema. Nothing downstream ever knows which tool a finding
   came from.
2. **Gate.** A candidate snapshot must pass five quality checks: asset-count
   delta, no findings from unreachable scanners, criticality present, provenance
   present, and no ordinal labels in numeric fields. If it fails, the previous
   snapshot stays current.
3. **Quantify.** The engine builds FAIR loss-event scenarios from the findings.
   It sets their frequency and vulnerability from EPSS, CISA KEV and telemetry,
   and their loss magnitude from service criticality and named assumptions. It
   then runs a Monte Carlo simulation to produce a full annual-loss
   distribution. Where the snapshot carries network topology, internal assets
   are scored on their real attack paths in from internet-facing servers.
4. **Decide.** The optimizer ranks controls by how much each one reduces loss,
   given the ones before it. Given declared costs and a budget, it recommends a
   portfolio. Every candidate portfolio is re-simulated as a whole, never
   priced by adding up per-control savings.
5. **Explain.** The dashboard, the API, the CLI and the Ask Cypher assistant
   all show the same engine output, with the snapshot it came from.

## Design principles

These eight rules shape the whole codebase. The full text is in
[`CLAUDE.md`](CLAUDE.md).

1. **The rupee figure comes from a deterministic engine**, never from an ML
   model or an LLM. No organisation has enough labelled cyber-loss data to
   train a model that outputs rupees honestly.
2. **The LLM only touches the edges.** It turns a question into a tool call and
   narrates numbers that were already computed. Every number in its output is
   checked against real engine output (`ai/numeric_guard.py`); anything that
   can't be traced is flagged `[UNVERIFIED: …]`.
3. **One shared data contract.** Every connector emits
   `schema/aggregated_assets.schema.json`. The engine has no idea which tools exist.
4. **Quality gates fail safe.** A bad scan never replaces a good snapshot.
5. **Snapshots are immutable and bitemporal.** "Scanner didn't run" and
   "finding was fixed" are different facts, told apart by `scan_scope`.
6. **Compliance maps to findings and controls**, never to what the optimizer
   recommends.
7. **Portfolios are re-simulated jointly.** Overlapping controls make summed
   per-control savings badly overstate the benefit.
8. **Regulations are versioned and effective-dated.** RBI's 2016 Cyber Security
   Framework was repealed on 31 July 2026 and replaced by entity-specific
   Directions.

Missing data is shown as missing. An asset with no scan data reads "not
modelled", never ₹0. An unknown control is unknown, never "protected". With
no committed snapshot, every interface says so instead of showing a number.

## What's in the box

| Surface | What it does | More |
|---|---|---|
| **Dashboard** (`interfaces/dashboard/`) | Next.js app. Pages: first-run **setup** (pick your tools, see which telemetry is covered, choose your entity type), **overview** (EAL/VaR, trend, loss exceedance curve, top drivers, what-if lab), **assets & findings** (the FAIR parameters behind every figure), **attack paths** (interactive attack graph), **investment** (cost-free priority plan, plus budget-constrained portfolios over declared costs), **compliance** (control-by-control status and statutory penalty ceilings) and **data & model** (provenance, quality gates, coverage, live assumption register). | [README](interfaces/dashboard/README.md) |
| **Ask Cypher** (`ai/`) | A chat panel that answers questions like "what is driving our exposure?" by calling engine tools. Every number it says is verified before display. | [API README](interfaces/api/README.md#the-chat-assistant) |
| **API** (`interfaces/api/`) | FastAPI service behind the dashboard: exposure, history, exceedance, assets, attack graph, frameworks, what-if simulation, optimizer, assumptions, chat (JSON or SSE) and signed snapshot downloads. | [README](interfaces/api/README.md) |
| **CLI** (`interfaces/cli/cypher.py`) | `cypher ingest`, `validate-snapshot`, `run-engine`, `framework-status`, and `cypher plan` for pre-apply Terraform risk. | [below](#the-cypher-cli) |
| **Pipeline** (`.github/workflows/scheduled-ingest.yml`, `infra/`) | A daily GitHub Actions job scans a deliberately vulnerable AWS sandbox, ingests the results and publishes the snapshot store to S3 for the hosted API. | [below](#the-daily-pipeline) |

## Quick start

The repo holds **two separate applications** with separate toolchains: a
Python backend (everything except `interfaces/dashboard/`) and a Next.js
frontend (`interfaces/dashboard/`). The frontend talks to the backend only
over HTTP.

### Backend (Python ≥ 3.11)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # installs the `cypher` command too
cp .env.example .env             # every variable is optional for a first run

# Run the engine on the bundled sample snapshot (no scanners needed)
cypher validate-snapshot schema/sample_aggregated.json
cypher run-engine schema/sample_aggregated.json

# Price a sample Terraform change against a sample baseline
cypher plan infra/tests/fixtures/tf_plan_open_db.json \
  --snapshot infra/tests/fixtures/tf_plan_baseline.json

# Start the API
uvicorn --factory interfaces.api.app:create_app --reload --port 8000
```

One virtual environment covers the whole backend. `core/`, `governance/`,
`ai/`, `infra/` and `interfaces/` are one package (`pyproject.toml`) and
import each other directly.

### Dashboard (Node.js)

```bash
cd interfaces/dashboard
npm install
npm run dev                          # http://localhost:3000, expects the API on :8000
NEXT_PUBLIC_DEMO_MODE=1 npm run dev  # or: offline, with clearly-labelled SAMPLE data
```

The dashboard shows real figures once a snapshot has been committed by
`cypher ingest`, or when the API is syncing from the published S3 store.
Until then it shows an explicit "no figure yet" state rather than
placeholder numbers.

### Ask Cypher

Set `GROQ_API_KEY` in `.env` and restart the API, then:

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"what is driving our exposure?"}'
```

`POST /chat` returns a complete, verified turn. `POST /chat/stream` streams
the same turn as Server-Sent Events. Only its `final` event is verified.

## The `cypher` CLI

Every command is a thin adapter over `core/`, `governance/` and `ai/`. None
of them computes a figure on its own.

| Command | What it does |
|---|---|
| `cypher ingest [--no-commit]` | Runs every configured connector (Wazuh, Greenbone, Prowler, ScoutSuite, PMapper/IAM, CMDB). An unconfigured or failing connector is recorded as an unreachable scanner, never faked. Placeholder asset IDs are reconciled against the CMDB (Jev-assisted, every decision logged). The candidate goes through the five gates and is committed only if all of them pass. |
| `cypher validate-snapshot FILE` | Runs the five quality gates on a candidate against the current snapshot, and reports each gate. Never commits. |
| `cypher run-engine FILE` | Prints EAL, VaR and the top loss contributors for a snapshot file. |
| `cypher framework-status FRAMEWORK` | Control-by-control status of the current snapshot against one control library (`rbi_2026_directions`, `sebi_cscrf_cci`, `dpdp_act_2023`, `cis_controls`, `nist_csf`, `iso_27001`). |
| `cypher plan [PLAN.json \| --dir DIR]` | The change in EAL and VaR a Terraform plan would cause (see below). |
| `cypher optimize` | Not implemented yet. Use the dashboard's investment page or `POST /optimize`. |

## Pricing a Terraform change before apply (`cypher plan`)

`cypher plan` answers "what does this Terraform change do to our cyber risk,
in rupees?" before `terraform apply`, so it can run as a CI gate:

```bash
terraform plan -out tf.plan && terraform show -json tf.plan > tf_plan.json
cypher plan tf_plan.json                            # report only (exit 0)
cypher plan tf_plan.json --fail-on-eal-increase 0   # exit 2 if EAL rises
cypher plan --dir infra/terraform/environments/dev --json   # runs terraform for you
```

- **Baseline.** The current committed snapshot. With `SNAPSHOT_S3_BUCKET` set,
  the store published by the daily pipeline is mirrored into
  `SNAPSHOT_STORE_PATH` first, so the plan is priced against the latest ingest.
  If S3 can't be reached, the report says so and uses the local copy.
  `--offline` skips S3, and `--snapshot FILE` pins a specific baseline.
- **Translation.** `infra/connectors/terraform_plan.py` turns the plan into
  schema-shaped changes: security-group internet exposure and internal
  reachability, `AdministratorAccess` and console-without-MFA findings, DLM
  backup coverage, and deletions. The CLI overlays those changes on a copy of
  the baseline. `core.optimizer.compare_snapshots` then re-simulates the
  baseline and the proposed state on the same random draws.
- **Report.** Baseline, proposed and change for EAL and VaR. It also lists the
  loss scenarios that moved, with the Terraform address behind each, and the
  baseline's ID, source and age.
- **Stated limits.** A newly created resource has no scan data, so it is listed
  as unscanned with unknown risk, never ₹0. Values known only after apply,
  resources the baseline can't be matched to, and resource types with no rule
  are listed as not modelled. With no committed snapshot, the command exits 1
  instead of guessing.

## The daily pipeline

```
bastion (triggered via SSM, no SSH):  Wazuh export, Greenbone report  ─▶ S3 inputs/
GitHub Actions, 02:30 IST daily or on demand:
    Prowler + PMapper scan of the AWS sandbox                          ─▶ S3
    EC2 inventory (CMDB stand-in) + `cypher ingest`                     ─▶ S3 snapshots/
hosted API (infra/Dockerfile.api)  ─ syncs snapshots/ every 5 min ─▶  dashboard (Vercel)
```

The scanned environment is **LoanEase**, a deliberately vulnerable AWS
sandbox defined in [`infra/terraform/`](infra/terraform/README.md). Its
`manifest.yaml` records every planted weakness and how it was verified. A
missing or stale input is never faked: its scanner is recorded as
unreachable. If the gates reject a candidate, the previous snapshot stays
current and the workflow run fails visibly.

## Project status

| Area | Status |
|---|---|
| Schema, 5 quality gates, snapshot store (`core/snapshot*.py`) | ✅ Implemented |
| FAIR + Monte Carlo engine and Bayesian attack graph (`core/engine/`) | ✅ Implemented. The attack graph applies only when a snapshot carries `network_topology`, which no connector populates yet |
| Optimizer: priority plan, budgeted portfolio, snapshot comparison (`core/optimizer.py`) | ✅ Implemented |
| Connectors: Wazuh, Greenbone, Prowler, ScoutSuite, IAM (PMapper), CMDB | ✅ Implemented and wired into `cypher ingest`. ScoutSuite findings count as evidence only (`counts_toward_loss: false`), so they aren't double-counted against Prowler |
| Terraform plan translation (`infra/connectors/terraform_plan.py`) | ✅ Implemented, used by `cypher plan` |
| Control libraries (RBI 2026, SEBI CSCRF/CCI, DPDP 2023, CIS, NIST CSF, ISO 27001) and mapper | ✅ Implemented. DPDP has penalty provisions only, which are not in force until 2027-05-13 |
| API, dashboard, Ask Cypher, CLI | ✅ Implemented, except the items below |
| Connectors: EPSS/KEV threat intel, Nessus, nmap | ⏳ Stubs. Until threat intel lands, findings carry no EPSS score, and the engine uses a documented, criticality-scaled baseline exploit probability instead (see `docs/ASSUMPTIONS.md`) |
| `cypher optimize` and the assistant's `optimize_investment` tool | ⏳ Stubs. Nothing supplies control costs yet; the dashboard asks the user to declare them |
| Calibration | ⚠️ Modelling constants are documented judgement calls, not fitted to a real organisation's loss history. See [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) |

## Repository layout

```
schema/        The shared data contract (JSON Schema) and a sample snapshot.
infra/         Connectors, the Terraform-plan translator, the LoanEase sandbox
               (Terraform), bastion export scripts, inventory helpers, API image.
core/          Snapshot gates and store, the FAIR + Monte Carlo engine, attack
               graph, optimizer, and every named modelling assumption.
governance/    Versioned control libraries, the findings→controls mapper,
               manual attestations, evidence generation.
ai/            LLM client and transports, intent classifier, chat engine,
               numeric guard, and tool wrappers over core/ and governance/.
interfaces/    api/ (FastAPI), cli/ (the `cypher` command), dashboard/ (Next.js),
               shared S3 snapshot mirror, and their tests.
docs/          Project context, glossary, and ASSUMPTIONS.md.
.github/       CI (lint, types, tests, deps, secrets, Semgrep) and the daily ingest.
```

Imports follow strict layering. `schema/` depends on nothing. Connectors
never import the engine, and the engine never imports a connector. Only
`ai/` calls an LLM, and only `core/` produces a rupee figure. The dashboard
never imports Python. The full ownership map is in
[`CLAUDE.md`](CLAUDE.md#module-ownership-map).

## Configuration

Everything is configured through environment variables. They are documented
one by one in [`.env.example`](.env.example) (backend) and
[`interfaces/dashboard/.env.example`](interfaces/dashboard/.env.example)
(frontend). The main groups are:

- **LLM:** `GROQ_API_KEY` and `GROQ_MODEL` for Ask Cypher. `TYPESAFE_API_KEY`
  for Jev-assisted identity resolution during ingest.
- **Connectors:** one block per tool (API endpoints or export file paths). A
  connector with no configuration is simply recorded as unreachable.
- **Stores:** `SNAPSHOT_STORE_PATH`, `ATTESTATION_STORE_PATH` and
  `IDENTITY_RECONCILIATION_STORE_PATH`. All default to `./data/`, which is
  gitignored.
- **Hosting:** `SNAPSHOT_S3_BUCKET` / `SNAPSHOT_S3_PREFIX`,
  `CORS_ALLOWED_ORIGINS`, `SNAPSHOT_LINKS_TOKEN`, and for the dashboard
  `NEXT_PUBLIC_API_BASE_URL`.

## Tests and CI

```bash
pytest          # core/, governance/, ai/, infra/ and interfaces/ tests
mypy .          # --strict; type hints are required on every signature
ruff check .
cd interfaces/dashboard && npm run lint && npm run build
```

Connector and CLI tests run against recorded tool output in
`infra/tests/fixtures/` (Greenbone, Prowler, ScoutSuite, PMapper and Wazuh
exports, and `terraform show -json` plans), not against mocks. GitHub Actions
runs lint, type checks, tests, a build, a dependency audit, secret scanning
and Semgrep on every push and PR to `main` and `develop`.

## Where to read next

| If you want to… | Read |
|---|---|
| Understand the design rules and conventions | [`CLAUDE.md`](CLAUDE.md) |
| Know why this approach and which regulations apply | [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) |
| Challenge a number | [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md): every modelling constant and its justification |
| Look up FAIR, EAL, VaR, EPSS, KEV… | [`docs/glossary.md`](docs/glossary.md) |
| Understand the snapshot shape | [`schema/README.md`](schema/README.md) |
| Add or change a connector | [`infra/README.md`](infra/README.md) and `.claude/commands/add-connector.md` |
| See the regulatory sources | [`governance/control_library/README.md`](governance/control_library/README.md) |
| Call the API or embed the assistant | [`interfaces/api/README.md`](interfaces/api/README.md) |
| Work on the UI | [`interfaces/dashboard/README.md`](interfaces/dashboard/README.md) |
| Rebuild the sandbox or the bastion exports | [`infra/terraform/README.md`](infra/terraform/README.md), [`infra/bastion/README.md`](infra/bastion/README.md) |
