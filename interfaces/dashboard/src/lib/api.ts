/**
 * The dashboard's only channel to the backend: HTTP against `interfaces/api`.
 *
 * The dashboard never imports a Python module and never computes a risk figure
 * of its own (repo-root CLAUDE.md, principles 1 and 2, and the module
 * ownership map). Everything it displays either arrived from an endpoint here
 * or is explicitly labelled sample data.
 *
 * Every call returns an {@link ApiResult} rather than throwing or returning a
 * bare value. That is deliberate: "the engine has not produced a figure" is a
 * normal state of this system, not an error to be swallowed, and it must reach
 * the UI as its own case so a missing figure can never be rendered as a zero,
 * a dash, or a stale number.
 *
 * The same functions run in Server Components (page loads) and in Client
 * Components (what-if, optimizer, chat), so the API must be reachable at
 * `NEXT_PUBLIC_API_BASE_URL` from both the Next server and the browser, and
 * its `CORS_ALLOWED_ORIGINS` must include the dashboard's origin.
 */

import { demoResult, demoUnavailable } from "./demo-data";
import { parseSseFrames } from "./sse";
import type {
  AssetsResponse,
  AttackGraphResponse,
  AttackGraphTarget,
  AssumptionEntry,
  ChatResponse,
  ChatStreamFinal,
  ChatToolCallEvent,
  ChatToolResultEvent,
  Control,
  ControlCandidates,
  ExposureHistory,
  FrameworkStatus,
  FrameworkSummary,
  GateReport,
  HypotheticalComparison,
  LossExceedanceCurve,
  PortfolioRecommendation,
  PriorityPlan,
  RiskFigure,
  SnapshotProvenance,
} from "./types";

/**
 * Outcome of one backend call.
 *
 * - `ok` — the backend returned data computed by `core/` / `governance/`.
 * - `unavailable` — the backend answered, but there is nothing to give (no
 *   committed snapshot, or the computation cannot run yet). Not a failure; a
 *   truthful "nothing to show".
 * - `error` — the backend could not be reached, rejected the request, or
 *   answered unusably.
 */
export type ApiResult<T> =
  | { state: "ok"; data: T }
  | { state: "unavailable"; reason: string }
  | { state: "error"; reason: string; transport?: boolean };

/**
 * Whether the UI is showing illustrative sample data instead of engine output.
 *
 * Off unless `NEXT_PUBLIC_DEMO_MODE=1`. When on, every page renders a
 * persistent banner and every figure a `SAMPLE` tag — see
 * `src/lib/demo-data.ts` for why this exists and what it must never be used
 * for.
 */
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * HTTP statuses that mean "nothing to show", as distinct from "the request
 * failed". The API answers 404 when no snapshot has been committed and 501
 * when a computation cannot run yet; 409 is reserved for "engine has not run
 * against it".
 */
const NO_FIGURE_STATUSES = new Set([404, 409, 501]);

/** The API's own explanation from a FastAPI error body, if it sent one. */
async function readDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        // FastAPI request-validation errors: [{loc, msg, ...}, ...]
        return detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : JSON.stringify(item),
          )
          .join("; ");
      }
    }
  } catch {
    // Not JSON — fall through to the status-only message.
  }
  return null;
}

async function request<T>(
  path: string,
  init: { method?: "GET" | "POST" | "DELETE"; body?: unknown } = {},
  unavailableStatuses: ReadonlySet<number> = NO_FIGURE_STATUSES,
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method ?? "GET",
      // A risk figure must never be served from a cache: the whole point of
      // the snapshot lifecycle is that the current figure tracks the current
      // committed snapshot.
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch (cause) {
    return {
      state: "error",
      transport: true,
      reason: `Could not reach the Su₹aksha API at ${API_BASE_URL}${path} (${
        cause instanceof Error ? cause.message : "unknown transport error"
      }).`,
    };
  }

  if (unavailableStatuses.has(response.status)) {
    const detail = await readDetail(response);
    return {
      state: "unavailable",
      reason: detail ?? `The API has nothing for ${path} yet (HTTP ${response.status}).`,
    };
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    return {
      state: "error",
      reason: `${path} returned HTTP ${response.status}${detail ? `: ${detail}` : "."}`,
    };
  }

  try {
    return { state: "ok", data: (await response.json()) as T };
  } catch {
    return { state: "error", reason: `${path} returned a non-JSON body.` };
  }
}

/**
 * Current Expected Annual Loss and Value at Risk for the whole estate.
 *
 * Backed by `ai.tools.get_exposure` -> `core.engine.compute_risk_figure`. The
 * returned `top_contributors` are the engine's own ranking and are never
 * re-sorted here.
 */
export async function fetchExposure(): Promise<ApiResult<RiskFigure>> {
  if (DEMO_MODE) return demoResult("exposure");
  return request<RiskFigure>("/exposure");
}

/** The engine's figure for every committed snapshot, oldest first. */
export async function fetchExposureHistory(): Promise<ApiResult<ExposureHistory>> {
  if (DEMO_MODE) return demoResult("history");
  return request<ExposureHistory>("/exposure/history");
}

/** The current snapshot's loss exceedance curve (`core.engine`). */
export async function fetchLossExceedance(): Promise<ApiResult<LossExceedanceCurve>> {
  if (DEMO_MODE) return demoResult("exceedance");
  return request<LossExceedanceCurve>("/exposure/exceedance");
}

/** Provenance of the currently committed snapshot every figure derives from. */
export async function fetchSnapshotProvenance(): Promise<ApiResult<SnapshotProvenance>> {
  if (DEMO_MODE) return demoResult("provenance");
  return request<SnapshotProvenance>("/snapshot");
}

/** The five quality gates, re-run on the current snapshot and its predecessor. */
export async function fetchQualityGates(): Promise<ApiResult<GateReport>> {
  if (DEMO_MODE) return demoResult("gates");
  return request<GateReport>("/snapshot/gates");
}

/** Every asset with its posture, findings and the engine's FAIR parameters. */
export async function fetchAssets(): Promise<ApiResult<AssetsResponse>> {
  if (DEMO_MODE) return demoResult("assets");
  return request<AssetsResponse>("/assets");
}

/** Every versioned control library in force, with its statutory penalty ceilings. */
export async function fetchFrameworks(): Promise<ApiResult<FrameworkSummary[]>> {
  if (DEMO_MODE) return demoResult("frameworks");
  return request<FrameworkSummary[]>("/frameworks");
}

/**
 * Control-by-control status against one regulatory framework.
 *
 * Backed by `ai.tools.get_framework_status` -> `governance.mapper`. The
 * dashboard renders each control's own status and never collapses them into a
 * single compliant/non-compliant verdict (principle 6).
 */
export async function fetchFrameworkStatus(
  framework: string,
): Promise<ApiResult<FrameworkStatus>> {
  if (DEMO_MODE) return demoResult("frameworkStatus", framework);
  return request<FrameworkStatus>(`/frameworks/${encodeURIComponent(framework)}/status`);
}

/** Control gaps the optimizer can close — no cost, no benefit attached. */
export async function fetchControlGaps(): Promise<ApiResult<ControlCandidates>> {
  if (DEMO_MODE) return demoResult("candidates");
  return request<ControlCandidates>("/optimize/candidates");
}

/** Every candidate change, ordered by how much each cuts loss given the ones before it. */
export async function fetchPriorityPlan(): Promise<ApiResult<PriorityPlan>> {
  if (DEMO_MODE) return demoUnavailable("the priority plan");
  return request<PriorityPlan>("/optimize/plan");
}

/** The attack graph's segments, directed segment links, and every asset's routes in. */
export async function fetchAttackGraph(): Promise<ApiResult<AttackGraphResponse>> {
  if (DEMO_MODE) return demoUnavailable("the attack graph");
  return request<AttackGraphResponse>("/attack-graph");
}

/** One asset's bounded subgraph, simulated with every entry point attacked at once. */
export async function fetchAttackGraphTarget(
  assetId: string,
): Promise<ApiResult<AttackGraphTarget>> {
  if (DEMO_MODE) return demoUnavailable("attack graph inference");
  return request<AttackGraphTarget>(`/attack-graph/targets/${encodeURIComponent(assetId)}`);
}

/** Every constant in core/assumptions.py with its documented rationale. */
export async function fetchAssumptions(): Promise<ApiResult<AssumptionEntry[]>> {
  if (DEMO_MODE) return demoResult("assumptions");
  return request<AssumptionEntry[]>("/assumptions");
}

/**
 * A what-if: one joint re-simulation of the controls applied together, against
 * a baseline on the same random draws (`ai.tools.simulate_scenario`).
 */
export async function simulateScenario(
  controls: Pick<
    Control,
    "control_id" | "control_category" | "affected_asset_ids" | "finding_id" | "service_id"
  >[],
): Promise<ApiResult<HypotheticalComparison>> {
  if (DEMO_MODE) return demoUnavailable("what-if simulation");
  return request<HypotheticalComparison>("/simulate", {
    method: "POST",
    body: { hypothetical_controls: controls },
  });
}

/**
 * A budget-constrained portfolio recommendation over declared-cost candidates.
 *
 * Backed by `core.optimizer.recommend_portfolio`. The `risk_reduction_inr` in
 * the response comes from the optimizer's joint re-simulation; the dashboard
 * displays it as given and never derives its own benefit figure by summing
 * per-control deltas (principle 7).
 */
export async function recommendPortfolio(
  budgetInr: number,
  candidates: Control[],
): Promise<ApiResult<PortfolioRecommendation>> {
  if (DEMO_MODE) return demoUnavailable("portfolio optimization");
  return request<PortfolioRecommendation>("/optimize", {
    method: "POST",
    body: { budget_inr: budgetInr, candidate_controls: candidates },
  });
}

/** 503: the assistant is not configured (no LLM key) — nothing to show, not a failure. */
const CHAT_UNAVAILABLE_STATUSES = new Set([503]);

/**
 * One assistant turn. The response `text` has already been through
 * `ai.numeric_guard` on the server; render it verbatim, flags included.
 */
export async function sendChat(
  message: string,
  sessionId: string | null,
): Promise<ApiResult<ChatResponse>> {
  if (DEMO_MODE) return demoUnavailable("the Ask Suraksha assistant");
  return request<ChatResponse>(
    "/chat",
    { method: "POST", body: { message, session_id: sessionId } },
    CHAT_UNAVAILABLE_STATUSES,
  );
}

/** Progress callbacks for {@link streamChat}. */
export interface ChatStreamHandlers {
  /** A tool is about to run. */
  onToolCall?: (event: ChatToolCallEvent) => void;
  /** A tool finished; match it to its call by `tool_use_id`. */
  onToolResult?: (event: ChatToolResultEvent) => void;
  /**
   * The model is producing prose. Deliberately carries no text: the streamed
   * deltas are unverified, so the UI only learns *that* an answer is being
   * written, never what it says, until the guarded `final` arrives.
   */
  onComposing?: () => void;
}

/**
 * One assistant turn over `POST /chat/stream`, reporting tool calls live.
 *
 * Resolves with the `final` event — whose `text` has been through
 * `ai.numeric_guard` — or with the reason the turn failed. `text_delta`
 * payloads are dropped here on purpose (see {@link ChatStreamHandlers}), so
 * unverified model output can never reach the screen through this function.
 */
export async function streamChat(
  message: string,
  sessionId: string | null,
  handlers: ChatStreamHandlers = {},
): Promise<ApiResult<ChatStreamFinal>> {
  if (DEMO_MODE) return demoUnavailable("the Ask Suraksha assistant");
  const path = "/chat/stream";
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      cache: "no-store",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  } catch (cause) {
    return {
      state: "error",
      transport: true,
      reason: `Could not reach the Su₹aksha API at ${API_BASE_URL}${path} (${
        cause instanceof Error ? cause.message : "unknown transport error"
      }).`,
    };
  }

  if (CHAT_UNAVAILABLE_STATUSES.has(response.status)) {
    const detail = await readDetail(response);
    return { state: "unavailable", reason: detail ?? `The assistant is not configured (HTTP ${response.status}).` };
  }
  if (!response.ok || !response.body) {
    const detail = response.ok ? null : await readDetail(response);
    return {
      state: "error",
      reason: `${path} returned HTTP ${response.status}${detail ? `: ${detail}` : "."}`,
    };
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      // At end of stream, a final frame missing its blank line still counts.
      const { frames, rest } = parseSseFrames(done ? `${buffer}\n\n` : buffer);
      buffer = rest;
      for (const frame of frames) {
        let data: unknown;
        try {
          data = JSON.parse(frame.data);
        } catch {
          return { state: "error", reason: `${path} sent an unreadable "${frame.event}" event.` };
        }
        switch (frame.event) {
          case "tool_call":
            handlers.onToolCall?.(data as ChatToolCallEvent);
            break;
          case "tool_result":
            handlers.onToolResult?.(data as ChatToolResultEvent);
            break;
          case "text_delta":
            handlers.onComposing?.();
            break;
          case "final":
            return { state: "ok", data: data as ChatStreamFinal };
          case "error": {
            const { error, message: detail } = data as { error?: string; message?: string };
            const reason = detail || error || "The assistant turn failed.";
            // A missing key or SDK is "not set up", not a failure of this turn.
            return error === "LLMConfigurationError"
              ? { state: "unavailable", reason }
              : { state: "error", reason };
          }
        }
      }
      if (done) break;
    }
  } catch (cause) {
    return {
      state: "error",
      transport: true,
      reason: `The connection to ${path} dropped mid-answer (${
        cause instanceof Error ? cause.message : "unknown transport error"
      }).`,
    };
  } finally {
    reader.releaseLock();
  }
  // The API guarantees a final or error event; anything else means the stream was cut.
  return { state: "error", reason: `${path} ended without an answer. Please ask again.` };
}

/** Discard a conversation's server-side history. */
export async function deleteChatSession(
  sessionId: string,
): Promise<ApiResult<{ session_id: string; deleted: boolean }>> {
  if (DEMO_MODE) return demoUnavailable("the Ask Suraksha assistant");
  return request<{ session_id: string; deleted: boolean }>(
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}
