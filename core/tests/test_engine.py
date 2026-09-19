"""Tests for core/engine.py's Open FAIR + Monte Carlo pipeline.

Must include a determinism test (same snapshot + same assumptions +
same seed => same figure) since the engine's credibility depends on
reproducibility, and a test that every parameter traces back to
core.assumptions rather than a bare literal.
"""

from __future__ import annotations


def test_compute_risk_figure_is_deterministic_given_fixed_seed() -> None:
    """Running the engine twice against the same snapshot and seed must produce identical EAL/VaR."""
    raise NotImplementedError


def test_compute_risk_figure_never_invokes_an_llm_or_ml_model() -> None:
    """The engine pipeline must not call out to any LLM client or ML model at any stage."""
    raise NotImplementedError


def test_top_contributors_are_ranked_and_sum_consistently() -> None:
    """top_contributors must be sorted by expected_annual_loss_inr descending and be internally consistent with the total."""
    raise NotImplementedError


def test_parameterize_scenario_uses_only_named_assumptions() -> None:
    """Every FAIR parameter attached to a scenario must be traceable to a core.assumptions constant, never a bare literal."""
    raise NotImplementedError


def test_value_at_risk_percentile_matches_configured_assumption() -> None:
    """The percentile reported on RiskFigure must match core.assumptions.VALUE_AT_RISK_PERCENTILE at computation time."""
    raise NotImplementedError


def test_compute_risk_figure_against_sample_aggregated_fixture() -> None:
    """The engine should run end to end against schema/sample_aggregated.json and produce a well-formed RiskFigure."""
    raise NotImplementedError
