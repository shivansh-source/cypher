import type { ApiResult } from "@/lib/api";
import { formatAge, formatCount, formatTimestamp, hoursSince, shortSnapshotId } from "@/lib/format";
import type { SnapshotProvenance } from "@/lib/types";

/**
 * A snapshot older than this is flagged as stale. Snapshots are refreshed daily, so a day and
 * a half means a scheduled refresh was missed or rejected by a quality gate; the previous
 * snapshot correctly stays current, but a reader must be told how old it is. Operational
 * threshold, not a modelling constant.
 */
const STALE_AFTER_HOURS = 36;

/**
 * The provenance line that qualifies every figure on the page.
 *
 * A rupee figure without the snapshot it came from is not defensible, so this
 * strip sits directly beneath the figures rather than on a separate page. When
 * a scanner was unreachable for the snapshot, that is surfaced here as a
 * coverage caveat: absence of a finding from a scanner that never ran is not
 * evidence of remediation, and a reader of the headline number needs to know
 * which part of the estate the number is blind to.
 */
export function ProvenanceStrip({
  result,
}: {
  result: ApiResult<SnapshotProvenance>;
}) {
  if (result.state !== "ok") {
    return (
      <p className="notice info">
        Snapshot provenance unavailable — {result.reason}
      </p>
    );
  }

  const snapshot = result.data;
  const unreachable = snapshot.scan_scope.unreachable_scanners;
  const age = formatAge(snapshot.observed_at);
  const ageHours = hoursSince(snapshot.observed_at);
  const isStale = ageHours !== null && ageHours > STALE_AFTER_HOURS;

  return (
    <div className="card provstrip">
      <dl>
        <Item label="Snapshot">
          <span className="mono" title={snapshot.snapshot_id}>
            {shortSnapshotId(snapshot.snapshot_id)}
          </span>
        </Item>
        <Item label="Observed">
          <span className="mono">{formatTimestamp(snapshot.observed_at)}</span>
          {age ? <span> ({age})</span> : null}
        </Item>
        <Item label="Status">{snapshot.valid_to === null ? "Current" : "Superseded"}</Item>
        <Item label="Assets">
          <span className="mono">{formatCount(snapshot.asset_count)}</span>
        </Item>
        <Item label="Services">
          <span className="mono">{formatCount(snapshot.service_count)}</span>
        </Item>
        <Item label="Open findings">
          <span className="mono">
            {formatCount(snapshot.open_finding_count)} of {formatCount(snapshot.finding_count)}
          </span>
        </Item>
        <Item label="Scanners reporting">
          <span className="mono">
            {snapshot.scan_scope.reachable_scanners.length} of{" "}
            {snapshot.scan_scope.reachable_scanners.length + unreachable.length}
          </span>
        </Item>
      </dl>

      {isStale ? (
        <p className="notice" style={{ marginTop: 12 }}>
          <strong>Stale snapshot:</strong> this snapshot was observed {age}. The scheduled refresh
          has not produced a newer one, so these figures describe the estate as it was then.
        </p>
      ) : null}

      {unreachable.length > 0 ? (
        <p className="notice" style={{ marginTop: 12 }}>
          <strong>Coverage caveat:</strong> {unreachable.join(", ")} did not
          report for this snapshot. Anything these scanners would have found is
          missing from the figures — absence of a finding here is not evidence
          of remediation.
        </p>
      ) : null}
    </div>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
