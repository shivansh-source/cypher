import type { ApiResult } from "@/lib/api";
import { formatCount, formatTimestamp, shortSnapshotId } from "@/lib/format";
import type { SnapshotProvenance } from "@/lib/types";

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
