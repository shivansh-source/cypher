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
multi-step "stepping-stone" attacks, and the joint-simulation optimizer), six of
`infra/connectors/` (`prowler_connector.py`, `iam_connector.py` (PMapper),
`cmdb_connector.py` (asset inventory), `wazuh_connector.py`,
`greenbone_connector.py`, `scoutsuite_connector.py`) and the `ingest` command in
`interfaces/cli/riskctl.py` are real, and a daily GitHub Actions pipeline
(`.github/workflows/scheduled-ingest.yml`) refreshes and publishes snapshots to S3.
Still signatures and docstrings only:
the `threat_intel`, `nessus` and `nmap` connectors, the
`optimize_investment` tool in `ai/tools/`, and `riskctl`'s `optimize`
command. For the connector catalog and what each one produces today see
`docs/CONNECTORS.md`; for running, hosting, cost and runbooks see
`docs/OPERATIONS.md`; for the full history of what was built and why see
`docs/BUILD_LOG.md` — and see `CLAUDE.md` for the design principles that govern how the
remaining bodies must be implemented, and `docs/ASSUMPTIONS.md` for every
modelling constant `core/engine/` reads from and how far each is from being
calibrated to a real organization.

Once a snapshot has been committed (`riskctl ingest`), the API, the
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

### Do I need a venv per package?

No. `core/`, `governance/`, `ai/`, `infra/`, `interfaces/api/`, and
`interfaces/cli/` are one Python package (see the single root
`pyproject.toml`) and share one virtual environment — they import each
other directly (per the module ownership map in `CLAUDE.md`), so splitting
them into separate environments would only add friction. `interfaces/dashboard/`
is a different language runtime entirely (Node.js) and is never part of
that venv; it manages its own dependencies via `package.json`/`node_modules`
and is isolated by that mechanism instead.

`riskctl ingest` (see `infra/README.md`) runs every implemented connector,
passes the candidate through the five quality gates in `core/snapshot.py`, and
commits it to the snapshot store (`SNAPSHOT_STORE_PATH`). `core.engine.compute_risk_figure`
then computes the rupee figure from that committed snapshot, and the API,
dashboard and assistant read it. `schema/sample_aggregated.json` remains a
hand-authored fixture for exercising the engine. In the hosted setup the same
snapshot store is published to S3 by the daily workflow and pulled by the API
(see `docs/OPERATIONS.md`). See `.claude/commands/` for the workflows a
contributor will repeat.
