/**
 * TypeScript mirrors of the backend's response shapes.
 *
 * These are hand-maintained mirrors, not generated code. Each interface names
 * the Python type or route it mirrors; if that changes, this file must change
 * with it. The dashboard talks to the backend only over HTTP (see repo-root
 * CLAUDE.md), so these shapes are the whole of what it knows.
 */

/** Mirrors `core.engine.LossEventContribution`. */
export interface LossEventContribution {
  scenario_id: string;
  asset_id: string;
  expected_annual_loss_inr: number;
  description: string;
}

/** Mirrors `core.engine.RiskFigure`. */
export interface RiskFigure {
  snapshot_id: string;
  expected_annual_loss_inr: number;
  value_at_risk_inr: number;
  /** Copied from the engine at computation time — never assumed to match current config. */
  value_at_risk_percentile: number;
  /** Every scenario the engine simulated, largest first — not a truncated top-N. */
  top_contributors: LossEventContribution[];
  monte_carlo_iterations: number;
}

/** Mirrors `core.engine.LossExceedancePoint`. */
export interface LossExceedancePoint {
  loss_inr: number;
  exceedance_probability: number;
}

/** Mirrors `core.engine.LossExceedanceCurve` (`GET /exposure/exceedance`). */
export interface LossExceedanceCurve {
  snapshot_id: string;
  monte_carlo_iterations: number;
  probability_of_any_loss: number;
  points: LossExceedancePoint[];
}

/** One entry of `GET /exposure/history`. */
export interface ExposureHistoryEntry {
  snapshot_id: string;
  observed_at: string;
  risk_figure: RiskFigure;
}

/** `GET /exposure/history` — oldest snapshot first. */
export interface ExposureHistory {
  snapshots: ExposureHistoryEntry[];
}

/** Mirrors `scan_scope` in schema/aggregated_assets.schema.json. */
export interface ScanScope {
  reachable_scanners: string[];
  unreachable_scanners: string[];
  coverage?: { scanner: string; asset_ids: string[] }[];
}

/** `GET /snapshot` — the bitemporal identity every figure on screen derives from. */
export interface SnapshotProvenance {
  snapshot_id: string;
  observed_at: string;
  valid_from: string;
  valid_to: string | null;
  scan_scope: ScanScope;
  asset_count: number;
  service_count: number;
  finding_count: number;
  open_finding_count: number;
}

/** Mirrors `core.snapshot.GateResult`. */
export interface GateResult {
  gate_name: string;
  passed: boolean;
  detail: string;
}

/** `GET /snapshot/gates` — the five gates re-run on the current snapshot. */
export interface GateReport {
  snapshot_id: string;
  /** The snapshot the current one superseded; null if it was the first. */
  compared_against_snapshot_id: string | null;
  evaluated_at: string;
  gates: GateResult[];
}

/** A Beta-PERT three-point estimate, as the engine parameterizes it. */
export interface PertEstimate {
  min: number;
  most_likely: number;
  max: number;
}

/** The scenario `core.engine.parameterize_scenario` built for one open finding. */
export interface ScenarioParameters {
  scenario_id: string;
  description: string;
  exposure_profile: string;
  threat_event_frequency: PertEstimate;
  exploit_probability: number;
  active_control_resistances: Record<string, number>;
  vulnerability: number;
  loss_event_frequency: PertEstimate;
  criticality_tier: string;
  backup_posture: string;
  loss_magnitude: PertEstimate;
  expected_annual_loss_inr: number;
}

/** Mirrors `assets[].findings[]` in the schema. */
export interface Finding {
  finding_id: string;
  type: string;
  cve_id: string | null;
  epss_score: number | null;
  kev_listed: boolean | null;
  criticality: string | null;
  provenance: { connector: string; raw_source_id: string };
  first_seen_at: string;
  remediated_at: string | null;
}

export interface AssetFinding extends Finding {
  /** Null when the finding is remediated — a fixed finding is not a loss path. */
  scenario: ScenarioParameters | null;
}

/** Mirrors `services[]` in the schema. */
export interface Service {
  service_id: string;
  name: string;
  criticality: string;
  backup: {
    exists: boolean;
    last_tested_at: string | null;
    rpo_hours: number | null;
    rto_hours: number | null;
    immutable_copy: boolean | null;
  };
}

export interface AssetView {
  asset_id: string;
  service_ids: string[];
  services: Service[];
  unresolved_service_ids: string[];
  network: { internet_facing: boolean | null; open_ports: number[] | null } | null;
  edr: {
    agent_installed: boolean;
    agent_healthy: boolean | null;
    detection_rules_active: string[] | null;
    recent_alerts: unknown[] | null;
  } | null;
  identity_access: {
    privileged_accounts_count: number | null;
    mfa_enforced: boolean | null;
  } | null;
  /** `core.engine.expected_annual_loss_by_asset`; null when no scenario is modelled on it. */
  expected_annual_loss_inr: number | null;
  findings: AssetFinding[];
}

/** `GET /assets`. */
export interface AssetsResponse {
  snapshot_id: string;
  observed_at: string;
  monte_carlo_iterations: number;
  expected_annual_loss_inr: number;
  assets: AssetView[];
}

/** Mirrors `core.optimizer.Control`. */
export interface Control {
  control_id: string;
  control_category: string;
  estimated_cost_inr: number;
  affected_asset_ids: string[];
  /** For `remediate_finding`: the open finding to fix. */
  finding_id?: string | null;
  /** For `harden_backup`: the service whose backup is hardened. */
  service_id?: string | null;
}

/** Mirrors `core.optimizer.ControlGap` — carries no cost and no benefit. */
export interface ControlGap {
  control_id: string;
  control_category: string;
  affected_asset_ids: string[];
  finding_id?: string | null;
  service_id?: string | null;
}

/** Mirrors `core.optimizer.PortfolioStep` — every figure a joint simulation. */
export interface PortfolioStep {
  control: Control;
  cumulative_cost_inr: number;
  expected_annual_loss_inr: number;
  value_at_risk_inr: number;
  /** Difference of two joint simulations; the steps add up to the portfolio's reduction. */
  marginal_reduction_inr: number;
}

/** Mirrors `core.optimizer.RejectedControl`. */
export interface RejectedControl {
  control: Control;
  reason: "over_budget" | "no_reduction";
}

/** Mirrors `core.optimizer.PlanStep`. */
export interface PlanStep {
  gap: ControlGap;
  expected_annual_loss_inr: number;
  value_at_risk_inr: number;
  marginal_reduction_inr: number;
}

/** `GET /optimize/plan` — mirrors `core.optimizer.PriorityPlan`. */
export interface PriorityPlan {
  snapshot_id: string;
  baseline_risk_figure: RiskFigure;
  steps: PlanStep[];
  no_effect: ControlGap[];
  /** True when the step limit stopped the plan while more changes would still help. */
  truncated: boolean;
}

/** `GET /optimize/candidates`. */
export interface ControlCandidates {
  snapshot_id: string;
  applicable_categories: string[];
  gaps: ControlGap[];
}

/** Mirrors `core.optimizer.PortfolioRecommendation` (`POST /optimize`). */
export interface PortfolioRecommendation {
  snapshot_id: string;
  selected_controls: Control[];
  total_cost_inr: number;
  baseline_risk_figure: RiskFigure;
  post_investment_risk_figure: RiskFigure;
  /**
   * Derived from the two jointly-simulated figures above — never from summing
   * individual control deltas (CLAUDE.md principle 7).
   */
  risk_reduction_inr: number;
  value_at_risk_reduction_inr: number;
  /** One per selected control, in the order the search added them. */
  steps: PortfolioStep[];
  /** Every candidate not selected, and why. */
  rejected: RejectedControl[];
}

/** `POST /simulate` — mirrors `ai.tools.simulate_scenario`'s result. */
export interface HypotheticalComparison {
  snapshot_id: string;
  hypothetical_controls: Control[];
  /** Re-simulated on the same random draws as `hypothetical`. */
  baseline: RiskFigure;
  hypothetical: RiskFigure;
  expected_annual_loss_change_inr: number;
  value_at_risk_change_inr: number;
}

/** Mirrors `governance.mapper.StatusValue`. */
export type ControlStatusValue =
  | "met"
  | "not_met"
  | "unknown"
  | "expired_attestation";

/** Mirrors `governance.mapper.ControlStatus`, plus the library entry's name. */
export interface ControlStatus {
  control_id: string;
  framework: string;
  framework_version: string;
  status: ControlStatusValue;
  evidence_refs: string[];
  confidence: string;
  verified_by_human: boolean;
  parameter_name: string;
  framework_ref: string;
}

/** Mirrors `governance.mapper.WeightedScoreResult`. */
export interface WeightedScoreResult {
  framework: string;
  score: number | null;
  total_weight: number;
  determined_weight: number;
  coverage_fraction: number | null;
  low_confidence_weight_among_determined: number;
  low_confidence_fraction_of_determined: number | null;
  controls_excluded_no_weight: string[];
}

/** `GET /frameworks/{framework}/status` — mirrors `ai.tools.get_framework_status`. */
export interface FrameworkStatus {
  framework: string;
  version: string;
  effective_from: string | null;
  effective_to: string | null;
  snapshot_id: string;
  controls: ControlStatus[];
  weighted_score: WeightedScoreResult;
}

/** Mirrors `governance.library_loader.PenaltyProvision` — a statutory ceiling. */
export interface PenaltyProvision {
  id: string;
  statute: string;
  provision_ref: string;
  description: string;
  penalty_amount_inr: number | null;
  penalty_formula: string;
  currently_in_force: boolean;
  in_force_from: string | null;
  source: string;
  confidence: string;
  verified_by_human: boolean;
}

/** One entry of `GET /frameworks`. */
export interface FrameworkSummary {
  framework: string;
  version: string;
  effective_from: string | null;
  effective_to: string | null;
  supersedes: string | null;
  control_count: number;
  penalty_provisions: PenaltyProvision[];
}

/** One entry of `GET /assumptions` — a live constant from core/assumptions.py. */
export interface AssumptionEntry {
  name: string;
  value: unknown;
  assumption: string | null;
  justification: string | null;
  calibration: string | null;
}

/** Mirrors `interfaces.api.app.ToolCallResponse`. */
export interface ChatToolCall {
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "ok" | "unavailable" | "error" | string;
  detail: string | null;
  result: Record<string, unknown> | null;
}

/** Mirrors `interfaces.api.app.ChatResponse` — `text` is already guarded. */
export interface ChatResponse {
  session_id: string;
  text: string;
  all_claims_verified: boolean;
  unverified_claims: string[];
  tool_calls: ChatToolCall[];
  model: string;
  stop_reason: string;
}

/** `final` event of `POST /chat/stream`: the verified turn, as `POST /chat` returns it. */
export interface ChatStreamFinal extends ChatResponse {
  /** The guard changed the model's streamed text; `text` is what to show. */
  text_replaced: boolean;
}

/** `tool_call` event of `POST /chat/stream`: a tool is about to run. */
export interface ChatToolCallEvent {
  tool_use_id: string;
  /** Model/tool round trip this call belongs to, counting from 0. */
  round: number;
  tool_name: string;
  arguments: Record<string, unknown>;
}

/** `tool_result` event of `POST /chat/stream`: how that call went. */
export interface ChatToolResultEvent {
  tool_use_id: string;
  round: number;
  tool_name: string;
  status: ChatToolCall["status"];
  detail: string | null;
}
