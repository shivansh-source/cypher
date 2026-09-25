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


def _stream(seed: int, *key: str) -> np.random.Generator:
    """An independent random stream for one named part of a simulation run.

    Every scenario (and every shared control-health factor) draws from its
    own stream, keyed by the run's seed plus a stable hash of its name,
    instead of all of them consuming one sequential stream in list order.
    With one sequential stream, removing a scenario or changing how many
    draws one scenario makes shifts the draws of every scenario after it,
    so two runs that differ in one place differ everywhere — which defeats
    the common-random-numbers comparison ``core.optimizer`` relies on to
    tell a control's real effect from sampling noise.

    Args:
        seed: The run's seed.
        *key: Names identifying the stream, e.g. a scenario_id and a purpose.

    Returns:
        A generator whose draws depend only on ``seed`` and ``key``.
    """
    words = [
        int.from_bytes(hashlib.sha256(part.encode("utf-8")).digest()[:8], byteorder="big")
        for part in key
    ]
    return np.random.default_rng([seed, *words])


def _sample_shared_control_health(
    parameterized_scenarios: list[dict[str, Any]],
    resolved_iterations: int,
    seed: int,
) -> dict[str, np.ndarray]:
    """Sample each referenced shared latent control-health factor once per iteration.

    One draw per iteration per control category, shared across every
    scenario that has that category active — this is the mechanism behind
    core.assumptions.SHARED_CONTROL_HEALTH_PERT (see its docstring): every
    scenario relying on a degraded-that-iteration control is affected
    together, inducing the positive correlation the SIH105 Notion doc's
    Conflict Register item C3 calls for, instead of each scenario drawing
    independent control noise.

    Each category draws from its own stream (see :func:`_stream`), so
    whether another category is referenced never changes its draws.

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
            _stream(seed, "control_health", category),
        )
        for category in sorted(referenced_categories)
    }


def _sample_scenario_rate(
    scenario: dict[str, Any],
    shared_health_samples: dict[str, np.ndarray],
    resolved_iterations: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample this scenario's per-iteration loss event rate (events/year).

    The rate is built from the scenario's raw ``threat_event_frequency``
    times a per-iteration vulnerability: ``exploit_probability`` net of each
    active control's resistance, scaled by that iteration's shared health
    draw for the control's category (a category with no shared factor keeps
    its base resistance every iteration). With no active controls this is
    exactly the scenario's ``loss_event_frequency`` distribution, since that
    is ``threat_event_frequency`` scaled by the same vulnerability.

    Threat events are always drawn the same way, whatever controls are
    active, so crediting or removing a control changes only this scenario's
    vulnerability — never which threat-event draws it gets. That keeps a
    what-if comparison on common random numbers.

    A scenario without ``threat_event_frequency``/``exploit_probability``
    (e.g. built by hand in a test) is sampled directly from its
    ``loss_event_frequency``.
    """
    active_resistances: dict[str, float] = scenario.get("active_control_resistances", {})

    if "threat_event_frequency" not in scenario or "exploit_probability" not in scenario:
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
    resolved_seed = (
        seed if seed is not None else _derive_deterministic_seed(parameterized_scenarios)
    )
    shared_health_samples = _sample_shared_control_health(
        parameterized_scenarios, resolved_iterations, resolved_seed
    )

    per_scenario_losses: dict[str, np.ndarray] = {}
    for scenario in parameterized_scenarios:
        lm = scenario["loss_magnitude"]
        # Separate streams per scenario and per purpose: see _stream.
        scenario_id = str(scenario["scenario_id"])
        rate_samples = _sample_scenario_rate(
            scenario,
            shared_health_samples,
            resolved_iterations,
            _stream(resolved_seed, "rate", scenario_id),
        )
        event_counts = _stream(resolved_seed, "events", scenario_id).poisson(
            np.clip(rate_samples, 0, None)
        )
        magnitude_rng = _stream(resolved_seed, "magnitude", scenario_id)

        # One magnitude per loss event across every simulated year, drawn in
        # a single call, then summed back into the year each event fell in.
        total_events = int(event_counts.sum())
        if total_events:
            magnitude_samples = _sample_pert(
                lm["min"], lm["most_likely"], lm["max"], total_events, magnitude_rng
            )
            event_year = np.repeat(np.arange(resolved_iterations), event_counts)
            annual_losses = np.bincount(
                event_year, weights=magnitude_samples, minlength=resolved_iterations
            )
        else:
            annual_losses = np.zeros(resolved_iterations)

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
