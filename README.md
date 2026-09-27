# Su₹aksha

Cyber risk quantification for Smart India Hackathon 2026 (Problem Statement
26105).

Su₹aksha converts technical security telemetry — vulnerability scans, EDR
alerts, IAM posture, network exposure, threat intelligence, backup/DR
posture — into rupee-denominated risk figures (Expected Annual Loss, Value
at Risk) using the Open FAIR framework and Monte Carlo simulation. It then
recommends where to spend a finite security budget for maximum risk
reduction, and maps the underlying findings to Indian regulatory frameworks
(RBI Directions 2026, SEBI CSCRF/CCI, CIS Controls, NIST CSF, ISO 27001).

**This repository is partially implemented.** `governance/`, `ai/`
(LLM client, numeric guard, tool registry, chat assistant), `interfaces/api/`,
`interfaces/dashboard/`, `core/` (the snapshot quality gates and store, the
Open FAIR + Monte Carlo engine, the Bayesian attack graph that models
multi-step "stepping-stone" attacks, and the joint-simulation optimizer), four of
`infra/connectors/` (`wazuh_connector.py`, `greenbone_connector.py`,
`prowler_connector.py`, `scoutsuite_connector.py`) and the `ingest` command in
`interfaces/cli/cypher.py` are real. Still signatures and docstrings only:
the `threat_intel`, `iam`, `nessus` and `nmap` connectors, the
`optimize_investment` tool in `ai/tools/`, and `cypher`'s `optimize`
command — see `CLAUDE.md` for the design principles that govern how the
remaining bodies must be implemented, and `docs/ASSUMPTIONS.md` for every
modelling constant `core/engine/` reads from and how far each is from being
calibrated to a real organization.

Once a snapshot has been committed (`cypher ingest`), the API, the
dashboard and the chat assistant all report real figures from the engine.
The one exception is `optimize_investment`: nothing in the system supplies
candidate-control costs, so the assistant reports it as unavailable, and the
dashboard's investment view asks the user to declare costs and calls the
optimizer directly (`POST /optimize`). See `interfaces/api/README.md`.

The attack graph only takes effect when a snapshot carries network
segmentation (`network_topology` and `assets[].network.segment_id`, both
optional — see `schema/README.md`). No connector populates those yet, so
real snapshots are scored exactly as before until one does. When it applies,
an internal asset is scored on its real paths in: for each internet-facing
server that leads to it, how often that server is attacked times the chance
an attacker gets from there to it, summed over those routes. Findings that
share a CVE are treated as falling together. Every figure it changes says
so in its description, with each route's percentage share ("reached via
attack graph: asset-web-01 80% (p=0.263), …"), so a dashboard number that moves when topology
arrives can always be traced to why. See `docs/ASSUMPTIONS.md`.

## Why rupees, and why not ML

No organization has enough labeled historical cyber-loss data to train a
model that outputs a rupee figure honestly. Instead, Su₹aksha uses a
deterministic actuarial framework (Open FAIR) parameterized by real signals
(EPSS, CISA KEV, live telemetry) and propagates uncertainty with Monte Carlo
simulation. An LLM sits at the edges only — turning natural language into
structured tool calls, and narrating already-computed numbers into prose —
and every number it ever displays is checked against real engine output
first.

## Repository layout

```
schema/         The one shared data contract every connector must emit.
infra/          Connectors that pull from security tools and normalize
                their output to the schema.
core/           Snapshot lifecycle, quality gates, the FAIR + Monte Carlo
                engine, the budget optimizer, and every named assumption.
governance/     Regulatory framework mapping and evidence generation.
ai/             Intent classification, LLM client, numeric verification,
                and thin tool wrappers around core/ and governance/.
interfaces/     API (FastAPI), CLI (Typer), UI Dashboard entry points.
docs/           Project context, the assumptions/honesty artifact, glossary.
```

See `CLAUDE.md` for the full design principles, module ownership map, and
coding conventions. See `docs/PROJECT_CONTEXT.md` for background on the
hackathon problem statement, and `docs/ASSUMPTIONS.md` for the running list
of every modelling assumption and its justification.

## Getting started

Su₹aksha is two separate applications sharing one repo: a Python backend
(everything except `interfaces/dashboard/`) and a Next.js frontend
(`interfaces/dashboard/`). They have independent toolchains and are set up
separately — there is no single install command that does both.

### Backend (`schema/`, `infra/`, `core/`, `governance/`, `ai/`, `interfaces/api/`, `interfaces/cli/`)

One virtual environment for the whole backend — see "Do I need a venv per
package?" below.

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### Frontend (`interfaces/dashboard/`)

A standalone Next.js app (TypeScript, App Router), built from an earlier
standalone HTML/JS design prototype (removed; see `interfaces/prototype/` at
commit `55ef517`), with five views: overview (EAL/VaR,
their trend across committed snapshots, the loss exceedance curve, top
contributors and a what-if lab), assets & findings (posture and the FAIR
parameters behind each figure), investment (budget-constrained portfolio over
declared-cost candidates), compliance (control-by-control framework status
and statutory penalty ceilings) and data & model (provenance, quality gates,
scanner coverage, the live assumption register), plus the Ask Suraksha
assistant. Every figure comes from an API endpoint over `core/`; with no
committed snapshot or no backend it renders explicit "no figure" states, never
placeholder numbers. See `interfaces/dashboard/README.md` for the endpoint
contract and the opt-in sample-data mode.

```
cd interfaces/dashboard
npm install
npm run dev
```

It talks to the backend only through the FastAPI app in
`interfaces/api/app.py` (over HTTP) — never by importing Python modules
directly.

### Chat assistant (`ai/chat.py`, `interfaces/api/`)

A natural-language front door to the same tools the dashboard reads. The
model chooses which of `ai/tools/` answers a question and narrates what
those tools returned; it never produces a figure, and every number in its
prose is checked against real tool output by `ai/numeric_guard.py` before
it is returned. Run it with:

```
source .venv/bin/activate
uvicorn --factory interfaces.api.app:create_app --reload --port 8000
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"what is driving our exposure?"}'
```

`POST /chat` returns a complete turn; `POST /chat/stream` streams the same
turn as Server-Sent Events. `interfaces/api/README.md` has the full
contract, including why a streamed `text_delta` must never be displayed as
the final answer.

### Pre-apply risk of a Terraform change (`cypher plan`)

`cypher plan` answers "what does this Terraform change do to cyber risk, in
rupees?" before `terraform apply`:

```
terraform plan -out tf.plan && terraform show -json tf.plan > tf_plan.json
cypher plan tf_plan.json                          # report only (exit 0)
cypher plan tf_plan.json --fail-on-eal-increase 0 # exit 2 if Expected Annual Loss rises
cypher plan --dir infra/terraform/environments/dev --json   # runs terraform for you
```

The baseline is the current committed snapshot, found automatically: with
`SNAPSHOT_S3_BUCKET` set (see `.env.example`), the store the daily
`scheduled-ingest` workflow publishes to S3 is mirrored into
`SNAPSHOT_STORE_PATH` (`./data/snapshots`) first, so the report is priced
against the latest ingest; without it, the local store is used as it is. If S3
cannot be reached the report says so and falls back to the local copy (the
header shows its source and age). `--offline` skips S3, and `--snapshot FILE`
uses a specific snapshot instead (e.g. a test fixture). The mirror replaces
the local `current.json` with the published one and only ever adds history.

`infra/connectors/terraform_plan.py` translates the plan into
schema-shaped changes (security-group internet exposure and internal
reachability, `AdministratorAccess`/console-without-MFA findings, DLM backup
coverage, deletions). The CLI overlays them on a copy of the current
committed snapshot and re-simulates both jointly on the same random draws
(`core.optimizer.compare_snapshots`). The report gives baseline, proposed
and change for EAL and VaR, the loss scenarios that moved and the Terraform
address behind each, and the baseline snapshot id and age.

Limits, stated in the report rather than hidden: a created resource has no
scan findings, so it is listed as unscanned with unknown risk, never as
₹0; values known only after apply, resources the baseline cannot be
matched to, and resource types with no rule are listed as not modelled.
With no committed snapshot the command exits 1 rather than estimate a
figure. The figures are only as fresh as the last `cypher ingest`.

### Do I need a venv per package?

No. `core/`, `governance/`, `ai/`, `infra/`, `interfaces/api/`, and
`interfaces/cli/` are one Python package (see the single root
`pyproject.toml`) and share one virtual environment — they import each
other directly (per the module ownership map in `CLAUDE.md`), so splitting
them into separate environments would only add friction. `interfaces/dashboard/`
is a different language runtime entirely (Node.js) and is never part of
that venv; it manages its own dependencies via `package.json`/`node_modules`
and is isolated by that mechanism instead.

`cypher ingest` (see `infra/README.md`) is runnable today against real
Wazuh/Greenbone/Prowler/ScoutSuite output, and `core.engine.compute_risk_figure`
is runnable today against a hand-authored snapshot (see
`schema/sample_aggregated.json`) — but the two aren't connected yet: the
quality gates and snapshot commit lifecycle in `core/snapshot.py` are
still unimplemented, so an ingested snapshot has nowhere to go, and the
optimizer in `core/optimizer.py` (which calls `compute_risk_figure`
internally) is also still unimplemented. See `.claude/commands/` for the
workflows a contributor will repeat as that lands.
