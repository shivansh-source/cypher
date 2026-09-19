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

**This repository is currently a scaffold.** Every module contains
signatures and docstrings only — see `CLAUDE.md` for the design principles
that govern how the bodies must be implemented.

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

A standalone Next.js app (TypeScript, App Router, Tailwind), scaffolded but
still just the default `create-next-app` starter page — no Su₹aksha-specific
UI yet.

```
cd interfaces/dashboard
npm install
npm run dev
```

It talks to the backend only through the FastAPI app in
`interfaces/api/app.py` (over HTTP) — never by importing Python modules
directly.

### Do I need a venv per package?

No. `core/`, `governance/`, `ai/`, `infra/`, `interfaces/api/`, and
`interfaces/cli/` are one Python package (see the single root
`pyproject.toml`) and share one virtual environment — they import each
other directly (per the module ownership map in `CLAUDE.md`), so splitting
them into separate environments would only add friction. `interfaces/dashboard/`
is a different language runtime entirely (Node.js) and is never part of
that venv; it manages its own dependencies via `package.json`/`node_modules`
and is isolated by that mechanism instead.

There is nothing to run yet on the backend — connectors, the engine, and
the optimizer are unimplemented. See `.claude/commands/` for the workflows
a contributor will repeat once implementation begins.
