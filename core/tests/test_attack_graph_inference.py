"""Tests for core/engine/attack_graph_inference.py's bounded, simulated Bayesian inference.

Expected values are hand-calculated from the same per-finding vulnerability
math core/tests/test_engine.py already validates against a published FAIR
example. Inference is now estimated by simulation, so assertions use
tolerances of several standard errors at ATTACK_GRAPH_SAMPLES (50,000):
about 0.002 for a probability near 0.26, 0.0005 near 0.013.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from core.engine.attack_graph import (
    AttackGraph,
    AttackGraphEdge,
    AttackGraphNode,
    build_attack_graph,
)
from core.engine.attack_graph_inference import (
    compute_compromise_probabilities,
    compute_graph_reachability,
    extract_bounded_subgraph,
)
from core.engine.parameterization import parameterize_scenario
from core.engine.scenarios import build_loss_event_scenarios

SAMPLE_SNAPSHOT: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "schema" / "sample_aggregated.json").read_text()
)

# asset-web-01: EPSS 0.87 (above the KEV floor), MFA+EDR combined resistance
# 0.7 -> vulnerability 0.87 * 0.3 = 0.261 (as in test_engine.py).
WEB_VULNERABILITY = 0.261
# asset-hr-db-01: unscored finding, no controls -> vulnerability 0.05.
HR_DB_VULNERABILITY = 0.05
TOLERANCE_NEAR_QUARTER = 0.01
TOLERANCE_NEAR_ONE_PERCENT = 0.003


def _finding(finding_id: str, epss: float, cve_id: str | None, kev: bool = False) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "type": "cve",
        "cve_id": cve_id,
        "epss_score": epss,
        "kev_listed": kev,
        "criticality": "high",
        "provenance": {"connector": "test", "raw_source_id": finding_id},
        "first_seen_at": "2026-09-01T00:00:00Z",
        "remediated_at": None,
    }


def _asset(
    asset_id: str,
    segment_id: str,
    *,
    internet_facing: bool,
    findings: list[dict[str, Any]],
    service_ids: list[str],
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "service_ids": service_ids,
        "findings": findings,
        "threat_intel": {},
        "edr": {"agent_installed": False, "agent_healthy": None},
        "identity_access": {"mfa_enforced": False},
        "network": {"internet_facing": internet_facing, "segment_id": segment_id},
    }


def _scenario_for(snapshot: dict[str, Any], asset_id: str) -> dict[str, Any]:
    (scenario,) = [s for s in build_loss_event_scenarios(snapshot) if s["asset_id"] == asset_id]
    return scenario


def _with_second_entry_point() -> dict[str, Any]:
    """Fixture plus an internet-facing mail server (low-criticality service, so 2 attacks/yr)
    whose own vulnerability is 0.4, with a path into the same internal segment."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"].append(
        _asset(
            "asset-mail-01",
            "dmz2",
            internet_facing=True,
            findings=[_finding("finding-mail", 0.4, "CVE-2026-00002")],
            service_ids=["svc-internal-hr"],
        )
    )
    snapshot["network_topology"]["segments"].append({"segment_id": "dmz2", "name": "dmz2"})
    snapshot["network_topology"]["segment_reachability"].append(
        {"from_segment_id": "dmz2", "to_segment_id": "internal-corp"}
    )
    return snapshot


# --- Bounded subgraph --------------------------------------------------------


def test_extract_bounded_subgraph_includes_only_the_causal_path() -> None:
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    subgraph = extract_bounded_subgraph(graph, "asset-hr-db-01")

    assert subgraph.included_asset_ids == frozenset({"asset-web-01", "asset-hr-db-01"})


def test_extract_bounded_subgraph_excludes_nodes_the_crown_jewel_cannot_reach() -> None:
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    subgraph = extract_bounded_subgraph(graph, "asset-web-01")

    assert subgraph.included_asset_ids == frozenset({"asset-web-01"})


def test_extract_bounded_subgraph_raises_for_unknown_asset() -> None:
    graph = build_attack_graph(copy.deepcopy(SAMPLE_SNAPSHOT))

    with pytest.raises(KeyError):
        extract_bounded_subgraph(graph, "asset-does-not-exist")


# --- Crown-jewel summary (every entry point attacked at once) ----------------


def test_compute_compromise_probabilities_matches_hand_calculation() -> None:
    """Chain: web (entry, 0.261) -> hr-db (0.05). P(hr-db) = 0.261 * 0.05 = 0.01305."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    subgraph = extract_bounded_subgraph(build_attack_graph(snapshot), "asset-hr-db-01")

    result = compute_compromise_probabilities(snapshot, subgraph)

    assert result.reached_probabilities["asset-web-01"] == 1.0
    assert result.node_probabilities["asset-web-01"] == pytest.approx(
        WEB_VULNERABILITY, abs=TOLERANCE_NEAR_QUARTER
    )
    assert result.reached_probabilities["asset-hr-db-01"] == pytest.approx(
        WEB_VULNERABILITY, abs=TOLERANCE_NEAR_QUARTER
    )
    assert result.crown_jewel_compromise_probability == pytest.approx(
        WEB_VULNERABILITY * HR_DB_VULNERABILITY, abs=TOLERANCE_NEAR_ONE_PERCENT
    )


def test_crown_jewel_unreachable_from_any_entry_point_has_zero_probability() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["network_topology"]["segment_reachability"] = []
    subgraph = extract_bounded_subgraph(build_attack_graph(snapshot), "asset-hr-db-01")

    result = compute_compromise_probabilities(snapshot, subgraph)

    assert result.crown_jewel_compromise_probability == 0.0


def test_local_compromise_is_zero_with_no_open_findings() -> None:
    """An asset whose only finding is remediated can't be compromised — no fabricated weakness."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][1]["findings"][0]["remediated_at"] = "2026-09-20T00:00:00Z"
    subgraph = extract_bounded_subgraph(build_attack_graph(snapshot), "asset-hr-db-01")

    result = compute_compromise_probabilities(snapshot, subgraph)

    assert result.crown_jewel_compromise_probability == 0.0


def test_two_independent_routes_combine_as_noisy_or() -> None:
    """a, b entry points (0.5 each) -> c (0.2): reached(c) = 1 - 0.5*0.5 = 0.75, compromised = 0.15."""
    graph = AttackGraph(
        nodes={
            "a": AttackGraphNode(asset_id="a", segment_id="seg-a", internet_facing=True),
            "b": AttackGraphNode(asset_id="b", segment_id="seg-b", internet_facing=True),
            "c": AttackGraphNode(asset_id="c", segment_id="seg-c", internet_facing=False),
        },
        edges=[
            AttackGraphEdge(source_asset_id="a", target_asset_id="c", reason="test"),
            AttackGraphEdge(source_asset_id="b", target_asset_id="c", reason="test"),
        ],
    )
    snapshot = {
        "assets": [
            _asset(
                "a",
                "seg-a",
                internet_facing=True,
                findings=[_finding("fa", 0.5, "CVE-A")],
                service_ids=[],
            ),
            _asset(
                "b",
                "seg-b",
                internet_facing=True,
                findings=[_finding("fb", 0.5, "CVE-B")],
                service_ids=[],
            ),
            _asset(
                "c",
                "seg-c",
                internet_facing=False,
                findings=[_finding("fc", 0.2, "CVE-C")],
                service_ids=[],
            ),
        ]
    }

    result = compute_compromise_probabilities(snapshot, extract_bounded_subgraph(graph, "c"))

    assert result.reached_probabilities["c"] == pytest.approx(0.75, abs=TOLERANCE_NEAR_QUARTER)
    assert result.crown_jewel_compromise_probability == pytest.approx(
        0.15, abs=TOLERANCE_NEAR_QUARTER
    )


def test_inference_is_deterministic() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    subgraph = extract_bounded_subgraph(build_attack_graph(snapshot), "asset-hr-db-01")

    first = compute_compromise_probabilities(snapshot, subgraph)
    second = compute_compromise_probabilities(copy.deepcopy(snapshot), subgraph)

    assert first == second


# --- Homer et al. (2013): cycles and hidden correlations ---------------------


def test_cycle_cannot_inflate_reachability() -> None:
    """A second internal server beside hr-db makes a two-way loop, but every way behind
    the DMZ still runs through asset-web-01, so hr-db's reach must stay exactly
    P(web falls) = 0.261. A propagation formula iterated round the loop would feed
    hr-db's own compromise back into its reachability and overstate it."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"].append(
        _asset(
            "asset-app-01",
            "internal-corp",
            internet_facing=False,
            findings=[_finding("finding-app", 0.5, "CVE-2026-00003")],
            service_ids=["svc-internal-hr"],
        )
    )
    graph = build_attack_graph(snapshot)
    assert any(
        e.source_asset_id == "asset-app-01" and e.target_asset_id == "asset-hr-db-01"
        for e in graph.edges
    ), "setup should give hr-db a second, looping route in"

    (route,) = compute_graph_reachability(snapshot)["asset-hr-db-01"].routes

    assert route.reach_probability == pytest.approx(WEB_VULNERABILITY, abs=TOLERANCE_NEAR_QUARTER)


def test_findings_sharing_a_cve_are_correlated_across_hops() -> None:
    """Give hr-db the web server's own CVE (vulnerability 0.87 with no controls).

    One shared draw: the web server falls when it is below 0.261, hr-db's copy
    works when it is below 0.87. So whenever hr-db's exploit works *and* the
    attacker got in, the web server's did too:
    P(reached | hr-db exploit works) = 0.261 / 0.87 = 0.300 — versus 0.261
    if the two were independent. Each finding's own marginal is untouched.
    """
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    hr_db_finding = snapshot["assets"][1]["findings"][0]
    hr_db_finding.update(
        {"type": "cve", "cve_id": "CVE-2026-00001", "epss_score": 0.87, "kev_listed": True}
    )

    (route,) = compute_graph_reachability(snapshot)["asset-hr-db-01"].routes

    assert route.reach_probability == pytest.approx(WEB_VULNERABILITY, abs=TOLERANCE_NEAR_QUARTER)
    assert route.reach_given_finding["finding-0002"] == pytest.approx(
        WEB_VULNERABILITY / 0.87, abs=TOLERANCE_NEAR_QUARTER
    )


def test_findings_with_different_cves_stay_independent() -> None:
    """The fixture's hr-db finding has no CVE in common with the web server: no correlation."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)

    (route,) = compute_graph_reachability(snapshot)["asset-hr-db-01"].routes

    assert route.reach_given_finding["finding-0002"] == pytest.approx(
        route.reach_probability, abs=TOLERANCE_NEAR_QUARTER
    )


# --- Per-route breakdown -----------------------------------------------------


def test_each_route_keeps_its_own_attack_rate_and_share() -> None:
    """Web server (12 attacks/yr, reach 0.261) and mail server (2/yr, reach 0.4) both lead
    to hr-db. Contributions 12 x 0.261 = 3.13 and 2 x 0.4 = 0.80 -> shares 79.7% / 20.3%."""
    snapshot = _with_second_entry_point()

    routes = compute_graph_reachability(snapshot)["asset-hr-db-01"].routes

    assert [route.entry_asset_id for route in routes] == ["asset-web-01", "asset-mail-01"]
    web, mail = routes
    assert web.entry_exposure_profile == "internet_facing_critical_asset"
    assert mail.entry_exposure_profile == "internal_asset"
    assert mail.reach_probability == pytest.approx(0.4, abs=TOLERANCE_NEAR_QUARTER)
    expected_web_share = (12 * WEB_VULNERABILITY) / (12 * WEB_VULNERABILITY + 2 * 0.4)
    assert web.share == pytest.approx(expected_web_share, abs=TOLERANCE_NEAR_QUARTER)
    assert web.share + mail.share == pytest.approx(1.0)


def test_attack_rate_is_the_sum_over_routes() -> None:
    """hr-db's most-likely rate must be 12 x 0.261 + 2 x 0.4 = 3.93 attacks/yr reaching it,
    not the busiest route's 12 x (1 - (1 - 0.261)(1 - 0.4)) = 6.68 the old model gave."""
    snapshot = _with_second_entry_point()

    parameterized = parameterize_scenario(
        _scenario_for(snapshot, "asset-hr-db-01"),
        snapshot,
        graph_reachability=compute_graph_reachability(snapshot),
    )

    assert parameterized["threat_event_frequency"]["most_likely"] == pytest.approx(
        12 * WEB_VULNERABILITY + 2 * 0.4, abs=0.15
    )
    assert "asset-web-01 80%" in parameterized["description"]
    assert "asset-mail-01 20%" in parameterized["description"]


# --- Engine integration ------------------------------------------------------


def test_compute_graph_reachability_omits_unknown_segments() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][1]["network"]["segment_id"] = None

    reachability = compute_graph_reachability(snapshot)

    assert "asset-hr-db-01" not in reachability
    assert reachability["asset-web-01"].is_entry_point is True
    assert reachability["asset-web-01"].routes == []


def test_stepping_stone_asset_uses_perimeter_rate_times_reach() -> None:
    """hr-db's own profile is internal_asset (2/yr), but its only route in runs through a
    critical internet-facing server (12/yr). Rate = 12 x 0.261; LEF = that x 0.05."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)

    parameterized = parameterize_scenario(
        _scenario_for(snapshot, "asset-hr-db-01"),
        snapshot,
        graph_reachability=compute_graph_reachability(snapshot),
    )

    assert parameterized["graph_reachability_applied"] is True
    assert parameterized["exposure_profile"] == "internal_asset"
    assert parameterized["vulnerability"] == pytest.approx(HR_DB_VULNERABILITY)
    assert parameterized["threat_event_frequency"]["most_likely"] == pytest.approx(
        12 * WEB_VULNERABILITY, abs=0.15
    )
    assert "reached via attack graph: asset-web-01 100%" in parameterized["description"]


def test_entry_point_figures_are_unchanged_by_the_graph() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    scenario = _scenario_for(snapshot, "asset-web-01")

    without_graph = parameterize_scenario(scenario, snapshot)
    with_graph = parameterize_scenario(
        scenario, snapshot, graph_reachability=compute_graph_reachability(snapshot)
    )

    assert with_graph["graph_reachability_applied"] is False
    assert with_graph["loss_event_frequency"] == without_graph["loss_event_frequency"]
    assert "attack graph" not in with_graph["description"]


def test_unknown_topology_figures_are_unchanged_by_the_graph() -> None:
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][1]["network"]["segment_id"] = None
    scenario = _scenario_for(snapshot, "asset-hr-db-01")

    without_graph = parameterize_scenario(scenario, snapshot)
    with_graph = parameterize_scenario(
        scenario, snapshot, graph_reachability=compute_graph_reachability(snapshot)
    )

    assert with_graph["graph_reachability_applied"] is False
    assert with_graph["loss_event_frequency"] == without_graph["loss_event_frequency"]


def test_remediating_the_stepping_stone_makes_the_internal_asset_unreachable() -> None:
    """With the DMZ server's only finding fixed, no campaign gets past it: no routes,
    zero attack rate, and the description says why."""
    snapshot = copy.deepcopy(SAMPLE_SNAPSHOT)
    snapshot["assets"][0]["findings"][0]["remediated_at"] = "2026-09-20T00:00:00Z"
    reachability = compute_graph_reachability(snapshot)

    assert reachability["asset-hr-db-01"].routes == []
    parameterized = parameterize_scenario(
        _scenario_for(snapshot, "asset-hr-db-01"), snapshot, graph_reachability=reachability
    )
    assert parameterized["loss_event_frequency"]["max"] == 0.0
    assert "unreachable under the known network topology" in parameterized["description"]


def test_same_seed_gives_identical_reachability() -> None:
    """The seed core.engine.risk_figure passes through must fully determine the result,
    so the optimizer's paired comparisons see common random numbers here too."""
    snapshot = _with_second_entry_point()

    assert compute_graph_reachability(snapshot, seed=7) == compute_graph_reachability(
        copy.deepcopy(snapshot), seed=7
    )
