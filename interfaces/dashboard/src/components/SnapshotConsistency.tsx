import type { ApiResult } from "@/lib/api";
import { shortSnapshotId } from "@/lib/format";

/**
 * A warning when the figures on one page came from different snapshots.
 *
 * A page makes several requests; if a new snapshot is committed between them,
 * two panels can describe different snapshots. Rather than let a reader
 * combine them, the page says so and names both.
 */
export function SnapshotConsistency({
  results,
}: {
  results: ApiResult<{ snapshot_id: string }>[];
}) {
  const ids = Array.from(
    new Set(results.flatMap((r) => (r.state === "ok" ? [r.data.snapshot_id] : []))),
  );
  if (ids.length < 2) return null;
  return (
    <p className="notice" role="alert">
      A new snapshot was committed while this page loaded, so its panels describe different
      snapshots ({ids.map(shortSnapshotId).join(", ")}). Reload the page before comparing figures.
    </p>
  );
}
