import { useState, type CSSProperties } from "react";
import { CypherMarkShapes } from "@/components/CypherMark";
import type { CategoryCoverage, ChannelState } from "@/lib/coverage";
import { CATEGORY_INFO, type ToolCategory } from "@/lib/tool-catalog";

/* Geometry, in viewBox units (0 0 340 200). Display layout only. */
const W = 340;
const H = 200;
const ROW0 = 22;
const ROW_GAP = 31;
const LABEL_W = 98;
const START_X = 106;
const ENGINE = { x: 216, y: 99.5, r: 20 };
const DEST = { x: 310, y: 99.5, r: 18 };

const STATE_TEXT: Record<ChannelState, string> = {
  off: "not covered",
  declared: "declared, no connector yet",
  connected: "connects today",
};

/**
 * A solid line that draws itself in if motion was allowed when it mounted.
 * Captured once, on mount: lines that exist when a returning org's saved
 * picks load appear instantly, and only lines created by a pick animate.
 */
function DrawnPath({ className, d, animate }: { className: string; d: string; animate: boolean }) {
  const [draw] = useState(animate);
  return <path className={`${className}${draw ? " draw" : ""}`} d={d} pathLength={100} />;
}

function channelPath(y: number): string {
  const end = ENGINE.x - ENGINE.r;
  return `M${START_X} ${y} C${START_X + 44} ${y} ${end - 36} ${ENGINE.y} ${end} ${ENGINE.y}`;
}

/**
 * The setup screen's live map of where the org's telemetry comes from: one
 * channel per kind of telemetry, converging on the engine, which produces
 * the rupee figures. It shows coverage, never a figure.
 *
 * A channel's solid line is keyed by its state, so it re-draws whenever the
 * state changes; `pulse` (the last category picked, and a counter) sends one
 * signal down that channel into the engine. `intro` plays the one-time
 * entrance on an org's first visit. All motion is CSS, off under
 * reduced-motion.
 */
export function TelemetryMap({
  coverage,
  pulse,
  intro,
  animate,
  onJump,
}: {
  coverage: CategoryCoverage[];
  pulse: { category: ToolCategory; n: number } | null;
  intro: boolean;
  /** Whether lines created from now on may animate (the org has started picking). */
  animate: boolean;
  onJump: (category: ToolCategory) => void;
}) {
  const covered = coverage.filter((c) => c.state !== "off").length;
  const connected = coverage.some((c) => c.state === "connected");
  const summary = `Telemetry map: ${covered} of ${coverage.length} kinds of telemetry covered. ${coverage
    .map((c) => `${c.category}: ${STATE_TEXT[c.state]}`)
    .join("; ")}.`;

  return (
    <div className={`tmap${intro ? " intro" : ""}`}>
      <div className="tmap-canvas">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
          {coverage.map((c, i) => {
            const y = ROW0 + ROW_GAP * i;
            const d = channelPath(y);
            return (
              <g
                key={c.category}
                className="ch"
                data-state={c.state}
                style={{ "--i": i } as CSSProperties}
              >
                <text className="ch-label" x="0" y={y + 4}>
                  {CATEGORY_INFO[c.category].short}
                </text>
                <path className="ch-track" d={d} pathLength={100} />
                {c.state !== "off" ? (
                  <DrawnPath key={c.state} className="ch-line" d={d} animate={animate} />
                ) : null}
                {pulse && pulse.category === c.category && c.state !== "off" ? (
                  <path key={pulse.n} className="ch-pulse" d={d} pathLength={100} />
                ) : null}
                <circle className="ch-dot" cx={START_X} cy={y} r="3.2" />
              </g>
            );
          })}

          <g className={`engine${covered ? " on" : ""}`}>
            {pulse ? <circle key={pulse.n} className="engine-ping" cx={ENGINE.x} cy={ENGINE.y} r={ENGINE.r} /> : null}
            <circle className="engine-ring" cx={ENGINE.x} cy={ENGINE.y} r={ENGINE.r} />
            <svg
              x={ENGINE.x - 12}
              y={ENGINE.y - 12}
              width="24"
              height="24"
              viewBox="0 0 24 24"
              className="engine-mark"
            >
              <CypherMarkShapes />
            </svg>
          </g>

          <g className={`out${covered ? " on" : ""}${connected ? " live" : ""}`}>
            <path className="out-track" d={`M${ENGINE.x + ENGINE.r + 2} ${ENGINE.y} H${DEST.x - DEST.r - 4}`} />
            {covered ? (
              <DrawnPath
                key="out"
                className="out-line"
                d={`M${ENGINE.x + ENGINE.r + 2} ${ENGINE.y} H${DEST.x - DEST.r - 4}`}
                animate={animate}
              />
            ) : null}
            <path
              className="out-head"
              d={`M${DEST.x - DEST.r - 9} ${ENGINE.y - 4.5} L${DEST.x - DEST.r - 3.5} ${ENGINE.y} L${DEST.x - DEST.r - 9} ${ENGINE.y + 4.5}`}
            />
            <circle className="dest-ring" cx={DEST.x} cy={DEST.y} r={DEST.r} />
            <text className="dest-rupee" x={DEST.x} y={DEST.y + 6.5}>
              ₹
            </text>
            <text className="dest-label" x={DEST.x} y={DEST.y + DEST.r + 16}>
              EAL &amp; VaR
            </text>
          </g>
        </svg>

        {coverage.map((c, i) => {
          const y = ROW0 + ROW_GAP * i;
          return (
            <button
              key={c.category}
              type="button"
              className="tmap-hit"
              style={{
                top: `${((y - 13) / H) * 100}%`,
                height: `${(26 / H) * 100}%`,
                width: `${(LABEL_W / W) * 100}%`,
              }}
              onClick={() => onJump(c.category)}
              aria-label={`${c.category}: ${STATE_TEXT[c.state]}. Go to its tools`}
            />
          );
        })}
      </div>

      <p className="tmap-summary">
        {covered === 0 ? (
          "Pick the tools you run and watch each kind of telemetry reach the engine."
        ) : (
          <>
            Figures will reflect{" "}
            <b>
              {covered} of {coverage.length}
            </b>{" "}
            kinds of telemetry.
          </>
        )}
      </p>
      <ul className="tmap-legend" aria-hidden="true">
        <li data-state="connected">Connects today</li>
        <li data-state="declared">Declared, no connector</li>
        <li data-state="off">Not covered</li>
      </ul>
    </div>
  );
}
