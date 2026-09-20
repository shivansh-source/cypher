import type { ApiResult } from "@/lib/api";

/**
 * What the dashboard renders instead of a figure it does not have.
 *
 * This component is the load-bearing piece of the dashboard's honesty
 * contract. When the engine has not produced a number, the UI must say so in
 * words and explain what would make a number appear — it must never fall back
 * to a zero, an em dash, a spinner that never resolves, or a remembered
 * previous value, any of which a reader could mistake for a real result.
 */
export function Unavailable({
  result,
  what,
}: {
  result: Extract<ApiResult<unknown>, { state: "unavailable" | "error" }>;
  /** What could not be shown, e.g. "Expected Annual Loss". */
  what: string;
}) {
  const isError = result.state === "error";
  return (
    <div
      role="status"
      className={`rounded-md border border-dashed p-5 ${
        isError ? "border-danger/40 bg-danger/5" : "border-line bg-surface-2"
      }`}
    >
      <p
        className={`text-sm font-semibold ${
          isError ? "text-danger" : "text-ink"
        }`}
      >
        {isError
          ? `${what} could not be retrieved`
          : `No ${what} has been computed yet`}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">
        {result.reason}
      </p>
      <p className="mt-3 text-xs leading-relaxed text-faint">
        {isError
          ? "Check that the FastAPI backend (interfaces/api) is running and reachable at the configured NEXT_PUBLIC_API_BASE_URL."
          : "A figure appears here once a snapshot has passed the quality gates in core/snapshot.py and core/engine.py has run against it. Nothing is estimated or filled in meanwhile."}
      </p>
    </div>
  );
}
