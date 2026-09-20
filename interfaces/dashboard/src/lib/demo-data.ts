/**
 * ILLUSTRATIVE SAMPLE DATA — NOT ENGINE OUTPUT.
 *
 * Every figure in this file is invented for interface development and demos.
 * None of it was produced by `core/engine.py`, none of it is calibrated
 * against anything, and none of it may be cited, screenshotted as a result,
 * or presented to a regulator, auditor, or evaluator as a Su₹aksha finding.
 *
 * It is served only when `NEXT_PUBLIC_DEMO_MODE=1`. In that mode the UI
 * renders a persistent banner and tags every figure `SAMPLE`, so a reader can
 * never mistake one of these numbers for a computed one. When the flag is off
 * — the default — none of this is reachable, and a missing backend shows as an
 * explicit "no figure available" state instead.
 *
 * Repo-root CLAUDE.md, principle 1: the rupee figure comes from a
 * deterministic engine. A hardcoded constant is not that engine.
 */

import type {
  FrameworkStatus,
  GateResult,
  PortfolioRecommendation,
  RiskFigure,
  SnapshotProvenance,
} from "./types";

const DEMO_SNAPSHOT_ID =
  "sha256:9f2c41a7b3e85d06c1fa27be4d3908175ec6ab92f0d4471e8c35ba6027df1e4a";

const DEMO_EXPOSURE: RiskFigure = {
  snapshot_id: DEMO_SNAPSHOT_ID,
  expected_annual_loss_inr: 42_500_000,
  value_at_risk_inr: 186_400_000,
  value_at_risk_percentile: 0.95,
  monte_carlo_iterations: 100_000,
  top_contributors: [
    {
      scenario_id: "scn-ransomware-core-banking",
      asset_id: "host:10.24.8.15",
      expected_annual_loss_inr: 18_200_000,
      description:
        "Ransomware encrypting the core banking platform. KEV-listed RCE on an internet-facing host, backup tested but no immutable copy.",
    },
    {
      scenario_id: "scn-data-breach-customer-pii",
      asset_id: "cloud:arn:aws:s3:::loanease-customer-docs",
      expected_annual_loss_inr: 9_600_000,
      description:
        "Bulk exfiltration of customer KYC records from a publicly readable object store, no MFA on the owning principal.",
    },
    {
      scenario_id: "scn-credential-stuffing-portal",
      asset_id: "host:10.24.8.41",
      expected_annual_loss_inr: 6_400_000,
      description:
        "Credential stuffing against the borrower portal. No EDR agent, no rate limiting observed.",
    },
    {
      scenario_id: "scn-insider-privilege-abuse",
      asset_id: "host:10.24.12.9",
      expected_annual_loss_inr: 3_100_000,
      description:
        "Privileged insider access to the loan origination database; 14 standing admin accounts, no session recording.",
    },
    {
      scenario_id: "scn-third-party-api-compromise",
      asset_id: "cloud:arn:aws:lambda:ap-south-1:fn:credit-bureau-proxy",
      expected_annual_loss_inr: 1_900_000,
      description:
        "Compromise of the credit bureau integration path, leading to fraudulent disbursement decisions.",
    },
  ],
};

const DEMO_POST_INVESTMENT: RiskFigure = {
  ...DEMO_EXPOSURE,
  expected_annual_loss_inr: 26_800_000,
  value_at_risk_inr: 121_300_000,
  top_contributors: DEMO_EXPOSURE.top_contributors.slice(1),
};

const DEMO_RECOMMENDATION: PortfolioRecommendation = {
  total_cost_inr: 14_200_000,
  risk_reduction_inr: 15_700_000,
  baseline_risk_figure: DEMO_EXPOSURE,
  post_investment_risk_figure: DEMO_POST_INVESTMENT,
  selected_controls: [
    {
      control_id: "ctl-immutable-backup-core-banking",
      control_category: "backup_immutability",
      estimated_cost_inr: 6_500_000,
      affected_asset_ids: ["host:10.24.8.15", "host:10.24.8.16"],
    },
    {
      control_id: "ctl-patch-kev-internet-facing",
      control_category: "patch_current",
      estimated_cost_inr: 3_200_000,
      affected_asset_ids: ["host:10.24.8.15", "host:10.24.8.41"],
    },
    {
      control_id: "ctl-block-public-object-storage",
      control_category: "network_segmentation",
      estimated_cost_inr: 1_800_000,
      affected_asset_ids: ["cloud:arn:aws:s3:::loanease-customer-docs"],
    },
    {
      control_id: "ctl-mfa-privileged-principals",
      control_category: "mfa_enforced",
      estimated_cost_inr: 2_700_000,
      affected_asset_ids: [
        "host:10.24.12.9",
        "cloud:arn:aws:s3:::loanease-customer-docs",
      ],
    },
  ],
};

const DEMO_FRAMEWORK_STATUS: FrameworkStatus = {
  framework: "rbi_2026_directions",
  framework_version: "2026.1",
  effective_from: "2026-08-01",
  weighted_score: {
    framework: "rbi_2026_directions",
    score: 0.61,
    total_weight: 100,
    determined_weight: 74,
    coverage_fraction: 0.74,
    low_confidence_weight_among_determined: 12,
    low_confidence_fraction_of_determined: 0.162,
    controls_excluded_no_weight: ["rbi-anx-iii-7", "rbi-anx-iii-9"],
  },
  controls: [
    {
      control_id: "rbi-2026-4.2",
      framework: "rbi_2026_directions",
      framework_version: "2026.1",
      status: "met",
      evidence_refs: ["host:10.24.8.15", "host:10.24.8.16"],
      confidence: "high",
      verified_by_human: true,
    },
    {
      control_id: "rbi-2026-5.1",
      framework: "rbi_2026_directions",
      framework_version: "2026.1",
      status: "not_met",
      evidence_refs: ["finding-0421", "finding-0422", "host:10.24.8.41"],
      confidence: "high",
      verified_by_human: false,
    },
    {
      control_id: "rbi-2026-5.4",
      framework: "rbi_2026_directions",
      framework_version: "2026.1",
      status: "unknown",
      evidence_refs: [],
      confidence: "medium",
      verified_by_human: false,
    },
    {
      control_id: "rbi-2026-6.3",
      framework: "rbi_2026_directions",
      framework_version: "2026.1",
      status: "expired_attestation",
      evidence_refs: ["attestation-bcp-dr-2025-03"],
      confidence: "low",
      verified_by_human: true,
    },
    {
      control_id: "rbi-2026-7.2",
      framework: "rbi_2026_directions",
      framework_version: "2026.1",
      status: "met",
      evidence_refs: ["svc-core-banking", "attestation-vapt-2026-06"],
      confidence: "medium",
      verified_by_human: true,
    },
  ],
};

const DEMO_GATES: GateResult[] = [
  {
    gate_name: "asset_count_delta",
    passed: true,
    detail: "248 assets vs 246 in the previous snapshot (+0.8%), within tolerance.",
  },
  {
    gate_name: "no_findings_from_unreachable_scanners",
    passed: true,
    detail:
      "nmap_connector is unreachable this cycle and contributed no findings.",
  },
  {
    gate_name: "criticality_present_or_unknown",
    passed: true,
    detail:
      "1,843 findings checked; 37 carry the explicit string 'unknown', none are null.",
  },
  {
    gate_name: "provenance_non_null",
    passed: true,
    detail: "Every finding carries a connector and a raw_source_id.",
  },
  {
    gate_name: "no_ordinal_in_numeric_field",
    passed: true,
    detail: "No string ordinal found in epss_score or rto_hours.",
  },
];

/** Provenance of the sample snapshot the demo figures are attributed to. */
export const DEMO_SNAPSHOT_PROVENANCE: SnapshotProvenance = {
  snapshot_id: DEMO_SNAPSHOT_ID,
  observed_at: "2026-09-20T02:15:00Z",
  valid_from: "2026-09-20T02:15:00Z",
  valid_to: null,
  asset_count: 248,
  service_count: 12,
  finding_count: 1843,
  scan_scope: {
    reachable_scanners: [
      "wazuh_connector",
      "greenbone_connector",
      "prowler_connector",
      "scoutsuite_connector",
    ],
    unreachable_scanners: ["nmap_connector"],
  },
};

const DEMO_PAYLOADS = {
  exposure: DEMO_EXPOSURE,
  recommendation: DEMO_RECOMMENDATION,
  frameworkStatus: DEMO_FRAMEWORK_STATUS,
  gates: DEMO_GATES,
};

/**
 * Return one sample payload wrapped as a successful API result.
 *
 * Only ever called from `src/lib/api.ts` when {@link DEMO_MODE} is on.
 */
export function demoResult<K extends keyof typeof DEMO_PAYLOADS>(
  key: K,
): { state: "ok"; data: (typeof DEMO_PAYLOADS)[K] } {
  return { state: "ok", data: DEMO_PAYLOADS[key] };
}
