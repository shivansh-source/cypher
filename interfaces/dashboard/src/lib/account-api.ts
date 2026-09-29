import "server-only";

/** Server-side calls to the API's account routes (`interfaces/api/accounts.py`). */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface AccountResponse {
  email: string;
  org: { name: string; entity_type: string | null; onboarded: boolean };
  tools: { tool_id: string; is_custom: boolean; custom_name: string | null; category: string | null }[];
}

export type ApiOutcome<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string; fields: Record<string, string> };

/** Maps FastAPI's 422 body ([{loc, msg}]) to {fieldName: message}. */
function fieldErrors(detail: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const loc = (item as { loc?: unknown[] }).loc;
      const field = Array.isArray(loc) ? String(loc[loc.length - 1]) : "";
      const msg = String((item as { msg?: unknown }).msg ?? "").replace(/^Value error, /, "");
      if (field && !out[field]) out[field] = msg;
    }
  }
  return out;
}

export async function accountCall<T>(
  path: string,
  init: { method?: "GET" | "POST"; body?: unknown; token?: string | null } = {},
): Promise<ApiOutcome<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method ?? "GET",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(init.token ? { Authorization: `Bearer ${init.token}` } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    return { ok: false, status: 0, detail: "Could not reach the Cypher API.", fields: {} };
  }
  const json: unknown = await response.json().catch(() => null);
  if (response.ok) return { ok: true, data: json as T };
  const detail = (json as { detail?: unknown } | null)?.detail;
  return {
    ok: false,
    status: response.status,
    detail: typeof detail === "string" ? detail : "Something went wrong.",
    fields: fieldErrors(detail),
  };
}
