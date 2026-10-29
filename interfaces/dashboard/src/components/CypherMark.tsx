/**
 * Cypher's brand mark: the wide-brimmed, masked figure from the product logo
 * (repo-root `cypher.png`). `public/cypher-mark-small.png` is that artwork's line
 * work with the strokes thickened so it still reads at 16-34px, white on
 * transparency; it is used here only as a mask, so the mark is drawn in
 * `currentColor` and follows the theme like any icon. The full-detail version
 * is `public/cypher-mark.png` (the sign-in and register pages).
 */
const MARK_SRC = "/cypher-mark-small.png";

/** Width / height of the mark artwork. */
const MARK_ASPECT = 256 / 180;

/**
 * The mark for embedding inside another 24-unit SVG (the setup screen's
 * telemetry map). Filled with the parent's `color`.
 */
export function CypherMarkShapes() {
  const height = 24 / MARK_ASPECT;
  return (
    <>
      <defs>
        <mask id="cypher-mark-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24">
          <image href={MARK_SRC} x="0" y={(24 - height) / 2} width="24" height={height} />
        </mask>
      </defs>
      <rect width="24" height="24" fill="currentColor" stroke="none" mask="url(#cypher-mark-mask)" />
    </>
  );
}

/** The mark as an inline element; the parent sets its colour (`color`) and width. */
export function CypherMark({ className }: { className?: string }) {
  return <span className={`cypher-mark${className ? ` ${className}` : ""}`} aria-hidden="true" />;
}
