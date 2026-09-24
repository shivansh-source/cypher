# `interfaces/dashboard/`

The Su₹aksha frontend: a Next.js 16 App Router app (TypeScript, plain CSS)
that renders the rupee figures produced by `core/` and the compliance status
produced by `governance/`. Its design — shell, tokens, cards, charts, the Ask
Suraksha modal — is ported from the standalone prototype in
`interfaces/prototype/`, with one fundamental difference: the prototype runs
its own engine in the browser on sample data, and this app never computes a
figure. Everything it shows arrives from the API.

It talks to the backend **only over HTTP**, through `interfaces/api/app.py`.
It never imports a Python module, and no Python module imports anything from
here (repo-root `CLAUDE.md`, module ownership map).

```
npm install
npm run dev     # http://localhost:3000
npm run build
npm run lint    # Next 16 no longer runs the linter during `next build`
```

Point it at the API with `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000`, see `.env.example`). The what-if lab, the optimizer
and the assistant call the API from the browser, so the API must be reachable
from the browser at that URL and its `CORS_ALLOWED_ORIGINS` must include this
app's origin (the default, `http://localhost:3000`, does).

## What this dashboard is for

The product is the rupee figure, and the repo exists to *defend that figure
under scrutiny*. So this is a defensibility instrument, not a score card.
Every screen is built so that a number never appears without the context
needed to challenge it:

| Route | Answers | Sourced from |
|---|---|---|
| `/` | What does a year of cyber risk cost, what does a bad year look like, how has it moved, what drives it, and what if we changed a control? | `/exposure`, `/exposure/history`, `/exposure/exceedance`, `/assets`, `/simulate` |
| `/assets` | Which assets and findings carry the loss, and what FAIR parameters produced each figure? | `/assets` |
| `/investment` | Where does a finite budget buy the most risk reduction? | `/optimize/candidates`, `POST /optimize` |
| `/compliance` | Control-by-control status against each framework, and the statutory penalty ceilings behind it | `/frameworks`, `/frameworks/{framework}/status` |
| `/data-quality` | Do the figures rest on data worth trusting, what is the data blind to, and which assumptions are they built on? | `/snapshot`, `/snapshot/gates`, `/assumptions` |

The sidebar's snapshot card (`/snapshot`, `/snapshot/gates`) and the Ask
Suraksha assistant (`POST /chat`) are on every page.

Design rules the UI enforces, each tracing to a principle in the repo-root
`CLAUDE.md`:

- **No figure computed here.** The page components only format, rank and
  lay out what the API returned. Totals, changes and per-asset roll-ups come
  from `core/` (`expected_annual_loss_by_asset`, `compare_hypothetical`,
  `recommend_portfolio`); the only arithmetic here is shares of a total and
  chart geometry. The prototype's panels that needed an in-browser engine —
  the 8-week forecast, accrued loss, sensitivity tornado, lab efficacy, the
  1,024-portfolio frontier — are not ported, because the backend has no
  source for them.
- **No figure without provenance.** Every figure sits beside the
  `snapshot_id` it came from, when that snapshot was observed, the Monte Carlo
  iteration count, and the VaR percentile actually used. If a snapshot is
  committed while a page loads and its panels disagree, the page says so.
- **Compact figures are always paired with the exact value**, so a rounded
  headline is never the only figure on screen.
- **No bottom line without its drivers.** The headline EAL is shown with the
  engine's ranked contributors and how much of the total they account for.
- **Unmeasured is not clean.** When a scanner did not report, pages carrying
  a figure show a coverage caveat. An unknown control posture renders as
  unknown, never as protected, and an asset with no open finding reads
  "not modelled", never ₹0.
- **What-ifs compare against their own baseline.** `/simulate` and
  `/optimize` re-simulate the baseline on the same random draws as the
  hypothetical, so their baseline can differ slightly from the headline EAL;
  the UI shows that baseline and says why.
- **Benefit is never summed.** `/investment` presents `risk_reduction_inr`
  exactly as the optimizer's joint re-simulation returned it (principle 7).
  Candidate costs are typed in by the user — the system has no cost
  catalogue, and unpriced candidates are left out rather than guessed.
- **No collapsed compliance verdict.** `/compliance` reports each control's own
  status and never derives an overall "compliant" judgement. `unknown` and
  `expired_attestation` get their own non-green treatments. A weighted score is
  shown only with its coverage and low-confidence share (principle 6).
  Penalty ceilings are labelled as statutory maxima, never expected losses.
- **The assistant never shows unverified text.** Ask Suraksha uses the
  non-streaming `POST /chat`, whose `text` has already been through
  `ai.numeric_guard`, renders it verbatim, and highlights every
  `[UNVERIFIED: …]` flag. The tools it called are one click away.

## Missing figures are a first-class state

Every API call returns a discriminated `ApiResult` (`ok` / `unavailable` /
`error`, see `src/lib/api.ts`), and the UI renders an explicit explanation —
the API's own `detail` — of why there is no figure and what would produce one.
A missing figure is never rendered as a zero, an em dash, an unresolving
spinner, or a remembered previous value. With no committed snapshot or no
backend running, the dashboard renders no rupee risk figures at all.

### Demo mode

Setting `NEXT_PUBLIC_DEMO_MODE=1` (read at build time) serves the fixtures in
`src/lib/demo-data.ts` so the interface can be developed and demonstrated
offline. In that mode a persistent, non-dismissible `SAMPLE DATA` banner
renders on every page and every panel and headline figure carries a `SAMPLE`
tag. The what-if lab, the optimizer and the assistant are not faked: they
report that they need the live backend. None of that data came from the
engine and none of it may be cited as a result.

## Backend endpoint contract

Response shapes are mirrored in `src/lib/types.ts`; the full endpoint list is
in `interfaces/api/README.md`.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/exposure` | `RiskFigure` |
| `GET` | `/exposure/history` | `ExposureHistory` |
| `GET` | `/exposure/exceedance` | `LossExceedanceCurve` |
| `GET` | `/snapshot` | `SnapshotProvenance` |
| `GET` | `/snapshot/gates` | `GateReport` |
| `GET` | `/assets` | `AssetsResponse` |
| `GET` | `/frameworks` | `FrameworkSummary[]` |
| `GET` | `/frameworks/{framework}/status` | `FrameworkStatus` |
| `GET` | `/optimize/candidates` | `ControlCandidates` |
| `POST` | `/optimize` | `PortfolioRecommendation` |
| `POST` | `/simulate` | `HypotheticalComparison` |
| `GET` | `/assumptions` | `AssumptionEntry[]` |
| `POST` | `/chat` | `ChatResponse` (503 = assistant not configured) |

The API answers **404** when no snapshot has been committed and **501** when a
computation cannot run yet; the dashboard reads 404/409/501 as "nothing to
show" and renders the honest empty state. Any other non-2xx is surfaced as an
error, with the API's `detail`.

## Conventions

- `AGENTS.md` in this directory is generated by `next dev` and carries the
  Next.js version's own agent rules — read `node_modules/next/dist/docs/`
  before changing framework-level code.
- Pages are Server Components and fetch with `cache: "no-store"`, so every
  data route is rendered per request and a figure always tracks the current
  committed snapshot. Interactive panels (`WhatIf`, `InvestmentPlanner`,
  `AskSuraksha`, the charts, the sidebar) are Client Components; a helper
  a Server Component needs belongs in `src/lib/`, never in a `"use client"`
  module.
- Route props use the Next 16 generated `PageProps<'/route'>` / `LayoutProps`
  globals. Run `npx next typegen` after adding a route.
- Styles live in `src/app/globals.css`, one section per prototype stylesheet.
  Light and dark palettes follow the operating system. Semantic colour is
  reserved for status, so red on this screen always means "worse".
