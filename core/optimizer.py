"""Budget allocation optimizer.

Recommends which controls to fund, given a fixed budget, to maximize risk
reduction. The central constraint on this module: candidate portfolios of
controls must always be evaluated by re-running the full Monte Carlo
simulation (``core.engine.run_monte_carlo``) against the portfolio as a
whole, never by summing each control's individually-simulated delta. See
repo-root ``CLAUDE.md`` principle 7.

Overlapping controls (e.g. patching a CVE *and* hardening the EDR that
would have caught exploitation of that same CVE) make naive addition badly
overstate combined benefit — the true joint benefit is smaller than the
sum of the parts, and only a joint re-simulation captures that.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from core.assumptions import (
    CONTROL_RESISTANCE_STRENGTH,
    PERT_CONFIDENCE_FACTOR,
    SHARED_CONTROL_HEALTH_PERT,
)
from core.engine import (
    RiskFigure,
    build_loss_event_scenarios,
    compute_risk_figure,
    parameterize_scenario,
)

# The engine's own rules for "is this control observed active on this
# asset" and "what backup posture does this service have" — imported rather
# than restated so that what find_control_gaps calls a gap can never drift
# from what the engine credits.
from core.engine.parameterization import (
    _active_control_resistances,
    _single_service_backup_posture,
)

#: Control categories credited as resistance on an asset. Each needs an
#: entry in ``core.assumptions.CONTROL_RESISTANCE_STRENGTH``.
RESISTANCE_CONTROL_CATEGORIES: tuple[str, ...] = ("mfa_enforced", "edr_active")

#: Every control category :func:`apply_controls_to_snapshot` knows how to
#: express as a schema change. Must stay in step with :func:`_apply_control`
#: — ``core/tests/test_optimizer.py`` checks every entry here applies
#: cleanly and closes its gap.
#:
#: - ``mfa_enforced`` / ``edr_active``: turn the control on for an asset.
#: - ``remediate_finding``: fix one open finding (``Control.finding_id``).
#: - ``harden_backup``: give one service (``Control.service_id``) a tested
#:   backup with an immutable copy.
APPLICABLE_CONTROL_CATEGORIES: tuple[str, ...] = (
    *RESISTANCE_CONTROL_CATEGORIES,
    "remediate_finding",
    "harden_backup",
)

#: The backup posture ``harden_backup`` brings a service to — the best one
#: ``core.engine.parameterization`` recognizes.
_HARDENED_BACKUP_POSTURE = "backup_tested_immutable"

#: Relative tolerance below which a change in Expected Annual Loss counts
#: as no change. Removing a scenario reorders a floating-point sum, which
#: can move the total by a few ulps; this absorbs that, nothing more. A
#: numerical tolerance, not a modelling judgement.
_NUMERICAL_TOLERANCE = 1e-9


def _derive_comparison_seed(snapshot: dict[str, Any]) -> int:
    """Derive a Monte Carlo seed from the original (pre-control) snapshot.

    Every candidate portfolio evaluated against the same base snapshot
    gets this same seed, rather than each hypothetical snapshot deriving
    its own from its own (different) content — deliberately, since that
    makes every evaluation a common-random-numbers comparison: the same
    underlying draws, differing only in the modelled effect of the
    controls under test. ``core.engine.simulation`` keys each scenario's
    draws by its own id, so fixing one finding leaves every other
    scenario's draws untouched. Without this, two independently-seeded
    Monte Carlo runs of a low-probability scenario can differ by more than
    the controls' true effect, making a genuinely beneficial control look
    harmful from sampling noise alone. This mirrors the SIH105 project
    doc's lab-validation protocol (page 11), which uses the identical
    technique — seeding paired control on/off runs identically — for the
    same reason.
    """
    content = json.dumps(snapshot, sort_keys=True, default=str)
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % (2**32)


@dataclass(frozen=True)
class Control:
    """A candidate control investment.

    Attributes:
        control_id: Stable identifier for this control instance (e.g.
            "remediate_finding::asset-web-01::finding-0003").
        control_category: One of :data:`APPLICABLE_CONTROL_CATEGORIES`.
        estimated_cost_inr: Estimated first-year cost to implement this
            control, in INR — a declared input, never estimated here.
        affected_asset_ids: Assets this control changes. For
            ``harden_backup``, every asset that relies on the service.
        finding_id: For ``remediate_finding`` only: the finding to fix,
            which must be open on one of ``affected_asset_ids``.
        service_id: For ``harden_backup`` only: the service whose backup
            is hardened.
    """

    control_id: str
    control_category: str
    estimated_cost_inr: float
    affected_asset_ids: list[str]
    finding_id: str | None = None
    service_id: str | None = None


@dataclass(frozen=True)
class PortfolioStep:
    """One control in a portfolio, in the order the search added it.

    Every figure here is from a joint re-simulation of the portfolio up to
    and including this control — never an isolated per-control estimate.

    Attributes:
        control: The control added at this step.
        cumulative_cost_inr: Declared cost of every control up to and
            including this one.
        expected_annual_loss_inr: Joint Expected Annual Loss with every
            control up to and including this one applied.
        value_at_risk_inr: Joint Value at Risk for the same portfolio.
        marginal_reduction_inr: Expected Annual Loss before this step minus
            after it — the difference of two joint simulations, so the
            steps' reductions add up exactly to the portfolio's total.
    """

    control: Control
    cumulative_cost_inr: float
    expected_annual_loss_inr: float
    value_at_risk_inr: float
    marginal_reduction_inr: float


@dataclass(frozen=True)
class RejectedControl:
    """A candidate the recommendation leaves out, and why.

    Attributes:
        control: The candidate.
        reason: ``"over_budget"`` — it does not fit the budget left after
            the selected controls; ``"no_reduction"`` — it fits, but
            simulated together with the selected controls it gives no
            further measurable reduction (e.g. its asset's findings are
            already fixed by the portfolio, or it protects an asset with
            no open finding).
    """

    control: Control
    reason: Literal["over_budget", "no_reduction"]


@dataclass(frozen=True)
class PortfolioRecommendation:
    """The optimizer's recommended set of controls for a given budget.

    Attributes:
        selected_controls: The controls recommended for funding, in the
            order the search added them.
        total_cost_inr: Sum of ``estimated_cost_inr`` across
            ``selected_controls`` — this sum is a cost total and is fine to
            compute by addition; it is loss/benefit figures that must never
            be summed this way.
        baseline_risk_figure: The engine's output against the snapshot with
            no candidate controls applied.
        post_investment_risk_figure: The engine's output from a joint
            re-simulation of the snapshot with every selected control's
            effect applied simultaneously.
        risk_reduction_inr: ``baseline_risk_figure.expected_annual_loss_inr
            - post_investment_risk_figure.expected_annual_loss_inr``,
            derived from the two jointly-simulated figures above, never
            from summing individual control deltas.
        value_at_risk_reduction_inr: The same difference for Value at Risk.
        steps: One :class:`PortfolioStep` per selected control, in order.
        rejected: Every candidate not selected, with the reason.
    """

    selected_controls: list[Control]
    total_cost_inr: float
    baseline_risk_figure: RiskFigure
    post_investment_risk_figure: RiskFigure
    risk_reduction_inr: float
    value_at_risk_reduction_inr: float = 0.0
    steps: list[PortfolioStep] = field(default_factory=list)
    rejected: list[RejectedControl] = field(default_factory=list)


def _hypothetical_timestamp(snapshot: dict[str, Any]) -> str:
    """The instant a hypothetical change is stamped with: the snapshot's own observation time.

    Deliberately not the wall clock, so the same snapshot and candidates
    always produce the same hypothetical snapshot (and the same figures).
    """
    return str(snapshot["observed_at"])


def _apply_control(snapshot: dict[str, Any], control: Control) -> None:
    """Mutate ``snapshot`` (already a private copy) to reflect one control.

    Raises:
        ValueError: If the control cannot change anything real — an
            unmodelled category, a resistance category with no resistance
            value, or a finding/service that is missing or already in the
            target state. A control that silently changes nothing would be
            reported as worthless for a question never actually asked.
    """
    category = control.control_category
    assets_by_id = {asset["asset_id"]: asset for asset in snapshot["assets"]}

    if category in RESISTANCE_CONTROL_CATEGORIES:
        if category not in CONTROL_RESISTANCE_STRENGTH:
            raise ValueError(
                f"Control {control.control_id!r} has control_category {category!r}, which "
                "has no entry in core.assumptions.CONTROL_RESISTANCE_STRENGTH — applying it "
                "would have no modelled effect on the risk figure."
            )
        for asset_id in control.affected_asset_ids:
            asset = assets_by_id.get(asset_id)
            if asset is None:
                continue
            if category == "mfa_enforced":
                asset["identity_access"] = {
                    **(asset.get("identity_access") or {}),
                    "mfa_enforced": True,
                }
            else:
                asset["edr"] = {
                    **(asset.get("edr") or {}),
                    "agent_installed": True,
                    "agent_healthy": True,
                }
        return

    if category == "remediate_finding":
        if not control.finding_id:
            raise ValueError(f"Control {control.control_id!r} needs a finding_id to remediate")
        for asset_id in control.affected_asset_ids:
            asset = assets_by_id.get(asset_id)
            for finding in (asset or {}).get("findings", []):
                if finding.get("finding_id") != control.finding_id:
                    continue
                if finding.get("remediated_at") is not None:
                    raise ValueError(
                        f"Control {control.control_id!r}: finding {control.finding_id!r} is "
                        "already remediated, so fixing it would change nothing"
                    )
                finding["remediated_at"] = _hypothetical_timestamp(snapshot)
                return
        raise ValueError(
            f"Control {control.control_id!r}: finding {control.finding_id!r} is not on "
            f"asset(s) {', '.join(control.affected_asset_ids)}"
        )

    if category == "harden_backup":
        if not control.service_id:
            raise ValueError(f"Control {control.control_id!r} needs a service_id to harden")
        for service in snapshot.get("services", []):
            if service.get("service_id") == control.service_id:
                if _single_service_backup_posture(service) == _HARDENED_BACKUP_POSTURE:
                    raise ValueError(
                        f"Control {control.control_id!r}: service {control.service_id!r} "
                        "already has a tested, immutable backup"
                    )
                service["backup"] = {
                    **(service.get("backup") or {}),
                    "exists": True,
                    "last_tested_at": _hypothetical_timestamp(snapshot),
                    "immutable_copy": True,
                }
                return
        raise ValueError(
            f"Control {control.control_id!r}: service {control.service_id!r} is not in the snapshot"
        )

    raise ValueError(
        f"Control {control.control_id!r} has control_category {category!r}, which "
        "apply_controls_to_snapshot cannot express as a change to the snapshot "
        f"(known: {', '.join(APPLICABLE_CONTROL_CATEGORIES)}) — so it would have no "
        "modelled effect on the risk figure."
    )


def apply_controls_to_snapshot(snapshot: dict[str, Any], controls: list[Control]) -> dict[str, Any]:
    """Produce a hypothetical snapshot reflecting a candidate control portfolio.

    Every control's effect is applied to a single deep copy of the
    snapshot before that copy is ever read by anything — there is no
    intermediate "per-control snapshot" that gets its own risk figure
    computed, which is what would let overlap slip in through the back
    door even if the final numbers were computed jointly.

    Overlap is real and captured downstream: two resistance controls on
    one asset combine as ``1 - (1-r1)(1-r2)`` (see
    ``core.engine.parameterization._combine_resistances``); fixing a
    finding removes its scenario entirely, so MFA or EDR on the same asset
    protects less afterwards; hardening a backup shrinks the loss every
    remaining scenario on that service would cause.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        controls: The candidate portfolio of controls to hypothetically
            apply together.

    Returns:
        A new, hypothetical schema-shaped snapshot with the effects of
        every control in ``controls`` applied jointly (affected findings
        marked remediated, affected assets' control posture or services'
        backup posture updated) — never a real snapshot, and never
        committed via ``core.snapshot.commit_snapshot``.

    Raises:
        ValueError: If any control cannot change anything (see
            :func:`_apply_control`).

    Must never:
        Apply controls one at a time and cache each one's isolated effect
        for later summation — the whole point of this function is to
        produce one combined hypothetical state that
        ``core.engine.compute_risk_figure`` can be run against as a whole.
    """
    hypothetical_snapshot = copy.deepcopy(snapshot)
    for control in controls:
        _apply_control(hypothetical_snapshot, control)
    return hypothetical_snapshot


def evaluate_portfolio(snapshot: dict[str, Any], controls: list[Control]) -> RiskFigure:
    """Jointly re-simulate a candidate control portfolio's effect on risk.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        controls: The candidate portfolio of controls to evaluate together.

    Returns:
        The :class:`~core.engine.RiskFigure` computed by running
        ``core.engine.compute_risk_figure`` against the hypothetical
        snapshot from :func:`apply_controls_to_snapshot`, seeded from the
        original ``snapshot`` (see :func:`_derive_comparison_seed`) so a
        result from this function is directly, fairly comparable to any
        other ``evaluate_portfolio`` call against the same base snapshot
        — including a baseline via ``evaluate_portfolio(snapshot, [])``.

    Must never:
        Compute or return a result derived from summing any control's
        individually-simulated delta. Every candidate portfolio, including
        a portfolio of size one, must go through a full joint simulation.
    """
    hypothetical_snapshot = apply_controls_to_snapshot(snapshot, controls)
    comparison_seed = _derive_comparison_seed(snapshot)
    return compute_risk_figure(hypothetical_snapshot, seed=comparison_seed)


class _PortfolioEvaluator:
    """Memoized :func:`evaluate_portfolio` over sets of controls from one candidate list.

    A portfolio's figure depends only on which controls it contains (they
    are applied to one copy together), so a set already simulated is never
    simulated twice during a search. Every figure is still a full joint
    simulation of exactly that set.
    """

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot
        self._figures: dict[frozenset[str], RiskFigure] = {}

    def __call__(self, controls: Sequence[Control]) -> RiskFigure:
        key = frozenset(control.control_id for control in controls)
        if key not in self._figures:
            self._figures[key] = evaluate_portfolio(self._snapshot, list(controls))
        return self._figures[key]


def _is_reduction(before: float, after: float, baseline: float) -> bool:
    """Whether ``after`` is a measurable reduction on ``before``, beyond floating-point noise."""
    return before - after > _NUMERICAL_TOLERANCE * max(abs(baseline), 1.0)


def _pert_mean(estimate: dict[str, float]) -> float:
    """The mean of the Beta-PERT distribution ``core.engine.simulation`` samples for this estimate."""
    return (
        estimate["min"] + PERT_CONFIDENCE_FACTOR * estimate["most_likely"] + estimate["max"]
    ) / (PERT_CONFIDENCE_FACTOR + 2.0)


def _scenario_expected_loss(scenario: dict[str, Any]) -> float:
    """The expected annual loss the Monte Carlo would converge to for one parameterized scenario.

    Mean rate × mean loss per event (a compound Poisson mean), where the
    rate is mean threat events × exploit probability × each active
    control's miss probability at its mean shared health — the same
    parameters ``core.engine.simulation`` samples. Ignores the clip of
    resistance × health at 1, which the shipped assumptions never reach.
    Used only to order a search; never reported.
    """
    if "threat_event_frequency" in scenario and "exploit_probability" in scenario:
        miss = 1.0
        for category, resistance in scenario.get("active_control_resistances", {}).items():
            health = (
                _pert_mean(SHARED_CONTROL_HEALTH_PERT[category])
                if category in SHARED_CONTROL_HEALTH_PERT
                else 1.0
            )
            miss *= 1.0 - min(max(resistance * health, 0.0), 1.0)
        vulnerability = min(max(float(scenario["exploit_probability"]) * miss, 0.0), 1.0)
        rate = _pert_mean(scenario["threat_event_frequency"]) * vulnerability
    else:
        rate = _pert_mean(scenario["loss_event_frequency"])
    return rate * _pert_mean(scenario["loss_magnitude"])


class _ExpectedLossEstimator:
    """Memoized closed-form expected annual loss of a hypothetical portfolio.

    Expected annual loss is linear, so its exact expectation under the
    engine's own parameters costs microseconds per scenario, where a joint
    Monte Carlo run costs a full simulation. The search uses it for one
    thing only: deciding which candidate to try next. It is never reported,
    never used to accept a control (a joint simulation decides that), and
    never summed into a figure — see :func:`_Search.greedy`.

    A change that alters no scenario's parameters (e.g. MFA on an asset
    with no open finding) has an estimated effect of exactly zero, which is
    how the search recognizes it as having no modelled effect without
    simulating it.
    """

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = snapshot
        self._estimates: dict[frozenset[str], float] = {}

    def __call__(self, controls: Sequence[Control]) -> float:
        key = frozenset(control.control_id for control in controls)
        if key not in self._estimates:
            hypothetical = apply_controls_to_snapshot(self._snapshot, list(controls))
            self._estimates[key] = sum(
                _scenario_expected_loss(parameterize_scenario(scenario, hypothetical))
                for scenario in build_loss_event_scenarios(hypothetical)
            )
        return self._estimates[key]


class _Search:
    """One snapshot's search state: memoized joint simulations and expected-value estimates."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.evaluate = _PortfolioEvaluator(snapshot)
        self.estimate = _ExpectedLossEstimator(snapshot)
        self.baseline = self.evaluate([])
        self._estimate_tolerance = _NUMERICAL_TOLERANCE * max(abs(self.estimate([])), 1.0)

    def estimated_reduction(self, selected: Sequence[Control], control: Control) -> float:
        """Estimated reduction from adding ``control`` to ``selected``; ≤ 0 means no modelled effect."""
        reduction = self.estimate(selected) - self.estimate([*selected, control])
        return reduction if reduction > self._estimate_tolerance else 0.0

    def greedy(
        self,
        candidates: Sequence[Control],
        *,
        budget_inr: float,
        priority: Callable[[float, Control], float],
        start: Sequence[Control] = (),
        max_steps: int | None = None,
    ) -> list[Control]:
        """Grow a portfolio one control at a time, each time adding the best next control.

        "Best" is ``priority(marginal_reduction, control)`` — reduction per
        rupee for a budgeted search, plain reduction for an unpriced plan —
        with the marginal reduction always measured against the portfolio
        chosen so far. A control whose benefit is absorbed by what is
        already chosen therefore drops down the order, instead of being
        ranked by a stale standalone number.

        Candidates are tried in order of their *expected* marginal
        reduction (:class:`_ExpectedLossEstimator`), lazily (the CELF
        scheme: a stale priority is recomputed only when it reaches the top
        of the queue — valid because controls overlap sub-additively, so a
        recomputed priority never rises). The candidate on top is then
        accepted only if a joint Monte Carlo simulation of the portfolio
        with it confirms a real reduction; otherwise it is dropped. So the
        estimate only chooses what to simulate next — every accepted
        control, and every figure reported, comes from joint simulation.

        Args:
            candidates: Controls to choose from.
            budget_inr: Total declared cost the portfolio may reach.
            priority: Ranks a control by its marginal reduction.
            start: Controls already chosen before the search begins.
            max_steps: Stop after this many controls are added (None: no limit).

        Returns:
            The chosen controls, ``start`` first, in the order added.
        """
        selected: list[Control] = list(start)
        spent = sum(c.estimated_cost_inr for c in selected)
        current = self.evaluate(selected)
        chosen_ids = {c.control_id for c in selected}
        pool = [c for c in candidates if c.control_id not in chosen_ids]

        queue: list[tuple[float, int, int]] = []
        for index, control in enumerate(pool):
            if spent + control.estimated_cost_inr > budget_inr:
                continue
            expected = self.estimated_reduction(selected, control)
            if expected > 0:
                heapq.heappush(queue, (-priority(expected, control), index, len(selected)))

        added = 0
        while queue and (max_steps is None or added < max_steps):
            _, index, stamp = heapq.heappop(queue)
            control = pool[index]
            if spent + control.estimated_cost_inr > budget_inr:
                continue
            if stamp != len(selected):
                expected = self.estimated_reduction(selected, control)
                if expected > 0:
                    heapq.heappush(queue, (-priority(expected, control), index, len(selected)))
                continue
            figure = self.evaluate([*selected, control])
            if not _is_reduction(
                current.expected_annual_loss_inr,
                figure.expected_annual_loss_inr,
                self.baseline.expected_annual_loss_inr,
            ):
                continue
            selected.append(control)
            spent += control.estimated_cost_inr
            current = figure
            added += 1
        return selected


def _reduction_per_rupee(marginal: float, control: Control) -> float:
    """Priority for a budgeted search: reduction per rupee, a free control with any benefit first."""
    if control.estimated_cost_inr <= 0:
        return math.inf if marginal > 0 else 0.0
    return marginal / control.estimated_cost_inr


def _reduction(marginal: float, _control: Control) -> float:
    """Priority for an unpriced plan: the reduction itself."""
    return marginal


def _steps(
    selected: Sequence[Control], evaluate: _PortfolioEvaluator, baseline: RiskFigure
) -> list[PortfolioStep]:
    """Each prefix of ``selected``, jointly simulated, as a :class:`PortfolioStep`."""
    steps: list[PortfolioStep] = []
    previous = baseline.expected_annual_loss_inr
    cost = 0.0
    for i, control in enumerate(selected):
        figure = evaluate(selected[: i + 1])
        cost += control.estimated_cost_inr
        steps.append(
            PortfolioStep(
                control=control,
                cumulative_cost_inr=cost,
                expected_annual_loss_inr=figure.expected_annual_loss_inr,
                value_at_risk_inr=figure.value_at_risk_inr,
                marginal_reduction_inr=previous - figure.expected_annual_loss_inr,
            )
        )
        previous = figure.expected_annual_loss_inr
    return steps


def recommend_portfolio(
    snapshot: dict[str, Any],
    candidate_controls: list[Control],
    budget_inr: float,
) -> PortfolioRecommendation:
    """Select the subset of candidate controls that maximizes risk reduction
    within budget.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        candidate_controls: All controls under consideration, each with a
            declared cost.
        budget_inr: The total budget available, in INR.

    Returns:
        A :class:`PortfolioRecommendation` describing the selected subset,
        its cost, its jointly-simulated risk reduction versus baseline, the
        step-by-step build-up, and why each other candidate was left out.

    Raises:
        ValueError: If any candidate cannot change anything (see
            :func:`apply_controls_to_snapshot`).

    Must never:
        Rank or select controls using a precomputed per-control benefit
        estimate as a proxy for search efficiency and then report that
        estimate as the final answer — any search heuristic used to narrow
        the candidate space is allowed internally, but the reported
        ``risk_reduction_inr`` on the final recommended portfolio must come
        from an actual joint re-simulation via :func:`evaluate_portfolio`,
        not from the heuristic. See repo-root ``CLAUDE.md`` principle 7.

    The search (budgeted maximization of a diminishing-returns benefit):

    1. Lazy greedy by reduction per rupee (:meth:`_Search.greedy`): at
       every step, add the control whose *marginal* reduction against what
       is already chosen, per rupee, is highest, while it fits the
       remaining budget — accepted only once a joint simulation confirms
       it still reduces loss.
    2. The same search seeded with the single affordable control that
       reduces loss most on its own. Greedy-by-ratio alone can fill the
       budget with cheap, small wins and miss one expensive control worth
       more than all of them; running both (when the greedy result does
       not already contain that control) and keeping the better is the
       standard guard for this knapsack failure.
    3. Keep whichever portfolio's own joint simulation has the lower
       Expected Annual Loss (the cheaper one on a tie), and report that
       joint result — never a sum of per-step estimates.

    It finds a strong, defensible portfolio, not a proven optimum (that
    would need a combinatorial number of simulations).
    """
    search = _Search(snapshot)
    evaluate = search.evaluate
    baseline_figure = search.baseline

    if not candidate_controls:
        return PortfolioRecommendation(
            selected_controls=[],
            total_cost_inr=0.0,
            baseline_risk_figure=baseline_figure,
            post_investment_risk_figure=baseline_figure,
            risk_reduction_inr=0.0,
            value_at_risk_reduction_inr=0.0,
            steps=[],
            rejected=[],
        )

    by_ratio = search.greedy(
        candidate_controls, budget_inr=budget_inr, priority=_reduction_per_rupee
    )
    options = [by_ratio]

    affordable = [
        c
        for c in candidate_controls
        if c.estimated_cost_inr <= budget_inr and search.estimated_reduction([], c) > 0
    ]
    if affordable:
        strongest = max(affordable, key=lambda c: search.estimated_reduction([], c))
        already = strongest.control_id in {c.control_id for c in by_ratio}
        if not already and _is_reduction(
            baseline_figure.expected_annual_loss_inr,
            evaluate([strongest]).expected_annual_loss_inr,
            baseline_figure.expected_annual_loss_inr,
        ):
            options.append(
                search.greedy(
                    candidate_controls,
                    budget_inr=budget_inr,
                    priority=_reduction_per_rupee,
                    start=[strongest],
                )
            )

    def rank(option: list[Control]) -> tuple[float, float]:
        return (
            evaluate(option).expected_annual_loss_inr,
            sum(c.estimated_cost_inr for c in option),
        )

    selected = min(options, key=rank)
    final_figure = evaluate(selected)
    total_cost = sum(c.estimated_cost_inr for c in selected)
    selected_ids = {c.control_id for c in selected}
    rejected = [
        RejectedControl(
            control=c,
            reason="over_budget"
            if total_cost + c.estimated_cost_inr > budget_inr
            else "no_reduction",
        )
        for c in candidate_controls
        if c.control_id not in selected_ids
    ]

    return PortfolioRecommendation(
        selected_controls=selected,
        total_cost_inr=total_cost,
        baseline_risk_figure=baseline_figure,
        post_investment_risk_figure=final_figure,
        risk_reduction_inr=baseline_figure.expected_annual_loss_inr
        - final_figure.expected_annual_loss_inr,
        value_at_risk_reduction_inr=baseline_figure.value_at_risk_inr
        - final_figure.value_at_risk_inr,
        steps=_steps(selected, evaluate, baseline_figure),
        rejected=rejected,
    )


@dataclass(frozen=True)
class ControlGap:
    """Something that could be changed to reduce modelled loss, not yet priced.

    Every gap is something :func:`apply_controls_to_snapshot` can close, so
    each one is a candidate a caller can price and hand to
    :func:`recommend_portfolio`. A gap carries no cost: nothing in the
    snapshot or in ``core.assumptions`` says what closing it would cost,
    and this module will not invent one.

    Attributes:
        control_id: Stable per gap: ``"{category}::{asset_id}"`` for MFA
            and EDR, ``"remediate_finding::{asset_id}::{finding_id}"``,
            ``"harden_backup::{service_id}"``.
        control_category: A key of :data:`APPLICABLE_CONTROL_CATEGORIES`.
        affected_asset_ids: The asset(s) the gap is on.
        finding_id: The open finding, for ``remediate_finding``.
        service_id: The service, for ``harden_backup``.
    """

    control_id: str
    control_category: str
    affected_asset_ids: list[str]
    finding_id: str | None = None
    service_id: str | None = None

    def priced(self, estimated_cost_inr: float) -> Control:
        """This gap as a :class:`Control` with a declared cost."""
        return Control(
            control_id=self.control_id,
            control_category=self.control_category,
            estimated_cost_inr=estimated_cost_inr,
            affected_asset_ids=list(self.affected_asset_ids),
            finding_id=self.finding_id,
            service_id=self.service_id,
        )


def find_control_gaps(snapshot: dict[str, Any]) -> list[ControlGap]:
    """List every change the optimizer can model that the snapshot does not already reflect.

    - MFA / EDR not credited on an asset. A category counts as a gap
      exactly when the engine's own parameterization would not apply its
      resistance — so an MFA flag that is ``null`` (unknown) is a gap, just
      as ``false`` is: the engine gives no credit for a control it cannot see.
    - Every open finding (``remediated_at`` null), as one fix each.
    - Every service some asset relies on whose backup is not yet tested
      with an immutable copy.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.

    Returns:
        :class:`ControlGap` entries in snapshot order: per asset, its
        MFA/EDR gaps then its open findings; then services.

    Must never:
        Attach a cost or a benefit to a gap. Benefit only ever comes from
        a joint re-simulation (principle 7); cost is a declared input.
    """
    categories = [c for c in RESISTANCE_CONTROL_CATEGORIES if c in CONTROL_RESISTANCE_STRENGTH]
    gaps: list[ControlGap] = []
    used_service_ids: dict[str, list[str]] = {}
    for asset in snapshot["assets"]:
        asset_id = asset["asset_id"]
        active = _active_control_resistances(asset)
        for category in categories:
            if category not in active:
                gaps.append(
                    ControlGap(
                        control_id=f"{category}::{asset_id}",
                        control_category=category,
                        affected_asset_ids=[asset_id],
                    )
                )
        for finding in asset.get("findings", []):
            if finding.get("remediated_at") is None:
                gaps.append(
                    ControlGap(
                        control_id=f"remediate_finding::{asset_id}::{finding['finding_id']}",
                        control_category="remediate_finding",
                        affected_asset_ids=[asset_id],
                        finding_id=finding["finding_id"],
                    )
                )
        for service_id in asset.get("service_ids", []):
            used_service_ids.setdefault(service_id, []).append(asset_id)

    for service in snapshot.get("services", []):
        users = used_service_ids.get(service["service_id"])
        if users and _single_service_backup_posture(service) != _HARDENED_BACKUP_POSTURE:
            gaps.append(
                ControlGap(
                    control_id=f"harden_backup::{service['service_id']}",
                    control_category="harden_backup",
                    affected_asset_ids=users,
                    service_id=service["service_id"],
                )
            )
    return gaps


@dataclass(frozen=True)
class PlanStep:
    """One change in an unpriced priority plan.

    Attributes:
        gap: The change.
        expected_annual_loss_inr: Joint Expected Annual Loss with this and
            every earlier step applied.
        value_at_risk_inr: Joint Value at Risk for the same set.
        marginal_reduction_inr: Expected Annual Loss before this step minus
            after it — a difference of two joint simulations.
    """

    gap: ControlGap
    expected_annual_loss_inr: float
    value_at_risk_inr: float
    marginal_reduction_inr: float


@dataclass(frozen=True)
class PriorityPlan:
    """Which changes reduce modelled loss most, in order, before any cost is known.

    Attributes:
        baseline_risk_figure: ``evaluate_portfolio(snapshot, [])``.
        steps: Changes in the order that reduces Expected Annual Loss
            fastest; each step's figures are a joint simulation of it and
            every step before it.
        no_effect: Gaps that change no modelled scenario once the plan's
            steps are applied (or at all — e.g. MFA on an asset with no
            open finding, which no modelled scenario runs through), plus
            any whose effect a joint simulation could not confirm.
        truncated: True when ``max_steps`` stopped the plan while further
            changes would still alter a modelled scenario.
    """

    baseline_risk_figure: RiskFigure
    steps: list[PlanStep]
    no_effect: list[ControlGap]
    truncated: bool


def prioritize_controls(
    snapshot: dict[str, Any],
    gaps: list[ControlGap],
    *,
    max_steps: int | None = None,
) -> PriorityPlan:
    """Order gaps by how much each reduces modelled loss, given the ones before it.

    Works with no costs at all, so it always has something to say when the
    snapshot has any open finding: at each step it adds the gap with the
    largest marginal reduction against the steps already taken, confirmed
    by joint simulation (see :meth:`_Search.greedy`). Useful as "what matters most" before
    anyone has priced anything, and as a guide to what to price first.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        gaps: Candidate changes, e.g. from :func:`find_control_gaps`.
        max_steps: Stop after this many steps (None: until nothing helps).

    Returns:
        A :class:`PriorityPlan`.

    Must never:
        Rank by standalone per-gap estimates or report a total built by
        summing them: each step's reduction is measured against the steps
        before it, and the steps' reductions add up exactly to the joint
        reduction of the whole plan.
    """
    search = _Search(snapshot)
    evaluate = search.evaluate
    baseline_figure = search.baseline
    # A zero declared cost here is an internal device of the search (the
    # plan ignores cost entirely); these controls never leave this function.
    unpriced = [gap.priced(0.0) for gap in gaps]
    selected = search.greedy(
        unpriced, budget_inr=math.inf, priority=_reduction, max_steps=max_steps
    )
    gap_by_id = {gap.control_id: gap for gap in gaps}
    steps = [
        PlanStep(
            gap=gap_by_id[step.control.control_id],
            expected_annual_loss_inr=step.expected_annual_loss_inr,
            value_at_risk_inr=step.value_at_risk_inr,
            marginal_reduction_inr=step.marginal_reduction_inr,
        )
        for step in _steps(selected, evaluate, baseline_figure)
    ]
    selected_ids = {c.control_id for c in selected}
    # Whether a remaining change still does anything is structural: it
    # either alters some scenario's parameters or it does not.
    no_effect: list[ControlGap] = []
    helps_further = False
    for control in unpriced:
        if control.control_id in selected_ids:
            continue
        if search.estimated_reduction(selected, control) > 0:
            helps_further = True
        else:
            no_effect.append(gap_by_id[control.control_id])
    return PriorityPlan(
        baseline_risk_figure=baseline_figure,
        steps=steps,
        no_effect=no_effect,
        truncated=helps_further,
    )


@dataclass(frozen=True)
class HypotheticalComparison:
    """A what-if: the snapshot as it stands versus with some controls applied.

    Attributes:
        controls: The hypothetical controls, applied together.
        baseline_risk_figure: ``evaluate_portfolio(snapshot, [])``.
        hypothetical_risk_figure: ``evaluate_portfolio(snapshot, controls)``
            — one joint re-simulation on the same random draws as the
            baseline, so the difference comes from the controls, not noise.
        expected_annual_loss_change_inr: hypothetical minus baseline
            Expected Annual Loss; negative means the controls reduce it.
        value_at_risk_change_inr: hypothetical minus baseline Value at
            Risk, at the percentile both figures carry.
    """

    controls: list[Control]
    baseline_risk_figure: RiskFigure
    hypothetical_risk_figure: RiskFigure
    expected_annual_loss_change_inr: float
    value_at_risk_change_inr: float


def compare_hypothetical(
    snapshot: dict[str, Any], controls: list[Control]
) -> HypotheticalComparison:
    """Jointly re-simulate a "what if we did X" against the same baseline draws.

    The baseline here is ``evaluate_portfolio(snapshot, [])``, which uses
    the common-random-numbers seed (see :func:`_derive_comparison_seed`),
    not ``compute_risk_figure(snapshot)``'s own content seed. The two
    baselines describe the same snapshot with different random draws, so
    they can differ slightly; a caller comparing against a what-if must use
    this baseline, never the headline figure.

    Args:
        snapshot: The current committed, schema-shaped aggregated snapshot.
        controls: One or more controls to apply together.

    Returns:
        A :class:`HypotheticalComparison`.

    Raises:
        ValueError: If ``controls`` is empty, a control affects no asset,
            names an asset not in the snapshot, or has a category
            :func:`apply_controls_to_snapshot` cannot apply — a what-if
            that silently changes nothing would report a zero effect for a
            question it never actually asked.

    Must never:
        Derive the effect by summing individually-simulated deltas; the
        hypothetical figure is one joint simulation of every control.
    """
    if not controls:
        raise ValueError("a what-if needs at least one hypothetical control")
    known_asset_ids = {asset["asset_id"] for asset in snapshot["assets"]}
    for control in controls:
        if not control.affected_asset_ids:
            raise ValueError(f"control {control.control_id!r} affects no asset")
        unknown = sorted(set(control.affected_asset_ids) - known_asset_ids)
        if unknown:
            raise ValueError(
                f"control {control.control_id!r} names asset(s) not in the current "
                f"snapshot: {', '.join(unknown)}"
            )

    hypothetical_figure = evaluate_portfolio(snapshot, controls)
    baseline_figure = evaluate_portfolio(snapshot, [])
    return HypotheticalComparison(
        controls=list(controls),
        baseline_risk_figure=baseline_figure,
        hypothetical_risk_figure=hypothetical_figure,
        expected_annual_loss_change_inr=hypothetical_figure.expected_annual_loss_inr
        - baseline_figure.expected_annual_loss_inr,
        value_at_risk_change_inr=hypothetical_figure.value_at_risk_inr
        - baseline_figure.value_at_risk_inr,
    )
