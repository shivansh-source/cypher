import type { ReactNode } from "react";

/**
 * A small "i" button that reveals an explanation on hover or keyboard focus.
 *
 * For standing caveats that must stay one step away rather than on screen as
 * a paragraph. `id` must be unique on the page: it ties the tooltip to the
 * button for screen readers.
 */
export function InfoTip({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <span className="info">
      <button type="button" className="info-btn" aria-label={label} aria-describedby={id}>
        i
      </button>
      <span role="tooltip" id={id} className="info-tip">
        {children}
      </span>
    </span>
  );
}
