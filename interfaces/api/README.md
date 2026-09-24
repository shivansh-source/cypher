# `interfaces/api/`

The FastAPI backend. Every route is a thin adapter over `core/`,
`governance/` and `ai/` — no route computes a risk figure, maps a control, or
talks to an LLM on its own.

```
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn --factory interfaces.api.app:create_app --reload --port 8000
```

Configuration comes from the environment (see the repo-root `.env.example`):
`CORS_ALLOWED_ORIGINS`, `GROQ_API_KEY`, `GROQ_MODEL`,
`CHAT_SESSION_TTL_MINUTES`, `CHAT_MAX_SESSIONS`, `CHAT_MAX_TOOL_ITERATIONS`.

## The chat assistant

`POST /chat` answers natural-language questions about the infrastructure by
letting the model call the tools in `ai/tools/`. The model does exactly two
things (repo-root `CLAUDE.md` principle 2): it picks the tools, and it
narrates what they returned. It never produces a figure.

One turn runs as: `ai.chat.ChatEngine` sends the conversation plus the tool
catalogue from `ai.tool_registry` → the model calls tools → each call goes
through `ai.tool_registry.execute_tool`, which records every number the tool
produced → the model narrates → `ai.numeric_guard.guard_narration` checks
every number in that prose against those recorded numbers → the checked text
is what the route returns. Up to `CHAT_MAX_TOOL_ITERATIONS` round trips per
turn.

### What the guard does to a reply

`text` is never the model's raw output. Any number the guard could not trace
to a real tool result in this conversation is flagged inline:

```
Expected annual loss is [UNVERIFIED: ₹4.2 crore] for the current estate.
```

**Render `text` verbatim, flags included.** `all_claims_verified` tells you
whether any flag is present, and `unverified_claims` lists the exact
substrings. A flag is not a rendering bug — it is the assistant telling the
reader that a number in the sentence did not come from the engine. Ground
truth is per-session and cumulative, so a follow-up may restate a figure
computed in an earlier turn of the same conversation.

### Sessions

Send `session_id` to continue a conversation; omit it to start one. The
response's `session_id` is always the one to send next — an unknown or
expired id yields a *new* session rather than an error, so a client can tell
its history did not survive. Sessions live in the API process's memory only:
they are lost on restart and are not shared between workers. Run one worker,
or put a shared store behind `ai.sessions.InMemorySessionStore`'s interface.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | `{"status": "ok"}` |
| `POST` | `/chat` | A complete, guarded turn (below) |
| `POST` | `/chat/stream` | The same turn as Server-Sent Events |
| `GET` | `/chat/tools` | Every tool, with whether it can answer today |
| `DELETE` | `/chat/sessions/{session_id}` | Discards that conversation |
| `GET` | `/exposure?scope=` | `RiskFigure` for the current snapshot (via `ai.tools.get_exposure`) |
| `GET` | `/exposure/history` | `RiskFigure` for every committed snapshot, oldest first |
| `GET` | `/exposure/exceedance` | Loss exceedance curve, read off the same simulation as `/exposure` |
| `GET` | `/snapshot` | Current snapshot's provenance: ids, bitemporal fields, `scan_scope`, counts |
| `GET` | `/snapshot/gates` | The five quality gates, re-run on the current snapshot and its predecessor |
| `GET` | `/assets` | Every asset: posture, findings, and each open finding's FAIR parameters and EAL |
| `GET` | `/frameworks` | Every control library in force, with its statutory penalty ceilings |
| `GET` | `/frameworks/{framework}/status` | Control-by-control status and weighted score (via `ai.tools.get_framework_status`) |
| `POST` | `/simulate` | What-if: joint re-simulation of hypothetical controls (via `ai.tools.simulate_scenario`) |
| `GET` | `/optimize/candidates` | Control gaps the optimizer can close — no cost, no benefit |
| `POST` | `/optimize` | `PortfolioRecommendation` over candidates whose costs the caller declares |
| `GET` | `/optimize?budget_inr=` | `optimize_investment` tool — 501: no candidate-cost catalogue exists |
| `GET` | `/assumptions` | Every constant in `core/assumptions.py`, live, with its documented rationale |

`404` means no snapshot has been committed yet; `501` means the computation
cannot run yet; both carry a `detail` saying why, and neither is ever a zero.
`400` is a request the engine rejected (unknown asset, a control category the
optimizer cannot apply). The routes behind the dashboard live in
`dashboard_routes.py`; like every route here they only load the snapshot,
call into `core/`/`governance/`/`ai.tools`, and reshape the result.

**Baselines differ on purpose.** `/simulate` and `/optimize` compare against a
baseline re-simulated on the *same random draws* as the hypothetical (common
random numbers, `core.optimizer.evaluate_portfolio`), so their baseline EAL can
differ slightly from `/exposure`'s. Compare a what-if against its own baseline.

### `POST /chat`

```jsonc
// request
{ "message": "what is driving our exposure?", "session_id": "0f3c…" }

// response
{
  "session_id": "0f3c…",
  "text": "No exposure figure has been computed yet. …",
  "all_claims_verified": true,
  "unverified_claims": [],
  "tool_calls": [
    {
      "tool_name": "get_exposure",
      "arguments": {},
      "status": "unavailable",
      "detail": "No snapshot has been committed yet, so the FAIR + Monte Carlo engine…",
      "result": null
    }
  ],
  "model": "llama-3.3-70b-versatile",
  "stop_reason": "end_turn"
}
```

`status` on a tool call is `ok`, `unavailable` (the underlying computation
does not exist yet) or `error` (it exists and failed). `stop_reason` is the
provider's, except `max_tool_iterations`, which is this backend stopping a
turn that kept calling tools without answering.

`503` means the assistant is not configured (no `GROQ_API_KEY`, SDK not
installed); `502` means the provider call failed.

### `POST /chat/stream`

Same request body. Responds `text/event-stream`, with named events:

| Event | Payload | Meaning |
|---|---|---|
| `session` | `{session_id}` | First event, always |
| `text_delta` | `{text}` | Raw, **unverified** model text |
| `tool_call` | `{tool_name, arguments}` | A tool is about to run |
| `tool_result` | `{tool_name, status, detail}` | How it went |
| `final` | The `POST /chat` body, plus `text_replaced` | The verified answer |
| `error` | `{error, message}` | The turn failed |

Every stream ends with exactly one `final` or one `error`.

**`text_delta` is not the answer.** Those deltas are the model's raw output,
streamed before anything has been checked. When `final.text_replaced` is
true, the guard changed the text and the client must repaint from
`final.text`. A client that paints deltas and ignores `final` will show
unverified numbers — the one failure mode this design exists to prevent.

### `GET /chat/tools`

Lists each tool with its schema, `available`, and `unavailable_reason`, so a
client can say what the assistant cannot yet do without having to ask it.

## Adding a tool

Add a `ToolSpec` to `ai/tool_registry.py` pointing at a wrapper in
`ai/tools/`. The chat loop, the classifier and `/chat/tools` all read that
registry — nothing in `ai/chat.py` or this module knows about any individual
tool, and nothing should be taught to.
