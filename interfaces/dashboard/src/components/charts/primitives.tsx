"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";

/** Series colours for the first five named series; everything else is `--other`. */
export const SERIES_COLOURS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"];

/**
 * Track an element's rendered width, so SVG charts can be drawn at 1:1 scale
 * (crisp text, correct hit-testing) rather than stretched by a viewBox.
 * Width is 0 until the first measurement; charts render nothing until then.
 */
export function useElementWidth<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [node, setNode] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      setWidth(Math.floor(entries[0].contentRect.width));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, width];
}

export interface TipState {
  clientX: number;
  clientY: number;
  content: ReactNode;
}

/**
 * The shared hover tooltip, positioned beside the pointer and kept inside the
 * viewport. Positioning is applied to the DOM node directly after layout, since
 * it depends on the tooltip's own rendered size.
 */
export function ChartTooltip({ tip }: { tip: TipState | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || !tip) return;
    const rect = element.getBoundingClientRect();
    let x = tip.clientX + 14;
    let y = tip.clientY + 14;
    if (x + rect.width > window.innerWidth - 8) x = tip.clientX - rect.width - 14;
    if (y + rect.height > window.innerHeight - 8) y = tip.clientY - rect.height - 14;
    element.style.left = `${Math.max(8, x)}px`;
    element.style.top = `${Math.max(8, y)}px`;
  }, [tip]);
  if (!tip) return null;
  return (
    <div className="tip" ref={ref} role="tooltip">
      {tip.content}
    </div>
  );
}

/** A tooltip row: optional swatch, label, value. */
export function TipRow({
  colour,
  label,
  value,
  total = false,
}: {
  colour?: string;
  label: ReactNode;
  value?: ReactNode;
  total?: boolean;
}) {
  return (
    <div className={`r${total ? " tot" : ""}`}>
      <span>
        {colour ? <i className="sw" style={{ background: colour }} /> : null}
        {label}
      </span>
      {value !== undefined ? <b>{value}</b> : null}
    </div>
  );
}

export interface LegendItem {
  label: string;
  colour: string;
  kind?: "area" | "line";
  title?: string;
}

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span key={item.label} title={item.title}>
          <i className={`sw${item.kind === "line" ? " line" : ""}`} style={{ background: item.colour }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

function niceStep(raw: number): number {
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const fraction = raw / power;
  return (fraction < 1.5 ? 1 : fraction < 3 ? 2 : fraction < 7 ? 5 : 10) * power;
}

/** Evenly spaced "nice" ticks from 0 up to at least `max`. */
export function niceTicks(max: number, count: number): number[] {
  if (!(max > 0)) return [0, 1];
  const step = niceStep(max / count);
  const ticks: number[] = [];
  for (let value = 0; value < max + step * 1e-9; value += step) ticks.push(value);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

/** Map a pointer event to an x coordinate in the SVG's own user units. */
export function pointerX(event: MouseEvent<SVGSVGElement>, width: number): number {
  const rect = event.currentTarget.getBoundingClientRect();
  return ((event.clientX - rect.left) * width) / rect.width;
}
