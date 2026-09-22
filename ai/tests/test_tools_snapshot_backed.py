"""Tests for the ai/tools/* wrappers that read the current committed snapshot.

Each wrapper is exercised against a real committed snapshot (derived from
schema/sample_aggregated.json, committed and persisted through the real
core.snapshot / core.snapshot_store path) and against an empty store, to
confirm the "no snapshot committed yet" case reports unavailable rather
than a fabricated result.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from core.snapshot import commit_snapshot
from core.snapshot_store import save_snapshot

SAMPLE_SNAPSHOT: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "schema" / "sample_aggregated.json").read_text()
)


@pytest.fixture
def committed_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A snapshot store with one committed snapshot (derived from the sample fixture)."""
    candidate = copy.deepcopy(SAMPLE_SNAPSHOT)
    candidate["snapshot_id"] = ""
    committed = commit_snapshot(candidate, None)
    save_snapshot(tmp_path, committed)
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def empty_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A snapshot store directory that has never had a snapshot committed to it."""
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path / "empty"))
    return tmp_path


def test_get_exposure_unavailable_without_a_committed_snapshot(empty_store: Path) -> None:
    from ai.tools.get_exposure import get_exposure

    with pytest.raises(NotImplementedError):
        get_exposure()


def test_get_exposure_returns_real_figures(committed_store: Path) -> None:
    from ai.tools.get_exposure import get_exposure

    result = get_exposure()

    assert result["expected_annual_loss_inr"] > 0
    assert result["value_at_risk_inr"] >= result["expected_annual_loss_inr"]
    assert result["snapshot_id"]


def test_get_exposure_scope_filters_top_contributors(committed_store: Path) -> None:
    from ai.tools.get_exposure import get_exposure

    result = get_exposure(scope="asset-web-01")

    assert all(c["asset_id"] == "asset-web-01" for c in result["top_contributors"])


def test_get_top_contributors_respects_limit(committed_store: Path) -> None:
    from ai.tools.get_top_contributors import get_top_contributors

    result = get_top_contributors(limit=1)

    assert len(result["top_contributors"]) == 1


def test_get_control_posture_scopes_to_one_asset(committed_store: Path) -> None:
    from ai.tools.get_control_posture import get_control_posture

    result = get_control_posture(asset_id="asset-web-01")

    assert len(result["assets"]) == 1
    assert result["assets"][0]["asset_id"] == "asset-web-01"


def test_get_control_posture_whole_estate(committed_store: Path) -> None:
    from ai.tools.get_control_posture import get_control_posture

    result = get_control_posture()

    assert len(result["assets"]) == len(SAMPLE_SNAPSHOT["assets"])


def test_get_framework_status_returns_per_control_statuses(
    committed_store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATTESTATION_STORE_PATH", str(tmp_path / "attestations.json"))
    from ai.tools.get_framework_status import get_framework_status

    result = get_framework_status("rbi_2026_directions")

    assert result["framework"] == "rbi_2026_directions"
    assert len(result["controls"]) > 0
    assert {"met", "not_met", "unknown", "expired_attestation"} >= {
        c["status"] for c in result["controls"]
    }


def test_get_framework_status_unknown_framework_unavailable(committed_store: Path) -> None:
    from ai.tools.get_framework_status import get_framework_status

    with pytest.raises(NotImplementedError):
        get_framework_status("not-a-real-framework")


def test_explain_number_returns_derivation_trail(committed_store: Path) -> None:
    from ai.tools.explain_number import explain_number

    result = explain_number("asset-web-01::finding-0001")

    assert result["scenario_id"] == "asset-web-01::finding-0001"
    assert "loss_event_frequency" in result["parameters"]
    assert "loss_magnitude" in result["parameters"]
    assert result["assumptions_used"]


def test_explain_number_unknown_reference_unavailable(committed_store: Path) -> None:
    from ai.tools.explain_number import explain_number

    with pytest.raises(NotImplementedError):
        explain_number("does-not-exist")
