"""Monte Carlo simulation over parameterized FAIR loss event scenarios."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from core.assumptions import (
    MONTE_CARLO_ITERATIONS,
    PERT_CONFIDENCE_FACTOR,
    SHARED_CONTROL_HEALTH_PERT,
)


def _sample_pert(
    min_value: float,
    most_likely: float,
    max_value: float,
    size: int | tuple[int, int],
    rng: np.random.Generator,
    confidence: float = PERT_CONFIDENCE_FACTOR,
) -> np.ndarray:
    """Draw samples from a Beta-PERT(min, most_likely, max) distribution.

    Beta-PERT is the standard way to turn a three-point (min, most likely,
    max) FAIR factor estimate into a distribution, with ``confidence``
    (commonly called lambda) controlling how tightly probability mass
    concentrates around ``most_likely``. See
    ``core.assumptions.PERT_CONFIDENCE_FACTOR``.

    Args:
        min_value: Lower bound of the estimate.
        most_likely: Mode of the estimate.
        max_value: Upper bound of the estimate.
        size: Number of samples to draw, or a (rows, cols) shape.
        rng: A seeded numpy random Generator — caller controls reproducibility.
        confidence: The Beta-PERT shape factor.

    Returns:
        An array of samples in ``[min_value, max_value]``.
    """
    if max_value == min_value:
        return np.full(size, min_value)
    alpha = 1.0 + confidence * (most_likely - min_value) / (max_value - min_value)
    beta = 1.0 + confidence * (max_value - most_likely) / (max_value - min_value)
    return min_value + rng.beta(alpha, beta, size=size) * (max_value - min_value)


def _derive_deterministic_seed(parameterized_scenarios: list[dict[str, Any]]) -> int:
    """Derive a reproducible Monte Carlo seed from scenario content.

    Hashing the scenarios themselves (rather than using a hardcoded
    constant) means the same snapshot always simulates with the same seed,
    while a materially different snapshot gets a different one — satisfying
    "same snapshot + same assumptions => same figure" without the seed
    having to be threaded through every caller by hand.

    Args:
        parameterized_scenarios: The scenarios about to be simulated.

    Returns:
        A non-negative integer suitable for ``numpy.random.default_rng``.
    """
    content = json.dumps(parameterized_scenarios, sort_keys=True, default=str)
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % (2**32)


def _sample_shared_control_health(
    parameterized_scenarios: list[dict[str, Any]],
    resolved_iterations: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Sample each referenced shared latent control-health factor once per iteration.

    One draw per iteration per control category, shared across every
    scenario that has that category active — this is the mechanism behind
    core.assumptions.SHARED_CONTROL_HEALTH_PERT (see its docstring): every
    scenario relying on a degraded-that-iteration control is affected
    together, inducing the positive correlation the SIH105 Notion doc's
    Conflict Register item C3 calls for, instead of each scenario drawing
    independent control noise.

    Returns:
        A dict from control category to its ``(iterations,)`` sample array,
        containing only categories actually referenced by at least one
        scenario's ``active_control_resistances`` and present in
        ``SHARED_CONTROL_HEALTH_PERT``.
    """
    referenced_categories = {
        category
        for scenario in parameterized_scenarios
        for category in scenario.get("active_control_resistances", {})
        if category in SHARED_CONTROL_HEALTH_PERT
    }
    return {
        category: _sample_pert(
            SHARED_CONTROL_HEALTH_PERT[category]["min"],
            SHARED_CONTROL_HEALTH_PERT[category]["most_likely"],
            SHARED_CONTROL_HEALTH_PERT[category]["max"],
            resolved_iterations,
            rng,
        )
        for category in referenced_categories
    }


def _sample_scenario_rate(
    scenario: dict[str, Any],
    shared_health_samples: dict[str, np.ndarray],
    resolved_iterations: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample this scenario's per-iteration loss event rate (events/year).

    If the scenario has no active controls with a matching shared latent
    factor, this is the simple case: sample directly from the scenario's
    already-combined ``loss_event_frequency`` distribution, unchanged from
    before shared-factor modelling existed.

    Otherwise, resistance for each affected control category is scaled by
    that iteration's shared health draw before combining, and the rate is
    rebuilt from the scenario's raw ``threat_event_frequency`` and
    ``exploit_probability`` rather than the pre-combined
    ``loss_event_frequency`` — because the latter already baked in a fixed,
    independent resistance value that a shared per-iteration health draw
    needs to be able to move.
    """
    active_resistances: dict[str, float] = scenario.get("active_control_resistances", {})
    correlated_categories = [c for c in active_resistances if c in shared_health_samples]

    if not correlated_categories:
        lef = scenario["loss_event_frequency"]
        return _sample_pert(lef["min"], lef["most_likely"], lef["max"], resolved_iterations, rng)

    tef = scenario["threat_event_frequency"]
    tef_samples = _sample_pert(tef["min"], tef["most_likely"], tef["max"], resolved_iterations, rng)

    effective_resistances = np.ones(resolved_iterations)
    for category, base_resistance in active_resistances.items():
        health = shared_health_samples.get(category, np.ones(resolved_iterations))
        effective_resistance = np.clip(base_resistance * health, 0.0, 1.0)
        effective_resistances *= 1.0 - effective_resistance
    combined_resistance = 1.0 - effective_resistances

    exploit_probability: float = scenario["exploit_probability"]
    vulnerability = np.clip(exploit_probability * (1.0 - combined_resistance), 0.0, 1.0)
    return np.asarray(tef_samples * vulnerability)


def run_monte_carlo(
    parameterized_scenarios: list[dict[str, Any]],
    *,
    iterations: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Propagate uncertainty through all parameterized scenarios via Monte
    Carlo simulation to produce a joint loss distribution.

    Each scenario's Loss Event Frequency is modelled as a Poisson process
    whose rate is itself uncertain: for every iteration, a rate is drawn
    (see :func:`_sample_scenario_rate`), then the actual number of loss
    events that year is drawn from ``Poisson(rate)``. Each of those events
    draws its own loss magnitude from the scenario's ``loss_magnitude``
    Beta-PERT distribution, and the year's total for that scenario is their
    sum. This compound structure (uncertain rate -> Poisson event count ->
    summed magnitudes) is what reproduces heavy-tailed annual outcomes
    rather than a single frequency-times-magnitude point multiplication.

    Scenarios that share an active control category (e.g. two scenarios
    both relying on ``edr_active``) are not simulated independently: a
    single shared health value for that category is drawn per iteration
    (:func:`_sample_shared_control_health`) and applied to every scenario
    relying on it in that iteration, so a bad iteration for one shared
    control raises loss across every dependent scenario simultaneously.
    This is the engine's resolution of the SIH105 Notion doc's Conflict
    Register item C3 ("scenario independence in aggregation") — see
    ``core.assumptions.SHARED_CONTROL_HEALTH_PERT`` for the full rationale.
    Independent summation across scenarios remains correct for whatever
    portion of loss has no shared cause.

    Args:
        parameterized_scenarios: Output of
            :func:`core.engine.parameterization.parameterize_scenario` for
            every scenario in scope. Each element must contain:
            ``scenario_id`` (str), ``loss_event_frequency`` and
            ``loss_magnitude`` (dicts with ``min``/``most_likely``/``max``),
            and, to participate in shared-factor correlation,
            ``threat_event_frequency``, ``exploit_probability``, and
            ``active_control_resistances`` (all present when the scenario
            came from :func:`~core.engine.parameterization.parameterize_scenario`;
            a scenario missing these — e.g. built by hand in a test — is
            simply treated as having no correlated controls).
        iterations: Override for the iteration count. Defaults to
            ``core.assumptions.MONTE_CARLO_ITERATIONS`` — callers outside of
            tests must never pass this.
        seed: Override for the random seed. Defaults to a value derived
            deterministically from ``parameterized_scenarios`` via
            :func:`_derive_deterministic_seed` — callers outside of tests
            must never pass this, since a fixed literal here would make
            every snapshot simulate identically regardless of content.

    Returns:
        A dict with ``iterations``, ``seed`` (the values actually used, so
        the run is traceable and reproducible), ``total_annual_loss_samples_inr``
        (a ``(iterations,)`` array, one total per simulated year), and
        ``per_scenario_annual_loss_samples_inr`` (a dict from
        ``scenario_id`` to its own ``(iterations,)`` array).

    Must never:
        Use an iteration count other than
        ``core.assumptions.MONTE_CARLO_ITERATIONS``, or a fixed seed that
        isn't recorded alongside the result (the same snapshot + same
        assumptions must be reproducible on rerun).
    """
    resolved_iterations = iterations if iterations is not None else MONTE_CARLO_ITERATIONS
    resolved_seed = seed if seed is not None else _derive_deterministic_seed(parameterized_scenarios)
    rng = np.random.default_rng(resolved_seed)
    shared_health_samples = _sample_shared_control_health(parameterized_scenarios, resolved_iterations, rng)

    per_scenario_losses: dict[str, np.ndarray] = {}
    for scenario in parameterized_scenarios:
        lm = scenario["loss_magnitude"]

        rate_samples = _sample_scenario_rate(scenario, shared_health_samples, resolved_iterations, rng)
        event_counts = rng.poisson(np.clip(rate_samples, 0, None))

        annual_losses = np.zeros(resolved_iterations)
        max_events = int(event_counts.max()) if resolved_iterations else 0
        for count in range(1, max_events + 1):
            mask = event_counts == count
            n_masked = int(mask.sum())
            if n_masked == 0:
                continue
            magnitude_samples = _sample_pert(
                lm["min"], lm["most_likely"], lm["max"], (n_masked, count), rng
            )
            annual_losses[mask] = magnitude_samples.sum(axis=1)

        per_scenario_losses[scenario["scenario_id"]] = annual_losses

    if per_scenario_losses:
        total_losses = np.sum(list(per_scenario_losses.values()), axis=0)
    else:
        total_losses = np.zeros(resolved_iterations)

    return {
        "iterations": resolved_iterations,
        "seed": resolved_seed,
        "total_annual_loss_samples_inr": total_losses,
        "per_scenario_annual_loss_samples_inr": per_scenario_losses,
    }
