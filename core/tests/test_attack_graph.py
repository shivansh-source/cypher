"""Tests for core/engine/attack_graph.py's graph structure derivation.

Structure only — no probabilities here (that's the Bayesian inference
layer, still to come). Every test checks edges trace back to real
network_topology/segment_id facts, never inferred from anything else.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from core.engine.attack_graph import build_attack_graph, entry_point_asset_ids

SAMPLE_SNAPSHOT: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "schema" / "sample_aggregated.json").read_text()
)


def test_build_attack_graph_has_one_node_per_asset() -> None:
    """Every asset is a node, regardless of whether it has any edges."""
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    assert set(graph.nodes.keys()) == {"asset-web-01", "asset-hr-db-01"}
    assert graph.nodes["asset-web-01"].segment_id == "dmz"
    assert graph.nodes["asset-web-01"].internet_facing is True
    assert graph.nodes["asset-hr-db-01"].segment_id == "internal-corp"
    assert graph.nodes["asset-hr-db-01"].internet_facing is False


def test_build_attack_graph_derives_cross_segment_edge_from_reachability() -> None:
    """The fixture's dmz -> internal-corp segment_reachability must produce a real edge."""
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source_asset_id == "asset-web-01"
    assert edge.target_asset_id == "asset-hr-db-01"
    assert edge.reason == "segment_reachability:dmz->internal-corp"


def test_cross_segment_edge_is_directional_not_symmetric() -> None:
    """segment_reachability listing dmz->internal-corp must not also produce internal-corp->dmz."""
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    assert not any(
        edge.source_asset_id == "asset-hr-db-01" and edge.target_asset_id == "asset-web-01"
        for edge in graph.edges
    )


def test_same_segment_assets_are_mutually_reachable() -> None:
    """Two assets in the same segment must get edges in both directions."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][1]["network"]["segment_id"] = "dmz"  # move hr-db into the same segment

    graph = build_attack_graph(snapshot)

    reasons = {(e.source_asset_id, e.target_asset_id): e.reason for e in graph.edges}
    assert reasons[("asset-web-01", "asset-hr-db-01")] == "same_segment:dmz"
    assert reasons[("asset-hr-db-01", "asset-web-01")] == "same_segment:dmz"


def test_null_segment_id_produces_no_same_segment_edges() -> None:
    """Two assets both with unknown (null) segment_id must never be treated as 'the same segment'."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][0]["network"]["segment_id"] = None
    snapshot["assets"][1]["network"]["segment_id"] = None
    snapshot["network_topology"]["segment_reachability"] = []

    graph = build_attack_graph(snapshot)

    assert graph.edges == []


def test_missing_network_topology_produces_nodes_with_no_edges() -> None:
    """A snapshot with no network_topology at all must still produce every node, just with zero edges."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    del snapshot["network_topology"]
    snapshot["assets"][0]["network"]["segment_id"] = None
    snapshot["assets"][1]["network"]["segment_id"] = None

    graph = build_attack_graph(snapshot)

    assert set(graph.nodes.keys()) == {"asset-web-01", "asset-hr-db-01"}
    assert graph.edges == []


def test_entry_point_asset_ids_returns_internet_facing_assets() -> None:
    """Only internet-facing assets are valid attack-graph entry points."""
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    assert entry_point_asset_ids(graph) == ["asset-web-01"]
