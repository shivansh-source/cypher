"use client";

import { useState, type MouseEvent } from "react";
import {
  formatCount,
  formatInr,
  formatInrAxis,
  formatInrCompact,
  formatPercent,
} from "@/lib/format";
import type { LossExceedanceCurve } from "@/lib/types";
import {
  ChartTooltip,
  Legend,
  TipRow,
  niceTicks,
  pointerX,
  useElementWidth,
  type TipState,
} from "./primitives";

/**
 * The loss exceedance curve (`GET /exposure/exceedance`): for each annual loss
 * on a log scale, the share of simulated years whose total loss exceeded it.
 *
 * The curve is read by the engine off the same simulated years as the headline
 * Expected Annual Loss and Value at Risk, which are marked on it as given.
 * Nothing here fits, smooths or extrapolates the curve.
 */
export function LossExceedanceChart({
  curve,
  expectedAnnualLoss,
  valueAtRisk,
  valueAtRiskPercentile,
}: {
  curve: LossExceedanceCurve;
  expectedAnnualLoss: number;
  valueAtRisk: number;
  valueAtRiskPercentile: number;
}) {
  const [setNode, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const percentileLabel = formatPercent(valueAtRiskPercentile);
  const points = curve.points;

  if (points.length === 0) {
    return (
      <p className="notice info">
        None of the {formatCount(curve.monte_carlo_iterations)} simulated years produced a loss,
        so there is no curve to draw.
      </p>
    );
  }

  const mobile = width < 560;
  const height = mobile ? 250 : 290;
  const margin = { l: 46, r: 16, t: 14, b: 30 };
  const innerWidth = Math.max(0, width - margin.l - margin.r);
  const innerHeight = height - margin.t - margin.b;

  const markers = [expectedAnnualLoss, valueAtRisk].filter((v) => v > 0);
  const low = Math.min(points[0].loss_inr, ...markers);
  const high = Math.max(points[points.length - 1].loss_inr, ...markers);
  const logLow = Math.log10(low);
  const logSpan = Math.log10(high) - logLow;
  const xs = (loss: number) =>
    margin.l + (logSpan > 0 ? (Math.log10(loss) - logLow) / logSpan : 0.5) * innerWidth;

  const yTicks = niceTicks(Math.min(1, curve.probability_of_any_loss * 1.05), 4).filter(
    (t) => t <= 1 + 1e-9,
  );
  const yMax = yTicks[yTicks.length - 1];
  const ys = (p: number) => margin.t + innerHeight - (p / yMax) * innerHeight;

  const xTicks: number[] = [];
  for (let e = Math.ceil(logLow); e <= Math.floor(Math.log10(high)); e++) xTicks.push(10 ** e);
  if (xTicks.length < 2) {
    xTicks.splice(0, xTicks.length, low, high);
  }

  const line = points
    .map((p, i) => `${i ? "L" : "M"}${xs(p.loss_inr)},${ys(p.exceedance_probability)}`)
    .join("");
  const area = `${line}L${xs(points[points.length - 1].loss_inr)},${ys(0)}L${xs(points[0].loss_inr)},${ys(0)}Z`;

  function onMove(event: MouseEvent<SVGSVGElement>) {
    const px = pointerX(event, width);
    let nearest = 0;
    for (let i = 1; i < points.length; i++) {
      if (Math.abs(xs(points[i].loss_inr) - px) < Math.abs(xs(points[nearest].loss_inr) - px)) {
        nearest = i;
      }
    }
    const point = points[nearest];
    setHover(nearest);
    setTip({
      clientX: event.clientX,
      clientY: event.clientY,
      content: (
        <>
          <div className="t">Annual loss above {formatInr(point.loss_inr)}</div>
          <TipRow
            colour="var(--s1)"
            label="Share of simulated years"
            value={formatPercent(point.exceedance_probability, 1)}
          />
        </>
      ),
    });
  }

  const marker = (value: number, label: string, colour: string, dy: number) => {
    const x = xs(value);
    const right = x > margin.l + innerWidth * 0.7;
    return (
      <g key={label}>
        <line x1={x} x2={x} y1={margin.t} y2={margin.t + innerHeight} style={{ stroke: colour, strokeWidth: 1, opacity: 0.7 }} />
        <text className="dlabel" x={x + (right ? -5 : 5)} y={margin.t + 12 + dy} textAnchor={right ? "end" : "start"}>
          {label}
        </text>
      </g>
    );
  };

  return (
    <>
      <Legend
        items={[
          { label: "Current snapshot", colour: "var(--s1)", kind: "line" },
          { label: "Expected annual loss", colour: "var(--ink-2)", kind: "line" },
          { label: `Value at risk (${percentileLabel})`, colour: "var(--s7)", kind: "line" },
        ]}
      />
      <div className="chart" ref={setNode} style={{ minHeight: height }}>
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Loss exceedance curve"
            onMouseMove={onMove}
            onMouseLeave={() => {
              setHover(null);
              setTip(null);
            }}
          >
            <g className="ax">
              {yTicks.map((tick) => (
                <g key={tick}>
                  <line className="grid-l" x1={margin.l} x2={margin.l + innerWidth} y1={ys(tick)} y2={ys(tick)} />
                  <text className="lbl" x={margin.l - 8} y={ys(tick) + 4} textAnchor="end">
                    {formatPercent(tick)}
                  </text>
                </g>
              ))}
              {xTicks.map((tick, i) => (
                <g key={tick}>
                  <line className="grid-l" x1={xs(tick)} x2={xs(tick)} y1={margin.t} y2={margin.t + innerHeight} />
                  <text
                    className="lbl"
                    x={xs(tick)}
                    y={height - 10}
                    textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
                  >
                    {formatInrAxis(tick)}
                  </text>
                </g>
              ))}
            </g>
            <path d={area} style={{ fill: "var(--s1)", opacity: 0.1 }} />
            <path d={line} style={{ fill: "none", stroke: "var(--s1)", strokeWidth: 2 }} />
            {expectedAnnualLoss > 0
              ? marker(expectedAnnualLoss, `EAL ${formatInrCompact(expectedAnnualLoss)}`, "var(--ink-2)", 0)
              : null}
            {valueAtRisk > 0
              ? marker(valueAtRisk, `VaR ${percentileLabel} ${formatInrCompact(valueAtRisk)}`, "var(--s7)", 16)
              : null}
            {hover !== null ? (
              <circle
                cx={xs(points[hover].loss_inr)}
                cy={ys(points[hover].exceedance_probability)}
                r={4}
                style={{ fill: "var(--s1)", stroke: "var(--surface)", strokeWidth: 2 }}
              />
            ) : null}
            <rect x={margin.l} y={margin.t} width={innerWidth} height={innerHeight} style={{ fill: "transparent", cursor: "crosshair" }} />
          </svg>
        ) : null}
      </div>
      <ChartTooltip tip={tip} />
      <p className="small muted" style={{ marginTop: 6 }}>
        From {formatCount(curve.monte_carlo_iterations)} simulated years;{" "}
        {formatPercent(curve.probability_of_any_loss, 1)} of them had any loss at all.
        {valueAtRisk > 0
          ? null
          : ` Value at risk (${percentileLabel}) is ₹0: at most ${formatPercent(1 - valueAtRiskPercentile)} of simulated years had a loss.`}
      </p>
    </>
  );
}
