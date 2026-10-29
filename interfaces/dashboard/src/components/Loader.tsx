import { CypherMark } from "./CypherMark";

/** Small inline ring for buttons and status lines. Decorative: pair it with visible text. */
export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden="true" />;
}

/**
 * Centered loader for a whole page or region: the brand mark with a ring
 * around it, a label, and a polite live announcement for screen readers.
 */
export function PageLoader({ label = "Loading…", fill = false }: { label?: string; fill?: boolean }) {
  return (
    <div className={`page-loader${fill ? " fill" : ""}`} role="status" aria-live="polite" aria-busy="true">
      <div className="pl-mark" aria-hidden="true">
        <span className="pl-ring" />
        <CypherMark />
      </div>
      <p>{label}</p>
    </div>
  );
}
