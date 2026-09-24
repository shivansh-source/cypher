import type { ControlStatusValue } from "@/lib/types";

/**
 * Visual encoding of a control's evidence-derived status.
 *
 * `unknown` and `expired_attestation` are deliberately given their own
 * non-green treatments rather than being folded in with `met`: "we have no
 * evidence" and "the evidence we had has expired" are distinct findings, and
 * rendering either as a pass would be the exact fail-open reading the
 * governance layer exists to prevent.
 */
export const CONTROL_STATUS_STYLES: Record<
  ControlStatusValue,
  { label: string; pill: string; icon: string; colour: string }
> = {
  met: { label: "Met", pill: "good", icon: "✓", colour: "var(--good)" },
  not_met: { label: "Not met", pill: "crit", icon: "✕", colour: "var(--crit)" },
  expired_attestation: {
    label: "Attestation expired",
    pill: "warn",
    icon: "◷",
    colour: "var(--warn)",
  },
  unknown: { label: "Undetermined", pill: "info", icon: "?", colour: "var(--other)" },
};

/** Worst first — the order statuses are listed, counted and stacked in. */
export const CONTROL_STATUS_ORDER: ControlStatusValue[] = [
  "not_met",
  "expired_attestation",
  "unknown",
  "met",
];

export function ControlStatusPill({ status }: { status: ControlStatusValue }) {
  const style = CONTROL_STATUS_STYLES[status];
  return (
    <span className={`pill ${style.pill}`}>
      <span aria-hidden="true">{style.icon}</span> {style.label}
    </span>
  );
}

export function PassFailPill({ passed }: { passed: boolean }) {
  return (
    <span className={`pill ${passed ? "good" : "crit"}`}>
      <span aria-hidden="true">{passed ? "✓" : "✕"}</span> {passed ? "Pass" : "Fail"}
    </span>
  );
}
