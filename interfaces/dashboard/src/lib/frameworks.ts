/**
 * The regulatory frameworks the backend's control library holds
 * (`governance/control_library/*.yaml`), and which of them apply to which
 * kind of org.
 *
 * `frameworksForEntity` is guidance text for the setup screen only: it never
 * changes what the compliance view computes (every library is always
 * evaluated), and it never claims a framework the library does not hold. In
 * particular the RBI file is the Directions for NBFCs; RBI's Directions are
 * entity-specific (repo-root `CLAUDE.md`, principle 8), so a bank is not told
 * that file applies to it.
 */

/** Display names for the framework keys under governance/control_library/. */
export const FRAMEWORK_LABELS: Record<string, string> = {
  rbi_2026_directions: "RBI Directions 2026",
  sebi_cscrf_cci: "SEBI CSCRF + CCI",
  cis_controls: "CIS Controls",
  nist_csf: "NIST CSF",
  iso_27001: "ISO/IEC 27001",
  dpdp_act_2023: "DPDP Act 2023",
};

/** The regulator-led frameworks first; any library not named here follows. */
export const FRAMEWORK_ORDER = Object.keys(FRAMEWORK_LABELS);

export function frameworkLabel(key: string): string {
  return FRAMEWORK_LABELS[key] ?? key;
}

export type EntityType = "nbfc" | "bank" | "sebi" | "other";

export const ENTITY_TYPES: { id: EntityType; label: string; hint: string }[] = [
  { id: "nbfc", label: "NBFC", hint: "Non-banking financial company" },
  { id: "bank", label: "Bank", hint: "Scheduled commercial or cooperative bank" },
  { id: "sebi", label: "SEBI-regulated", hint: "Broker, depository, AMC, exchange" },
  { id: "other", label: "Other", hint: "Any other organisation" },
];

export interface EntityFrameworks {
  /** Mandatory frameworks the control library holds for this kind of org. */
  mandatory: string[];
  /** Voluntary baselines worth tracking. */
  voluntary: string[];
  /** A caveat to show as-is, e.g. a regulator whose rules the library lacks. */
  note?: string;
}

export function frameworksForEntity(type: EntityType): EntityFrameworks {
  switch (type) {
    case "nbfc":
      return { mandatory: ["rbi_2026_directions", "dpdp_act_2023"], voluntary: ["iso_27001"] };
    case "sebi":
      return { mandatory: ["sebi_cscrf_cci", "dpdp_act_2023"], voluntary: ["iso_27001"] };
    case "bank":
      return {
        mandatory: ["dpdp_act_2023"],
        voluntary: ["iso_27001"],
        note: "RBI's Directions for banks aren't in the control library yet, so bank-specific RBI controls won't be mapped.",
      };
    case "other":
      return {
        mandatory: ["dpdp_act_2023"],
        voluntary: ["cis_controls", "nist_csf", "iso_27001"],
        note: "The DPDP Act applies if you process personal data of people in India.",
      };
  }
}
