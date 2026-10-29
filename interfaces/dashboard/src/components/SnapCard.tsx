"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Spinner } from "./Loader";
import { fetchQualityGates, fetchSnapshotProvenance, type ApiResult } from "@/lib/api";
import { formatDate, formatTimestamp, shortSnapshotId } from "@/lib/format";
import type { GateReport, SnapshotProvenance } from "@/lib/types";

/** How old the card's data may be before a navigation re-fetches it. Not a modelling constant. */
const REFRESH_AFTER_MS = 15_000;

interface Loaded {
  provenance: ApiResult<SnapshotProvenance>;
  gates: ApiResult<GateReport>;
}

/**
 * The sidebar's "current snapshot" card.
 *
 * Fetched in the browser and re-fetched on navigation, because the sidebar
 * lives in the root layout, which Next does not re-render between pages — a
 * server-rendered card would keep showing the snapshot that was current when
 * the app first loaded, beside pages computed from a newer one. Snapshots
 * change about once a day, so a navigation within {@link REFRESH_AFTER_MS} of
 * the last fetch reuses it rather than queueing two more API calls in front
 * of the page's own; returning to the tab always re-fetches.
 */
export function SnapCard() {
  const pathname = usePathname();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const fetchedAt = useRef<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    // A fetch is never cancelled by a later navigation (only by unmounting): one that
    // skips re-fetching relies on the in-flight result still landing.
    const load = (force: boolean) => {
      const now = Date.now();
      if (!force && fetchedAt.current !== null && now - fetchedAt.current < REFRESH_AFTER_MS) return;
      fetchedAt.current = now;
      Promise.all([fetchSnapshotProvenance(), fetchQualityGates()]).then(
        ([provenance, gates]) => {
          if (mounted.current) setLoaded({ provenance, gates });
        },
      );
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") load(true);
    };
    load(false);
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [pathname]);

  return (
    <Link className="snapcard" href="/data-quality" aria-live="polite">
      {loaded === null ? (
        <p className="small muted sc-loading">
          <Spinner size={12} /> Loading snapshot…
        </p>
      ) : loaded.provenance.state !== "ok" ? (
        <>
          <span className="sc-status warn">
            <span className="lamp off" aria-hidden="true" />
            <b>No current snapshot</b>
          </span>
          <p className="small muted">
            {loaded.provenance.state === "unavailable"
              ? "Nothing has been committed yet."
              : "The API could not be reached."}
          </p>
        </>
      ) : (
        <SnapDetails provenance={loaded.provenance.data} gates={loaded.gates} />
      )}
    </Link>
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
  const missing = provenance.scan_scope.unreachable_scanners.length;
  const total = reachable + missing;
  const passed = gates.state === "ok" ? gates.data.gates.filter((g) => g.passed).length : null;
  const gateCount = gates.state === "ok" ? gates.data.gates.length : null;
  const failing = passed !== null && gateCount !== null ? gateCount - passed : null;

  // Worst first: a failing gate outranks a missing scanner; unknown gates never read as passing.
  const status =
    failing === null
      ? { tone: "warn", text: "Gate results unavailable" }
      : failing > 0
        ? { tone: "crit", text: `${failing} gate${failing === 1 ? "" : "s"} failing` }
        : missing > 0
          ? { tone: "warn", text: `${missing} scanner${missing === 1 ? "" : "s"} missing` }
          : { tone: "good", text: "All checks pass" };

  return (
    <>
      <span className={`sc-status ${status.tone}`}>
        <span className={`lamp ${status.tone === "good" ? "" : status.tone}`} aria-hidden="true" />
        <b>{status.text}</b>
      </span>
      <span className="small muted" title={formatTimestamp(provenance.observed_at)}>
        {provenance.valid_to === null ? "Current snapshot" : "Superseded snapshot"}, observed{" "}
        {formatDate(provenance.observed_at)}
      </span>
      <span className="sc-stats">
        <span className={failing === null ? "" : failing > 0 ? "crit" : "good"}>
          <b>{passed === null || gateCount === null ? "—" : `${passed}/${gateCount}`}</b>
          gates pass
        </span>
        <span className={missing > 0 ? "warn" : ""}>
          <b>
            {reachable}/{total}
          </b>
          scanners
        </span>
      </span>
      <span className="sc-id mono" title={provenance.snapshot_id}>
        {shortSnapshotId(provenance.snapshot_id)}
      </span>
    </>
  );
}
