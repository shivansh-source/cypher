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
    RESISTANCE_CONTROL_CATEGORIES,
    Control,
    _derive_comparison_seed,
    _reduction_per_rupee,
    _Search,
    apply_controls_to_snapshot,
    compare_hypothetical,
    compare_snapshots,
    evaluate_portfolio,
    find_control_gaps,
    prioritize_controls,
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
    gaps = [
        g
        for g in find_control_gaps(copy.deepcopy(SAMPLE_SNAPSHOT))
        if g.control_category in RESISTANCE_CONTROL_CATEGORIES
    ]

    assert {(g.control_category, tuple(g.affected_asset_ids)) for g in gaps} == {
        ("mfa_enforced", ("asset-hr-db-01",)),
        ("edr_active", ("asset-hr-db-01",)),
    }
    assert all(g.control_id == f"{g.control_category}::{g.affected_asset_ids[0]}" for g in gaps)


def test_find_control_gaps_lists_every_open_finding_and_weak_backup() -> None:
    """Each open finding is one fix; a service with no backup is one hardening."""
    gaps = find_control_gaps(copy.deepcopy(SAMPLE_SNAPSHOT))

    fixes = {
        (g.affected_asset_ids[0], g.finding_id)
        for g in gaps
        if g.control_category == "remediate_finding"
    }
    backups = {
        g.service_id: g.affected_asset_ids for g in gaps if g.control_category == "harden_backup"
    }
    assert fixes == {("asset-web-01", "finding-0001"), ("asset-hr-db-01", "finding-0002")}
    # svc-core-banking already has a tested, immutable backup; svc-internal-hr has none.
    assert backups == {"svc-internal-hr": ["asset-hr-db-01"]}


def test_remediated_finding_is_not_a_candidate() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][0]["findings"][0]["remediated_at"] = "2026-09-19T00:00:00Z"

    ids = {g.finding_id for g in find_control_gaps(snapshot)}

    assert "finding-0001" not in ids


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

    closed = apply_controls_to_snapshot(snapshot, [g.priced(0.0) for g in gaps])

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


def test_compare_snapshots_of_a_snapshot_with_itself_is_exactly_zero() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)

    comparison = compare_snapshots(snapshot, copy.deepcopy(snapshot))

    assert comparison.expected_annual_loss_change_inr == 0.0
    assert comparison.value_at_risk_change_inr == 0.0
    assert comparison.proposed_risk_figure == comparison.baseline_risk_figure


def test_compare_snapshots_uses_the_baselines_seed_for_both_runs() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    proposed = copy.deepcopy(snapshot)
    proposed["assets"][1]["network"]["internet_facing"] = True
    seed = _derive_comparison_seed(snapshot)

    comparison = compare_snapshots(snapshot, proposed)

    assert comparison.baseline_risk_figure == compute_risk_figure(snapshot, seed=seed)
    assert comparison.proposed_risk_figure == compute_risk_figure(proposed, seed=seed)
    assert comparison.expected_annual_loss_change_inr == (
        comparison.proposed_risk_figure.expected_annual_loss_inr
        - comparison.baseline_risk_figure.expected_annual_loss_inr
    )
    # Common random numbers: a scenario the change does not touch keeps its exact draws.
    untouched = {
        c.scenario_id: c.expected_annual_loss_inr
        for c in comparison.baseline_risk_figure.top_contributors
        if c.asset_id != "asset-hr-db-01"
    }
    assert untouched
    for contribution in comparison.proposed_risk_figure.top_contributors:
        if contribution.scenario_id in untouched:
            assert contribution.expected_annual_loss_inr == untouched[contribution.scenario_id]


def test_compare_hypothetical_is_compare_snapshots_on_the_applied_portfolio() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    controls = [_mfa_control("asset-hr-db-01"), _edr_control("asset-hr-db-01")]

    hypothetical = compare_hypothetical(snapshot, controls)
    direct = compare_snapshots(snapshot, apply_controls_to_snapshot(snapshot, controls))

    assert hypothetical.baseline_risk_figure == direct.baseline_risk_figure
    assert hypothetical.hypothetical_risk_figure == direct.proposed_risk_figure
    assert hypothetical.expected_annual_loss_change_inr == direct.expected_annual_loss_change_inr
    assert hypothetical.value_at_risk_change_inr == direct.value_at_risk_change_inr


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


def _gap(snapshot: dict[str, Any], control_id: str, cost: float) -> Control:
    return next(g for g in find_control_gaps(snapshot) if g.control_id == control_id).priced(cost)


def test_remediating_a_finding_removes_its_loss_and_leaves_the_input_untouched() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    reference = copy.deepcopy(snapshot)
    fix = _gap(snapshot, "remediate_finding::asset-web-01::finding-0001", 0.0)

    baseline = evaluate_portfolio(snapshot, [])
    fixed = evaluate_portfolio(snapshot, [fix])

    assert snapshot == reference
    assert fixed.expected_annual_loss_inr < baseline.expected_annual_loss_inr
    web = next(
        a
        for a in apply_controls_to_snapshot(snapshot, [fix])["assets"]
        if a["asset_id"] == "asset-web-01"
    )
    assert web["findings"][0]["remediated_at"] == snapshot["observed_at"]


def test_fixing_one_finding_leaves_other_scenarios_draws_unchanged() -> None:
    """Common random numbers survive removing a scenario: the other scenario's loss is identical."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][1]["network"]["internet_facing"] = True
    fix_web = _gap(snapshot, "remediate_finding::asset-web-01::finding-0001", 0.0)
    fix_hr = _gap(snapshot, "remediate_finding::asset-hr-db-01::finding-0002", 0.0)

    only_hr_left = evaluate_portfolio(snapshot, [fix_web])
    only_web_left = evaluate_portfolio(snapshot, [fix_hr])
    baseline = evaluate_portfolio(snapshot, [])

    assert (
        only_hr_left.expected_annual_loss_inr + only_web_left.expected_annual_loss_inr
        == pytest.approx(baseline.expected_annual_loss_inr, rel=1e-9)
    )


@pytest.mark.parametrize(
    "control",
    [
        Control(
            "fix a ghost", "remediate_finding", 0.0, ["asset-web-01"], finding_id="finding-nope"
        ),
        Control("fix nothing", "remediate_finding", 0.0, ["asset-web-01"]),
        Control("harden a ghost", "harden_backup", 0.0, ["asset-web-01"], service_id="svc-nope"),
        Control(
            "harden what is already hard",
            "harden_backup",
            0.0,
            ["asset-web-01"],
            service_id="svc-core-banking",
        ),
    ],
)
def test_a_change_that_changes_nothing_is_refused(control: Control) -> None:
    with pytest.raises(ValueError):
        apply_controls_to_snapshot(copy.deepcopy(SAMPLE_SNAPSHOT), [control])


def test_already_remediated_finding_cannot_be_fixed_again() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    fix = _gap(snapshot, "remediate_finding::asset-web-01::finding-0001", 0.0)
    snapshot["assets"][0]["findings"][0]["remediated_at"] = "2026-09-19T00:00:00Z"

    with pytest.raises(ValueError, match="already remediated"):
        apply_controls_to_snapshot(snapshot, [fix])


def test_hardening_a_missing_backup_reduces_loss() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    harden = _gap(snapshot, "harden_backup::svc-internal-hr", 0.0)

    assert (
        evaluate_portfolio(snapshot, [harden]).expected_annual_loss_inr
        < evaluate_portfolio(snapshot, []).expected_annual_loss_inr
    )


def test_control_on_an_asset_whose_findings_are_fixed_is_rejected_as_no_reduction() -> None:
    """Overlap: once hr-db's only finding is fixed, MFA there protects nothing modelled."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    fix_hr = _gap(snapshot, "remediate_finding::asset-hr-db-01::finding-0002", 1.0)
    mfa_hr = _gap(snapshot, "mfa_enforced::asset-hr-db-01", 1.0)

    recommendation = recommend_portfolio(snapshot, [fix_hr, mfa_hr], budget_inr=10.0)

    assert [c.control_id for c in recommendation.selected_controls] == [fix_hr.control_id]
    assert [(r.control.control_id, r.reason) for r in recommendation.rejected] == [
        (mfa_hr.control_id, "no_reduction")
    ]


def test_one_expensive_control_beats_many_cheap_small_ones() -> None:
    """The knapsack guard: greedy-by-ratio alone would spend the budget on cheap, small wins."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    fix_web = _gap(snapshot, "remediate_finding::asset-web-01::finding-0001", 10_000.0)
    small = [
        _gap(snapshot, "mfa_enforced::asset-hr-db-01", 1.0),
        _gap(snapshot, "edr_active::asset-hr-db-01", 1.0),
    ]
    budget = 10_000.0  # the fix alone fits; the fix plus anything else does not
    search = _Search(snapshot)
    evaluator = search.evaluate
    ratio_only = search.greedy([*small, fix_web], budget_inr=budget, priority=_reduction_per_rupee)
    # Premise: ratio-greedy alone takes the cheap controls and then cannot afford the fix,
    # although the fix on its own is worth far more than both of them together.
    assert fix_web.control_id not in {c.control_id for c in ratio_only}
    assert (
        evaluator([fix_web]).expected_annual_loss_inr
        < evaluator(ratio_only).expected_annual_loss_inr
    )

    recommendation = recommend_portfolio(snapshot, [*small, fix_web], budget)

    assert [c.control_id for c in recommendation.selected_controls] == [fix_web.control_id]
    assert recommendation.total_cost_inr <= budget


def test_steps_are_joint_and_add_up_to_the_portfolio_reduction() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    candidates = [g.priced(10_000.0) for g in find_control_gaps(snapshot)]

    recommendation = recommend_portfolio(snapshot, candidates, budget_inr=1_000_000.0)

    assert recommendation.steps
    assert recommendation.steps[-1].expected_annual_loss_inr == pytest.approx(
        recommendation.post_investment_risk_figure.expected_annual_loss_inr
    )
    assert sum(s.marginal_reduction_inr for s in recommendation.steps) == pytest.approx(
        recommendation.risk_reduction_inr
    )
    for i, step in enumerate(recommendation.steps):
        prefix = [s.control for s in recommendation.steps[: i + 1]]
        assert (
            step.expected_annual_loss_inr
            == evaluate_portfolio(snapshot, prefix).expected_annual_loss_inr
        )
    selected = {c.control_id for c in recommendation.selected_controls}
    assert selected | {r.control.control_id for r in recommendation.rejected} == {
        c.control_id for c in candidates
    }


def test_budget_below_every_cost_selects_nothing_and_says_why() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    candidates = [g.priced(50_000.0) for g in find_control_gaps(snapshot)]

    recommendation = recommend_portfolio(snapshot, candidates, budget_inr=1_000.0)

    assert recommendation.selected_controls == []
    assert recommendation.risk_reduction_inr == 0.0
    assert {r.reason for r in recommendation.rejected} == {"over_budget"}


def test_priority_plan_orders_by_marginal_reduction_and_is_joint() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    gaps = find_control_gaps(snapshot)

    plan = prioritize_controls(snapshot, gaps)

    assert plan.steps
    reductions = [s.marginal_reduction_inr for s in plan.steps]
    assert all(r > 0 for r in reductions)
    assert reductions == sorted(reductions, reverse=True)
    joint = evaluate_portfolio(snapshot, [s.gap.priced(0.0) for s in plan.steps])
    assert plan.steps[-1].expected_annual_loss_inr == joint.expected_annual_loss_inr
    assert sum(reductions) == pytest.approx(
        plan.baseline_risk_figure.expected_annual_loss_inr - joint.expected_annual_loss_inr
    )
    assert not plan.truncated
    planned = {s.gap.control_id for s in plan.steps} | {g.control_id for g in plan.no_effect}
    assert planned == {g.control_id for g in gaps}


def test_priority_plan_respects_max_steps_and_flags_truncation() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][1]["network"]["internet_facing"] = True

    plan = prioritize_controls(snapshot, find_control_gaps(snapshot), max_steps=1)

    assert len(plan.steps) == 1
    assert plan.truncated


def test_search_estimate_matches_the_simulated_expected_loss() -> None:
    """The closed form that orders the search must agree with the Monte Carlo it stands in for.

    If an engine change made them drift apart, the search would quietly try
    candidates in the wrong order; this pins them together (to within
    sampling error at the engine's iteration count).
    """
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    search = _Search(snapshot)
    for controls in ([], [_mfa_control("asset-hr-db-01")], [_edr_control("asset-hr-db-01")]):
        simulated = search.evaluate(controls).expected_annual_loss_inr
        assert search.estimate(controls) == pytest.approx(simulated, rel=0.05)
