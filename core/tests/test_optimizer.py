"""Tests for core/optimizer.py's joint-simulation budget optimizer.

The single most important property to test here is that overlapping
controls are never double-counted — a naive sum-of-deltas implementation
must fail these tests even if it produces plausible-looking numbers.
"""

from __future__ import annotations


def test_evaluate_portfolio_runs_joint_simulation_not_summed_deltas() -> None:
    """evaluate_portfolio's result for two overlapping controls must differ from the sum of their individually-simulated deltas."""
    raise NotImplementedError


def test_overlapping_controls_do_not_double_count_benefit() -> None:
    """Patching a CVE and hardening the EDR that would have caught it must show less combined benefit than the sum of each alone."""
    raise NotImplementedError


def test_recommend_portfolio_respects_budget_constraint() -> None:
    """The total_cost_inr of a recommended portfolio must never exceed the given budget_inr."""
    raise NotImplementedError


def test_recommend_portfolio_reports_jointly_simulated_risk_reduction() -> None:
    """The risk_reduction_inr on the final recommendation must come from an actual joint re-simulation, not a heuristic used to search."""
    raise NotImplementedError


def test_apply_controls_to_snapshot_never_mutates_input_snapshot() -> None:
    """apply_controls_to_snapshot must return a new hypothetical snapshot and leave the input snapshot unchanged."""
    raise NotImplementedError


def test_empty_candidate_controls_yields_zero_risk_reduction() -> None:
    """recommend_portfolio with no candidate controls must return baseline == post_investment risk figures."""
    raise NotImplementedError
