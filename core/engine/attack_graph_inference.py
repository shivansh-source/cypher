"""Bayesian inference over a bounded attack subgraph, by simulating attack spread.

Kept separate from ``core/engine/attack_graph.py``'s pure structure
(nodes/edges) so the graph's shape stays testable independently of the
modelling judgement in this file. This module attaches the probabilities
``attack_graph.py`` deliberately withholds.

**Bounded subgraphs, never whole-network inference** (SIH105 Conflict
Register item C5): exact inference on a Bayesian attack graph is
#P-complete, so every computation is scoped by
:func:`extract_bounded_subgraph` to one target asset and the nodes on some
path from an entry point to it.

**Estimated by simulation, not a closed-form formula.** Each sample plays
out one attack: every exploit group's success is drawn, and the attacker
spreads forward from the starting entry point(s) through every asset
whose exploit worked. Probabilities are the fraction of samples in which
something happened. Following Matthews et al., "Stochastic Simulation
Techniques for Inference and Sensitivity Analysis of Bayesian Attack
Graphs" (arXiv 2103.10212), this is chosen over a propagation formula for
two reasons, both raised by Homer et al., "Aggregating Vulnerability
Metrics in Enterprise Networks using Attack Graphs" (J. Computer
Security, 2013):

1. **Hidden correlations.** Findings with the same CVE on different
   assets share one uniform draw per sample: each still succeeds with its
   own probability (its own EPSS/KEV and that asset's controls), but an
   exploit that works on one host is far more likely to work on the next.
   A formula that multiplies per-hop probabilities cannot represent that;
   a shared draw does, exactly.
2. **No self-referencing cycles.** Iterating a formula around a cycle lets
   an asset's own compromise probability feed back into its own
   reachability. A simulated attacker only ever moves forward from where
   they actually are, so a cycle can never inflate anything.

No real per-hop measurement exists yet (that is the SIH105 lab's job, not
built in this codebase). Each finding's own success probability is the
same EPSS/KEV-informed, control-discounted vulnerability the engine
already computes (:func:`core.engine.parameterization._vulnerability_probability`)
— imported rather than restated, so it can never drift from what the rest
of the engine credits as exploitable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.assumptions import ATTACK_GRAPH_SAMPLES, BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR
from core.engine.attack_graph import (
    AttackGraph,
    AttackRoute,
    GraphReachability,
    build_attack_graph,
    entry_point_asset_ids,
)
from core.engine.parameterization import _exposure_profile, _vulnerability_probability


def _open_findings(asset: dict[str, Any]) -> list[dict[str, Any]]:
    return [finding for finding in asset["findings"] if finding.get("remediated_at") is None]


def _exploit_group(asset_id: str, finding: dict[str, Any]) -> str:
    """Findings sharing a CVE share one draw; any other finding is its own group.

    Grouping by CVE only, never by ``provenance.raw_source_id`` or any other
    tool-native identifier, which ``core/`` must not read (see
    ``schema/aggregated_assets.schema.json``).
    """
    cve_id = finding.get("cve_id")
    return f"cve:{cve_id}" if cve_id else f"finding:{asset_id}:{finding['finding_id']}"


def _stable_int(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], byteorder="big")


def _snapshot_seed(snapshot: dict[str, Any]) -> int:
    """Same snapshot content, same seed — so graph figures are reproducible."""
    return _stable_int(json.dumps(snapshot, sort_keys=True, default=str)) % (2**32)


def _reachable_from(graph: AttackGraph, start_asset_ids: set[str]) -> set[str]:
    """Every node reachable by following edges forward from any of start_asset_ids (inclusive)."""
    successors: dict[str, list[str]] = {}
    for edge in graph.edges:
        successors.setdefault(edge.source_asset_id, []).append(edge.target_asset_id)

    visited = set(start_asset_ids)
    frontier = list(start_asset_ids)
    while frontier:
        current = frontier.pop()
        for next_asset_id in successors.get(current, []):
            if next_asset_id not in visited:
                visited.add(next_asset_id)
                frontier.append(next_asset_id)
    return visited


def _can_reach(graph: AttackGraph, target_asset_id: str) -> set[str]:
    """Every node that has some forward path to target_asset_id (inclusive)."""
    predecessors: dict[str, list[str]] = {}
    for edge in graph.edges:
        predecessors.setdefault(edge.target_asset_id, []).append(edge.source_asset_id)

    visited = {target_asset_id}
    frontier = [target_asset_id]
    while frontier:
        current = frontier.pop()
        for previous_asset_id in predecessors.get(current, []):
            if previous_asset_id not in visited:
                visited.add(previous_asset_id)
                frontier.append(previous_asset_id)
    return visited


@dataclass(frozen=True)
class BoundedAttackSubgraph:
    """One target asset's causally-relevant neighbourhood, per C5's scoping rule.

    Attributes:
        crown_jewel_asset_id: The asset this subgraph was scoped around.
        included_asset_ids: Every asset on some path from an entry point to
            the target, plus the target itself even if unreachable.
        graph: The full graph this subgraph was extracted from; edges are
            filtered by membership at inference time.
    """

    crown_jewel_asset_id: str
    included_asset_ids: frozenset[str]
    graph: AttackGraph


def extract_bounded_subgraph(
    graph: AttackGraph, crown_jewel_asset_id: str
) -> BoundedAttackSubgraph:
    """Scope inference to one target asset's causally-relevant neighbourhood.

    Args:
        graph: The full attack graph (see :func:`core.engine.attack_graph.build_attack_graph`).
        crown_jewel_asset_id: The asset to scope the subgraph around.

    Returns:
        A :class:`BoundedAttackSubgraph` containing every node that lies on
        some path from an entry point to the target — a set that stays
        small regardless of overall network size (SIH105 C5).

    Raises:
        KeyError: If ``crown_jewel_asset_id`` is not a node in ``graph``.

    Must never:
        Include a node that cannot reach the target, or that no entry point
        reaches — either would widen the subgraph back toward whole-network
        size on a large, densely-connected estate.
    """
    if crown_jewel_asset_id not in graph.nodes:
        raise KeyError(f"{crown_jewel_asset_id!r} is not a node in this attack graph")

    entry_points = set(entry_point_asset_ids(graph))
    reachable_from_entry = _reachable_from(graph, entry_points)
    can_reach_crown_jewel = _can_reach(graph, crown_jewel_asset_id)
    included = (reachable_from_entry & can_reach_crown_jewel) | {crown_jewel_asset_id}

    return BoundedAttackSubgraph(
        crown_jewel_asset_id=crown_jewel_asset_id,
        included_asset_ids=frozenset(included),
        graph=graph,
    )


def _bfs_distance(graph: AttackGraph, start_asset_ids: set[str], *, reverse: bool) -> dict[str, int]:
    """Fewest-hop distance from the nearest of ``start_asset_ids``, following edges forward
    (or backward, if ``reverse``, i.e. distance *to* ``start_asset_ids``)."""
    adjacency: dict[str, list[str]] = {}
    for edge in graph.edges:
        source, target = (
            (edge.target_asset_id, edge.source_asset_id)
            if reverse
            else (edge.source_asset_id, edge.target_asset_id)
        )
        adjacency.setdefault(source, []).append(target)

    distance = {asset_id: 0 for asset_id in start_asset_ids}
    frontier = list(start_asset_ids)
    while frontier:
        next_frontier: list[str] = []
        for current in frontier:
            for neighbour in adjacency.get(current, []):
                if neighbour not in distance:
                    distance[neighbour] = distance[current] + 1
                    next_frontier.append(neighbour)
        frontier = next_frontier
    return distance


def shortest_path_edges(subgraph: BoundedAttackSubgraph) -> frozenset[str]:
    """Directed edge keys (``"source_asset_id>target_asset_id"``) on some *shortest*
    entry-to-target path — for display only.

    ``included_asset_ids`` is every asset on *some* path to the target, which is right for
    scoping the simulation, but wrong for deciding which lines to highlight: a real network
    segment is usually a full mesh (every asset can reach every other in one hop), so almost
    any edge between two included assets technically lies on *some* walk to the target.
    Highlighting all of them floods a busy segment with colour instead of showing the route
    that actually explains how the target is reached. This restricts to edges that lie on a
    shortest path, which excludes the "sideways" mesh edges that don't make progress toward
    the target.

    Returns:
        Empty when the target has no path from any entry point — nothing to highlight, which
        is distinct from (and must not be confused with) a target reached in exactly one hop.

    Must never:
        Be used to narrow ``included_asset_ids`` itself or anything
        :func:`compute_compromise_probabilities` reads — this is a cosmetic view over the
        same subgraph, not a different, smaller one; narrowing the simulation's own node set
        this way would silently change ``node_probabilities`` for display reasons.
    """
    graph = subgraph.graph
    entry_points = set(entry_point_asset_ids(graph)) & subgraph.included_asset_ids
    dist_from_entry = _bfs_distance(graph, entry_points, reverse=False)
    target_distance = dist_from_entry.get(subgraph.crown_jewel_asset_id)
    if target_distance is None:
        return frozenset()
    dist_to_target = _bfs_distance(graph, {subgraph.crown_jewel_asset_id}, reverse=True)

    hot: set[str] = set()
    for edge in graph.edges:
        source, target = edge.source_asset_id, edge.target_asset_id
        if source not in subgraph.included_asset_ids or target not in subgraph.included_asset_ids:
            continue
        du = dist_from_entry.get(source)
        dv = dist_to_target.get(target)
        if du is not None and dv is not None and du + 1 + dv == target_distance:
            hot.add(f"{source}>{target}")
    return frozenset(hot)


@dataclass(frozen=True)
class _Draws:
    """One set of sampled exploit outcomes for every open finding in a subgraph.

    Attributes:
        finding_success: ``(asset_id, finding_id) -> (samples,)`` bool array.
        asset_exploitable: ``asset_id -> (samples,)`` bool array: at least one
            of the asset's open findings succeeded in that sample.
        finding_vulnerability: ``(asset_id, finding_id) -> probability``,
            the marginal each finding's draw was made against.
    """

    finding_success: dict[tuple[str, str], np.ndarray]
    asset_exploitable: dict[str, np.ndarray]
    finding_vulnerability: dict[tuple[str, str], float]


def _draw_exploits(
    snapshot: dict[str, Any],
    included: frozenset[str],
    samples: int,
    rng: np.random.Generator,
) -> _Draws:
    """Sample every open finding's success, sharing one uniform per exploit group.

    A finding succeeds in a sample when its group's uniform falls below the
    finding's own vulnerability. Findings in the same group (same CVE) see
    the same uniform, so they succeed together far more often than
    independent draws would, while each still succeeds with exactly its own
    probability overall.
    """
    assets_by_id = {asset["asset_id"]: asset for asset in snapshot["assets"]}
    groups = sorted(
        {
            _exploit_group(asset_id, finding)
            for asset_id in included
            for finding in _open_findings(assets_by_id[asset_id])
        }
    )
    column = {group: index for index, group in enumerate(groups)}
    uniforms = rng.random((samples, len(groups)))

    finding_success: dict[tuple[str, str], np.ndarray] = {}
    finding_vulnerability: dict[tuple[str, str], float] = {}
    asset_exploitable: dict[str, np.ndarray] = {}
    for asset_id in sorted(included):
        asset = assets_by_id[asset_id]
        exploitable = np.zeros(samples, dtype=bool)
        for finding in _open_findings(asset):
            key = (asset_id, finding["finding_id"])
            vulnerability = _vulnerability_probability(finding, asset)
            success = uniforms[:, column[_exploit_group(asset_id, finding)]] < vulnerability
            finding_success[key] = success
            finding_vulnerability[key] = vulnerability
            exploitable |= success
        asset_exploitable[asset_id] = exploitable
    return _Draws(finding_success, asset_exploitable, finding_vulnerability)


def _spread(
    graph: AttackGraph,
    included: frozenset[str],
    sources: set[str],
    draws: _Draws,
    samples: int,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Play out every sampled attack from ``sources`` and record where it got.

    Returns:
        ``(reached, compromised)``: per asset, a ``(samples,)`` bool array.
        An asset is reached when the attacker starts there or has
        compromised an asset with an edge into it; it is compromised when
        reached and at least one of its own open findings succeeded.

    Must never:
        Let an asset's reachability depend on its own compromise. Spread
        only moves forward from where the attacker already is, so this holds
        by construction — the self-referencing cycle problem Homer et al.
        describe cannot arise.
    """
    predecessors: dict[str, list[str]] = {asset_id: [] for asset_id in included}
    for edge in graph.edges:
        if edge.source_asset_id in included and edge.target_asset_id in included:
            predecessors[edge.target_asset_id].append(edge.source_asset_id)

    reached = {asset_id: np.zeros(samples, dtype=bool) for asset_id in included}
    for source in sources:
        reached[source][:] = True
    compromised = {
        asset_id: reached[asset_id] & draws.asset_exploitable[asset_id] for asset_id in included
    }

    # Each pass can only add reached assets, so this settles within one pass
    # per asset; the bound is structural, not a tuning constant.
    for _ in range(len(included)):
        changed = False
        for asset_id in included:
            incoming = np.zeros(samples, dtype=bool)
            for predecessor_id in predecessors[asset_id]:
                incoming |= compromised[predecessor_id]
            newly_reached = incoming & ~reached[asset_id]
            if newly_reached.any():
                reached[asset_id] |= newly_reached
                compromised[asset_id] = reached[asset_id] & draws.asset_exploitable[asset_id]
                changed = True
        if not changed:
            break
    return reached, compromised


def _target_rng(seed: int, target_asset_id: str) -> np.random.Generator:
    """One stream per target, keyed by its id, so the same target sees the same
    draws across snapshots that differ only in controls — the common random
    numbers ``core.optimizer`` relies on to compare portfolios fairly."""
    return np.random.default_rng([seed, _stable_int(target_asset_id) % (2**32)])


@dataclass(frozen=True)
class AttackGraphInferenceResult:
    """Every included node's probabilities when all entry points are attacked at once.

    Attributes:
        crown_jewel_asset_id: The asset this result was computed for.
        crown_jewel_compromise_probability: The target's own compromise
            probability — never reported alone (see ``node_probabilities``).
        node_probabilities: Every included node's compromise probability.
        reached_probabilities: Every included node's probability of being
            reached (1.0 for an entry point).
        samples: How many attacks were simulated.
    """

    crown_jewel_asset_id: str
    crown_jewel_compromise_probability: float
    node_probabilities: dict[str, float]
    reached_probabilities: dict[str, float]
    samples: int


def compute_compromise_probabilities(
    snapshot: dict[str, Any],
    subgraph: BoundedAttackSubgraph,
    *,
    samples: int | None = None,
    seed: int | None = None,
) -> AttackGraphInferenceResult:
    """Crown-jewel summary: every included node's odds with every entry point under attack.

    A worst-case view for display ("if the whole perimeter is being hit,
    how exposed is this asset and everything on the way to it"). The
    engine's figures instead use :func:`compute_graph_reachability`, which
    keeps each entry point's campaigns separate so they can carry their own
    attack rates.

    Args:
        snapshot: The committed, schema-shaped snapshot the subgraph's
            assets came from.
        subgraph: The bounded subgraph to run inference over.
        samples: Override for the sample count; defaults to
            ``core.assumptions.ATTACK_GRAPH_SAMPLES``.
        seed: Override for the seed; defaults to one derived from the
            snapshot's content.

    Returns:
        An :class:`AttackGraphInferenceResult`.
    """
    resolved_samples = samples if samples is not None else ATTACK_GRAPH_SAMPLES
    resolved_seed = seed if seed is not None else _snapshot_seed(snapshot)
    included = subgraph.included_asset_ids
    graph = subgraph.graph

    draws = _draw_exploits(
        snapshot,
        included,
        resolved_samples,
        _target_rng(resolved_seed, subgraph.crown_jewel_asset_id),
    )
    sources = {asset_id for asset_id in included if graph.nodes[asset_id].internet_facing}
    reached, compromised = _spread(graph, included, sources, draws, resolved_samples)

    node_probabilities = {asset_id: float(np.mean(compromised[asset_id])) for asset_id in included}
    return AttackGraphInferenceResult(
        crown_jewel_asset_id=subgraph.crown_jewel_asset_id,
        crown_jewel_compromise_probability=node_probabilities[subgraph.crown_jewel_asset_id],
        node_probabilities=node_probabilities,
        reached_probabilities={
            asset_id: float(np.mean(reached[asset_id])) for asset_id in included
        },
        samples=resolved_samples,
    )


def _asset_exposure_profile(asset: dict[str, Any], snapshot: dict[str, Any]) -> str:
    """The asset's own exposure profile, exactly as parameterize_scenario would derive it."""
    services_by_id = {service["service_id"]: service for service in snapshot["services"]}
    related_services = [
        services_by_id[service_id]
        for service_id in asset.get("service_ids", [])
        if service_id in services_by_id
    ]
    return _exposure_profile(asset, related_services)


def _routes_into(
    snapshot: dict[str, Any],
    graph: AttackGraph,
    target_asset_id: str,
    samples: int,
    seed: int,
) -> list[AttackRoute]:
    """Every entry point with a path to the target, as a separately-simulated route.

    Each route is simulated with campaigns starting at that one entry point
    only, over the same exploit draws, so routes differ only in where the
    attacker starts. Separate campaigns are separate streams of events, so
    their rates add; this is what lets each entry point keep its own attack
    rate instead of borrowing the busiest one.
    """
    assets_by_id = {asset["asset_id"]: asset for asset in snapshot["assets"]}
    subgraph = extract_bounded_subgraph(graph, target_asset_id)
    included = subgraph.included_asset_ids
    draws = _draw_exploits(snapshot, included, samples, _target_rng(seed, target_asset_id))
    target_findings = [
        ((target_asset_id, finding["finding_id"]), _exploit_group(target_asset_id, finding))
        for finding in _open_findings(assets_by_id[target_asset_id])
    ]
    # Groups some *other* asset on the way in also draws from. The target's
    # own draws can't decide whether the target is reached, so a finding in
    # no such group is independent of reach: its conditional is exactly the
    # unconditional reach, and estimating it from the few samples where the
    # finding happens to succeed would only add noise.
    upstream_groups = {
        _exploit_group(asset_id, finding)
        for asset_id in included
        if asset_id != target_asset_id
        for finding in _open_findings(assets_by_id[asset_id])
    }

    raw_routes: list[tuple[str, str, float, dict[str, float]]] = []
    for entry_id in sorted(a for a in included if graph.nodes[a].internet_facing):
        reached, _ = _spread(graph, included, {entry_id}, draws, samples)
        target_reached = reached[target_asset_id]
        reach_probability = float(np.mean(target_reached))
        if reach_probability == 0.0:
            continue
        reach_given_finding: dict[str, float] = {}
        for key, group in target_findings:
            if group not in upstream_groups:
                reach_given_finding[key[1]] = reach_probability
                continue
            vulnerability = draws.finding_vulnerability[key]
            joint = float(np.mean(target_reached & draws.finding_success[key]))
            # P(reached | this finding's exploit works) = P(both) / P(works).
            reach_given_finding[key[1]] = joint / vulnerability if vulnerability > 0.0 else 0.0
        raw_routes.append(
            (
                entry_id,
                _asset_exposure_profile(assets_by_id[entry_id], snapshot),
                reach_probability,
                reach_given_finding,
            )
        )

    weights = [
        BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR[profile]["most_likely"] * reach
        for _, profile, reach, _ in raw_routes
    ]
    total_weight = sum(weights)
    routes = [
        AttackRoute(
            entry_asset_id=entry_id,
            entry_exposure_profile=profile,
            reach_probability=reach,
            reach_given_finding=given,
            share=weight / total_weight if total_weight > 0.0 else 0.0,
        )
        for (entry_id, profile, reach, given), weight in zip(raw_routes, weights, strict=True)
    ]
    return sorted(routes, key=lambda route: route.share, reverse=True)


def compute_graph_reachability(
    snapshot: dict[str, Any], *, seed: int | None = None
) -> dict[str, GraphReachability]:
    """What the attack graph says about every asset whose topology is actually known.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot.
        seed: Override for the seed; defaults to one derived from the
            snapshot's content. ``core.engine.risk_figure`` passes its own
            seed through so a caller comparing snapshots (the optimizer)
            gets common random numbers here too.

    Returns:
        ``{asset_id: GraphReachability}`` for exactly the assets with a known
        ``network.segment_id``. An internet-facing asset is marked
        ``is_entry_point`` with no routes. Any other asset lists every entry
        point with a path to it (see :func:`_routes_into`); no routes means
        unreachable under the known topology. An asset with a null
        ``segment_id`` is **omitted**, never reported as unreachable: null
        means *unknown* topology (see ``schema/README.md``), and reporting
        "unreachable" for "unknown" would silently understate its risk.

    Must never:
        Include an asset whose segment is unknown. Run inference over the
        whole graph at once rather than one bounded subgraph per asset.
    """
    resolved_seed = seed if seed is not None else _snapshot_seed(snapshot)
    graph = build_attack_graph(snapshot)
    reachability: dict[str, GraphReachability] = {}
    for asset_id, node in graph.nodes.items():
        if node.segment_id is None:
            continue
        if node.internet_facing:
            reachability[asset_id] = GraphReachability(is_entry_point=True, routes=[])
            continue
        reachability[asset_id] = GraphReachability(
            is_entry_point=False,
            routes=_routes_into(snapshot, graph, asset_id, ATTACK_GRAPH_SAMPLES, resolved_seed),
        )
    return reachability
