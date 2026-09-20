import { DEMO_MODE } from "@/lib/api";
import { formatInr, formatInrCompact } from "@/lib/format";

/**
 * A headline rupee figure.
 *
 * Always renders the compact form *and* the exact rupee value: a rounded
 * headline is never the only representation of a figure on screen, so nobody
 * can quote `₹4.25 Cr` without the precise number being right there. The
 * `SAMPLE` tag is attached here rather than at the page level so that no
 * figure can be rendered in demo mode without carrying its own label.
 */
export function FigureCard({
  label,
  valueInr,
  qualifier,
  tone = "neutral",
}: {
  label: string;
  valueInr: number;
  /** What qualifies the number, e.g. "at the 95th percentile". */
  qualifier?: string;
  tone?: "neutral" | "danger" | "ok";
}) {
  const toneClass =
    tone === "danger"
      ? "text-danger"
      : tone === "ok"
        ? "text-ok"
        : "text-ink";

  return (
    <div className="rounded-lg border border-line bg-surface-2 p-5">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold tracking-wider text-muted uppercase">
          {label}
        </h3>
        {DEMO_MODE ? (
          <span className="rounded border border-sample/50 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-sample">
            SAMPLE
          </span>
        ) : null}
      </div>
      <p
        className={`tnum mt-3 text-4xl leading-none font-semibold ${toneClass}`}
      >
        {formatInrCompact(valueInr)}
      </p>
      <p className="tnum mt-2 text-sm text-muted">{formatInr(valueInr)}</p>
      {qualifier ? (
        <p className="mt-2 text-xs text-faint">{qualifier}</p>
      ) : null}
    </div>
  );
}
