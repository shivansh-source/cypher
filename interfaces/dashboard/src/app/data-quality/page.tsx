import { Card } from "@/components/Card";
import { InfoTip } from "@/components/InfoTip";
import { KpiStrip } from "@/components/Kpi";
import { Lede } from "@/components/Lede";
import { SnapshotConsistency } from "@/components/SnapshotConsistency";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets, fetchQualityGates, fetchSnapshotProvenance, type ApiResult } from "@/lib/api";
import { formatCount, formatTimestamp, humanize, shortSnapshotId } from "@/lib/format";
import { scannerLabel } from "@/lib/labels";
import type {
  AssetsResponse,
  AssetView,
  GateReport,
  ScanScope,
  SnapshotProvenance,
} from "@/lib/types";

/** Plain-language names for the five gates in `core/`; unknown gates fall back to their id. */
const GATE_LABELS: Record<string, string> = {
  asset_count_delta: "Asset count is stable",
  no_findings_from_unreachable_scanners: "No findings from scanners that didn't report",
  criticality_present_or_unknown: "Every finding has a criticality",
  provenance_non_null: "Every finding traces to its source",
  no_ordinal_in_numeric_field: "Numeric fields hold numbers",
};

function gateLabel(name: string): string {
  const label = GATE_LABELS[name] ?? humanize(name);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

export default async function DataQualityPage() {
  const [provenance, gates, assets] = await Promise.all([
    fetchSnapshotProvenance(),
    fetchQualityGates(),
    fetchAssets(),
  ]);

  // Per-asset evidence is only drawn from an inventory of the same snapshot.
  const inventory =
    provenance.state === "ok" &&
    assets.state === "ok" &&
    assets.data.snapshot_id === provenance.data.snapshot_id
      ? assets.data
      : null;

  return (
    <div className="grid">
      <SnapshotConsistency results={[provenance, gates, assets]} />

      {provenance.state !== "ok" ? (
        <Unavailable result={provenance} what="snapshot provenance" />
      ) : (
        <SnapshotStrip snapshot={provenance.data} gates={gates} />
      )}

      <div className="grid g-2" style={{ alignItems: "start" }}>
        <Card
          title="Scanner coverage"
          subtitle="Which scanners fed this snapshot, and where their findings land."
          actions={
            <InfoTip id="coverage-basis" label="Why coverage matters">
              A scanner that didn&apos;t report leaves its part of the estate unmeasured, not
              clean: no finding from it says nothing about whether an issue exists. Any finding
              attributed to a scanner that didn&apos;t report is rejected by the quality gates.
            </InfoTip>
          }
        >
          {provenance.state !== "ok" ? (
            <Unavailable result={provenance} what="scan scope" />
          ) : (
            <CoverageMatrix scope={provenance.data.scan_scope} inventory={inventory} assets={assets} />
          )}
        </Card>

        <Card
          title="Quality gates"
          subtitle="A snapshot becomes current only if all of these pass."
          actions={
            gates.state === "ok" ? (
              <InfoTip id="gates-basis" label="How the gates were checked">
                Gate results are not stored when a snapshot is committed, so these were re-run on
                snapshot {shortSnapshotId(gates.data.snapshot_id)}
                {gates.data.compared_against_snapshot_id
                  ? `, comparing its asset count against the snapshot it superseded (${shortSnapshotId(
                      gates.data.compared_against_snapshot_id,
                    )}).`
                  : ", with no earlier snapshot in the store to compare its asset count against."}{" "}
                If any gate fails on a new candidate, the previous snapshot stays current.
              </InfoTip>
            ) : null
          }
        >
          {gates.state !== "ok" ? (
            <Unavailable result={gates} what="quality gate results" />
          ) : (
            <Gates report={gates.data} />
          )}
        </Card>
      </div>
    </div>
  );
}

/** The page's headline row, in the same strip form as the overview's figures. */
function SnapshotStrip({
  snapshot,
  gates,
}: {
  snapshot: SnapshotProvenance;
  gates: ApiResult<GateReport>;
}) {
  const reporting = snapshot.scan_scope.reachable_scanners.length;
  const missing = snapshot.scan_scope.unreachable_scanners;
  const expected = reporting + missing.length;
  const gatesPassed = gates.state === "ok" ? gates.data.gates.filter((g) => g.passed).length : null;
  const gatesTotal = gates.state === "ok" ? gates.data.gates.length : null;

  return (
    <KpiStrip>
      <div className="kpi">
        <span className="eyebrow">Snapshot</span>
        <span className="v">{snapshot.valid_to === null ? "Current" : "Superseded"}</span>
        <span className="exact" title={snapshot.snapshot_id}>
          {shortSnapshotId(snapshot.snapshot_id)}
        </span>
        <span className="s">Observed {formatTimestamp(snapshot.observed_at)}</span>
      </div>
      <div className="kpi">
        <span className="eyebrow">Quality gates</span>
        {gatesPassed === null || gatesTotal === null ? (
          <>
            <span className="v muted">—</span>
            <span className="s">Gate results unavailable</span>
          </>
        ) : (
          <>
            <span
              className="v num"
              style={{ color: gatesPassed === gatesTotal ? "var(--good)" : "var(--crit)" }}
            >
              {gatesPassed} / {gatesTotal}
            </span>
            <span className="s">
              {gatesPassed === gatesTotal
                ? "All pass on re-check"
                : `${gatesTotal - gatesPassed} failing on re-check`}
            </span>
          </>
        )}
      </div>
      <div className="kpi">
        <span className="eyebrow">Scanners reporting</span>
        <span className="v num" style={{ color: missing.length ? "var(--warn)" : undefined }}>
          {reporting} / {expected}
        </span>
        <span className="s">
          {missing.length === 0
            ? "Every expected scanner reported"
            : `Missing: ${missing.map((id) => scannerLabel(id).name).join(", ")}`}
        </span>
      </div>
      <div className="kpi">
        <span className="eyebrow">Open findings</span>
        <span className="v num">{formatCount(snapshot.open_finding_count)}</span>
        <span className="s">
          Of {formatCount(snapshot.finding_count)} recorded, across{" "}
          {plural(snapshot.asset_count, "asset")} and {plural(snapshot.service_count, "service")}
        </span>
      </div>
    </KpiStrip>
  );
}

type CellState = "hit" | "clear" | "quiet" | "outside" | "dark";

const CELL_LEGEND: Record<CellState, string> = {
  hit: "Findings on this asset",
  clear: "Scanned, nothing found",
  quiet: "No finding; per-asset scope not recorded",
  outside: "Not in this scanner's scope",
  dark: "Didn't report: unmeasured",
};

/**
 * Scanners × assets: where each scanner's evidence lands in this snapshot.
 *
 * A blank cell is only drawn as "scanned, nothing found" when the snapshot
 * records that scanner's per-asset scope — otherwise the absence of a finding
 * is shown as exactly that, never as a clean result. A scanner that did not
 * report is drawn as unmeasured across every asset.
 */
function CoverageMatrix({
  scope,
  inventory,
  assets,
}: {
  scope: ScanScope;
  inventory: AssetsResponse | null;
  assets: ApiResult<AssetsResponse>;
}) {
  const unreachable = new Set(scope.unreachable_scanners);
  const scanners = [...scope.unreachable_scanners, ...scope.reachable_scanners];
  const scopeByScanner = new Map(
    (scope.coverage ?? []).map((c) => [c.scanner, new Set(c.asset_ids)] as const),
  );
  const columns: AssetView[] = inventory?.assets ?? [];

  const cell = (scanner: string, asset: AssetView): { state: CellState; open: number } => {
    if (unreachable.has(scanner)) return { state: "dark", open: 0 };
    const findings = asset.findings.filter((f) => f.provenance.connector === scanner);
    const open = findings.filter((f) => f.remediated_at == null).length;
    if (open > 0) return { state: "hit", open };
    const scoped = scopeByScanner.get(scanner);
    if (scoped === undefined) return { state: "quiet", open: 0 };
    return { state: scoped.has(asset.asset_id) ? "clear" : "outside", open: 0 };
  };

  const seen = new Set<CellState>();
  const rows = scanners.map((scanner) => {
    const cells = columns.map((asset) => {
      const c = cell(scanner, asset);
      seen.add(c.state);
      return { asset, ...c };
    });
    const all = columns.flatMap((a) => a.findings.filter((f) => f.provenance.connector === scanner));
    const open = all.filter((f) => f.remediated_at == null).length;
    return { scanner, cells, open, remediated: all.length - open };
  });

  return (
    <div className="cov">
      {unreachable.size > 0 ? (
        <p className="notice">
          {plural(unreachable.size, "scanner")} didn&apos;t report for this snapshot. What{" "}
          {unreachable.size === 1 ? "it covers" : "they cover"} is missing from every figure —
          absence of a finding there is not evidence of remediation.
        </p>
      ) : null}

      <div className="tbl">
        <table className="covtbl">
          <thead>
            <tr>
              <th scope="col">Scanner</th>
              {columns.map((asset) => (
                <th scope="col" key={asset.asset_id} className="as" title={asset.asset_id}>
                  {asset.asset_id}
                </th>
              ))}
              <th scope="col" className="r">
                Open findings
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const label = scannerLabel(row.scanner);
              const dark = unreachable.has(row.scanner);
              return (
                <tr key={row.scanner} className={dark ? "dark" : undefined}>
                  <th scope="row">
                    <span className="sc">
                      <span className={`lamp${dark ? " off" : ""}`} aria-hidden="true" />
                      <span>
                        <b title={row.scanner}>{label.name}</b>
                        <span className="role">
                          {dark ? "Didn't report" : (label.role ?? row.scanner)}
                        </span>
                      </span>
                    </span>
                  </th>
                  {row.cells.map((c) => (
                    <td key={c.asset.asset_id} className="cellwrap">
                      <span
                        className={`cell ${c.state}`}
                        role="img"
                        aria-label={`${label.name} on ${c.asset.asset_id}: ${
                          c.state === "hit" ? plural(c.open, "open finding") : CELL_LEGEND[c.state]
                        }`}
                        title={`${label.name} on ${c.asset.asset_id}: ${
                          c.state === "hit" ? plural(c.open, "open finding") : CELL_LEGEND[c.state]
                        }`}
                      >
                        {c.state === "hit" ? c.open : null}
                      </span>
                    </td>
                  ))}
                  <td className="r tally">
                    {dark ? (
                      <span style={{ color: "var(--warn)" }}>Unmeasured</span>
                    ) : inventory === null ? (
                      <span className="muted">—</span>
                    ) : (
                      <>
                        <b className={row.open ? undefined : "muted"}>{formatCount(row.open)}</b>
                        {row.remediated > 0 ? (
                          <span className="sub">{formatCount(row.remediated)} remediated</span>
                        ) : null}
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {inventory === null ? (
        <p className="small muted">
          Per-asset findings unavailable —{" "}
          {assets.state !== "ok"
            ? assets.reason
            : "the asset inventory came from a different snapshot; reload the page"}
          .
        </p>
      ) : (
        <ul className="covkey" aria-label="Legend">
          {(Object.keys(CELL_LEGEND) as CellState[])
            .filter((state) => seen.has(state))
            .map((state) => (
              <li key={state}>
                <span className={`cell ${state} sm`} aria-hidden="true" />
                {CELL_LEGEND[state]}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}

function Gates({ report }: { report: GateReport }) {
  const failed = report.gates.filter((g) => !g.passed).length;
  const ok = failed === 0;
  return (
    <div className="gatebox">
      <Lede
        tone={ok ? "good" : "crit"}
        icon={ok ? "✓" : "✕"}
        title={
          ok ? `All ${report.gates.length} gates pass` : `${failed} of ${report.gates.length} gates fail`
        }
      >
        Re-checked {formatTimestamp(report.evaluated_at)}
      </Lede>
      <ul className="gatelist">
        {report.gates.map((gate) => (
          <li key={gate.gate_name} className={gate.passed ? "ok" : "bad"}>
            <span className="ic" aria-label={gate.passed ? "Pass" : "Fail"}>
              {gate.passed ? "✓" : "✕"}
            </span>
            <span>
              <b title={gate.gate_name}>{gateLabel(gate.gate_name)}</b>
              <span className="d">{gate.detail.charAt(0).toUpperCase() + gate.detail.slice(1)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
