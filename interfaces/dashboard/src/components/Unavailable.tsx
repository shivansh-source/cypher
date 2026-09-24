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
    <div role="status" className={`unavail${isError ? " err" : ""}`}>
      <p className="head">
        {isError ? `${what} could not be retrieved` : `No ${what} to show yet`}
      </p>
      <p className="why">{result.reason}</p>
      <p className="next">
        {isError && !(result.state === "error" && result.transport)
          ? "The API answered, but could not produce this. The reason above is its own; if a newer snapshot was committed since this page loaded, reload the page."
          : isError
          ? "Check that the FastAPI backend (interfaces/api) is running and reachable at the configured NEXT_PUBLIC_API_BASE_URL, and that its CORS_ALLOWED_ORIGINS includes this dashboard."
          : "Nothing is estimated or filled in meanwhile. Figures appear once a snapshot has passed the five quality gates and been committed (riskctl ingest)."}
      </p>
    </div>
  );
}
