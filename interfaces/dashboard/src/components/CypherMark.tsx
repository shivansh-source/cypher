/**
 * The mark's strokes on a 24-unit grid, for embedding inside another SVG
 * (the setup screen's telemetry map). Inherits stroke styling from its parent.
 */
export function CypherMarkShapes() {
  return (
    <>
      <circle cx="12" cy="3.9" r="1.5" />
      <path d="M8.9 9.6l1.2-3.1h3.8l1.2 3.1" />
      <path d="M1.8 11.4l7-1.8h6.4l7 1.8-10.2 2.9z" />
      <path d="M8.7 13.6v3.9l2.9 3h2.7l2.4-2.8.6-5" />
      <circle cx="14" cy="16" r="1.1" />
    </>
  );
}

/**
 * Cypher's small brand mark: the wide-brimmed, masked figure from the full
 * logo (`public/cypher-logo.svg`), redrawn as an outline icon in the same style as the
 * nav icons (24-unit grid, 1.7 stroke, round caps and joins) so it sits with
 * them and still reads at 16-34px.
 *
 * Drawn in `currentColor` with no fill; the parent sets the colour and size.
 */
export function CypherMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <CypherMarkShapes />
    </svg>
  );
}
