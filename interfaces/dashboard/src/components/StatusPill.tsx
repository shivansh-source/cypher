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
const CONTROL_STATUS_STYLES: Record<
  ControlStatusValue,
  { label: string; className: string }
> = {
  met: { label: "Met", className: "border-ok/40 bg-ok/10 text-ok" },
  not_met: {
    label: "Not met",
    className: "border-danger/40 bg-danger/10 text-danger",
  },
  unknown: {
    label: "Unknown",
    className: "border-line bg-surface-2 text-muted",
  },
  expired_attestation: {
    label: "Attestation expired",
    className: "border-warn/40 bg-warn/10 text-warn",
  },
};

export function ControlStatusPill({ status }: { status: ControlStatusValue }) {
  const style = CONTROL_STATUS_STYLES[status];
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${style.className}`}
    >
      {style.label}
    </span>
  );
}

export function PassFailPill({ passed }: { passed: boolean }) {
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${
        passed
          ? "border-ok/40 bg-ok/10 text-ok"
          : "border-danger/40 bg-danger/10 text-danger"
      }`}
    >
      {passed ? "Pass" : "Fail"}
    </span>
  );
}
