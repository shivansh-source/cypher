/**
 * The tools an org can tell Cypher it uses, and whether a connector exists
 * for it today.
 *
 * "Available" means `infra/connectors/` has a normalizer for it *and*
 * `interfaces/cli/cypher.py::ingest_command` actually calls it during
 * `cypher ingest` — the two things that together decide whether selecting
 * a tool here does anything real yet. A tool marked "Not yet supported" may
 * still have a connector module started in the repo (e.g. Nessus, Nmap) —
 * that distinction is not exposed here, because from the ingest pipeline's
 * point of view an unwired connector does nothing, same as no connector at
 * all.
 *
 * This list, and which tools are "ours", is presentation data only. Nothing
 * here is read by the backend — see `ToolSelectionNote` in
 * `tool-selection-state.ts` for exactly what this screen does and doesn't
 * control today.
 */

export type ToolCategory =
  | "Vulnerability scanning"
  | "Cloud security posture"
  | "Endpoint detection & response"
  | "Identity & access"
  | "Network exposure"
  | "Asset inventory";

export interface ToolOption {
  id: string;
  name: string;
  category: ToolCategory;
  /** What it's for, in one short phrase — shown under the name. */
  blurb: string;
  available: boolean;
  /** Set only when `available`: the connector module backing it. */
  connector?: string;
  /** Two-letter monogram, shown when there is no `logo` (and as the image's fallback). */
  mark: string;
  /** Path under `public/` to the tool's logo — see `public/logos/README.md` for sources. */
  logo?: string;
  /** Which series colour token (`--s1`..`--s8`) tints the icon tile. */
  tone: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
}

export const CATEGORY_ORDER: ToolCategory[] = [
  "Vulnerability scanning",
  "Cloud security posture",
  "Endpoint detection & response",
  "Identity & access",
  "Network exposure",
  "Asset inventory",
];

/** How each category reaches the rupee figure, in the engine's own terms. */
export const CATEGORY_INFO: Record<
  ToolCategory,
  {
    /** A short name for the telemetry map's channel label. */
    short: string;
    /** What its findings feed in the model. */
    feeds: string;
    /** What the figures lack without any source for it. */
    gap: string;
  }
> = {
  "Vulnerability scanning": {
    short: "Vulnerabilities",
    feeds: "Feeds exploit likelihood for every host and service",
    gap: "no host or network vulnerabilities",
  },
  "Cloud security posture": {
    short: "Cloud posture",
    feeds: "Feeds cloud misconfigurations, the most common cloud breach path",
    gap: "no cloud misconfigurations",
  },
  "Endpoint detection & response": {
    short: "Endpoints",
    feeds: "Feeds how often an attack is caught before it becomes a loss",
    gap: "no EDR credit on any asset",
  },
  "Identity & access": {
    short: "Identity",
    feeds: "Feeds MFA coverage and who holds privileged access",
    gap: "no MFA or privilege posture",
  },
  "Network exposure": {
    short: "Exposure",
    feeds: "Feeds which assets an attacker can reach from the internet",
    gap: "no open-port exposure",
  },
  "Asset inventory": {
    short: "Inventory",
    feeds: "Ties every finding to one real asset, so nothing is counted twice",
    gap: "no canonical asset identity",
  },
};

export const TOOL_CATALOG: ToolOption[] = [
  {
    id: "greenbone",
    name: "Greenbone (OpenVAS/GVM)",
    category: "Vulnerability scanning",
    blurb: "Network and host vulnerability scanning",
    available: true,
    connector: "greenbone_connector",
    mark: "Gb",
    tone: 3,
    logo: "/logos/greenbone.png",
  },
  {
    id: "nessus",
    name: "Tenable Nessus",
    category: "Vulnerability scanning",
    blurb: "Network and host vulnerability scanning",
    available: false,
    mark: "Ns",
    tone: 1,
    logo: "/logos/nessus.png",
  },
  {
    id: "qualys",
    name: "Qualys VMDR",
    category: "Vulnerability scanning",
    blurb: "Vulnerability management, detection and response",
    available: false,
    mark: "Qy",
    tone: 8,
    logo: "/logos/qualys.svg",
  },
  {
    id: "insightvm",
    name: "Rapid7 InsightVM",
    category: "Vulnerability scanning",
    blurb: "Vulnerability risk management",
    available: false,
    mark: "R7",
    tone: 2,
    logo: "/logos/insightvm.png",
  },
  {
    id: "prowler",
    name: "Prowler",
    category: "Cloud security posture",
    blurb: "AWS/Azure/GCP misconfiguration scanning",
    available: true,
    connector: "prowler_connector",
    mark: "Pw",
    tone: 4,
    logo: "/logos/prowler.svg",
  },
  {
    id: "scoutsuite",
    name: "ScoutSuite",
    category: "Cloud security posture",
    blurb: "Multi-cloud configuration auditing",
    available: true,
    connector: "scoutsuite_connector",
    mark: "Ss",
    tone: 7,
  },
  {
    id: "security-hub",
    name: "AWS Security Hub",
    category: "Cloud security posture",
    blurb: "Aggregated AWS security findings",
    available: false,
    mark: "SH",
    tone: 2,
    logo: "/logos/security-hub.png",
  },
  {
    id: "wiz",
    name: "Wiz",
    category: "Cloud security posture",
    blurb: "Cloud-native application protection",
    available: false,
    mark: "Wz",
    tone: 1,
    logo: "/logos/wiz.png",
  },
  {
    id: "wazuh",
    name: "Wazuh",
    category: "Endpoint detection & response",
    blurb: "Endpoint agents, alerts and log analysis",
    available: true,
    connector: "wazuh_connector",
    mark: "Wa",
    tone: 1,
    logo: "/logos/wazuh.png",
  },
  {
    id: "crowdstrike",
    name: "CrowdStrike Falcon",
    category: "Endpoint detection & response",
    blurb: "Endpoint detection and response",
    available: false,
    mark: "CS",
    tone: 8,
    logo: "/logos/crowdstrike.png",
  },
  {
    id: "defender",
    name: "Microsoft Defender for Endpoint",
    category: "Endpoint detection & response",
    blurb: "Endpoint detection and response",
    available: false,
    mark: "MD",
    tone: 1,
    logo: "/logos/defender.png",
  },
  {
    id: "sentinelone",
    name: "SentinelOne",
    category: "Endpoint detection & response",
    blurb: "Endpoint detection and response",
    available: false,
    mark: "S1",
    tone: 7,
    logo: "/logos/sentinelone.png",
  },
  {
    id: "aws-iam",
    name: "AWS IAM (via PMapper)",
    category: "Identity & access",
    blurb: "Privileged-access and permission graph analysis",
    available: true,
    connector: "iam_connector",
    mark: "IA",
    tone: 4,
    logo: "/logos/aws-iam.svg",
  },
  {
    id: "nmap",
    name: "Nmap",
    category: "Network exposure",
    blurb: "Open-port and network exposure scanning",
    available: false,
    mark: "Nm",
    tone: 3,
    logo: "/logos/nmap.png",
  },
  {
    id: "cmdb",
    name: "Internal CMDB",
    category: "Asset inventory",
    blurb: "Canonical asset identity (hostnames, IPs, cloud IDs)",
    available: true,
    connector: "cmdb_connector",
    mark: "DB",
    tone: 5,
  },
];
