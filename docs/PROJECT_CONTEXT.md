# Project context

## Problem statement

Su₹aksha is built for Smart India Hackathon 2026, Problem Statement 26105.
The problem statement asks for a system that quantifies cyber risk in
financial terms for Indian organizations and helps them prioritize security
spend, while accounting for applicable Indian regulatory frameworks.

TODO: paste the exact PS 26105 problem statement text here once finalized,
including any evaluation criteria the hackathon specifies, so design
decisions can be checked against it directly rather than from memory.

## Why this approach

Most "cyber risk scoring" tools produce a unitless score (e.g. 0-100) that
cannot be compared to a budget, a insurance premium, or a regulatory fine.
Su₹aksha's premise is that the only number worth acting on is one
denominated in rupees, derived transparently enough to defend to a CISO, a
board, or a regulator. That requirement drives every design principle in
the repo-root `CLAUDE.md` — most directly, principle 1 (the rupee figure
comes from a deterministic engine, never an ML model or LLM) and principle
2 (the LLM only classifies intent and narrates already-computed numbers).

## Regulatory landscape this project tracks

- **RBI** — entity-specific Directions, 2026, which replaced the repealed
  2016 Cyber Security Framework on 31 July 2026 (see repo-root `CLAUDE.md`
  principle 8 and `governance/control_library/rbi_2026_directions.yaml`).
- **SEBI** — Cybersecurity and Cyber Resilience Framework (CSCRF) and Cyber
  Capability Index (CCI), for regulated market infrastructure and
  intermediaries.
- **CIS Controls / NIST CSF / ISO 27001** — used as general-purpose control
  baselines alongside the India-specific frameworks above.

TODO: confirm which entity type(s) (bank, NBFC, payment system operator,
market infrastructure institution, etc) the hackathon demo/target
organization falls under, since RBI's Directions and SEBI's CSCRF are
entity-specific rather than uniform.

## Relationship to `docs/ASSUMPTIONS.md`

Because the rupee figure depends on modelling constants that aren't yet
calibrated to any real organization's loss history (see
`core/assumptions.py`), `docs/ASSUMPTIONS.md` exists as the honesty
artifact: every assumption, its justification, and what it would take to
calibrate it properly. Any demo or evaluation of this system should be read
alongside that document, not the headline number alone.

## Where the project stands (2026-09-26)

Working end to end on real sandbox data: six connectors feed a daily pipeline that passes five quality
gates, commits an immutable snapshot, and publishes it to S3. The engine turns each snapshot into an
Expected Annual Loss and Value at Risk, and the dashboard shows real figures on every page. Hosting the API
and dashboard (Render/Fly and Vercel) is configured in the repo but not yet deployed.

Read next, in this order:

- `docs/BUILD_LOG.md` — what was built, why, what broke, and what is still open.
- `docs/CONNECTORS.md` — the connector catalog with honest Live / Ready / Planned status.
- `docs/OPERATIONS.md` — the pipeline, hosting, cost, shutdown and rebuild runbooks.
- `docs/DASHBOARD_WIRING.md` — which page reads which endpoint, and what was verified.
- `docs/ASSUMPTIONS.md` — every modelling constant and how far it is from calibrated.

The rupee figure is still driven largely by placeholder assumptions; treat it as a demonstration of the
method, and read it alongside `docs/ASSUMPTIONS.md`.
