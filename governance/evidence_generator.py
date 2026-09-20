"""Generates deterministic, auditor-facing evidence packages from control status.

An evidence package is pinned to one ``snapshot_id``: re-running generation
against the same snapshot, library, statuses, and ``generated_at`` must
produce byte-identical output. This module never calls ``datetime.now()``
or any other non-deterministic source internally — ``generated_at`` is
always supplied by the caller.

Every package prominently surfaces how much of its content is
``verified_by_human: false`` — an evidence report handed to an auditor must
never imply more certainty than actually exists.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from governance.library_loader import ControlLibrary
from governance.mapper import ControlStatus, WeightedScoreResult


@dataclass(frozen=True)
class ControlEvidenceEntry:
    """One control's status, formatted for an evidence package.

    Attributes:
        control_id: The control's stable identifier.
        framework_ref: The framework's own clause/safeguard reference.
        parameter_name: Short human-readable title.
        status: The control's computed status.
        evidence_refs: What justifies ``status``.
        confidence: The underlying control library entry's confidence.
        verified_by_human: The underlying control library entry's
            verification flag.
        source: Citation for the underlying regulatory fact.
    """

    control_id: str
    framework_ref: str
    parameter_name: str
    status: str
    evidence_refs: list[str]
    confidence: str
    verified_by_human: bool
    source: str


@dataclass(frozen=True)
class EvidencePackage:
    """A complete, deterministic evidence package for one framework and snapshot.

    Attributes:
        snapshot_id: The snapshot this package's evidence was computed from.
            Re-running generation against the same snapshot_id (and the
            same library/statuses/generated_at) must be byte-identical.
        framework: Which framework this package covers.
        framework_version: The framework's effective version string.
        generated_at: When this package was generated — always supplied by
            the caller, never computed internally.
        controls: Every control's status, in library order.
        weighted_score: The framework's weighted composite score, if it
            defines one (e.g. SEBI's CCI); None otherwise.
        total_control_count: Total number of controls in the package.
        unverified_control_count: How many controls are
            ``verified_by_human: false`` — surfaced at the top level so it
            can never be missed.
    """

    snapshot_id: str
    framework: str
    framework_version: str
    generated_at: datetime
    controls: list[ControlEvidenceEntry]
    weighted_score: WeightedScoreResult | None
    total_control_count: int
    unverified_control_count: int


def generate_evidence_package(
    snapshot_id: str,
    library: ControlLibrary,
    statuses: list[ControlStatus],
    weighted_score: WeightedScoreResult | None,
    generated_at: datetime,
) -> EvidencePackage:
    """Assemble a deterministic evidence package from already-computed status.

    Args:
        snapshot_id: The snapshot the statuses were computed from.
        library: The control library the statuses belong to.
        statuses: Output of ``governance.mapper.compute_all_control_statuses``
            for ``library`` — must cover every control in ``library.controls``.
        weighted_score: Output of ``governance.mapper.compute_weighted_score``
            for the same library/statuses, or None if the framework doesn't
            define a weighted score.
        generated_at: The timestamp to record on the package. Supplied by
            the caller so this function has no internal source of
            non-determinism.

    Returns:
        A fully assembled :class:`EvidencePackage`.

    Must never:
        Add, remove, or reinterpret a status — this function only formats
        what ``governance.mapper`` already determined. Must never include
        or reference any ``core.optimizer`` output. Must never call
        ``datetime.now()`` or otherwise introduce non-determinism.
    """
    status_by_id = {s.control_id: s for s in statuses}

    entries = [
        ControlEvidenceEntry(
            control_id=control.id,
            framework_ref=control.framework_ref,
            parameter_name=control.parameter_name,
            status=status_by_id[control.id].status,
            evidence_refs=status_by_id[control.id].evidence_refs,
            confidence=control.confidence,
            verified_by_human=control.verified_by_human,
            source=control.source,
        )
        for control in library.controls
    ]

    return EvidencePackage(
        snapshot_id=snapshot_id,
        framework=library.framework,
        framework_version=library.version,
        generated_at=generated_at,
        controls=entries,
        weighted_score=weighted_score,
        total_control_count=len(entries),
        unverified_control_count=sum(1 for e in entries if not e.verified_by_human),
    )


def render_evidence_package_to_markdown(package: EvidencePackage) -> str:
    """Render an evidence package into an auditor-readable Markdown document.

    Args:
        package: Output of :func:`generate_evidence_package`.

    Returns:
        A Markdown document with a prominent verification-status banner,
        every control's status listed individually, and the weighted score
        (if any) shown with its coverage/confidence caveats — never
        collapsed into a single compliance verdict.

    Must never:
        Summarize or round several controls' statuses into a broader claim
        (e.g. "mostly compliant") — every control's actual status must be
        individually visible. Must never omit the ``verified_by_human``
        banner.
    """
    lines: list[str] = []
    lines.append(f"# Evidence package — {package.framework} ({package.framework_version})")
    lines.append("")
    lines.append(f"- Snapshot: `{package.snapshot_id}`")
    lines.append(f"- Generated at: {package.generated_at.isoformat()}")
    lines.append("")
    lines.append(
        f"> **{package.unverified_control_count} of {package.total_control_count} "
        "controls in this package are `verified_by_human: false`.** Every figure "
        "below reflects automated evaluation and/or unreviewed research — none of "
        "it has been confirmed by a human against its cited source. Treat this "
        "package as provisional until that review happens."
    )
    lines.append("")

    if package.weighted_score is not None:
        ws = package.weighted_score
        lines.append("## Weighted score")
        lines.append("")
        score_pct = (
            f"{ws.score * 100:.1f}%" if ws.score is not None else "n/a (no weighted controls)"
        )
        coverage_pct = (
            f"{ws.coverage_fraction * 100:.1f}%" if ws.coverage_fraction is not None else "n/a"
        )
        low_conf_pct = (
            f"{ws.low_confidence_fraction_of_determined * 100:.1f}%"
            if ws.low_confidence_fraction_of_determined is not None
            else "n/a"
        )
        lines.append(f"- Score: {score_pct}")
        lines.append(f"- Coverage (fraction of total weight actually determinable): {coverage_pct}")
        lines.append(
            f"- Of the determinable portion, share from `confidence: low` entries: {low_conf_pct}"
        )
        if ws.controls_excluded_no_weight:
            lines.append(
                f"- Controls excluded from this score (no weight on file): "
                f"{', '.join(ws.controls_excluded_no_weight)}"
            )
        lines.append("")

    lines.append("## Controls")
    lines.append("")
    lines.append("| Control | Ref | Status | Confidence | Verified | Evidence | Source |")
    lines.append("|---|---|---|---|---|---|---|")
    for entry in package.controls:
        verified = "yes" if entry.verified_by_human else "**no**"
        evidence = ", ".join(entry.evidence_refs) if entry.evidence_refs else "—"
        lines.append(
            f"| {entry.parameter_name} | {entry.framework_ref} | {entry.status} | "
            f"{entry.confidence} | {verified} | {evidence} | {entry.source} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_evidence_package_to_json(package: EvidencePackage) -> str:
    """Render an evidence package as a JSON string.

    Args:
        package: Output of :func:`generate_evidence_package`.

    Returns:
        A JSON string (stable key ordering, 2-space indent) suitable for
        machine consumption or archival. Re-serializing the same package
        must be byte-identical.

    Must never:
        Reorder or omit any field present on :class:`EvidencePackage` or
        :class:`ControlEvidenceEntry`.
    """
    payload = asdict(package)
    payload["generated_at"] = package.generated_at.isoformat()
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
