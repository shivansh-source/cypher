"""Tests for infra/connectors/_identity_resolution.py.

Pure logic — no network, no httpx/Jev mocking needed here (that lives in
ai/tests/test_jev_transport.py). ``decide_merge`` takes a confidence value
directly, exactly as the real caller (interfaces/cli/riskctl.py) would pass
one derived from a real ai.jev_transport.TypedAnswer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from infra.connectors._identity_resolution import (
    MERGE_CONFIDENCE_THRESHOLD,
    CandidateMerge,
    CMDBIdentityRecord,
    cmdb_records_from_endpoints,
    decide_merge,
    find_candidate_merges,
    load_merge_decisions,
    parse_placeholder_asset_id,
    record_merge_decision,
    render_evidence_state,
)

_CMDB_RECORD = CMDBIdentityRecord(
    canonical_asset_id="cmdb:AST-04821",
    known_identifiers={"host": ["web-01", "web-01.corp.local"], "ip": ["10.0.0.5"], "cloud": []},
)
_OTHER_CMDB_RECORD = CMDBIdentityRecord(
    canonical_asset_id="cmdb:AST-09911", known_identifiers={"cloud": ["i-0abc123"]}
)


# --- parse_placeholder_asset_id ---------------------------------------------


@pytest.mark.parametrize(
    ("asset_id", "expected"),
    [("host:10.0.0.5", ("host", "10.0.0.5")), ("cloud:i-0abc123", ("cloud", "i-0abc123"))],
)
def test_parse_placeholder_asset_id_recognizes_known_prefixes(
    asset_id: str, expected: tuple[str, str]
) -> None:
    assert parse_placeholder_asset_id(asset_id) == expected


@pytest.mark.parametrize("asset_id", ["cmdb:AST-04821", "no-colon-here"])
def test_parse_placeholder_asset_id_returns_none_for_non_placeholder_ids(asset_id: str) -> None:
    assert parse_placeholder_asset_id(asset_id) is None


# --- cmdb_records_from_endpoints ---------------------------------------------


def test_cmdb_records_from_endpoints_groups_by_resolved_asset_id() -> None:
    endpoints = [
        {"endpoint_id": "e1", "address_type": "hostname", "address": "web-01", "resolved_asset_id": "cmdb:AST-04821"},
        {"endpoint_id": "e2", "address_type": "ipv4", "address": "10.0.0.5", "resolved_asset_id": "cmdb:AST-04821"},
        {"endpoint_id": "e3", "address_type": "cloud_instance_id", "address": "i-0abc123", "resolved_asset_id": "cmdb:AST-09911"},
    ]
    records = {r.canonical_asset_id: r for r in cmdb_records_from_endpoints(endpoints)}
    assert set(records) == {"cmdb:AST-04821", "cmdb:AST-09911"}
    assert records["cmdb:AST-04821"].known_identifiers == {"host": ["web-01"], "ip": ["10.0.0.5"]}
    assert records["cmdb:AST-09911"].known_identifiers == {"cloud": ["i-0abc123"]}


def test_cmdb_records_from_endpoints_skips_unresolved_endpoints() -> None:
    endpoints = [
        {"endpoint_id": "e1", "address_type": "hostname", "address": "orphan", "resolved_asset_id": None}
    ]
    assert cmdb_records_from_endpoints(endpoints) == []


# --- find_candidate_merges ---------------------------------------------------


def test_find_candidate_merges_same_kind_ip_match() -> None:
    placeholders = {"host:10.0.0.5": "wazuh_connector"}
    [candidate] = find_candidate_merges(placeholders, [_CMDB_RECORD, _OTHER_CMDB_RECORD])
    assert candidate.canonical_asset_id == "cmdb:AST-04821"
    assert candidate.source_connector == "wazuh_connector"
    [evidence] = candidate.evidence
    assert evidence.value == "10.0.0.5"
    assert evidence.matched_cmdb_kind == "ip"
    # placeholder kind "host" vs matched CMDB kind "ip" -> different kinds.
    assert evidence.same_kind is False


def test_find_candidate_merges_matches_case_insensitively() -> None:
    placeholders = {"host:WEB-01": "greenbone_connector"}
    [candidate] = find_candidate_merges(placeholders, [_CMDB_RECORD])
    assert candidate.evidence[0].same_kind is True  # host placeholder vs CMDB "host" list


def test_find_candidate_merges_cloud_placeholder_matches_cloud_record() -> None:
    placeholders = {"cloud:i-0abc123": "prowler_connector"}
    [candidate] = find_candidate_merges(placeholders, [_CMDB_RECORD, _OTHER_CMDB_RECORD])
    assert candidate.canonical_asset_id == "cmdb:AST-09911"


def test_find_candidate_merges_no_shared_evidence_emits_nothing() -> None:
    placeholders = {"host:192.168.1.1": "wazuh_connector"}
    assert find_candidate_merges(placeholders, [_CMDB_RECORD, _OTHER_CMDB_RECORD]) == []


def test_find_candidate_merges_skips_already_canonical_ids() -> None:
    placeholders = {"cmdb:AST-04821": "cmdb_connector"}
    assert find_candidate_merges(placeholders, [_CMDB_RECORD]) == []


def test_find_candidate_merges_multiple_shared_identifiers_produce_multiple_evidence_items() -> None:
    """A pair sharing two identifiers is stronger evidence than sharing one."""
    placeholders = {"host:10.0.0.5": "wazuh_connector"}
    richer_record = CMDBIdentityRecord(
        canonical_asset_id="cmdb:AST-04821",
        known_identifiers={"host": ["10.0.0.5"], "ip": ["10.0.0.5"]},
    )
    [candidate] = find_candidate_merges(placeholders, [richer_record])
    assert len(candidate.evidence) == 2


# --- render_evidence_state ---------------------------------------------------


def test_render_evidence_state_reflects_evidence_strength_differences() -> None:
    """A shared cloud instance id (strong) and a shared IP-only match (weak) must render differently."""
    strong = CandidateMerge(
        placeholder_asset_id="cloud:i-0abc123",
        source_connector="prowler_connector",
        canonical_asset_id="cmdb:AST-09911",
        evidence=find_candidate_merges(
            {"cloud:i-0abc123": "prowler_connector"}, [_OTHER_CMDB_RECORD]
        )[0].evidence,
    )
    weak = CandidateMerge(
        placeholder_asset_id="host:10.0.0.5",
        source_connector="wazuh_connector",
        canonical_asset_id="cmdb:AST-04821",
        evidence=find_candidate_merges({"host:10.0.0.5": "wazuh_connector"}, [_CMDB_RECORD])[
            0
        ].evidence,
    )

    strong_state = render_evidence_state(strong)
    weak_state = render_evidence_state(weak)

    assert "same-kind, strong" in strong_state
    assert "cross-kind, weak" in weak_state
    assert strong_state != weak_state
    assert "i-0abc123" in strong_state
    assert "10.0.0.5" in weak_state


# --- decide_merge: threshold behavior ----------------------------------------


def _candidate() -> CandidateMerge:
    return find_candidate_merges({"host:10.0.0.5": "wazuh_connector"}, [_CMDB_RECORD])[0]


def test_decide_merge_above_threshold_merges() -> None:
    decision = decide_merge(_candidate(), jev_confidence=0.99, as_of=datetime.now(UTC))
    assert decision.merged is True


def test_decide_merge_below_threshold_does_not_merge() -> None:
    decision = decide_merge(_candidate(), jev_confidence=0.5, as_of=datetime.now(UTC))
    assert decision.merged is False


def test_decide_merge_exactly_at_threshold_merges_inclusive_boundary() -> None:
    """The boundary is documented as inclusive: confidence == threshold merges."""
    decision = decide_merge(
        _candidate(), jev_confidence=MERGE_CONFIDENCE_THRESHOLD, as_of=datetime.now(UTC)
    )
    assert decision.merged is True


def test_decide_merge_just_below_threshold_does_not_merge() -> None:
    decision = decide_merge(
        _candidate(), jev_confidence=MERGE_CONFIDENCE_THRESHOLD - 0.001, as_of=datetime.now(UTC)
    )
    assert decision.merged is False


def test_decide_merge_records_full_evidence_trail_not_just_outcome() -> None:
    as_of = datetime.now(UTC)
    decision = decide_merge(_candidate(), jev_confidence=0.5, as_of=as_of)
    assert decision.evidence_state == render_evidence_state(_candidate())
    assert decision.jev_confidence == 0.5
    assert decision.threshold_at_decision == MERGE_CONFIDENCE_THRESHOLD
    assert decision.decided_at == as_of


# --- record/load: append-only store -----------------------------------------


def test_record_and_load_merge_decision_round_trips(tmp_path: Path) -> None:
    store_path = tmp_path / "identity_reconciliation.json"
    decision = decide_merge(_candidate(), jev_confidence=0.9, as_of=datetime.now(UTC))

    record_merge_decision(store_path, decision)
    [loaded] = load_merge_decisions(store_path)

    assert loaded.placeholder_asset_id == decision.placeholder_asset_id
    assert loaded.merged is True
    assert loaded.jev_confidence == 0.9


def test_record_merge_decision_never_overwrites_prior_records(tmp_path: Path) -> None:
    store_path = tmp_path / "identity_reconciliation.json"
    first = decide_merge(_candidate(), jev_confidence=0.5, as_of=datetime.now(UTC))
    second = decide_merge(_candidate(), jev_confidence=0.95, as_of=datetime.now(UTC))

    record_merge_decision(store_path, first)
    record_merge_decision(store_path, second)

    decisions = load_merge_decisions(store_path)
    assert len(decisions) == 2
    assert decisions[0].merged is False
    assert decisions[1].merged is True


def test_load_merge_decisions_returns_empty_list_when_store_missing(tmp_path: Path) -> None:
    assert load_merge_decisions(tmp_path / "does_not_exist.json") == []


def test_record_merge_decision_store_is_valid_json(tmp_path: Path) -> None:
    store_path = tmp_path / "identity_reconciliation.json"
    decision = decide_merge(_candidate(), jev_confidence=0.9, as_of=datetime.now(UTC))
    record_merge_decision(store_path, decision)
    payload = json.loads(store_path.read_text())
    assert "decisions" in payload
    assert payload["decisions"][0]["merged"] is True
