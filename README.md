# Cypher: Cyber Risk in Rupees

This repository contains the complete implementation of our Smart India Hackathon (SIH 2026) project: a cyber risk quantification and security-budget platform that expresses risk in rupees, with the Open FAIR framework and Monte Carlo simulation.

Cypher was originally called *Su₹aksha*. You will still see `suraksha` in the Python package name, AWS resource names and a few other identifiers that deployed infrastructure depends on.

## Contents

1. [Project Information](#1-project-information)
2. [Problem Statement](#2-problem-statement)
3. [Proposed Solution](#3-proposed-solution)
4. [Key Features](#4-key-features)
5. [Technology Stack](#5-technology-stack)
6. [Architecture](#6-architecture)
7. [Repository Structure](#7-repository-structure)
8. [Prototype Walkthrough](#8-prototype-walkthrough)
9. [Installation](#9-installation)
10. [Run](#10-run)
11. [Future Scope](#11-future-scope)

---

## 1. Project Information

- **Project Title:** Cypher: cyber risk quantification and investment optimisation, in rupees (formerly *Su₹aksha*)
- **PS ID:** 26105
- **PS Title:** AI-Powered Continuous Cyber Risk Quantification and Investment Optimization Platform
- **Category:** Software
- **Theme:** Blockchain & Cybersecurity
- **Team Name:** DLL Not Found
- **Team ID:** 181865
- **Organization:** AICTE

## 2. Problem Statement

Cyber risk is usually reported as a unitless score or a Low / Medium / High label. That cannot be compared with a budget, an insurance premium or a regulatory penalty, so a CFO, a board or a regulator cannot tell whether the current security spend is adequate or well allocated. Security telemetry (scanner output, EDR alerts, cloud and IAM misconfigurations) is technical and disconnected from those decisions. Indian regulated entities also have to evidence their posture against RBI, SEBI and DPDP requirements, and those rules are entity-specific and change over time.

PS 26105 asks for a system that quantifies cyber risk in financial terms for Indian organisations and helps them prioritise security spend, while accounting for the applicable Indian regulatory frameworks.

## 3. Proposed Solution

Cypher takes what an organisation's security tools report (vulnerability scans, EDR alerts, cloud and IAM misconfigurations, network exposure, backup posture) and turns it into two numbers a CFO, a board or a regulator can act on:

- **Expected Annual Loss (EAL):** what a year of cyber risk costs on average, in ₹.
- **Value at Risk (VaR, p95):** what a bad year looks like, in ₹.

It then shows which assets and findings drive those numbers, which controls would reduce them most for a given budget, what a Terraform change would do to them *before* it is applied, and how the underlying findings map to Indian regulatory frameworks (RBI Directions 2026, SEBI CSCRF/CCI, DPDP Act 2023) and to CIS Controls, NIST CSF and ISO 27001.

### Design principles

These eight rules shape the whole codebase. The full text is in [`CLAUDE.md`](CLAUDE.md).

1. **The rupee figure comes from a deterministic engine**, never from an ML model or an LLM. No organisation has enough labelled cyber-loss data to train a model that outputs rupees honestly.
2. **The LLM only touches the edges.** It turns a question into a tool call and narrates numbers that were already computed. Every number in its output is checked against real engine output (`ai/numeric_guard.py`); anything that can't be traced is flagged `[UNVERIFIED: …]`.
3. **One shared data contract.** Every connector emits `schema/aggregated_assets.schema.json`. The engine has no idea which tools exist.
4. **Quality gates fail safe.** A bad scan never replaces a good snapshot.
5. **Snapshots are immutable and bitemporal.** "Scanner didn't run" and "finding was fixed" are different facts, told apart by `scan_scope`.
6. **Compliance maps to findings and controls**, never to what the optimizer recommends.
7. **Portfolios are re-simulated jointly.** Overlapping controls make summed per-control savings badly overstate the benefit.
8. **Regulations are versioned and effective-dated.** RBI's 2016 Cyber Security Framework was repealed on 31 July 2026 and replaced by entity-specific Directions.

Missing data is shown as missing. An asset with no scan data reads "not modelled", never ₹0. An unknown control is unknown, never "protected". With no committed snapshot, every interface says so instead of showing a number.

## 4. Key Features

- **Connector-based ingestion into one shared schema.** Six connectors (Wazuh, Greenbone, Prowler, ScoutSuite, PMapper/IAM, CMDB) each wrap one tool and normalise its output into `schema/aggregated_assets.schema.json`. An unconfigured or failing connector is recorded as an unreachable scanner, never faked.
- **Five quality gates.** A candidate snapshot must pass asset-count delta, no findings from unreachable scanners, criticality present, provenance present, and no ordinal labels in numeric fields. If it fails, the previous snapshot stays current.
- **Immutable, bitemporal snapshots.** Content-hash snapshot IDs, `observed_at` / `valid_from` / `valid_to`, and an append-only history.
- **Open FAIR + Monte Carlo engine.** FAIR loss-event scenarios are built from findings. Frequency and vulnerability come from EPSS, CISA KEV and telemetry, and loss magnitude from service criticality and named assumptions. Monte Carlo produces a full annual-loss distribution: EAL, VaR and ranked contributors.
- **Bayesian attack graph.** Where a snapshot carries network topology, internal assets are scored on their real attack paths in from internet-facing servers.
- **Joint-simulation investment optimizer.** A cost-free priority plan, plus budget-constrained portfolios over declared costs. Every candidate portfolio is re-simulated as a whole, never priced by adding up per-control savings.
- **Pre-apply Terraform pricing (`cypher plan`).** The change in EAL and VaR a Terraform plan would cause, usable as a CI gate.
- **Multi-framework compliance mapping.** Control-by-control status against RBI Directions 2026, SEBI CSCRF/CCI, DPDP Act 2023, CIS Controls, NIST CSF and ISO 27001. Libraries are versioned and effective-dated, and statutory penalty ceilings are shown.
- **Ask Cypher.** A chat assistant that answers questions such as "what is driving our exposure?" by calling engine tools. Every number it says is verified before display.
- **Dashboard.** Setup, overview (EAL/VaR, trend, loss exceedance curve, top drivers, what-if lab), assets and findings, attack paths, investment, compliance, and data and model (provenance, quality gates, coverage, assumption register).
- **Accounts and onboarding.** Anyone who is not signed in lands on the register screen (organisation name, email, password), then picks the security tools their organisation runs, then reaches the dashboard. Accounts, organisations and tool selections are stored in Postgres. The API rejects unauthenticated requests to its data routes.
- **Daily pipeline.** A scheduled GitHub Actions job scans a deliberately vulnerable AWS sandbox, ingests the results and publishes the snapshot store to S3 for the hosted API.

Every modelling constant is a documented judgement call, not fitted to a real organisation's loss history. See [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md).

## 5. Technology Stack

- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, plain CSS with hand-written SVG charts (no charting or UI library)
- **Backend:** Python ≥ 3.11, FastAPI, Uvicorn, Pydantic, Typer and Rich (the `cypher` CLI), httpx, requests
- **Quantitative Engine & Mathematics:** NumPy, `jsonschema`, PyYAML (Open FAIR, Monte Carlo, Bayesian attack graph, joint-simulation optimizer)
- **Connectors & Infrastructure:** boto3, python-gvm (Greenbone), Wazuh REST and indexer APIs, Prowler, ScoutSuite, PMapper, Terraform, AWS, Docker, GitHub Actions, Vercel (dashboard hosting)
- **AI / LLM:** Groq (Ask Cypher chat and intent classification) and Jev by TypeSafe AI (CMDB identity resolution during ingest), both called from the backend and never from the browser. The LLM never produces a rupee figure.
- **Authentication:** argon2 password hashing (`argon2-cffi`), signed expiring session tokens (`PyJWT`), httpOnly session cookie on the dashboard
- **Database:** Postgres for accounts, organisations and tool selections via `psycopg`. See the note below.
- **Testing & Quality Assurance:** pytest, mypy (`--strict`), ruff, ESLint, `next build`, plus dependency audit, secret scanning and Semgrep in CI

### A Note on the Database

Two kinds of data are stored differently:

- **Accounts, organisations and tool selections** live in Postgres (`users`, `organizations`, `org_tools`), reached through the `DATABASE_URL` environment variable. Any Postgres works, including a hosted Supabase database. The tables are created automatically on first use from `interfaces/api/sql/0001_accounts.sql`. Passwords are stored only as argon2 hashes.
- **Risk data** lives in the snapshot store, not in the database. Snapshots are immutable JSON files (`current.json` plus an append-only `history/`), and the daily pipeline publishes them to S3, which the hosted API syncs down. This suits the bitemporal, content-addressed design. It is also **not yet per organisation**: every signed-in organisation sees the same snapshot. See [Future Scope](#11-future-scope).

## 6. Architecture

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

1. **Connect.** Each connector wraps one tool and normalises its output into the one shared schema. Nothing downstream ever knows which tool a finding came from.
2. **Gate.** A candidate snapshot must pass the five quality checks. If it fails, the previous snapshot stays current.
3. **Quantify.** The engine builds FAIR loss-event scenarios from the findings and runs a Monte Carlo simulation to produce a full annual-loss distribution.
4. **Decide.** The optimizer ranks controls by how much each one reduces loss, given the ones before it. Given declared costs and a budget, it recommends a portfolio, re-simulating every candidate as a whole.
5. **Explain.** The dashboard, the API, the CLI and Ask Cypher all show the same engine output, with the snapshot it came from.

### API surface (FastAPI, `interfaces/api/`)

```
User / Browser
      │
      ▼
Next.js Dashboard (interfaces/dashboard)
      │   /register, /login, /setup (tool selection), then the app
      ▼ (REST over HTTP, Authorization: Bearer <session token>)
FastAPI (interfaces/api/app.py)
      ├── /auth/register, /auth/login        (public: create an account, obtain a token)
      ├── /auth/me, /org/setup               (who am I; save entity type and tool selection)
      ├── /health, /health/snapshot-sync     (public: probes and snapshot sync status)
      ├── /snapshot, /snapshot/gates         (current snapshot provenance and gate results)
      ├── /exposure, /exposure/history, /exposure/exceedance   (EAL, VaR, trend, loss exceedance curve)
      ├── /assets                            (findings and the FAIR parameters behind every figure)
      ├── /attack-graph, /attack-graph/targets/{asset_id}
      ├── /frameworks, /frameworks/{framework}/status          (control-by-control compliance status)
      ├── /simulate                          (what-if simulation)
      ├── /optimize, /optimize/candidates, /optimize/plan      (priority plan and budgeted portfolios)
      ├── /assumptions                       (live assumption register)
      ├── /chat, /chat/stream, /chat/tools   (Ask Cypher; JSON or Server-Sent Events)
      └── /snapshots, /snapshots/{id}/download-url             (signed S3 links; own shared-secret header)
```

Every route needs a valid session token except `/health*`, `/docs`, `/snapshots` (which has its own token) and `/auth/register` and `/auth/login`. With no `AUTH_JWT_SECRET` configured the API answers 503 rather than letting requests through.

### Module ownership

Imports follow strict layering. `schema/` depends on nothing. Connectors never import the engine, and the engine never imports a connector. Only `ai/` calls an LLM, and only `core/` produces a rupee figure. The dashboard never imports Python. The full ownership map is in [`CLAUDE.md`](CLAUDE.md#module-ownership-map).

### Pricing a Terraform change before apply (`cypher plan`)

`cypher plan` answers "what does this Terraform change do to our cyber risk, in rupees?" before `terraform apply`, so it can run as a CI gate:

```bash
terraform plan -out tf.plan && terraform show -json tf.plan > tf_plan.json
cypher plan tf_plan.json                            # report only (exit 0)
cypher plan tf_plan.json --fail-on-eal-increase 0   # exit 2 if EAL rises
cypher plan --dir infra/terraform/environments/dev --json   # runs terraform for you
```

- **Baseline.** The current committed snapshot. With `SNAPSHOT_S3_BUCKET` set, the store published by the daily pipeline is mirrored into `SNAPSHOT_STORE_PATH` first, so the plan is priced against the latest ingest. If S3 can't be reached, the report says so and uses the local copy. `--offline` skips S3, and `--snapshot FILE` pins a specific baseline.
- **Translation.** `infra/connectors/terraform_plan.py` turns the plan into schema-shaped changes: security-group internet exposure and internal reachability, `AdministratorAccess` and console-without-MFA findings, DLM backup coverage, and deletions. The CLI overlays those changes on a copy of the baseline. `core.optimizer.compare_snapshots` then re-simulates the baseline and the proposed state on the same random draws.
- **Report.** Baseline, proposed and change for EAL and VaR. It also lists the loss scenarios that moved, with the Terraform address behind each, and the baseline's ID, source and age.
- **Stated limits.** A newly created resource has no scan data, so it is listed as unscanned with unknown risk, never ₹0. Values known only after apply, resources the baseline can't be matched to, and resource types with no rule are listed as not modelled. With no committed snapshot, the command exits 1 instead of guessing.

### The daily pipeline

```
bastion (triggered via SSM, no SSH):  Wazuh export, Greenbone report  ─▶ S3 inputs/
GitHub Actions, 02:30 IST daily or on demand:
    Prowler + PMapper scan of the AWS sandbox                          ─▶ S3
    EC2 inventory (CMDB stand-in) + `cypher ingest`                     ─▶ S3 snapshots/
hosted API (infra/Dockerfile.api)  ─ syncs snapshots/ every 5 min ─▶  dashboard (Vercel)
```

The scanned environment is **LoanEase**, a deliberately vulnerable AWS sandbox defined in [`infra/terraform/`](infra/terraform/README.md). Its `manifest.yaml` records every planted weakness and how it was verified. A missing or stale input is never faked: its scanner is recorded as unreachable. If the gates reject a candidate, the previous snapshot stays current and the workflow run fails visibly.

## 7. Repository Structure

```
Su₹aksha/
├── README.md                     # Project overview and instructions
├── CLAUDE.md                     # Design principles, ownership map, conventions
├── pyproject.toml                # Backend package, dependencies, tool config
├── .env.example                  # Every backend environment variable
├── schema/                       # The shared data contract (JSON Schema) and a sample snapshot
├── infra/                        # Connectors, Terraform-plan translator, sandbox and API image
│   ├── connectors/               # One connector per tool: fetch → normalize → schema shape
│   ├── inventory/                # Operator helpers that produce connector input files
│   ├── bastion/                  # Export scripts run on the bastion
│   ├── terraform/                # The LoanEase sandbox (infrastructure as code)
│   └── tests/fixtures/           # Recorded tool output and Terraform plans
├── core/                         # Snapshot gates and store, FAIR + Monte Carlo engine,
│                                 # attack graph, optimizer, assumptions.py (all modelling constants)
├── governance/                   # Versioned control libraries, findings→controls mapper, attestations
├── ai/                           # LLM client, intent classifier, chat engine, numeric guard, tool wrappers
├── interfaces/
│   ├── api/                      # FastAPI app, dashboard routes, accounts, auth, snapshot sync and links
│   │   └── sql/                  # Account tables (applied automatically on first use)
│   ├── cli/                      # The `cypher` command
│   ├── dashboard/                # Next.js app (separate toolchain, talks to the API over HTTP only)
│   └── tests/                    # Pure-logic and account/auth tests
├── docs/                         # Project context, glossary, ASSUMPTIONS.md, operations
└── .github/                      # CI (lint, types, tests, deps, secrets, Semgrep) and the daily ingest
```

### What Goes Where?

| Item | Location |
|---|---|
| Shared data contract | `schema/aggregated_assets.schema.json` |
| Connectors (one per security tool) | `infra/connectors/` |
| Risk engine, quality gates, optimizer, every modelling constant | `core/` (constants in `core/assumptions.py`) |
| Regulatory control libraries and the findings→controls mapper | `governance/` |
| LLM, chat assistant and numeric verification | `ai/` |
| API, CLI, account and auth code | `interfaces/api/`, `interfaces/cli/` |
| Dashboard (setup, overview, attack paths, investment, compliance) | `interfaces/dashboard/` |
| Account schema (Postgres) | `interfaces/api/sql/` |
| Sandbox infrastructure and bastion scripts | `infra/terraform/`, `infra/bastion/` |
| Technical documentation and assumptions | `docs/` (start with `docs/PROJECT_CONTEXT.md` and `docs/ASSUMPTIONS.md`) |

## 8. Prototype Walkthrough

The walkthrough below describes what each screen shows.

1. **Register and Sign in.** Anyone who is not signed in lands here. Register takes an organisation name, work email and password (with a strength meter). Sign in shows one generic error for any bad credential.
2. **Setup: Tool Selection.** Pick the security tools your organisation runs, grouped by category. The screen shows which kinds of telemetry are covered, which connect today and which are declare-only, and asks for your entity type so the right regulations are mapped.
3. **Overview.** EAL and VaR, the trend, the loss exceedance curve, top drivers and the what-if lab.
4. **Assets & Findings.** The FAIR parameters behind every figure, per asset.
5. **Attack Paths.** An interactive attack graph.
6. **Investment.** A cost-free priority plan, plus budget-constrained portfolios over declared costs, each re-simulated as a whole.
7. **Compliance.** Control-by-control status against each framework, and statutory penalty ceilings.
8. **Data & Model.** Snapshot provenance, the five quality gates, coverage and the live assumption register.
9. **Ask Cypher.** The chat panel, where every number is verified against engine output before display.

## 9. Installation

### Prerequisites

- Python ≥ 3.11
- Node.js and npm
- A Postgres database (for accounts). Any Postgres works, including a hosted Supabase project.

### 1. Clone the Repository

```bash
git clone https://github.com/shivansh-source/ps105.git
cd ps105
```

### 2. Backend Setup

One virtual environment covers the whole backend. `core/`, `governance/`, `ai/`, `infra/` and `interfaces/` are one package (`pyproject.toml`) and import each other directly.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # installs the `cypher` command too
cp .env.example .env             # then fill in the values below
```

For accounts and sign-in, set these two in `.env`:

```
DATABASE_URL=postgresql://...     # your Postgres connection string; tables are created automatically
AUTH_JWT_SECRET=...               # at least 32 random bytes:
                                  #   python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For local development without a database, set `AUTH_DISABLED=1` to skip the sign-in check. Never set it in a hosted environment. Every other variable is optional for a first run.

### 3. Frontend Setup

```bash
cd interfaces/dashboard
cp .env.example .env.local       # then set NEXT_PUBLIC_API_BASE_URL if the API is not on :8000,
                                 # and AUTH_JWT_SECRET to the same value as the API's
npm install
```

## 10. Run

### 1. Start the Backend API Server

```bash
# with the virtual environment active:
uvicorn --factory interfaces.api.app:create_app --reload --port 8000
```

### 2. Start the Frontend Development Server

```bash
cd interfaces/dashboard
npm run dev                          # http://localhost:3000, expects the API on :8000
NEXT_PUBLIC_DEMO_MODE=1 npm run dev  # or: offline, with clearly-labelled SAMPLE data
```

Open http://localhost:3000. You land on the register screen. Register, pick your tools, and you reach the dashboard.

The dashboard shows real figures once a snapshot has been committed by `cypher ingest`, or when the API is syncing from the published S3 store. Until then it shows an explicit "no figure yet" state rather than placeholder numbers.

### 3. Run the Engine Without Any Scanners

```bash
cypher validate-snapshot schema/sample_aggregated.json
cypher run-engine schema/sample_aggregated.json

# Price a sample Terraform change against a sample baseline
cypher plan infra/tests/fixtures/tf_plan_open_db.json \
  --snapshot infra/tests/fixtures/tf_plan_baseline.json
```

### 4. Ask Cypher

Set `GROQ_API_KEY` in `.env` and restart the API, then (sign in first, or use `AUTH_DISABLED=1` locally):

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"what is driving our exposure?"}'
```

`POST /chat` returns a complete, verified turn. `POST /chat/stream` streams the same turn as Server-Sent Events. Only its `final` event is verified.

### The `cypher` CLI

Every command is a thin adapter over `core/`, `governance/` and `ai/`. None of them computes a figure on its own.

| Command | What it does |
|---|---|
| `cypher ingest [--no-commit]` | Runs every configured connector (Wazuh, Greenbone, Prowler, ScoutSuite, PMapper/IAM, CMDB). An unconfigured or failing connector is recorded as an unreachable scanner, never faked. Placeholder asset IDs are reconciled against the CMDB (Jev-assisted, every decision logged). The candidate goes through the five gates and is committed only if all of them pass. |
| `cypher validate-snapshot FILE` | Runs the five quality gates on a candidate against the current snapshot, and reports each gate. Never commits. |
| `cypher run-engine FILE` | Prints EAL, VaR and the top loss contributors for a snapshot file. |
| `cypher framework-status FRAMEWORK` | Control-by-control status of the current snapshot against one control library (`rbi_2026_directions`, `sebi_cscrf_cci`, `dpdp_act_2023`, `cis_controls`, `nist_csf`, `iso_27001`). |
| `cypher plan [PLAN.json \| --dir DIR]` | The change in EAL and VaR a Terraform plan would cause. |
| `cypher optimize` | Not implemented yet. Use the dashboard's investment page or `POST /optimize`. |

### Configuration

Everything is configured through environment variables, documented one by one in [`.env.example`](.env.example) (backend) and [`interfaces/dashboard/.env.example`](interfaces/dashboard/.env.example) (frontend). The main groups are:

- **Accounts:** `DATABASE_URL`, `AUTH_JWT_SECRET` (the API and the dashboard share it), and `AUTH_DISABLED` (local development only).
- **LLM:** `GROQ_API_KEY` and `GROQ_MODEL` for Ask Cypher. `TYPESAFE_API_KEY` for Jev-assisted identity resolution during ingest.
- **Connectors:** one block per tool (API endpoints or export file paths). A connector with no configuration is simply recorded as unreachable.
- **Stores:** `SNAPSHOT_STORE_PATH`, `ATTESTATION_STORE_PATH` and `IDENTITY_RECONCILIATION_STORE_PATH`. All default to `./data/`, which is gitignored.
- **Hosting:** `SNAPSHOT_S3_BUCKET` / `SNAPSHOT_S3_PREFIX`, `CORS_ALLOWED_ORIGINS`, `SNAPSHOT_LINKS_TOKEN`, and for the dashboard `NEXT_PUBLIC_API_BASE_URL`.

### Run Tests

```bash
pytest          # core/, governance/, ai/, infra/ and interfaces/ tests
mypy .          # --strict; type hints are required on every signature
ruff check .
ruff format --check .
cd interfaces/dashboard && npm run lint && npm run build
```

The `ai/` tests read `./data/snapshots`, so run them with `SNAPSHOT_STORE_PATH` pointing at an empty directory if you have a real snapshot there. Connector and CLI tests run against recorded tool output in `infra/tests/fixtures/` (Greenbone, Prowler, ScoutSuite, PMapper and Wazuh exports, and `terraform show -json` plans), not against mocks. The account tests start a throwaway Postgres through `pgserver`. GitHub Actions runs lint, type checks, tests, a build, a dependency audit, secret scanning and Semgrep on every push and PR to `main` and `develop`.

## 11. Future Scope

- **Per-organisation data isolation.** Accounts and tool selections are per organisation, but the snapshot store is still one global store, so every signed-in organisation sees the same figures. Next step: a snapshot store per organisation.
- **Tool selection that drives ingestion.** The saved selection records what an organisation runs, but does not yet decide which connectors `cypher ingest` executes; that is still a fixed list, gated by each connector's own environment variables.
- **Threat intelligence connectors.** EPSS/KEV, Nessus and nmap are stubs. Until threat intel lands, findings carry no EPSS score and the engine uses a documented, criticality-scaled baseline exploit probability (see [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md)).
- **Control costs and `cypher optimize`.** `cypher optimize` and the assistant's `optimize_investment` tool are stubs because nothing supplies control costs yet; the dashboard asks the user to declare them.
- **Network topology.** The attack graph applies only when a snapshot carries `network_topology`, which no connector populates yet.
- **Calibration.** Fit the modelling constants to real loss history instead of documented judgement calls.
- **Sign-in hardening.** Login rate limiting, password reset, email confirmation, and multiple users and roles per organisation.
- **Hosting.** The API and dashboard (Render/Fly and Vercel) are configured in the repo but not yet deployed.
- **DPDP Act penalties.** The DPDP library has penalty provisions only, which are not in force until 2027-05-13.

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
| Set up accounts and sign-in | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
