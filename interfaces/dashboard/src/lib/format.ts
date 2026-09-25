/**
 * Display formatting for rupee figures and the metadata that qualifies them.
 *
 * Formatting here is presentation only: it never rounds a figure into a
 * different number and then lets that number be read back as the engine's
 * output. Compact forms (`₹4.25 Cr`) are always paired in the UI with the
 * exact value, so a rounded headline is never the only figure on screen.
 * The one exception is {@link formatInrAxis}, which labels chart gridlines —
 * positions on a scale, not figures.
 */

const LAKH = 100_000;
const CRORE = 10_000_000;
const DAY_MS = 86_400_000;
/**
 * Parse an ISO timestamp, reading one with no UTC offset as UTC — the same
 * rule the backend applies — rather than as the viewer's local time.
 */
function parseIso(iso: string): Date {
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  return new Date(hasOffset || isDateOnly ? iso : `${iso}Z`);
}

/** {@link parseIso} as epoch milliseconds (NaN if unreadable). */
export function parseIsoMs(iso: string): number {
  return parseIso(iso).getTime();
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Exact rupee amount with Indian digit grouping, e.g. `₹4,25,00,000`. */
export function formatInr(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Exact rupee change with an explicit sign, e.g. `+₹1,200` / `−₹76,245`. */
export function formatInrChange(value: number): string {
  const rounded = Math.round(value);
  if (rounded === 0) return formatInr(0);
  return `${rounded > 0 ? "+" : "−"}${formatInr(Math.abs(rounded))}`;
}

/**
 * Short rupee amount in Indian units, e.g. `₹4.25 Cr` / `₹12.50 L`.
 *
 * Lossy by construction — only ever used as a headline alongside the exact
 * value from {@link formatInr}, never as the sole representation of a figure.
 */
export function formatInrCompact(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= CRORE) return `${sign}₹${(abs / CRORE).toFixed(2)} Cr`;
  if (abs >= LAKH) return `${sign}₹${(abs / LAKH).toFixed(2)} L`;
  return `${sign}${formatInr(abs)}`;
}

/** A chart gridline label, e.g. `₹2.5 Cr`, `₹40 L`, `₹500k`. Never a figure. */
export function formatInrAxis(value: number): string {
  if (value === 0) return "₹0";
  const trim = (x: number) => String(Number(x.toFixed(2)));
  const abs = Math.abs(value);
  if (abs >= CRORE) return `₹${trim(value / CRORE)} Cr`;
  if (abs >= LAKH) return `₹${trim(value / LAKH)} L`;
  if (abs >= 1_000) return `₹${trim(value / 1_000)}k`;
  return `₹${trim(value)}`;
}

/** A fraction in [0,1] as a percentage string, e.g. 0.95 -> `95%`. */
export function formatPercent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Integer with Indian digit grouping, e.g. `50,000`. */
export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-IN").format(value);
}

/** A plain decimal for model parameters, trimmed of trailing zeros, e.g. `0.05`. */
export function formatDecimal(value: number, digits = 3): string {
  return String(Number(value.toFixed(digits)));
}

/**
 * An ISO timestamp as a readable UTC string.
 *
 * Rendered in UTC deliberately: a snapshot's `observed_at` is audit metadata,
 * and showing it in the viewer's local timezone would make two people reading
 * the same evidence disagree about when it was collected.
 */
export function formatTimestamp(iso: string): string {
  const parsed = parseIso(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return `${parsed.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

/** An ISO date or timestamp as a UTC calendar date, e.g. `20 Sep 2026`. */
export function formatDate(iso: string): string {
  const parsed = parseIso(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return `${parsed.getUTCDate()} ${MONTHS[parsed.getUTCMonth()]} ${parsed.getUTCFullYear()}`;
}

/** A UTC day and month, e.g. `20 Sep`, for chart axes. */
export function formatDayMonth(ms: number): string {
  const parsed = new Date(ms);
  return `${parsed.getUTCDate()} ${MONTHS[parsed.getUTCMonth()]}`;
}

/** Whole days from one ISO timestamp to another, or null if either is unreadable. */
export function daysBetween(fromIso: string, toIso: string): number | null {
  const from = parseIso(fromIso).getTime();
  const to = parseIso(toIso).getTime();
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return Math.max(0, Math.floor((to - from) / DAY_MS));
}

/** First 12 characters of a content-hash snapshot id, for dense display. */
export function shortSnapshotId(snapshotId: string): string {
  return snapshotId.length > 12 ? `${snapshotId.slice(0, 12)}…` : snapshotId;
}

/** Human names for the control categories `core.optimizer` can apply. */
const CONTROL_CATEGORY_LABELS: Record<string, string> = {
  mfa_enforced: "Enforce MFA",
  edr_active: "Deploy a healthy EDR agent",
  remediate_finding: "Fix a finding",
  harden_backup: "Harden backups",
};

export function controlCategoryLabel(category: string): string {
  return CONTROL_CATEGORY_LABELS[category] ?? category;
}

/** Snake-case engine labels (e.g. `internet_facing_critical_asset`) as words. */
export function humanize(label: string): string {
  return label.replaceAll("_", " ");
}

/**
 * The engine's scenario description without its parenthetical qualifier, e.g.
 * `cve CVE-2026-00001 on asset-web-01`. The full description stays available
 * wherever this short label is shown.
 */
export function scenarioLabel(contribution: { description: string }): string {
  const cut = contribution.description.indexOf(" (");
  return cut > 0 ? contribution.description.slice(0, cut) : contribution.description;
}

/**
 * Hours since an ISO timestamp, or null if it is unreadable. Reads the clock, so call it
 * only from code that runs per request (pages here fetch with `cache: "no-store"`).
 */
export function hoursSince(iso: string): number | null {
  const then = parseIso(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, (Date.now() - then) / (60 * 60 * 1000));
}

/** A coarse age such as `40 min ago`, `3 h ago` or `2 d ago`, or null if unreadable. */
export function formatAge(iso: string): string | null {
  const hours = hoursSince(iso);
  if (hours === null) return null;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  if (hours < 48) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
