"""Tests for governance/evidence_generator.py.

The most important property: generating an evidence package twice from the
same inputs (same snapshot_id, library, statuses, weighted_score,
generated_at) must be byte-identical.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from governance.evidence_generator import (
    generate_evidence_package,
    render_evidence_package_to_json,
    render_evidence_package_to_markdown,
)
from governance.library_loader import ControlLibrary, load_control_library
from governance.mapper import ControlStatus, compute_weighted_score
from governance.tests.conftest import minimal_control, write_library_yaml

GENERATED_AT = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


def _library_and_statuses(
    tmp_path: Path, as_of_date: date
) -> tuple[ControlLibrary, list[ControlStatus]]:
    controls = [
        minimal_control(id="c1", weight=50.0, confidence="high", parameter_name="Control One"),
        minimal_control(id="c2", weight=50.0, confidence="low", parameter_name="Control Two"),
    ]
    path = write_library_yaml(tmp_path / "lib.yaml", framework="demo_fw", controls=controls)
    library = load_control_library(path, as_of_date)
    statuses = [
        ControlStatus("c1", "demo_fw", "1.0", "met", ["asset-1"], "high", False),
        ControlStatus("c2", "demo_fw", "1.0", "not_met", ["asset-2"], "low", False),
    ]
    return library, statuses


def test_generate_evidence_package_is_deterministic(tmp_path: Path, as_of_date: date) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)

    package_1 = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)
    package_2 = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)

    assert render_evidence_package_to_json(package_1) == render_evidence_package_to_json(package_2)
    assert render_evidence_package_to_markdown(package_1) == render_evidence_package_to_markdown(
        package_2
    )


def test_generate_evidence_package_pins_snapshot_id(tmp_path: Path, as_of_date: date) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:pinned", library, statuses, score, GENERATED_AT)
    assert package.snapshot_id == "sha256:pinned"


def test_generate_evidence_package_covers_every_control(tmp_path: Path, as_of_date: date) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)
    assert {c.control_id for c in package.controls} == {"c1", "c2"}
    assert package.total_control_count == 2


def test_unverified_control_count_reflects_verified_by_human_false(
    tmp_path: Path, as_of_date: date
) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)
    # minimal_control() defaults verified_by_human=False for both controls.
    assert package.unverified_control_count == 2


def test_markdown_render_surfaces_unverified_banner(tmp_path: Path, as_of_date: date) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)
    markdown = render_evidence_package_to_markdown(package)
    assert "verified_by_human: false" in markdown
    assert "2 of 2" in markdown


def test_markdown_render_never_collapses_statuses_into_single_verdict(
    tmp_path: Path, as_of_date: date
) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)
    markdown = render_evidence_package_to_markdown(package)
    # Both individual statuses must be visible, not summarized away.
    assert "met" in markdown
    assert "not_met" in markdown
    assert "Control One" in markdown
    assert "Control Two" in markdown


def test_markdown_render_shows_weighted_score_caveats(tmp_path: Path, as_of_date: date) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)
    markdown = render_evidence_package_to_markdown(package)
    assert "Coverage" in markdown
    assert "confidence: low" in markdown


def test_json_render_never_reorders_or_drops_fields(tmp_path: Path, as_of_date: date) -> None:
    library, statuses = _library_and_statuses(tmp_path, as_of_date)
    score = compute_weighted_score(library, statuses)
    package = generate_evidence_package("sha256:abc", library, statuses, score, GENERATED_AT)

    parsed = json.loads(render_evidence_package_to_json(package))
    assert parsed["snapshot_id"] == "sha256:abc"
    assert parsed["total_control_count"] == 2
    assert len(parsed["controls"]) == 2
    assert parsed["weighted_score"]["coverage_fraction"] == 1.0
