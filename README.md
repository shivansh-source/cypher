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
(LLM client, numeric guard, tool registry, chat assistant), the chat
endpoints in `interfaces/api/`, four of `infra/connectors/`
(`wazuh_connector.py`, `greenbone_connector.py`, `prowler_connector.py`,
`scoutsuite_connector.py`), the `ingest` command in
`interfaces/cli/riskctl.py`, `interfaces/dashboard/`, and `core/engine/`
(the Open FAIR + Monte Carlo pipeline: scenario derivation,
parameterization, simulation, and the final risk figure) are real;
everything else (`core/optimizer.py`, `core/snapshot.py`, the thin
wrappers in `ai/tools/` that call into `core/`, the remaining connectors
and CLI commands) still contains signatures and docstrings only — see
`CLAUDE.md` for the design principles that govern how the remaining
bodies must be implemented, and `docs/ASSUMPTIONS.md` for every modelling
constant `core/engine/` reads from and how far each is from being
calibrated to a real organization.

Because `ai/tools/` and `core/optimizer.py`/`core/snapshot.py` are still
unimplemented, the chat assistant can be talked to today but cannot yet
report a real figure through that path: every tool call comes back as an
explicit "not computed yet, and here is why", which the assistant relays
rather than filling in. `core.engine.compute_risk_figure` itself is
runnable today given a snapshot (see `schema/sample_aggregated.json`) —
it just isn't wired to the chat assistant or the dashboard's API yet. See
`interfaces/api/README.md`.

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

A standalone Next.js app (TypeScript, App Router, Tailwind) with four routes:
exposure (EAL/VaR and what drives them), investment (budget-constrained
portfolio), compliance (control-by-control framework status), and data quality
(snapshot provenance, quality gates, scanner coverage). `interfaces/api/app.py`
now registers `/exposure` and `/optimize` routes, and `core/engine/` can
compute a real figure today — but those routes delegate through
`ai/tools/get_exposure.py`/`ai/tools/optimize_investment.py` and
`core/snapshot.py`'s (still unimplemented) current-committed-snapshot
lookup, so calling them still errors rather than returning a figure. The
dashboard renders explicit "no figure computed yet" states rather than
placeholder numbers until that chain is wired end to end; see
`interfaces/dashboard/README.md` for the backend endpoint contract it
expects and for the opt-in sample-data mode.

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

`riskctl ingest` (see `infra/README.md`) is runnable today against real
Wazuh/Greenbone/Prowler/ScoutSuite output, and `core.engine.compute_risk_figure`
is runnable today against a hand-authored snapshot (see
`schema/sample_aggregated.json`) — but the two aren't connected yet: the
quality gates and snapshot commit lifecycle in `core/snapshot.py` are
still unimplemented, so an ingested snapshot has nowhere to go, and the
optimizer in `core/optimizer.py` (which calls `compute_risk_figure`
internally) is also still unimplemented. See `.claude/commands/` for the
workflows a contributor will repeat as that lands.
