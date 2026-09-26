import Link from "next/link";
import { InfoTip } from "@/components/InfoTip";
import type { ApiResult } from "@/lib/api";
import { formatAge, formatDate, hoursSince, shortSnapshotId } from "@/lib/format";
import type { SnapshotProvenance } from "@/lib/types";

/**
 * A snapshot older than this is flagged as stale. Snapshots are refreshed daily, so a day and
 * a half means a scheduled refresh was missed or rejected by a quality gate; the previous
 * snapshot correctly stays current, but a reader must be told how old it is. Operational
 * threshold, not a modelling constant.
 */
const STALE_AFTER_HOURS = 36;

/**
 * The one-line identity of the snapshot every figure on the page derives
 * from: which one, when, and whether it's stale or missing coverage.
 *
 * A rupee figure without the snapshot it came from is not defensible, so this
 * sits directly beneath the headline figures. It states the identity and the
 * worst caveat up front; the fuller breakdown (asset/service/finding counts,
 * per-scanner coverage) lives on Data quality & coverage, linked from here
 * rather than repeated.
 */
export function ProvenanceStrip({ result }: { result: ApiResult<SnapshotProvenance> }) {
  if (result.state !== "ok") {
    return <p className="notice info">Snapshot provenance unavailable — {result.reason}</p>;
  }

  const snapshot = result.data;
  const unreachable = snapshot.scan_scope.unreachable_scanners;
  const age = formatAge(snapshot.observed_at);
  const ageHours = hoursSince(snapshot.observed_at);
  const isStale = ageHours !== null && ageHours > STALE_AFTER_HOURS;
  const caveat = isStale
    ? `stale — observed ${age}, no newer snapshot has passed the quality gates since`
    : unreachable.length > 0
      ? `${unreachable.length} scanner${unreachable.length === 1 ? "" : "s"} not reporting`
      : null;

  return (
    <p className={`provline${caveat ? " warn" : ""}`}>
      <span className={`dot${caveat ? " warn" : ""}`} aria-hidden="true" />
      <span>
        {snapshot.valid_to === null ? "Current snapshot" : "Superseded snapshot"}, observed{" "}
        {formatDate(snapshot.observed_at)}
        {age ? ` (${age})` : ""}
      </span>
      {caveat ? (
        <InfoTip id="provline-caveat" label="Why this snapshot needs a caveat">
          {isStale
            ? `This snapshot was observed ${age}. The scheduled refresh has not produced a newer one, so every figure on this page describes the estate as it was then, not as it is today.`
            : `${unreachable.join(", ")} did not report for this snapshot. Anything these scanners would have found is missing from the figures — absence of a finding here is not evidence of remediation.`}
        </InfoTip>
      ) : null}
      <span className="provid mono" title={snapshot.snapshot_id}>
        {shortSnapshotId(snapshot.snapshot_id)}
      </span>
      <Link className="provlink" href="/data-quality">
        Full coverage detail
      </Link>
    </p>
  );
}
