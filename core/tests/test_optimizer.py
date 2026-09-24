"""Tests for core/optimizer.py's joint-simulation budget optimizer.

The single most important property to test here is that overlapping
controls are never double-counted — a naive sum-of-deltas implementation
must fail these tests even if it produces plausible-looking numbers.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from core.engine import compute_risk_figure
from core.optimizer import (
    APPLICABLE_CONTROL_CATEGORIES,
    Control,
    _derive_comparison_seed,
    apply_controls_to_snapshot,
    compare_hypothetical,
    evaluate_portfolio,
    find_control_gaps,
    recommend_portfolio,
)

SAMPLE_SNAPSHOT: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "schema" / "sample_aggregated.json").read_text()
)


def test_apply_controls_to_snapshot_never_mutates_input_snapshot() -> None:
    """apply_controls_to_snapshot must return a new hypothetical snapshot and leave the input snapshot unchanged."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    reference = copy.deepcopy(snapshot)
    control = Control(
        control_id="enable MFA on asset-hr-db-01",
        control_category="mfa_enforced",
        estimated_cost_inr=50_000.0,
        affected_asset_ids=["asset-hr-db-01"],
    )

    hypothetical = apply_controls_to_snapshot(snapshot, [control])

    assert snapshot == reference
    hr_db_asset = next(a for a in hypothetical["assets"] if a["asset_id"] == "asset-hr-db-01")
    assert hr_db_asset["identity_access"]["mfa_enforced"] is True


def test_apply_controls_to_snapshot_applies_multiple_controls_to_same_asset() -> None:
    """Two controls targeting the same asset must both take effect in the hypothetical snapshot."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    controls = [
        Control(
            control_id="enable MFA on asset-hr-db-01",
            control_category="mfa_enforced",
            estimated_cost_inr=50_000.0,
            affected_asset_ids=["asset-hr-db-01"],
        ),
        Control(
            control_id="roll out EDR to asset-hr-db-01",
            control_category="edr_active",
            estimated_cost_inr=100_000.0,
            affected_asset_ids=["asset-hr-db-01"],
        ),
    ]

    hypothetical = apply_controls_to_snapshot(snapshot, controls)

    hr_db_asset = next(a for a in hypothetical["assets"] if a["asset_id"] == "asset-hr-db-01")
    assert hr_db_asset["identity_access"]["mfa_enforced"] is True
    assert hr_db_asset["edr"]["agent_installed"] is True
    assert hr_db_asset["edr"]["agent_healthy"] is True


def test_apply_controls_to_snapshot_leaves_unaffected_assets_untouched() -> None:
    """A control targeting one asset must not change any other asset's posture."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    reference_web_asset = copy.deepcopy(
        next(a for a in snapshot["assets"] if a["asset_id"] == "asset-web-01")
    )
    control = Control(
        control_id="enable MFA on asset-hr-db-01",
        control_category="mfa_enforced",
        estimated_cost_inr=50_000.0,
        affected_asset_ids=["asset-hr-db-01"],
    )

    hypothetical = apply_controls_to_snapshot(snapshot, [control])

    web_asset = next(a for a in hypothetical["assets"] if a["asset_id"] == "asset-web-01")
    assert web_asset == reference_web_asset


def test_apply_controls_to_snapshot_rejects_unmodelled_control_category() -> None:
    """A control_category with no entry in CONTROL_RESISTANCE_STRENGTH must raise, never silently no-op."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    control = Control(
        control_id="segment the network",
        control_category="network_segmentation",
        estimated_cost_inr=500_000.0,
        affected_asset_ids=["asset-web-01"],
    )

    with pytest.raises(ValueError, match="network_segmentation"):
        apply_controls_to_snapshot(snapshot, [control])


def _mfa_control(asset_id: str) -> Control:
    return Control(
        control_id=f"enable MFA on {asset_id}",
        control_category="mfa_enforced",
        estimated_cost_inr=50_000.0,
        affected_asset_ids=[asset_id],
    )


def _edr_control(asset_id: str) -> Control:
    return Control(
        control_id=f"roll out EDR to {asset_id}",
        control_category="edr_active",
        estimated_cost_inr=100_000.0,
        affected_asset_ids=[asset_id],
    )


def test_evaluate_portfolio_runs_joint_simulation_not_summed_deltas() -> None:
    """evaluate_portfolio must be a real, deterministic simulation of the jointly-applied hypothetical snapshot, not a shortcut.

    Verified two ways: it matches compute_risk_figure run directly against
    the same hypothetical snapshot with the same comparison seed (proving
    it's really that pipeline and nothing else), and calling it twice
    independently gives an identical result (proving it isn't reseeded
    freshly, non-reproducibly, on every call).
    """
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    controls = [_mfa_control("asset-hr-db-01"), _edr_control("asset-hr-db-01")]

    result = evaluate_portfolio(snapshot, controls)
    expected = compute_risk_figure(
        apply_controls_to_snapshot(snapshot, controls),
        seed=_derive_comparison_seed(snapshot),
    )
    repeated = evaluate_portfolio(copy.deepcopy(snapshot), controls)

    assert result == expected
    assert result == repeated


def test_overlapping_controls_do_not_double_count_benefit() -> None:
    """Two controls covering the same asset's exposure must show less combined risk reduction than the sum of each alone.

    asset-hr-db-01's finding has no EPSS score, so its exploit probability
    is the unscored baseline (0.05) with no control discount. Adding MFA
    alone or EDR alone each independently discount that same probability;
    adding both combines their resistance multiplicatively
    (1 - (1-0.4)(1-0.5) = 0.7), not additively (0.4+0.5 = 0.9) — so the
    joint reduction must be smaller than the sum of the two individual
    reductions. Expected Annual Loss is a mean, which is linear regardless
    of the shared-latent-factor correlation in core.engine.simulation, so
    this comparison holds up to Monte Carlo sampling noise only.
    """
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    mfa_control = _mfa_control("asset-hr-db-01")
    edr_control = _edr_control("asset-hr-db-01")

    baseline = evaluate_portfolio(snapshot, [])
    mfa_only = evaluate_portfolio(snapshot, [mfa_control])
    edr_only = evaluate_portfolio(snapshot, [edr_control])
    both = evaluate_portfolio(snapshot, [mfa_control, edr_control])

    reduction_mfa = baseline.expected_annual_loss_inr - mfa_only.expected_annual_loss_inr
    reduction_edr = baseline.expected_annual_loss_inr - edr_only.expected_annual_loss_inr
    reduction_both = baseline.expected_annual_loss_inr - both.expected_annual_loss_inr

    assert reduction_mfa > 0
    assert reduction_edr > 0
    assert reduction_both < reduction_mfa + reduction_edr


def test_recommend_portfolio_respects_budget_constraint() -> None:
    """The total_cost_inr of a recommended portfolio must never exceed the given budget_inr."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    candidates = [_mfa_control("asset-hr-db-01"), _edr_control("asset-hr-db-01")]
    budget_inr = 75_000.0  # enough for the 50k MFA control alone, not both (150k)

    recommendation = recommend_portfolio(snapshot, candidates, budget_inr)

    assert recommendation.total_cost_inr <= budget_inr
    assert sum(c.estimated_cost_inr for c in recommendation.selected_controls) == pytest.approx(
        recommendation.total_cost_inr
    )


def test_recommend_portfolio_reports_jointly_simulated_risk_reduction() -> None:
    """The risk_reduction_inr on the final recommendation must equal a real joint re-simulation of exactly the selected controls, not a sum of the per-control search estimates."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    candidates = [_mfa_control("asset-hr-db-01"), _edr_control("asset-hr-db-01")]

    recommendation = recommend_portfolio(snapshot, candidates, budget_inr=1_000_000.0)

    assert recommendation.selected_controls  # budget is generous enough to select something
    independently_verified = evaluate_portfolio(snapshot, recommendation.selected_controls)
    assert recommendation.post_investment_risk_figure == independently_verified
    assert recommendation.risk_reduction_inr == pytest.approx(
        recommendation.baseline_risk_figure.expected_annual_loss_inr
        - independently_verified.expected_annual_loss_inr
    )


def test_empty_candidate_controls_yields_zero_risk_reduction() -> None:
    """recommend_portfolio with no candidate controls must return baseline == post_investment risk figures."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)

    recommendation = recommend_portfolio(snapshot, [], budget_inr=1_000_000.0)

    assert recommendation.selected_controls == []
    assert recommendation.total_cost_inr == 0.0
    assert recommendation.baseline_risk_figure == recommendation.post_investment_risk_figure
    assert recommendation.risk_reduction_inr == 0.0


def test_find_control_gaps_lists_only_controls_the_engine_does_not_credit() -> None:
    """asset-web-01 has MFA and a healthy EDR agent; asset-hr-db-01 has neither."""
    gaps = find_control_gaps(copy.deepcopy(SAMPLE_SNAPSHOT))

    assert {(g.control_category, tuple(g.affected_asset_ids)) for g in gaps} == {
        ("mfa_enforced", ("asset-hr-db-01",)),
        ("edr_active", ("asset-hr-db-01",)),
    }
    assert all(g.control_id == f"{g.control_category}::{g.affected_asset_ids[0]}" for g in gaps)


def test_unknown_mfa_posture_is_a_gap_not_a_pass() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    web = next(a for a in snapshot["assets"] if a["asset_id"] == "asset-web-01")
    web["identity_access"]["mfa_enforced"] = None

    gaps = find_control_gaps(snapshot)

    assert "mfa_enforced::asset-web-01" in {g.control_id for g in gaps}


def test_every_applicable_category_applies_and_closes_its_gap() -> None:
    """APPLICABLE_CONTROL_CATEGORIES must stay in step with _apply_control_to_asset."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    gaps = find_control_gaps(snapshot)
    assert {g.control_category for g in gaps} == set(APPLICABLE_CONTROL_CATEGORIES)

    closed = apply_controls_to_snapshot(
        snapshot,
        [Control(g.control_id, g.control_category, 0.0, list(g.affected_asset_ids)) for g in gaps],
    )

    assert find_control_gaps(closed) == []


def test_compare_hypothetical_uses_common_random_numbers_baseline() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    controls = [_mfa_control("asset-hr-db-01"), _edr_control("asset-hr-db-01")]

    comparison = compare_hypothetical(snapshot, controls)

    assert comparison.baseline_risk_figure == evaluate_portfolio(snapshot, [])
    assert comparison.hypothetical_risk_figure == evaluate_portfolio(snapshot, controls)
    assert comparison.expected_annual_loss_change_inr == pytest.approx(
        comparison.hypothetical_risk_figure.expected_annual_loss_inr
        - comparison.baseline_risk_figure.expected_annual_loss_inr
    )
    assert comparison.value_at_risk_change_inr == pytest.approx(
        comparison.hypothetical_risk_figure.value_at_risk_inr
        - comparison.baseline_risk_figure.value_at_risk_inr
    )
    assert comparison.expected_annual_loss_change_inr < 0


@pytest.mark.parametrize(
    "controls",
    [
        [],
        [Control("mfa nowhere", "mfa_enforced", 0.0, [])],
        [Control("mfa on a ghost", "mfa_enforced", 0.0, ["asset-does-not-exist"])],
    ],
)
def test_compare_hypothetical_refuses_a_what_if_that_changes_nothing(
    controls: list[Control],
) -> None:
    with pytest.raises(ValueError):
        compare_hypothetical(copy.deepcopy(SAMPLE_SNAPSHOT), controls)
