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
 */

import { DEMO_SNAPSHOT_PROVENANCE, demoResult } from "./demo-data";
import type {
  FrameworkStatus,
  GateResult,
  PortfolioRecommendation,
  RiskFigure,
  SnapshotProvenance,
} from "./types";

/**
 * Outcome of one backend call.
 *
 * - `ok` — the backend returned a figure computed by `core/`.
 * - `unavailable` — the backend answered, but there is no figure to give
 *   (endpoint not implemented yet, engine has not run, no committed snapshot).
 *   Not a failure; a truthful "nothing to show".
 * - `error` — the backend could not be reached or answered unusably.
 */
export type ApiResult<T> =
  | { state: "ok"; data: T }
  | { state: "unavailable"; reason: string }
  | { state: "error"; reason: string };

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
 * HTTP statuses that mean "no figure exists", as distinct from "the request
 * failed". 501 is what an unimplemented FastAPI route should return; 404/409
 * cover "no committed snapshot yet" and "engine has not run against it".
 */
const NO_FIGURE_STATUSES = new Set([404, 409, 501]);

async function getJson<T>(path: string): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      // A risk figure must never be served from a cache: the whole point of
      // the snapshot lifecycle is that the current figure tracks the current
      // committed snapshot. (Next 16 does not cache fetch by default; this is
      // explicit so a future default change cannot silently stale the number.)
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    return {
      state: "error",
      reason: `Could not reach the Su₹aksha API at ${API_BASE_URL}${path} (${
        cause instanceof Error ? cause.message : "unknown transport error"
      }).`,
    };
  }

  if (NO_FIGURE_STATUSES.has(response.status)) {
    return {
      state: "unavailable",
      reason: `The API has no figure for ${path} yet (HTTP ${response.status}).`,
    };
  }

  if (!response.ok) {
    return {
      state: "error",
      reason: `${path} returned HTTP ${response.status}.`,
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
 * Backed by `ai.tools.get_exposure`, which delegates to
 * `core.engine.compute_risk_figure`. The returned `top_contributors` are the
 * engine's own ranking and are never re-sorted here.
 */
export async function fetchExposure(): Promise<ApiResult<RiskFigure>> {
  if (DEMO_MODE) return demoResult("exposure");
  return getJson<RiskFigure>("/exposure");
}

/**
 * A budget-constrained control portfolio recommendation.
 *
 * Backed by `ai.tools.optimize_investment` -> `core.optimizer.recommend_portfolio`.
 * The `risk_reduction_inr` in the response comes from the optimizer's joint
 * re-simulation; the dashboard displays it as given and never derives its own
 * benefit figure by summing per-control deltas (principle 7).
 */
export async function fetchRecommendation(
  budgetInr: number,
): Promise<ApiResult<PortfolioRecommendation>> {
  if (DEMO_MODE) return demoResult("recommendation");
  return getJson<PortfolioRecommendation>(
    `/optimize?budget_inr=${encodeURIComponent(budgetInr)}`,
  );
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
  if (DEMO_MODE) return demoResult("frameworkStatus");
  return getJson<FrameworkStatus>(
    `/frameworks/${encodeURIComponent(framework)}/status`,
  );
}

/** Provenance of the currently committed snapshot every figure derives from. */
export async function fetchSnapshotProvenance(): Promise<
  ApiResult<SnapshotProvenance>
> {
  if (DEMO_MODE) {
    return { state: "ok", data: DEMO_SNAPSHOT_PROVENANCE };
  }
  return getJson<SnapshotProvenance>("/snapshot");
}

/** The 5 quality gates' results for the current candidate/committed snapshot. */
export async function fetchQualityGates(): Promise<ApiResult<GateResult[]>> {
  if (DEMO_MODE) return demoResult("gates");
  return getJson<GateResult[]>("/snapshot/gates");
}
