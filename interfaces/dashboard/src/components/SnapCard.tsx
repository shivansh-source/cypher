"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchQualityGates, fetchSnapshotProvenance, type ApiResult } from "@/lib/api";
import { formatTimestamp, shortSnapshotId } from "@/lib/format";
import type { GateReport, SnapshotProvenance } from "@/lib/types";

interface Loaded {
  provenance: ApiResult<SnapshotProvenance>;
  gates: ApiResult<GateReport>;
}

/**
 * The sidebar's "current snapshot" card.
 *
 * Fetched in the browser and re-fetched on every navigation, because the
 * sidebar lives in the root layout, which Next does not re-render between
 * pages — a server-rendered card would keep showing the snapshot that was
 * current when the app first loaded, beside pages computed from a newer one.
 */
export function SnapCard() {
  const pathname = usePathname();
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchSnapshotProvenance(), fetchQualityGates()]).then(
      ([provenance, gates]) => {
        if (!cancelled) setLoaded({ provenance, gates });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <div className="snapcard" aria-live="polite">
      <div className="eyebrow">Current snapshot</div>
      {loaded === null ? (
        <p className="small muted">Loading snapshot…</p>
      ) : loaded.provenance.state !== "ok" ? (
        <p className="small muted">
          {loaded.provenance.state === "unavailable"
            ? "No snapshot has been committed yet."
            : "The API could not be reached."}
        </p>
      ) : (
        <SnapDetails provenance={loaded.provenance.data} gates={loaded.gates} />
      )}
    </div>
  );
}

function SnapDetails({
  provenance,
  gates,
}: {
  provenance: SnapshotProvenance;
  gates: ApiResult<GateReport>;
}) {
  const reachable = provenance.scan_scope.reachable_scanners.length;
  const total = reachable + provenance.scan_scope.unreachable_scanners.length;
  const passed = gates.state === "ok" ? gates.data.gates.filter((g) => g.passed).length : null;
  const gateCount = gates.state === "ok" ? gates.data.gates.length : null;
  return (
    <>
      <div className="mono small wrap" title={provenance.snapshot_id}>
        {shortSnapshotId(provenance.snapshot_id)}
      </div>
      <div className="row">
        <span className="muted">Observed</span>
        <span className="mono">{formatTimestamp(provenance.observed_at)}</span>
      </div>
      <div className="row">
        <span className="muted">Quality gates</span>
        {passed === null || gateCount === null ? (
          <span className="mono muted">unavailable</span>
        ) : (
          <span
            className="mono"
            style={{ color: passed === gateCount ? "var(--good)" : "var(--crit)" }}
          >
            {passed} / {gateCount} pass
          </span>
        )}
      </div>
      <div className="row">
        <span className="muted">Scanners reporting</span>
        <span
          className="mono"
          style={{ color: reachable === total ? undefined : "var(--warn)" }}
        >
          {reachable} / {total}
        </span>
      </div>
    </>
  );
}
