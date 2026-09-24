import { DEMO_MODE } from "@/lib/api";

/**
 * Persistent, non-dismissible notice that the figures on screen are invented.
 *
 * Non-dismissible on purpose: a banner that can be closed is a banner that is
 * absent from the screenshot someone later presents as a result. It renders on
 * every page whenever `NEXT_PUBLIC_DEMO_MODE=1`, and nothing else in the UI
 * can suppress it.
 */
export function DemoBanner() {
  if (!DEMO_MODE) return null;
  return (
    <div className="demo-banner" role="note">
      <strong>SAMPLE DATA —</strong> demo mode is on. Every figure shown is
      illustrative, was not produced by the FAIR engine, and must not be cited
      as a result.
    </div>
  );
}

/**
 * The per-figure `SAMPLE` tag. Attached next to figures rather than only at
 * the page level, so that no figure can render in demo mode without carrying
 * its own label.
 */
export function SampleTag() {
  if (!DEMO_MODE) return null;
  return <span className="sample-tag">SAMPLE</span>;
}
