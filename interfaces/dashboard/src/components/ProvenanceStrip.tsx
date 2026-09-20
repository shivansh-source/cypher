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
      <p className="rounded-md border border-line bg-surface px-4 py-2.5 text-xs text-muted">
        Snapshot provenance unavailable — {result.reason}
      </p>
    );
  }

  const snapshot = result.data;
  const unreachable = snapshot.scan_scope.unreachable_scanners;

  return (
    <div className="rounded-md border border-line bg-surface px-4 py-3">
      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-xs">
        <Item label="Snapshot">
          <span className="tnum font-mono" title={snapshot.snapshot_id}>
            {shortSnapshotId(snapshot.snapshot_id)}
          </span>
        </Item>
        <Item label="Observed">
          <span className="tnum">{formatTimestamp(snapshot.observed_at)}</span>
        </Item>
        <Item label="Status">
          {snapshot.valid_to === null ? "Current" : "Superseded"}
        </Item>
        <Item label="Assets">
          <span className="tnum">{formatCount(snapshot.asset_count)}</span>
        </Item>
        <Item label="Services">
          <span className="tnum">{formatCount(snapshot.service_count)}</span>
        </Item>
        <Item label="Findings">
          <span className="tnum">{formatCount(snapshot.finding_count)}</span>
        </Item>
        <Item label="Scanners reporting">
          <span className="tnum">
            {snapshot.scan_scope.reachable_scanners.length}
          </span>
        </Item>
      </dl>

      {unreachable.length > 0 ? (
        <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-warn">
          <strong className="font-semibold">Coverage caveat:</strong>{" "}
          {unreachable.join(", ")} did not report for this snapshot. Anything
          these scanners would have found is missing from the figures above —
          absence of a finding here is not evidence of remediation.
        </p>
      ) : null}
    </div>
  );
}

function Item({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-faint">{label}</dt>
      <dd className="mt-0.5 text-ink">{children}</dd>
    </div>
  );
}
