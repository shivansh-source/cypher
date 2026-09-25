"""Deriving an attack graph's nodes and edges from a snapshot's network topology.

This module owns *structure* only: which assets exist as nodes, and which
directed edges connect them. It deliberately does not attach probabilities
— that is the Bayesian inference layer (see the module docstring in
``core/engine/__init__.py`` for where this fits in the overall pipeline).
Splitting these apart means the graph's shape can be tested and trusted
independently of any modelling judgement about how likely a given edge is
to be used.

Edges come only from ``network_topology`` and ``assets[].network.segment_id``
(see ``schema/aggregated_assets.schema.json`` and ``schema/README.md``) —
never guessed from any other field. Both are optional: a snapshot with no
``network_topology`` produces a graph with nodes but no edges at all, which
is the honest answer ("we don't know how these assets relate"), not zero
risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AttackGraphNode:
    """One asset as a node in the attack graph.

    Attributes:
        asset_id: The asset this node represents.
        segment_id: The network segment this asset was reported in, or
            None if unknown. A None here is not "isolated" — see the
            module docstring — it means the edges this node could have
            are simply not derivable yet, not that there are none.
        internet_facing: Whether this asset is internet-facing, per
            ``assets[].network.internet_facing``. Used elsewhere (see
            :func:`entry_point_asset_ids`) to seed which nodes an
            external attacker can reach without needing a first hop.
    """

    asset_id: str
    segment_id: str | None
    internet_facing: bool


@dataclass(frozen=True)
class AttackGraphEdge:
    """One directed edge: an attacker already at ``source_asset_id`` can reach ``target_asset_id``.

    Attributes:
        source_asset_id: The asset an attacker is presumed to already
            control or be pivoting from.
        target_asset_id: The asset this edge says is reachable from there.
        reason: Human-readable provenance for this edge — which rule
            produced it and from what topology data — so a reviewer can
            trace any edge back to the snapshot fact that justified it,
            the same discipline ``findings[].provenance`` applies to
            scanner data (see repo-root ``CLAUDE.md`` principle 3's spirit
            extended to derived structure).
    """

    source_asset_id: str
    target_asset_id: str
    reason: str


@dataclass(frozen=True)
class AttackGraph:
    """The full attack graph derived from one snapshot.

    Attributes:
        nodes: Every asset in the snapshot, keyed by ``asset_id`` — every
            asset is a node even if it has no edges at all (an asset with
            unknown segment membership, for instance).
        edges: Every derived directed edge. May contain more than one edge
            between the same pair of nodes only if they have different
            ``reason`` values; in practice each pair gets at most one edge
            per direction today.
    """

    nodes: dict[str, AttackGraphNode]
    edges: list[AttackGraphEdge]


def _same_segment_edges(
    nodes: list[AttackGraphNode],
) -> list[AttackGraphEdge]:
    """Every asset in the same non-null segment is mutually reachable.

    Must never:
        Produce an edge for a None segment_id — unknown segment membership
        must never be silently treated as "same segment as every other
        unknown-segment asset," which would fabricate reachability the
        snapshot never asserted.
    """
    edges: list[AttackGraphEdge] = []
    by_segment: dict[str, list[str]] = {}
    for node in nodes:
        if node.segment_id is None:
            continue
        by_segment.setdefault(node.segment_id, []).append(node.asset_id)

    for segment_id, asset_ids in by_segment.items():
        for source_asset_id in asset_ids:
            for target_asset_id in asset_ids:
                if source_asset_id == target_asset_id:
                    continue
                edges.append(
                    AttackGraphEdge(
                        source_asset_id=source_asset_id,
                        target_asset_id=target_asset_id,
                        reason=f"same_segment:{segment_id}",
                    )
                )
    return edges


def _cross_segment_edges(
    nodes: list[AttackGraphNode],
    segment_reachability: list[dict[str, Any]],
) -> list[AttackGraphEdge]:
    """Every asset in from_segment_id reaches every asset in to_segment_id, directionally.

    Must never:
        Treat a listed (from, to) pair as symmetric — real network ACLs
        and firewall rules are routinely one-directional, and assuming
        symmetry would fabricate a return path the snapshot never
        asserted.
    """
    by_segment: dict[str, list[str]] = {}
    for node in nodes:
        if node.segment_id is not None:
            by_segment.setdefault(node.segment_id, []).append(node.asset_id)

    edges: list[AttackGraphEdge] = []
    for pair in segment_reachability:
        from_segment_id = pair["from_segment_id"]
        to_segment_id = pair["to_segment_id"]
        for source_asset_id in by_segment.get(from_segment_id, []):
            for target_asset_id in by_segment.get(to_segment_id, []):
                if source_asset_id == target_asset_id:
                    continue
                edges.append(
                    AttackGraphEdge(
                        source_asset_id=source_asset_id,
                        target_asset_id=target_asset_id,
                        reason=f"segment_reachability:{from_segment_id}->{to_segment_id}",
                    )
                )
    return edges


def build_attack_graph(snapshot: dict[str, Any]) -> AttackGraph:
    """Derive the attack graph's nodes and edges from a schema-shaped snapshot.

    Args:
        snapshot: A committed, schema-shaped aggregated snapshot.

    Returns:
        An :class:`AttackGraph` with one node per asset (regardless of
        whether it has any edges) and every edge derivable from
        ``network_topology`` and ``assets[].network.segment_id``: same-segment
        pairs (mutually reachable) plus whatever ``segment_reachability``
        explicitly lists (directional, cross-segment).

    Must never:
        Read anything beyond ``network_topology`` and
        ``assets[].network.segment_id`` to derive an edge, or treat a null
        ``segment_id`` / a missing ``network_topology`` as "isolated" —
        both mean "unknown," which is a different, more dangerous claim
        than "no path exists."
    """
    nodes = {
        asset["asset_id"]: AttackGraphNode(
            asset_id=asset["asset_id"],
            segment_id=(asset.get("network") or {}).get("segment_id"),
            internet_facing=bool((asset.get("network") or {}).get("internet_facing")),
        )
        for asset in snapshot["assets"]
    }
    node_list = list(nodes.values())

    topology = snapshot.get("network_topology")
    segment_reachability = topology["segment_reachability"] if topology else []

    edges = _same_segment_edges(node_list) + _cross_segment_edges(node_list, segment_reachability)

    return AttackGraph(nodes=nodes, edges=edges)


def entry_point_asset_ids(graph: AttackGraph) -> list[str]:
    """Asset IDs an external attacker can reach with no prior foothold.

    Returns:
        Every internet-facing node's ``asset_id``, in the graph's own node
        order. This is the seed set for any traversal starting "from the
        internet" — an attacker doesn't need an edge to reach these, only
        to the assets beyond them.
    """
    return [node.asset_id for node in graph.nodes.values() if node.internet_facing]


@dataclass(frozen=True)
class AttackRoute:
    """One way into an asset: campaigns that start at a given internet-facing entry point.

    Attributes:
        entry_asset_id: The internet-facing asset these campaigns start at.
        entry_exposure_profile: That entry point's exposure profile — the
            key into ``core.assumptions.BASELINE_THREAT_EVENT_FREQUENCY_PER_YEAR``
            that sets how often campaigns hit it at all.
        reach_probability: Probability a campaign starting at this entry
            point gains a foothold from which to attempt the target asset.
        reach_given_finding: For each open finding on the target,
            probability the campaign reaches the target *given that
            finding's own exploit works*. Usually equal to
            ``reach_probability``; higher when the finding shares a CVE with
            an asset on the way in, because an attacker whose exploit worked
            upstream is likely to find it works here too (the "hidden
            correlation" of Homer et al., 2013).
        share: This route's fraction of all campaigns that reach the target
            — its entry point's attack rate times ``reach_probability``, over
            the sum across routes. The "80% of the risk comes through the web
            server" figure.
    """

    entry_asset_id: str
    entry_exposure_profile: str
    reach_probability: float
    reach_given_finding: dict[str, float]
    share: float


@dataclass(frozen=True)
class GraphReachability:
    """What the attack graph says about one asset, for the engine to consume.

    Defined here (not in ``attack_graph_inference.py``) so that
    ``core/engine/parameterization.py`` can type against it without
    importing the inference module, which itself imports parameterization.

    Attributes:
        is_entry_point: The asset is internet-facing, so campaigns hit it
            directly at its own rate; the engine scores it exactly as it
            would without the graph, and ``routes`` is empty.
        routes: For an asset that is not internet-facing, every entry point
            with a path to it, largest share first. Empty means no known
            path: the asset is unreachable given the known topology.
    """

    is_entry_point: bool
    routes: list[AttackRoute]
