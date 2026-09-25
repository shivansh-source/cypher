import type { ReactNode } from "react";

export type LedeTone = "good" | "warn" | "crit" | "info";

/**
 * A section's one-line answer, stated before its detail: a tinted band with a
 * status badge, a headline and a supporting line.
 *
 * The tone is a status colour, so it must follow the facts it summarizes —
 * never "good" for anything short of every item passing on real evidence.
 */
export function Lede({
  tone,
  icon,
  title,
  children,
}: {
  tone: LedeTone;
  icon: string;
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className={`lede ${tone}`}>
      <span className="badge" aria-hidden="true">
        {icon}
      </span>
      <span>
        <b>{title}</b>
        {children ? <span className="small muted">{children}</span> : null}
      </span>
    </div>
  );
}
