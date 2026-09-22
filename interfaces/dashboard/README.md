# `interfaces/dashboard/`

The Su₹aksha frontend: a Next.js 16 App Router app (TypeScript, Tailwind v4)
that renders the rupee figures produced by `core/` and the compliance status
produced by `governance/`.

It talks to the backend **only over HTTP**, through `interfaces/api/app.py`.
It never imports a Python module, and no Python module imports anything from
here (repo-root `CLAUDE.md`, module ownership map).

```
npm install
npm run dev     # http://localhost:3000
npm run build
npm run lint    # Next 16 no longer runs the linter during `next build`
```

## What this dashboard is for

The product is the rupee figure, and the repo exists to *defend that figure
under scrutiny*. So this is a defensibility instrument, not a score card.
Every screen is built so that a number never appears without the context
needed to challenge it:

| Route | Answers | Sourced from |
|---|---|---|
| `/` | What is a year of cyber risk expected to cost, what does a bad year look like, and what drives it? | `core.engine.compute_risk_figure` |
| `/investment` | Where does a finite budget buy the most risk reduction? | `core.optimizer.recommend_portfolio` |
| `/compliance` | Control-by-control status against each framework | `governance.mapper` |
| `/data-quality` | Do the figures rest on data worth trusting, and what is the data blind to? | `core.snapshot` + `scan_scope` |

Design rules the UI enforces, each tracing to a principle in the repo-root
`CLAUDE.md`:

- **No figure without provenance.** Every rupee amount is accompanied by the
  `snapshot_id` it came from, when that snapshot was observed, the Monte Carlo
  iteration count, and the VaR percentile actually used (not the one currently
  configured).
- **No bottom line without its drivers.** The headline EAL is always shown
  with the ranked loss-event contributors, and with how much of the total they
  account for, so the tail is visibly part of the figure rather than missing
  from it.
- **Unmeasured is not clean.** When a scanner did not report for a snapshot,
  every page carrying a figure shows a coverage caveat. Absence of a finding
  from a scanner that never ran is never presented as remediation.
- **No collapsed compliance verdict.** `/compliance` reports each control's own
  status and never derives an overall "compliant" judgement. `unknown` and
  `expired_attestation` get their own non-green treatments rather than being
  folded in with `met`. The weighted score is always shown with its coverage
  fraction and its low-confidence share (principle 6).
- **Benefit is never summed.** `/investment` presents `risk_reduction_inr`
  exactly as the optimizer's joint re-simulation returned it, and says so on
  screen (principle 7).

## Missing figures are a first-class state

`core/engine.py` can compute a real figure today given a snapshot (see
repo-root `README.md` and `docs/ASSUMPTIONS.md`), and `interfaces/api/app.py`
now registers `/exposure` and `/optimize` routes — but those routes
delegate through `ai/tools/` wrappers and `core/snapshot.py`'s
current-committed-snapshot lookup, both still unimplemented, so calling
either route errors rather than returning a figure. There is currently no
real number to display. Rather than filling that gap, every API call
returns a discriminated `ApiResult` (`ok` / `unavailable` / `error`, see
`src/lib/api.ts`) and the UI renders an explicit explanation of why there
is no figure and what would produce one.

A missing figure is never rendered as a zero, an em dash, an unresolving
spinner, or a remembered previous value — any of which a reader could mistake
for a result. With no backend running, the dashboard renders no rupee figures
at all.

### Demo mode

Setting `NEXT_PUBLIC_DEMO_MODE=1` serves the fixtures in `src/lib/demo-data.ts`
so the interface can be developed and demonstrated offline. In that mode a
persistent, non-dismissible `SAMPLE DATA` banner renders on every page and
every figure carries a `SAMPLE` tag — deliberately impossible to suppress, so
a screenshot cannot lose the disclaimer. None of that data came from the
engine and none of it may be cited as a result.

## Backend endpoint contract

The dashboard expects these endpoints from `interfaces/api/app.py`. `/exposure`
and `/optimize` are now registered there, but error today because their
backing tools (`ai/tools/get_exposure.py`, `ai/tools/optimize_investment.py`,
and `core/snapshot.py`'s current-snapshot lookup) are still unimplemented;
the remaining three routes below don't exist at all yet. This table is the
contract to implement against, and the response shapes are mirrored in
`src/lib/types.ts`.

| Method | Path | Returns | Backing tool |
|---|---|---|---|
| `GET` | `/exposure` | `RiskFigure` | `ai.tools.get_exposure` |
| `GET` | `/optimize?budget_inr=<number>` | `PortfolioRecommendation` | `ai.tools.optimize_investment` |
| `GET` | `/frameworks/{framework}/status` | `FrameworkStatus` | `ai.tools.get_framework_status` |
| `GET` | `/snapshot` | `SnapshotProvenance` | `core.snapshot` |
| `GET` | `/snapshot/gates` | `GateResult[]` | `core.snapshot.validate_snapshot` |

Return **501** (or 404/409) when there is no figure to give — no committed
snapshot, or the engine has not run. The dashboard reads those statuses as
"nothing to show" and renders the honest empty state; any other non-2xx is
surfaced as a transport error.

## Conventions

- `AGENTS.md` in this directory is generated by `next dev` and carries the
  Next.js version's own agent rules — read `node_modules/next/dist/docs/`
  before changing framework-level code.
- Pages are Server Components and fetch with `cache: "no-store"`; a risk figure
  must always track the current committed snapshot.
- Route props use the Next 16 generated `PageProps<'/route'>` / `LayoutProps`
  globals. Run `npx next typegen` after adding a route.
- The theme is a single fixed dark palette (`src/app/globals.css`). Semantic
  colour is reserved for status, so red on this screen always means "worse".
