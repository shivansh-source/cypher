"use client";

import { useState, type MouseEvent } from "react";
import {
  formatDate,
  formatDayMonth,
  formatInr,
  formatInrAxis,
  formatInrCompact,
  formatPercent,
  parseIsoMs,
  shortSnapshotId,
} from "@/lib/format";
import { contributionLabel } from "@/lib/labels";
import type { AssetView, ExposureHistoryEntry } from "@/lib/types";
import {
  ChartTooltip,
  Legend,
  SERIES_COLOURS,
  TipRow,
  niceTicks,
  pointerX,
  useElementWidth,
  type LegendItem,
  type TipState,
} from "./primitives";

/** How many of the latest snapshot's scenarios get their own colour. */
const NAMED_SCENARIOS = 5;

interface Row {
  observedAt: string;
  time: number;
  snapshotId: string;
  /** Contribution of each named scenario, or undefined if it was not in that snapshot. */
  values: (number | undefined)[];
  otherCount: number;
  eal: number;
  valueAtRisk: number;
}

/**
 * Expected Annual Loss across every committed snapshot, each re-simulated in
 * full by the engine (`GET /exposure/history`).
 *
 * Every point is a committed snapshot; nothing is interpolated between them or
 * projected past the latest one. "By scenario" stacks the latest snapshot's
 * five largest scenarios, and the band above them runs up to the engine's own
 * Expected Annual Loss for that snapshot — so the top of the stack is always
 * the engine's figure, never a total summed here.
 */
export function ExposureTrendChart({
  snapshots,
  assets,
}: {
  snapshots: ExposureHistoryEntry[];
  /** The latest snapshot's asset inventory, for real names — see `contributionLabel`. */
  assets: AssetView[] | null;
}) {
  const [mode, setMode] = useState<"scenario" | "tail">("scenario");
  const [setNode, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);

  const latest = snapshots[snapshots.length - 1];
  const named = latest.risk_figure.top_contributors.slice(0, NAMED_SCENARIOS);
  const namedIds = new Set(named.map((c) => c.scenario_id));
  const percentileLabel = formatPercent(latest.risk_figure.value_at_risk_percentile);

  if (snapshots.length < 2) {
    return (
      <p className="notice info">
        One snapshot has been committed so far (observed {formatDate(latest.observed_at)}). A
        trend appears once a second snapshot is committed — nothing is interpolated or projected
        in the meantime.
      </p>
    );
  }

  const rows: Row[] = snapshots.map((entry) => {
    const byId = new Map(
      entry.risk_figure.top_contributors.map((c) => [c.scenario_id, c.expected_annual_loss_inr]),
    );
    return {
      observedAt: entry.observed_at,
      time: parseIsoMs(entry.observed_at),
      snapshotId: entry.snapshot_id,
      values: named.map((c) => byId.get(c.scenario_id)),
      otherCount: entry.risk_figure.top_contributors.filter((c) => !namedIds.has(c.scenario_id))
        .length,
      eal: entry.risk_figure.expected_annual_loss_inr,
      valueAtRisk: entry.risk_figure.value_at_risk_inr,
    };
  });

  const mobile = width < 560;
  const height = mobile ? 280 : 340;
  const margin = { l: mobile ? 58 : 70, r: 18, t: 16, b: 30 };
  const innerWidth = Math.max(0, width - margin.l - margin.r);
  const innerHeight = height - margin.t - margin.b;

  const times = rows.map((row) => row.time);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const byTime = times.every(Number.isFinite) && t1 > t0;
  const xs = (index: number) =>
    margin.l + (byTime ? (times[index] - t0) / (t1 - t0) : index / (rows.length - 1)) * innerWidth;

  const maxValue =
    mode === "scenario"
      ? Math.max(...rows.map((row) => row.eal))
      : Math.max(...rows.map((row) => Math.max(row.valueAtRisk, row.eal)));
  const ticks = niceTicks(maxValue * 1.04, mobile ? 4 : 5);
  const yMax = ticks[ticks.length - 1];
  const ys = (value: number) => margin.t + innerHeight - (value / yMax) * innerHeight;

  const areaPath = (upper: number[], lower: number[]) => {
    let d = "";
    for (let i = 0; i < rows.length; i++) d += `${i ? "L" : "M"}${xs(i)},${ys(upper[i])}`;
    for (let i = rows.length - 1; i >= 0; i--) d += `L${xs(i)},${ys(lower[i])}`;
    return `${d}Z`;
  };
  const linePath = (values: number[]) =>
    values.map((value, i) => `${i ? "L" : "M"}${xs(i)},${ys(value)}`).join("");

  // Stacking geometry only: positions on screen, never a displayed figure.
  const bands: { d: string; colour: string }[] = [];
  let base = rows.map(() => 0);
  for (let k = 0; k < named.length; k++) {
    const upper = rows.map((row, i) => base[i] + (row.values[k] ?? 0));
    bands.push({ d: areaPath(upper, base), colour: SERIES_COLOURS[k] });
    base = upper;
  }
  const otherBand = areaPath(
    rows.map((row, i) => Math.max(base[i], row.eal)),
    base,
  );

  // Label every snapshot when there is room, otherwise every `labelStep`-th,
  // always ending on the latest (replacing a label too close to it).
  const labelStep = Math.ceil(rows.length / (mobile ? 4 : 7));
  const labelled = rows.map((_, i) => i).filter((i) => i % labelStep === 0);
  const lastIndex = rows.length - 1;
  if (labelled[labelled.length - 1] !== lastIndex) {
    if (lastIndex - labelled[labelled.length - 1] < labelStep / 2) labelled.pop();
    labelled.push(lastIndex);
  }

  const legend: LegendItem[] =
    mode === "scenario"
      ? [
          ...named.map((c, k) => {
            const { title, where } = contributionLabel(c, assets);
            // The same CVE open on two assets gives two scenarios with one title: name the
            // asset too, so the two bands can be told apart.
            const shared = named.some((other) => other !== c && contributionLabel(other, assets).title === title);
            return {
              key: c.scenario_id,
              label: shared ? `${title} · ${where}` : title,
              colour: SERIES_COLOURS[k],
              title: `${c.description} — ${where}`,
            };
          }),
          { label: "All other scenarios", colour: "var(--other)" },
        ]
      : [
          { label: "Expected annual loss", colour: "var(--s1)", kind: "line" },
          { label: `Value at risk (${percentileLabel})`, colour: "var(--s7)", kind: "line" },
        ];

  function tooltipFor(index: number) {
    const row = rows[index];
    return (
      <>
        <div className="t">
          {formatDate(row.observedAt)} · {shortSnapshotId(row.snapshotId)}
        </div>
        {mode === "scenario" ? (
          <>
            {named
              .map((c, k) => ({ c, k }))
              .reverse()
              .map(({ c, k }) => {
                const value = row.values[k];
                return (
                  <TipRow
                    key={c.scenario_id}
                    colour={SERIES_COLOURS[k]}
                    label={contributionLabel(c, assets).title}
                    value={value === undefined ? "not in snapshot" : formatInr(value)}
                  />
                );
              })}
            <TipRow
              colour="var(--other)"
              label={`${row.otherCount} other scenario${row.otherCount === 1 ? "" : "s"}`}
            />
            <TipRow total label="Expected annual loss" value={formatInr(row.eal)} />
          </>
        ) : (
          <>
            <TipRow colour="var(--s1)" label="Expected annual loss" value={formatInr(row.eal)} />
            <TipRow
              colour="var(--s7)"
              label={`Value at risk (${percentileLabel})`}
              value={formatInr(row.valueAtRisk)}
            />
          </>
        )}
      </>
    );
  }

  function onMove(event: MouseEvent<SVGSVGElement>) {
    const px = pointerX(event, width);
    let nearest = 0;
    for (let i = 1; i < rows.length; i++) {
      if (Math.abs(xs(i) - px) < Math.abs(xs(nearest) - px)) nearest = i;
    }
    setHover(nearest);
    setTip({ clientX: event.clientX, clientY: event.clientY, content: tooltipFor(nearest) });
  }

  const last = rows[rows.length - 1];

  return (
    <>
      <div className="ctrls" style={{ marginBottom: 10 }}>
        <div className="seg" role="group" aria-label="Show">
          <button type="button" aria-pressed={mode === "scenario"} onClick={() => setMode("scenario")}>
            By scenario
          </button>
          <button type="button" aria-pressed={mode === "tail"} onClick={() => setMode("tail")}>
            Mean &amp; tail
          </button>
        </div>
      </div>
      <Legend items={legend} />
      <div className="chart" ref={setNode} style={{ minHeight: height }}>
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Expected annual loss across ${rows.length} committed snapshots`}
            onMouseMove={onMove}
            onMouseLeave={() => {
              setHover(null);
              setTip(null);
            }}
          >
            <g className="ax">
              {ticks.map((tick) => (
                <g key={tick}>
                  <line className="grid-l" x1={margin.l} x2={margin.l + innerWidth} y1={ys(tick)} y2={ys(tick)} />
                  <text className="lbl" x={margin.l - 8} y={ys(tick) + 4} textAnchor="end">
                    {formatInrAxis(tick)}
                  </text>
                </g>
              ))}
              {labelled.map((i) => (
                <text
                  key={i}
                  className="lbl"
                  x={xs(i)}
                  y={height - 10}
                  textAnchor={i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle"}
                >
                  {Number.isFinite(rows[i].time) ? formatDayMonth(rows[i].time) : rows[i].observedAt.slice(0, 10)}
                </text>
              ))}
            </g>

            {mode === "scenario" ? (
              <>
                {bands.map((band, k) => (
                  <path key={k} d={band.d} style={{ fill: band.colour, opacity: 0.88, stroke: "var(--surface)", strokeWidth: 1.5, strokeLinejoin: "round" }} />
                ))}
                <path d={otherBand} style={{ fill: "var(--other)", opacity: 0.88, stroke: "var(--surface)", strokeWidth: 1.5 }} />
                {rows.map((row, i) => (
                  <circle key={i} cx={xs(i)} cy={ys(row.eal)} r={3} style={{ fill: "var(--ink)", stroke: "var(--surface)", strokeWidth: 1.5 }} />
                ))}
              </>
            ) : (
              <>
                <path
                  d={`${linePath(rows.map((r) => r.eal))}L${xs(rows.length - 1)},${ys(0)}L${xs(0)},${ys(0)}Z`}
                  style={{ fill: "var(--s1)", opacity: 0.1 }}
                />
                <path d={linePath(rows.map((r) => r.eal))} style={{ fill: "none", stroke: "var(--s1)", strokeWidth: 2 }} />
                <path d={linePath(rows.map((r) => r.valueAtRisk))} style={{ fill: "none", stroke: "var(--s7)", strokeWidth: 2 }} />
                {rows.map((row, i) => (
                  <g key={i}>
                    <circle cx={xs(i)} cy={ys(row.eal)} r={3} style={{ fill: "var(--s1)" }} />
                    <circle cx={xs(i)} cy={ys(row.valueAtRisk)} r={3} style={{ fill: "var(--s7)" }} />
                  </g>
                ))}
                <text className="dlabel" x={xs(rows.length - 1) - 6} y={ys(last.valueAtRisk) - 8} textAnchor="end">
                  VaR {formatInrCompact(last.valueAtRisk)}
                </text>
                <text className="dlabel" x={xs(rows.length - 1) - 6} y={ys(last.eal) - 8} textAnchor="end">
                  EAL {formatInrCompact(last.eal)}
                </text>
              </>
            )}

            <line x1={margin.l} x2={margin.l + innerWidth} y1={ys(0)} y2={ys(0)} style={{ stroke: "var(--ink-2)", opacity: 0.5 }} />
            {hover !== null ? (
              <line x1={xs(hover)} x2={xs(hover)} y1={margin.t} y2={margin.t + innerHeight} style={{ stroke: "var(--ink)", opacity: 0.35 }} />
            ) : null}
            <rect x={margin.l} y={margin.t} width={innerWidth} height={innerHeight} style={{ fill: "transparent", cursor: "crosshair" }} />
          </svg>
        ) : null}
      </div>
      <ChartTooltip tip={tip} />
      <div className="herofoot">
        <span>
          Latest snapshot ({formatDate(last.observedAt)}): EAL <b>{formatInr(last.eal)}</b>, VaR{" "}
          {percentileLabel} <b>{formatInr(last.valueAtRisk)}</b>
        </span>
        <span className="muted">
          {rows.length} committed snapshots, each re-simulated in full. A candidate snapshot that
          failed a quality gate was never committed, so it never becomes a point.
        </span>
      </div>
    </>
  );
}
