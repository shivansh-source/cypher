import type { ReactNode } from "react";
import { Card } from "@/components/Card";
import { ProvenanceStrip } from "@/components/ProvenanceStrip";
import { PassFailPill } from "@/components/StatusPill";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssumptions, fetchQualityGates, fetchSnapshotProvenance } from "@/lib/api";
import {
  formatCount,
  formatDecimal,
  formatInr,
  formatTimestamp,
  humanize,
  shortSnapshotId,
} from "@/lib/format";
import type { AssumptionEntry, GateReport, ScanScope } from "@/lib/types";

export default async function DataQualityPage() {
  const [provenance, gates, assumptions] = await Promise.all([
    fetchSnapshotProvenance(),
    fetchQualityGates(),
    fetchAssumptions(),
  ]);

  return (
    <div className="grid">
      <ProvenanceStrip result={provenance} />

      <div className="grid g-2e">
        <Card
          title="Quality gates"
          subtitle="A candidate snapshot becomes current only if all five pass. If any fails, the previous snapshot stays current."
        >
          {gates.state !== "ok" ? (
            <Unavailable result={gates} what="quality gate results" />
          ) : (
            <Gates report={gates.data} />
          )}
        </Card>

        <Card
          title="Scanner coverage"
          subtitle="Which connectors reported for this snapshot, and which did not."
        >
          {provenance.state !== "ok" ? (
            <Unavailable result={provenance} what="scan scope" />
          ) : (
            <ScannerCoverage scope={provenance.data.scan_scope} />
          )}
        </Card>
      </div>

      <Card
        id="assumptions"
        title="Assumption register"
        subtitle="Every constant the engine reads from core/assumptions.py, with the value in force right now and the rationale written beside it in the source. Each is a declared input awaiting calibration, not a finding."
      >
        {assumptions.state !== "ok" ? (
          <Unavailable result={assumptions} what="assumption register" />
        ) : (
          <AssumptionTable entries={assumptions.data} />
        )}
      </Card>
    </div>
  );
}

function Gates({ report }: { report: GateReport }) {
  const passed = report.gates.filter((g) => g.passed).length;
  return (
    <>
      <div className="gates">
        {report.gates.map((gate, i) => (
          <div className="gate" key={gate.gate_name}>
            <PassFailPill passed={gate.passed} />
            <div>
              <b>
                {i + 1}. {humanize(gate.gate_name)}
              </b>
              <div className="small muted">{gate.detail}</div>
            </div>
          </div>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        {passed} of {report.gates.length} pass. Gate results are not stored at commit time, so these
        were re-run at {formatTimestamp(report.evaluated_at)} on snapshot{" "}
        <span className="mono" title={report.snapshot_id}>
          {shortSnapshotId(report.snapshot_id)}
        </span>
        {report.compared_against_snapshot_id ? (
          <>
            {" "}
            against the snapshot it superseded,{" "}
            <span className="mono" title={report.compared_against_snapshot_id}>
              {shortSnapshotId(report.compared_against_snapshot_id)}
            </span>
          </>
        ) : (
          ", with no earlier committed snapshot in the store to compare its asset count against"
        )}
        .
      </p>
    </>
  );
}

function ScannerCoverage({ scope }: { scope: ScanScope }) {
  return (
    <div className="detail">
      <div className="kv">
        <div>
          <div className="k">Reported ({scope.reachable_scanners.length})</div>
          <ul className="valuelist" style={{ color: "var(--good)" }}>
            {scope.reachable_scanners.length === 0 ? (
              <li className="muted">none</li>
            ) : (
              scope.reachable_scanners.map((s) => <li key={s}>{s}</li>)
            )}
          </ul>
        </div>
        <div>
          <div className="k">Did not report ({scope.unreachable_scanners.length})</div>
          <ul className="valuelist" style={{ color: "var(--warn)" }}>
            {scope.unreachable_scanners.length === 0 ? (
              <li className="muted">Every expected scanner reported</li>
            ) : (
              scope.unreachable_scanners.map((s) => <li key={s}>{s}</li>)
            )}
          </ul>
        </div>
      </div>
      {scope.coverage && scope.coverage.length > 0 ? (
        <p className="small muted">
          Per-scanner asset coverage:{" "}
          {scope.coverage
            .map((c) => `${c.scanner} ${formatCount(c.asset_ids.length)} asset${c.asset_ids.length === 1 ? "" : "s"}`)
            .join(" · ")}
        </p>
      ) : null}
      <p className="small muted">
        This split is why the schema records scan scope at all. For a scanner that did not report,
        the absence of a finding says nothing about whether the issue exists — it is unmeasured, not
        clean. Findings attributed to a scanner listed as not reporting are rejected outright by
        quality gate 2.
      </p>
    </div>
  );
}

/** Render a constant's live value; rupee-valued constants (names ending `_INR`) as exact rupees. */
function renderValue(name: string, value: unknown): ReactNode {
  const rupees = /_INR$/.test(name);
  const scalar = (v: unknown): string => {
    if (typeof v === "number") {
      if (rupees) return formatInr(v);
      // No digit grouping: some integer constants are port numbers, not quantities.
      return Number.isInteger(v) ? String(v) : formatDecimal(v, 4);
    }
    if (typeof v === "boolean" || typeof v === "string") return String(v);
    if (v === null) return "null";
    if (Array.isArray(v)) return v.map(scalar).join(", ");
    if (typeof v === "object") {
      return Object.entries(v as Record<string, unknown>)
        .map(([k, inner]) => `${k} ${scalar(inner)}`)
        .join(" / ");
    }
    return String(v);
  };
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="muted">empty — not populated yet</span>;
    return (
      <ul className="valuelist">
        {entries.map(([key, inner]) => (
          <li key={key}>
            <span className="muted">{key}:</span> {scalar(inner)}
          </li>
        ))}
      </ul>
    );
  }
  if (Array.isArray(value) && value.length === 0) return <span className="muted">empty</span>;
  return <span className="mono">{scalar(value)}</span>;
}

function AssumptionTable({ entries }: { entries: AssumptionEntry[] }) {
  return (
    <div className="tbl">
      <table>
        <thead>
          <tr>
            <th>Constant</th>
            <th>Value in force</th>
            <th>What it represents</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const placeholder = entry.justification?.startsWith("PLACEHOLDER") ?? false;
            return (
              <tr key={entry.name}>
                <td className="mono small">
                  <b>{entry.name}</b>
                  {placeholder ? (
                    <div style={{ marginTop: 4 }}>
                      <span className="prov declared">PLACEHOLDER</span>
                    </div>
                  ) : null}
                </td>
                <td className="small">{renderValue(entry.name, entry.value)}</td>
                <td className="small">
                  {entry.assumption ?? <span className="muted">No documented rationale found.</span>}
                  {entry.justification || entry.calibration ? (
                    <details className="explain">
                      <summary>Justification and calibration</summary>
                      {entry.justification ? (
                        <p>
                          <b>Justification:</b> {entry.justification}
                        </p>
                      ) : null}
                      {entry.calibration ? (
                        <p>
                          <b>To calibrate:</b> {entry.calibration}
                        </p>
                      ) : null}
                    </details>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
