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
    <div className="border-b border-sample/40 bg-sample/10 px-6 py-2.5 text-center text-xs text-sample">
      <strong className="font-bold tracking-wide">SAMPLE DATA —</strong>{" "}
      demo mode is on. Every figure shown is illustrative, was not produced by
      the FAIR engine, and must not be cited as a result.
    </div>
  );
}
