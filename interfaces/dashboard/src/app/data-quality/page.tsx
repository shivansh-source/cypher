import { Panel } from "@/components/Panel";
import { ProvenanceStrip } from "@/components/ProvenanceStrip";
import { PassFailPill } from "@/components/StatusPill";
import { Unavailable } from "@/components/Unavailable";
import { fetchQualityGates, fetchSnapshotProvenance } from "@/lib/api";
import type { ScanScope } from "@/lib/types";

export default async function DataQualityPage() {
  const [provenance, gates] = await Promise.all([
    fetchSnapshotProvenance(),
    fetchQualityGates(),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Data quality</h1>
        <p className="mt-1 text-sm text-muted">
          Whether the figures elsewhere in this dashboard rest on data worth
          trusting, and what the data does not cover.
        </p>
      </div>

      <ProvenanceStrip result={provenance} />

      <Panel
        title="Quality gates"
        subtitle="A candidate snapshot must pass all five before it can become current. If any fails, the previous snapshot stays current."
      >
        {gates.state !== "ok" ? (
          <Unavailable result={gates} what="quality gate results" />
        ) : gates.data.length === 0 ? (
          <p className="text-sm text-muted">
            No gate results reported for the current snapshot.
          </p>
        ) : (
          <ul className="divide-y divide-line/60">
            {gates.data.map((gate) => (
              <li
                key={gate.gate_name}
                className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <div className="max-w-2xl">
                  <p className="font-mono text-sm text-ink">{gate.gate_name}</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">
                    {gate.detail}
                  </p>
                </div>
                <PassFailPill passed={gate.passed} />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {provenance.state === "ok" ? (
        <Panel
          title="Scanner coverage"
          subtitle="Which connectors reported for this snapshot, and which did not."
        >
          <ScannerCoverage scope={provenance.data.scan_scope} />
        </Panel>
      ) : null}
    </div>
  );
}

function ScannerCoverage({ scope }: { scope: ScanScope }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <h3 className="text-xs tracking-wider text-faint uppercase">
            Reported ({scope.reachable_scanners.length})
          </h3>
          <ul className="mt-2 space-y-1">
            {scope.reachable_scanners.map((scanner) => (
              <li key={scanner} className="font-mono text-sm text-ok">
                {scanner}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs tracking-wider text-faint uppercase">
            Did not report ({scope.unreachable_scanners.length})
          </h3>
          {scope.unreachable_scanners.length === 0 ? (
            <p className="mt-2 text-sm text-muted">
              Every expected scanner reported.
            </p>
          ) : (
            <ul className="mt-2 space-y-1">
              {scope.unreachable_scanners.map((scanner) => (
                <li key={scanner} className="font-mono text-sm text-warn">
                  {scanner}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="border-t border-line pt-4 text-xs leading-relaxed text-faint">
        This split is the reason the schema records scan scope at all. For a
        scanner that did not report, the absence of a finding says nothing
        about whether the underlying issue exists — it is unmeasured, not
        clean. Findings attributed to a scanner listed here as not reporting
        are rejected outright by quality gate 2.
      </p>
    </div>
  );
}
