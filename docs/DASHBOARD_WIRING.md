# Dashboard ↔ API wiring

What each dashboard page reads from the backend, what was verified against **real data**, and how to run
the two together. The dashboard never imports Python and never computes a figure: everything comes over
HTTP from `interfaces/api`, through one layer (`interfaces/dashboard/src/lib/api.ts`).

Written for: engineers working on the dashboard or the API, and anyone checking that what the screens show is
real. Verified on **2026-09-26** against the live snapshot `sha256:1993a3c…` (55 assets, 215 open findings, 4
services; Wazuh, Greenbone, Prowler, IAM and CMDB reporting).

## How the data layer behaves

Every call returns `ok`, `unavailable` or `error`:

- `ok`: the backend computed and returned data.
- `unavailable`: HTTP 404, 409 or 501 (no snapshot yet, or the computation cannot run). It renders as an
  explanatory state, never as a zero or a dash.
- `error`: the API was unreachable or rejected the request.

Requests use `cache: "no-store"`, so a figure always tracks the current snapshot. All six pages are
server-rendered on every request. `NEXT_PUBLIC_DEMO_MODE=1` swaps in labelled sample data (banner plus `SAMPLE`
tags); leave it unset for anything real.

## Page → endpoint map

| Page | Server-side reads | Browser-side calls |
|---|---|---|
| `/` Overview | `/exposure`, `/exposure/history`, `/exposure/exceedance`, `/snapshot`, `/assets`, `/optimize/candidates` | the chat panel (`/chat/stream`) |
| `/assets` | `/assets` | none |
| `/attack-paths` | `/attack-graph`, `/assets` | `/attack-graph/targets/{asset_id}` when a node is opened |
| `/compliance` | `/frameworks`, `/frameworks/{framework}/status`, `/assets` | none |
| `/data-quality` | `/snapshot`, `/snapshot/gates`, `/assets` | none |
| `/investment` | `/optimize/plan`, `/optimize/candidates`, `/assets` | `POST /optimize` (budgeted plan), `POST /simulate` (what-if) |

`/assumptions` and the signed-link routes (`/snapshots`, `/snapshots/{id}/download-url`) are served but no page
calls them yet. The browser-side calls need the API reachable from the user's browser and the dashboard's
origin in `CORS_ALLOWED_ORIGINS`.

## What was verified

Every GET returned 200 with real data, and all six pages rendered with **no unavailable, error or sample-data
state**. Spot checks against the API's own numbers: the overview's expected annual loss `₹13,07,54,303` equals the
API's `130,754,302` (10,000 simulated years); the data-quality page shows the real scanner coverage (five
reporting, ScoutSuite not reporting in this snapshot) and the 5 of 5 quality gates.

Browser-initiated calls, sent with the dashboard's `Origin` header:

| Call | Result |
|---|---|
| `POST /simulate` (two controls, jointly) | 200 in under a second; baseline vs hypothetical from one joint re-simulation |
| `POST /optimize` (₹20 lakh budget, 10 candidates) | 200 in under a second; risk reduction from joint simulation |
| `GET /optimize/plan` | 200 |
| CORS preflight (`OPTIONS /simulate`) | 200; origin and `GET, POST, DELETE, OPTIONS` allowed |
| `POST /chat` with no LLM key | 503 with a clear message; the UI treats this as "not configured", not a failure |
| `GET /attack-graph/targets/{asset}` | 409 for every asset (see the attack graph below) |

## Data states you will see (all correct, none are wiring faults)

- **Attack graph is empty.** `topology_declared: false`, 0 segments, 0 edges. No connector supplies
  `network_topology` or `assets[].network.segment_id` yet, and the engine deliberately reports "unknown, not
  unreachable". Per-asset target calls return 409 with that explanation. To make the page meaningful, a source
  of real segmentation is needed (AWS subnets and security-group rules can supply it).
- **Compliance has no scores.** Most controls are `unknown` (nothing in the telemetry can prove them) and only 3–4
  per framework are `not_met`; the weighted score is null because the control library carries no weights. The
  DPDP library currently has 0 controls and SEBI has 4.
- **Chat needs `GROQ_API_KEY`** on the API host; without it the panel reports the assistant as unavailable.
- **Overview and history:** exposure history re-simulates every committed snapshot on each request (about 0.1 s
  each). Fine for a few snapshots; if history grows into the dozens, cache the figure per `snapshot_id`
  (snapshots are immutable and the seed is derived from content, so this is safe).

## Running the API and dashboard together locally

```bash
# 1. A real snapshot store (or point at data/snapshots)
aws s3 sync s3://loanease-raw-findings-f00321/snapshots/ /tmp/suraksha-store --profile loanease-sandbox

# 2. API (Linux/WSL: history files are named sha256:<hash>.json, which Windows cannot create)
SNAPSHOT_STORE_PATH=/tmp/suraksha-store CORS_ALLOWED_ORIGINS=http://localhost:3000 \
  uvicorn --factory interfaces.api.app:create_app --port 8000

# 3. Dashboard: use the production build
cd interfaces/dashboard
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run build
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm start        # http://localhost:3000
```

Notes:

- `NEXT_PUBLIC_API_BASE_URL` is inlined **at build time**; rebuild after changing it (also on Vercel).
- **`next dev` (Turbopack) returned HTTP 500 on every page in the Windows setup we tested**, from a Turbopack
  Google-font loader error, although Google Fonts is reachable. The production build (`next build`) succeeds and
  type-checks, so use build + start, and Vercel is unaffected.
- On Windows-to-WSL2, `localhost` can add about 2 s per request (IPv6 tried first). Use `127.0.0.1` for the API
  URL when testing.
- `npm ci` may fail to spawn `cmd.exe` in some shells; `npm ci --ignore-scripts` is enough for build and lint.

## Checklist before pointing a hosted dashboard at a hosted API

1. `GET https://<api>/health` returns `{"status":"ok"}`.
2. `GET https://<api>/health/snapshot-sync` shows `last_error: null` and a recent `last_success_at`.
3. `GET https://<api>/snapshot` returns the expected `snapshot_id` and `observed_at`.
4. `CORS_ALLOWED_ORIGINS` contains the dashboard's exact origin (no trailing slash).
5. `NEXT_PUBLIC_API_BASE_URL` on Vercel is the API's `https://` URL and was set before the build.
6. Open every page once; open one what-if and one optimizer run to prove the browser-side calls work.
7. The overview's provenance strip shows the snapshot's age (added in this work; it flags a snapshot older than
   36 hours as stale).
