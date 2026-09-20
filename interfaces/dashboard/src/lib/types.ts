/**
 * TypeScript mirrors of the backend's Python contracts.
 *
 * These are hand-maintained mirrors, not generated code. Each interface names
 * the Python dataclass it mirrors; if that dataclass changes, this file must
 * change with it. The dashboard talks to the backend only over HTTP (see
 * repo-root CLAUDE.md), so these shapes are the whole of what it knows.
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
  top_contributors: LossEventContribution[];
  monte_carlo_iterations: number;
}

/** Mirrors `core.optimizer.Control`. */
export interface Control {
  control_id: string;
  control_category: string;
  estimated_cost_inr: number;
  affected_asset_ids: string[];
}

/** Mirrors `core.optimizer.PortfolioRecommendation`. */
export interface PortfolioRecommendation {
  selected_controls: Control[];
  total_cost_inr: number;
  baseline_risk_figure: RiskFigure;
  post_investment_risk_figure: RiskFigure;
  /**
   * Derived from the two jointly-simulated figures above — never from summing
   * individual control deltas (CLAUDE.md principle 7).
   */
  risk_reduction_inr: number;
}

/** Mirrors `governance.mapper.StatusValue`. */
export type ControlStatusValue =
  | "met"
  | "not_met"
  | "unknown"
  | "expired_attestation";

/** Mirrors `governance.mapper.ControlStatus`. */
export interface ControlStatus {
  control_id: string;
  framework: string;
  framework_version: string;
  status: ControlStatusValue;
  evidence_refs: string[];
  confidence: string;
  verified_by_human: boolean;
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

/** Mirrors the response of `ai.tools.get_framework_status.get_framework_status`. */
export interface FrameworkStatus {
  framework: string;
  framework_version: string;
  effective_from: string | null;
  controls: ControlStatus[];
  weighted_score: WeightedScoreResult | null;
}

/** Mirrors `scan_scope` in schema/aggregated_assets.schema.json. */
export interface ScanScope {
  reachable_scanners: string[];
  unreachable_scanners: string[];
  coverage?: { scanner: string; asset_ids: string[] }[];
}

/**
 * Snapshot provenance: the bitemporal identity of the snapshot every figure on
 * screen was computed from. Mirrors the top-level fields of
 * schema/aggregated_assets.schema.json plus counts the API derives from it.
 */
export interface SnapshotProvenance {
  snapshot_id: string;
  observed_at: string;
  valid_from: string;
  valid_to: string | null;
  scan_scope: ScanScope;
  asset_count: number;
  service_count: number;
  finding_count: number;
}

/** Mirrors `core.snapshot.GateResult`. */
export interface GateResult {
  gate_name: string;
  passed: boolean;
  detail: string;
}
