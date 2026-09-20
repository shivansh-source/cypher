/**
 * Display formatting for rupee figures and the metadata that qualifies them.
 *
 * Formatting here is presentation only: it never rounds a figure into a
 * different number and then lets that number be read back as the engine's
 * output. Compact forms (`₹4.25 Cr`) are always paired in the UI with the
 * exact value, so a rounded headline is never the only figure on screen.
 */

const LAKH = 100_000;
const CRORE = 10_000_000;

/** Exact rupee amount with Indian digit grouping, e.g. `₹4,25,00,000`. */
export function formatInr(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Short rupee amount in Indian units, e.g. `₹4.25 Cr` / `₹12.5 L`.
 *
 * Lossy by construction — only ever used as a headline alongside the exact
 * value from {@link formatInr}, never as the sole representation of a figure.
 */
export function formatInrCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= CRORE) return `₹${(value / CRORE).toFixed(2)} Cr`;
  if (abs >= LAKH) return `₹${(value / LAKH).toFixed(2)} L`;
  return formatInr(value);
}

/** A fraction in [0,1] as a percentage string, e.g. 0.95 -> `95%`. */
export function formatPercent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Integer with Indian digit grouping, e.g. `50,000`. */
export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-IN").format(value);
}

/**
 * An ISO timestamp as a readable UTC string.
 *
 * Rendered in UTC deliberately: a snapshot's `observed_at` is audit metadata,
 * and showing it in the viewer's local timezone would make two people reading
 * the same evidence disagree about when it was collected.
 */
export function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return `${parsed.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

/** First 12 characters of a content-hash snapshot id, for dense display. */
export function shortSnapshotId(snapshotId: string): string {
  return snapshotId.length > 12 ? `${snapshotId.slice(0, 12)}…` : snapshotId;
}
