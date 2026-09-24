import type { ReactNode } from "react";
import { formatInr, formatInrCompact } from "@/lib/format";
import { SampleTag } from "./DemoBanner";

/** The KPI strip container. */
export function KpiStrip({ children }: { children: ReactNode }) {
  return <div className="kpis">{children}</div>;
}

/**
 * A headline rupee figure in the KPI strip.
 *
 * Always renders the compact form *and* the exact rupee value: a rounded
 * headline is never the only representation of a figure on screen, so nobody
 * can quote `₹4.25 Cr` without the precise number being right there. The
 * `SAMPLE` tag is attached here so that no figure can be rendered in demo mode
 * without carrying its own label.
 */
export function RupeeKpi({
  label,
  valueInr,
  note,
  hero = false,
}: {
  label: string;
  valueInr: number;
  note?: ReactNode;
  hero?: boolean;
}) {
  return (
    <div className="kpi">
      <span className="eyebrow">
        {label}
        <SampleTag />
      </span>
      <span className={`v num${hero ? " hero" : ""}`}>{formatInrCompact(valueInr)}</span>
      <span className="exact">{formatInr(valueInr)}</span>
      {note ? <span className="s">{note}</span> : null}
    </div>
  );
}

/** A non-rupee KPI (a count or a coverage ratio). */
export function Kpi({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="kpi">
      <span className="eyebrow">{label}</span>
      <span className="v num">{value}</span>
      {note ? <span className="s">{note}</span> : null}
    </div>
  );
}
