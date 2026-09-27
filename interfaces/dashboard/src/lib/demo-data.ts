/**
 * ILLUSTRATIVE SAMPLE DATA — NOT ENGINE OUTPUT.
 *
 * Every figure in this file is invented for interface development and demos.
 * None of it was produced by `core/engine/`, none of it is calibrated
 * against anything, and none of it may be cited, screenshotted as a result,
 * or presented to a regulator, auditor, or evaluator as a Cypher finding.
 *
 * It is served only when `NEXT_PUBLIC_DEMO_MODE=1`. In that mode the UI
 * renders a persistent banner and tags every figure `SAMPLE`, so a reader can
 * never mistake one of these numbers for a computed one. When the flag is off
 * — the default — none of this is reachable, and a missing backend shows as an
 * explicit "no figure available" state instead.
 *
 * Interactive engine runs (what-if, optimizer, assistant) are deliberately not
 * faked: in demo mode they report that they need the live backend.
 *
 * Repo-root CLAUDE.md, principle 1: the rupee figure comes from a
 * deterministic engine. A hardcoded constant is not that engine.
 */

import type {
  AssetView,
  AssetsResponse,
  AssumptionEntry,
  ControlCandidates,
  ControlStatus,
  ExposureHistory,
  FrameworkStatus,
  FrameworkSummary,
  GateReport,
  LossExceedanceCurve,
  RiskFigure,
  SnapshotProvenance,
} from "./types";

const DEMO_SNAPSHOT_ID =
  "sha256:9f2c41a7b3e85d06c1fa27be4d3908175ec6ab92f0d4471e8c35ba6027df1e4a";
const DEMO_OBSERVED_AT = "2026-09-20T02:15:00Z";
const DEMO_ITERATIONS = 10_000;

interface DemoScenario {
  asset_id: string;
  finding_id: string;
  cve_id: string | null;
  type: string;
  epss_score: number | null;
  kev_listed: boolean | null;
  criticality: string;
  connector: string;
  first_seen_at: string;
  eal: number;
  profile: string;
  tier: string;
}

const DEMO_SCENARIOS: DemoScenario[] = [
  { asset_id: "cust-portal", finding_id: "F-0877", cve_id: "CVE-2021-44228", type: "cve", epss_score: 0.94, kev_listed: true, criticality: "critical", connector: "greenbone_connector", first_seen_at: "2026-06-02T00:00:00Z", eal: 18_200_000, profile: "internet_facing_critical_asset", tier: "critical" },
  { asset_id: "kyc-store", finding_id: "F-1390", cve_id: null, type: "misconfiguration", epss_score: null, kev_listed: null, criticality: "high", connector: "prowler_connector", first_seen_at: "2026-07-21T00:00:00Z", eal: 9_600_000, profile: "internet_facing_critical_asset", tier: "critical" },
  { asset_id: "ad-dc-01", finding_id: "F-0791", cve_id: "CVE-2020-1472", type: "cve", epss_score: 0.94, kev_listed: true, criticality: "critical", connector: "wazuh_connector", first_seen_at: "2026-08-04T00:00:00Z", eal: 6_400_000, profile: "internal_asset", tier: "critical" },
  { asset_id: "dev-ci", finding_id: "F-1364", cve_id: "CVE-2024-23897", type: "cve", epss_score: 0.94, kev_listed: true, criticality: "high", connector: "wazuh_connector", first_seen_at: "2026-07-14T00:00:00Z", eal: 3_100_000, profile: "internal_asset", tier: "high" },
  { asset_id: "mkt-site", finding_id: "F-1402", cve_id: "CVE-2024-4577", type: "cve", epss_score: 0.94, kev_listed: true, criticality: "critical", connector: "greenbone_connector", first_seen_at: "2026-07-28T00:00:00Z", eal: 1_900_000, profile: "internal_asset", tier: "low" },
  { asset_id: "core-lms-db", finding_id: "F-0955", cve_id: null, type: "patch_level", epss_score: null, kev_listed: null, criticality: "unknown", connector: "greenbone_connector", first_seen_at: "2026-04-27T00:00:00Z", eal: 1_200_000, profile: "internal_asset", tier: "critical" },
];

function demoFigure(snapshotId: string, scale: (index: number) => number): RiskFigure {
  const top_contributors = DEMO_SCENARIOS.map((s, index) => ({
    scenario_id: `${s.asset_id}::${s.finding_id}`,
    asset_id: s.asset_id,
    expected_annual_loss_inr: Math.round(s.eal * scale(index)),
    description: `${s.type} ${s.cve_id ?? s.finding_id} on ${s.asset_id} (${s.profile}, ${s.tier}-tier service impact)`,
  }))
    // A scenario scaled to zero was not open in that snapshot, and the engine
    // lists only scenarios it simulated.
    .filter((c) => c.expected_annual_loss_inr > 0)
    .sort((a, b) => b.expected_annual_loss_inr - a.expected_annual_loss_inr);
  const eal = top_contributors.reduce((sum, c) => sum + c.expected_annual_loss_inr, 0);
  return {
    snapshot_id: snapshotId,
    // Keeps the engine's invariant: EAL is exactly the sum of every contributor.
    expected_annual_loss_inr: eal,
    value_at_risk_inr: Math.round(eal * 4.1),
    value_at_risk_percentile: 0.95,
    top_contributors,
    monte_carlo_iterations: DEMO_ITERATIONS,
  };
}

const DEMO_EXPOSURE: RiskFigure = demoFigure(DEMO_SNAPSHOT_ID, () => 1);

const DEMO_HISTORY: ExposureHistory = {
  snapshots: [
    { id: "sha256:1b7e", at: "2026-08-30T02:15:00Z", k: [0.7, 0, 1.3, 1, 1, 1.1] },
    { id: "sha256:5c02", at: "2026-09-06T02:15:00Z", k: [0.8, 0.9, 1.2, 1, 1, 1.05] },
    { id: "sha256:a4d9", at: "2026-09-13T02:15:00Z", k: [1.1, 1.05, 1.1, 1, 1, 1] },
  ]
    .map(({ id, at, k }) => ({
      snapshot_id: `${id}${DEMO_SNAPSHOT_ID.slice(11)}`,
      observed_at: at,
      risk_figure: demoFigure(`${id}${DEMO_SNAPSHOT_ID.slice(11)}`, (i) => k[i]),
    }))
    .concat([
      { snapshot_id: DEMO_SNAPSHOT_ID, observed_at: DEMO_OBSERVED_AT, risk_figure: DEMO_EXPOSURE },
    ]),
};

const DEMO_EXCEEDANCE: LossExceedanceCurve = (() => {
  const probabilityOfAnyLoss = 0.93;
  const low = 400_000;
  const high = 900_000_000;
  const count = 60;
  const points = Array.from({ length: count }, (_, i) => {
    const loss = low * (high / low) ** (i / (count - 1));
    const shaped = probabilityOfAnyLoss / (1 + (loss / 25_000_000) ** 1.5);
    return { loss_inr: loss, exceedance_probability: i === count - 1 ? 0 : shaped };
  });
  return {
    snapshot_id: DEMO_SNAPSHOT_ID,
    monte_carlo_iterations: DEMO_ITERATIONS,
    probability_of_any_loss: probabilityOfAnyLoss,
    points,
  };
})();

const DEMO_PROVENANCE: SnapshotProvenance = {
  snapshot_id: DEMO_SNAPSHOT_ID,
  observed_at: DEMO_OBSERVED_AT,
  valid_from: DEMO_OBSERVED_AT,
  valid_to: null,
  asset_count: 7,
  service_count: 5,
  finding_count: 7,
  open_finding_count: 6,
  scan_scope: {
    reachable_scanners: ["wazuh_connector", "greenbone_connector", "prowler_connector", "scoutsuite_connector"],
    unreachable_scanners: ["nmap_connector"],
  },
};

const DEMO_GATES: GateReport = {
  snapshot_id: DEMO_SNAPSHOT_ID,
  compared_against_snapshot_id: DEMO_HISTORY.snapshots[2].snapshot_id,
  evaluated_at: DEMO_OBSERVED_AT,
  gates: [
    { gate_name: "asset_count_delta", passed: true, detail: "asset count 7 -> 7 (0.0% change, tolerance 50%)" },
    { gate_name: "no_findings_from_unreachable_scanners", passed: true, detail: "no finding attributed to a scanner marked unreachable" },
    { gate_name: "criticality_present_or_unknown", passed: true, detail: "every finding has non-null criticality" },
    { gate_name: "provenance_non_null", passed: true, detail: "every finding has non-null provenance" },
    { gate_name: "no_ordinal_in_numeric_field", passed: true, detail: "no ordinal string found in a numeric-typed field" },
  ],
};

const DEMO_SERVICES = {
  payments: { service_id: "svc-payments", name: "Payments gateway", criticality: "critical", backup: { exists: true, last_tested_at: "2026-08-01T00:00:00Z", rpo_hours: 1, rto_hours: 4, immutable_copy: true } },
  lending: { service_id: "svc-lending", name: "Loan management", criticality: "critical", backup: { exists: true, last_tested_at: null, rpo_hours: 4, rto_hours: 12, immutable_copy: false } },
  digital: { service_id: "svc-portal", name: "Customer portal", criticality: "critical", backup: { exists: true, last_tested_at: "2026-07-10T00:00:00Z", rpo_hours: 2, rto_hours: 8, immutable_copy: false } },
  identity: { service_id: "svc-identity", name: "Directory & identity", criticality: "critical", backup: { exists: true, last_tested_at: "2026-06-15T00:00:00Z", rpo_hours: 4, rto_hours: 8, immutable_copy: false } },
  web: { service_id: "svc-web", name: "Marketing website", criticality: "low", backup: { exists: false, last_tested_at: null, rpo_hours: null, rto_hours: null, immutable_copy: null } },
};

const DEMO_ASSET_POSTURE: Record<string, Pick<AssetView, "services" | "network" | "edr" | "identity_access">> = {
  "cust-portal": { services: [DEMO_SERVICES.digital], network: { internet_facing: true, open_ports: [443] }, edr: { agent_installed: true, agent_healthy: true, detection_rules_active: ["rule-web"], recent_alerts: [] }, identity_access: { privileged_accounts_count: 3, mfa_enforced: false } },
  "kyc-store": { services: [DEMO_SERVICES.lending], network: { internet_facing: true, open_ports: [443] }, edr: { agent_installed: false, agent_healthy: null, detection_rules_active: null, recent_alerts: null }, identity_access: { privileged_accounts_count: 2, mfa_enforced: false } },
  "ad-dc-01": { services: [DEMO_SERVICES.identity], network: { internet_facing: false, open_ports: [389, 445] }, edr: { agent_installed: true, agent_healthy: true, detection_rules_active: ["rule-ad"], recent_alerts: [] }, identity_access: { privileged_accounts_count: 14, mfa_enforced: null } },
  "dev-ci": { services: [DEMO_SERVICES.digital], network: { internet_facing: false, open_ports: [8080] }, edr: { agent_installed: false, agent_healthy: null, detection_rules_active: null, recent_alerts: null }, identity_access: { privileged_accounts_count: 5, mfa_enforced: false } },
  "mkt-site": { services: [DEMO_SERVICES.web], network: { internet_facing: true, open_ports: [80, 443] }, edr: { agent_installed: true, agent_healthy: false, detection_rules_active: null, recent_alerts: null }, identity_access: { privileged_accounts_count: 1, mfa_enforced: true } },
  "core-lms-db": { services: [DEMO_SERVICES.lending], network: { internet_facing: false, open_ports: [3306] }, edr: { agent_installed: true, agent_healthy: true, detection_rules_active: ["rule-db"], recent_alerts: [] }, identity_access: { privileged_accounts_count: 4, mfa_enforced: false } },
  "pay-gw-01": { services: [DEMO_SERVICES.payments], network: { internet_facing: true, open_ports: [443] }, edr: { agent_installed: true, agent_healthy: true, detection_rules_active: ["rule-pay"], recent_alerts: [] }, identity_access: { privileged_accounts_count: 2, mfa_enforced: true } },
};

const DEMO_ASSETS: AssetsResponse = {
  snapshot_id: DEMO_SNAPSHOT_ID,
  observed_at: DEMO_OBSERVED_AT,
  monte_carlo_iterations: DEMO_ITERATIONS,
  expected_annual_loss_inr: DEMO_EXPOSURE.expected_annual_loss_inr,
  assets: Object.entries(DEMO_ASSET_POSTURE).map(([asset_id, posture]) => {
    const scenarios = DEMO_SCENARIOS.filter((s) => s.asset_id === asset_id);
    const internet = posture.network?.internet_facing === true;
    const tef = internet ? { min: 6, most_likely: 12, max: 24 } : { min: 1, most_likely: 2, max: 6 };
    const findings: AssetView["findings"] = scenarios.map((s) => {
      const exploit = Math.max(s.epss_score ?? 0.05, s.kev_listed ? 0.5 : 0);
      const resistances: Record<string, number> = {};
      if (posture.identity_access?.mfa_enforced === true) resistances.mfa_enforced = 0.4;
      if (posture.edr?.agent_installed && posture.edr.agent_healthy === true) resistances.edr_active = 0.5;
      const vulnerability = Object.values(resistances).reduce((v, r) => v * (1 - r), exploit);
      return {
        finding_id: s.finding_id,
        type: s.type,
        cve_id: s.cve_id,
        epss_score: s.epss_score,
        kev_listed: s.kev_listed,
        criticality: s.criticality,
        provenance: { connector: s.connector, raw_source_id: `raw-${s.finding_id}` },
        first_seen_at: s.first_seen_at,
        remediated_at: null,
        scenario: {
          scenario_id: `${s.asset_id}::${s.finding_id}`,
          description: `${s.type} ${s.cve_id ?? s.finding_id} on ${s.asset_id} (${s.profile}, ${s.tier}-tier service impact)`,
          exposure_profile: s.profile,
          threat_event_frequency: tef,
          exploit_probability: exploit,
          active_control_resistances: resistances,
          vulnerability,
          loss_event_frequency: { min: tef.min * vulnerability, most_likely: tef.most_likely * vulnerability, max: tef.max * vulnerability },
          criticality_tier: s.tier,
          backup_posture: "backup_untested",
          loss_magnitude: { min: 9_000_000, most_likely: 36_000_000, max: 144_000_000 },
          expected_annual_loss_inr: s.eal,
        },
      };
    });
    if (asset_id === "pay-gw-01") {
      findings.push({
        finding_id: "F-0930", type: "cve", cve_id: "CVE-2024-6387", epss_score: 0.41, kev_listed: false,
        criticality: "high", provenance: { connector: "greenbone_connector", raw_source_id: "raw-F-0930" },
        first_seen_at: "2026-06-23T00:00:00Z", remediated_at: "2026-09-02T00:00:00Z", scenario: null,
      });
    }
    return {
      asset_id,
      service_ids: posture.services.map((s) => s.service_id),
      unresolved_service_ids: [],
      ...posture,
      expected_annual_loss_inr: scenarios.length ? scenarios.reduce((sum, s) => sum + s.eal, 0) : null,
      findings,
    };
  }),
};

const DEMO_CANDIDATES: ControlCandidates = {
  snapshot_id: DEMO_SNAPSHOT_ID,
  applicable_categories: ["mfa_enforced", "edr_active"],
  gaps: DEMO_ASSETS.assets.flatMap((asset) => [
    ...(asset.identity_access?.mfa_enforced === true ? [] : [{ control_id: `mfa_enforced::${asset.asset_id}`, control_category: "mfa_enforced", affected_asset_ids: [asset.asset_id] }]),
    ...(asset.edr?.agent_installed && asset.edr.agent_healthy === true ? [] : [{ control_id: `edr_active::${asset.asset_id}`, control_category: "edr_active", affected_asset_ids: [asset.asset_id] }]),
  ]),
};

const DEMO_FRAMEWORKS: FrameworkSummary[] = [
  { framework: "cis_controls", version: "8.1", effective_from: null, effective_to: null, supersedes: null, control_count: 4, penalty_provisions: [] },
  { framework: "dpdp_act_2023", version: "Digital Personal Data Protection Act, 2023", effective_from: "2023-08-11", effective_to: null, supersedes: null, control_count: 0, penalty_provisions: [
    { id: "dpdp_security_safeguard_failure", statute: "Digital Personal Data Protection Act, 2023", provision_ref: "Schedule, item 1", description: "Failure to take reasonable security safeguards to prevent a personal data breach.", penalty_amount_inr: 2_500_000_000, penalty_formula: "Up to the ceiling per instance.", currently_in_force: false, in_force_from: "2027-05-13", source: "Sample citation", confidence: "medium", verified_by_human: false },
  ] },
  { framework: "iso_27001", version: "ISO/IEC 27001:2022", effective_from: "2022-10-25", effective_to: null, supersedes: null, control_count: 4, penalty_provisions: [] },
  { framework: "nist_csf", version: "2.0", effective_from: "2024-02-26", effective_to: null, supersedes: null, control_count: 4, penalty_provisions: [] },
  { framework: "rbi_2026_directions", version: "RBI Directions, 2026", effective_from: "2026-07-31", effective_to: null, supersedes: "rbi_nbfc_it_framework_2017", control_count: 5, penalty_provisions: [
    { id: "rbi_nbfc_58g_noncompliance", statute: "Reserve Bank of India Act, 1934", provision_ref: "Section 58G(1)(b)", description: "Contravention of directions issued by the Reserve Bank.", penalty_amount_inr: 1_000_000, penalty_formula: "Up to the ceiling per contravention, plus a daily amount for continuing default.", currently_in_force: true, in_force_from: null, source: "Sample citation", confidence: "medium", verified_by_human: false },
  ] },
  { framework: "sebi_cscrf_cci", version: "SEBI CSCRF (2024)", effective_from: "2024-08-20", effective_to: null, supersedes: null, control_count: 4, penalty_provisions: [] },
];

const DEMO_STATUS_CYCLE: [ControlStatus["status"], string[], string][] = [
  ["not_met", ["cust-portal", "kyc-store"], "high"],
  ["met", ["pay-gw-01", "mkt-site"], "medium"],
  ["unknown", [], "medium"],
  ["expired_attestation", ["attestation:2025-03-01T00:00:00+00:00"], "low"],
  ["met", ["core-lms-db"], "high"],
];

function demoFrameworkStatus(framework: string): FrameworkStatus {
  const summary = DEMO_FRAMEWORKS.find((f) => f.framework === framework) ?? DEMO_FRAMEWORKS[4];
  const controls: ControlStatus[] = Array.from({ length: summary.control_count }, (_, i) => {
    const [status, evidence_refs, confidence] = DEMO_STATUS_CYCLE[i % DEMO_STATUS_CYCLE.length];
    return {
      control_id: `${summary.framework}_control_${i + 1}`,
      framework: summary.framework,
      framework_version: summary.version,
      status,
      evidence_refs,
      confidence,
      verified_by_human: false,
      parameter_name: ["Multi-factor authentication for privileged access", "Endpoint protection on servers", "Backups tested and restorable", "Incident reporting within timelines", "Vulnerability remediation within timelines"][i % 5],
      framework_ref: `Sample ref ${i + 1}`,
    };
  });
  return {
    framework: summary.framework,
    version: summary.version,
    effective_from: summary.effective_from,
    effective_to: summary.effective_to,
    snapshot_id: DEMO_SNAPSHOT_ID,
    controls,
    weighted_score: {
      framework: summary.framework,
      score: summary.framework === "sebi_cscrf_cci" ? 0.42 : null,
      total_weight: summary.framework === "sebi_cscrf_cci" ? 100 : 0,
      determined_weight: summary.framework === "sebi_cscrf_cci" ? 70 : 0,
      coverage_fraction: summary.framework === "sebi_cscrf_cci" ? 0.7 : null,
      low_confidence_weight_among_determined: 0,
      low_confidence_fraction_of_determined: summary.framework === "sebi_cscrf_cci" ? 0 : null,
      controls_excluded_no_weight: summary.framework === "sebi_cscrf_cci" ? [] : controls.map((c) => c.control_id),
    },
  };
}

const DEMO_ASSUMPTIONS: AssumptionEntry[] = [
  { name: "CONTROL_RESISTANCE_STRENGTH", value: { mfa_enforced: 0.4, edr_active: 0.5 }, assumption: "Relative strength each control category contributes toward resisting a threat event.", justification: "PLACEHOLDER — sample text.", calibration: "Sample text." },
  { name: "MONTE_CARLO_ITERATIONS", value: DEMO_ITERATIONS, assumption: "Number of Monte Carlo iterations.", justification: "Sample text.", calibration: "Sample text." },
  { name: "VALUE_AT_RISK_PERCENTILE", value: 0.95, assumption: "Percentile used to express Value at Risk.", justification: "Sample text.", calibration: "Sample text." },
];

const DEMO_PAYLOADS = {
  exposure: DEMO_EXPOSURE,
  history: DEMO_HISTORY,
  exceedance: DEMO_EXCEEDANCE,
  provenance: DEMO_PROVENANCE,
  gates: DEMO_GATES,
  assets: DEMO_ASSETS,
  frameworks: DEMO_FRAMEWORKS,
  candidates: DEMO_CANDIDATES,
  assumptions: DEMO_ASSUMPTIONS,
};

type DemoPayloads = typeof DEMO_PAYLOADS & { frameworkStatus: FrameworkStatus };

/**
 * Return one sample payload wrapped as a successful API result.
 *
 * Only ever called from `src/lib/api.ts` when `DEMO_MODE` is on.
 */
export function demoResult<K extends keyof DemoPayloads>(
  key: K,
  framework?: string,
): { state: "ok"; data: DemoPayloads[K] } {
  const data =
    key === "frameworkStatus"
      ? demoFrameworkStatus(framework ?? "rbi_2026_directions")
      : DEMO_PAYLOADS[key as keyof typeof DEMO_PAYLOADS];
  return { state: "ok", data: data as DemoPayloads[K] };
}

/** What an interactive engine run reports in demo mode: it needs the real backend. */
export function demoUnavailable(what: string): { state: "unavailable"; reason: string } {
  return {
    state: "unavailable",
    reason: `Demo mode is on, and ${what} runs the real engine — it needs the live backend. Unset NEXT_PUBLIC_DEMO_MODE to use it.`,
  };
}
