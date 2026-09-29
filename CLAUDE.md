# Su₹aksha — project instructions

## What this is

Su₹aksha is a cyber risk quantification platform built for Smart India
Hackathon 2026 (Problem Statement 26105). It converts technical security
telemetry (vulnerability scans, EDR alerts, IAM posture, network exposure,
threat intel, backup/DR posture) into rupee-denominated risk figures —
Expected Annual Loss (EAL) and Value at Risk (VaR) — using the Open FAIR risk
framework plus Monte Carlo simulation. From those figures it recommends where
to spend a finite security budget, and it maps underlying findings to Indian
regulatory frameworks (RBI Directions 2026, SEBI CSCRF/CCI, CIS Controls,
NIST CSF, ISO 27001).

The rupee number is the product. Everything else in this repo — connectors,
schema, quality gates, the optimizer, the LLM layer — exists to get that
number right and to defend it under scrutiny.

## The 8 non-negotiable design principles

These are guardrails, not suggestions. Any change that violates one of these
should be rejected in review regardless of how convenient it is.

1. **The rupee figure comes from a deterministic engine, never from an ML
   model or an LLM.** Open FAIR supplies the structure; EPSS/KEV/telemetry
   supply parameters; Monte Carlo propagates uncertainty. No organization has
   enough labeled cyber-loss data to train a model that outputs rupees
   honestly.
2. **The LLM touches only the edges**: turning a user's sentence into a
   structured tool call, and narrating already-computed numbers into prose.
   It never computes a figure. Every number in any LLM output is verified
   against real engine output before display (`numeric_guard`).
3. **`schema/aggregated_assets.schema.json` is the one shared contract.** All
   connectors emit this shape regardless of which tool they wrap. The engine
   reads only this shape and has no knowledge of specific tools. If a module
   ever needs `if source == "nessus"`, normalization happened in the wrong
   place.
4. **Quality gates sit between aggregation and the engine.** A candidate
   snapshot must pass 5 checks before becoming current. Fail → previous
   snapshot stays current (fail-safe, never fail-open).
5. **Snapshots are bitemporal and immutable** (`observed_at`, `valid_from`,
   `valid_to`, content-hash `snapshot_id`). Absence of a finding must
   distinguish "scanner didn't run" from "actually remediated", resolved via
   `scan_scope`.
6. **Compliance maps to findings and controls, never to optimizer output.**
   We never certify a recommendation as compliant — only underlying facts.
7. **The optimizer must re-simulate candidate portfolios jointly**, never sum
   precomputed per-item deltas. Overlapping controls (e.g. patching a CVE
   *and* hardening the EDR that would have caught it) make naive addition
   badly overstate benefit.
8. **RBI's 2016 Cyber Security Framework was repealed 31 July 2026** and
   replaced by entity-specific Directions, 2026. The control library must be
   versioned and effective-dated. Do not hardcode the 2016 framework.

## Module ownership map

| Folder | Owns | May import from | Must never import from |
|---|---|---|---|
| `schema/` | The shared data contract (JSON Schema, sample fixture) | nothing | — |
| `infra/connectors/` | Fetching raw tool output and normalizing it into `schema/aggregated_assets.schema.json` | `schema/` | `core/`, `governance/`, `ai/` |
| `core/` | Snapshot lifecycle, quality gates, the FAIR + Monte Carlo engine (including the bounded Bayesian attack graph that feeds its vulnerability factor), the joint-simulation optimizer, all named assumptions | `schema/` | `infra/`, `governance/`, `ai/`, `interfaces/` |
| `governance/` | Mapping findings/controls to regulatory frameworks, evidence generation | `schema/`, `core/` (read-only: findings/controls, never optimizer output) | `infra/`, `ai/`, `interfaces/` |
| `ai/` | Intent classification, LLM client, numeric verification, tool wrappers | `core/`, `governance/` | `infra/` |
| `interfaces/` |Dashboard, API and CLI entry points | `core/`, `governance/`, `ai/` | — |

`schema/` sits at the bottom of the dependency graph and depends on nothing.
`core/` is the only place that produces a rupee figure. `ai/` is the only
place an LLM is invoked.

Other folders, and the rules that apply to them:

- `infra/inventory/` — operator-run helpers that produce *input files* for
  connectors (e.g. `export_ec2_inventory.py`, `build_wazuh_bundle.py`). Same
  import rules as `infra/connectors/`: never `core/`, `governance/` or `ai/`.
- `infra/bastion/` and `infra/terraform/` — shell scripts run on the bastion,
  and the sandbox's infrastructure as code. No Python imports; see
  `docs/OPERATIONS.md`.
- `core/declared/` (with `core/declared_services.py`) — **human-declared**
  business context (service criticality, backup posture, which assets serve
  them). It is declared, never observed, and its files must say so.
- `interfaces/api/snapshot_sync.py` and `snapshot_links.py` — pull the
  published snapshot store from S3 and issue short-lived signed URLs; see
  `docs/OPERATIONS.md`.

## Code conventions

- **Type hints are required** on every function and method signature, no
  exceptions. `mypy --strict` must pass.
- **No magic numbers.** Every tunable modelling constant (control resistance
  values, RTO multipliers, cost-per-record, expected regulatory penalty,
  baseline frequencies, etc.) lives in `core/assumptions.py` and is imported
  from there. If you catch yourself writing a bare numeric literal that
  represents a modelling judgement call anywhere else in the codebase, stop
  and move it to `core/assumptions.py` first.
- Docstrings describe the contract: parameters, return shape, and — where
  relevant — what the function must never do (e.g. "must never sum
  precomputed deltas").
- Prefer explicit dataclasses/Pydantic models over passing raw dicts between
  layers, except at the exact boundary where the schema-shaped JSON crosses
  in or out.

## Two applications, two toolchains

This repo holds a Python backend and a Next.js frontend, set up and run
independently:

- **Backend** — `schema/`, `infra/`, `core/`, `governance/`, `ai/`,
  `interfaces/api/` (FastAPI), `interfaces/cli/` (Typer). One package, one
  virtual environment (see root `pyproject.toml`) — these modules import
  each other directly per the ownership map above, so there is no reason
  to split them into separate environments.
- **Frontend** — `interfaces/dashboard/`, a Next.js app with its own
  `package.json`/`node_modules`, entirely outside the Python venv. It talks
  to the backend only over HTTP, through `interfaces/api/app.py` — it must
  never import a Python module directly, and no Python module may import
  anything from `interfaces/dashboard/`.

## Running tests

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
mypy .
ruff check .
```

Tests are colocated per top-level package: `core/tests/`, `governance/tests/`,
`ai/tests/`, `infra/tests/` and `interfaces/tests/` (all in pytest's
`testpaths`). Connector tests run against fixtures in the real tool's output
shape — each fixture says whether it is a **real capture** or **synthetic**
(synthetic ones use the reserved `192.0.2.0/24` range and invented names) —
never against mocks that assert nothing about real output shapes.
`interfaces/tests/` covers pure logic only (snapshot sync, signed links).
`interfaces/dashboard/` has no test runner yet; check it with `next build`
(which type-checks) and `eslint`, separate from `pytest`/`mypy`/`ruff`.

Two local-environment notes: history files are named `sha256:<hash>.json`, which
NTFS cannot create, so 4 `core/tests/test_snapshot_store.py` tests fail on
Windows (they pass on Linux/CI); and the `ai/` tests read `./data/snapshots`, so
run them with `SNAPSHOT_STORE_PATH` pointing at an empty directory if you have a
real snapshot there.

## Common mistakes (do not do these)

- **Do not let a model output a rupee figure.** If you're tempted to have the
  LLM "just estimate" a loss number when the engine hasn't run, don't. Return
  an error or ask the engine to run instead. (Principle 1)
- **Do not let the LLM's prose drift from the numbers it's narrating.** Any
  number appearing in generated text must have been produced by `core/` and
  passed through `ai/numeric_guard.py` first. A narration step is not allowed
  to round, restate, or "helpfully" recompute a figure. (Principle 2)
- **Do not special-case a data source anywhere outside `infra/connectors/`.**
  If `core/engine/` or `governance/mapper.py` needs to know whether a
  finding came from Nessus vs. Prowler, the connector didn't normalize
  correctly — fix the connector, not the consumer. (Principle 3)
- **Do not mark a compliance control "met" because the optimizer recommended
  funding it, or because a recommendation was accepted.** Compliance status
  is derived only from evidence about the current state of controls and
  findings, never from what the optimizer suggested doing next. (Principle 6)
- **Do not compute portfolio benefit by summing each control's individual
  simulated delta.** Controls overlap (patching a vulnerability an EDR rule
  already mitigates, for example). Any multi-control recommendation must be
  produced by re-running the Monte Carlo simulation on the candidate
  portfolio as a whole. (Principle 7)
- **Do not use `counts_toward_loss: false` to hide a finding.** It means
  "corroborating evidence, counted elsewhere", not "fixed" and not "ignore".
  The finding stays in the snapshot; using the flag needs a written reason in
  `docs/ASSUMPTIONS.md`. (Principles 1 and 5)
- **Do not fabricate or backfill connector data, and do not let a missing
  input look clean.** A missing, stale or unparseable input must leave its
  scanner in `unreachable_scanners`. Never invent a timestamp, criticality or
  identifier, and never present a synthetic fixture as captured output.
  (Principle 5)
