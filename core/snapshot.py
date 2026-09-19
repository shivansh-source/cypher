"""Snapshot lifecycle: quality gates, validation, and commit.

A candidate aggregated snapshot (schema/aggregated_assets.schema.json-shaped)
must pass all 5 quality gates defined here before it may become the current
snapshot. If any gate fails, the previous snapshot remains current — this
module must be fail-safe, never fail-open. See repo-root ``CLAUDE.md``
principle 4 and ``.claude/commands/validate-snapshot.md``.

Snapshots are bitemporal and immutable (see repo-root ``CLAUDE.md``
principle 5 and ``schema/README.md``): once committed, a snapshot's content
is never mutated, and only ``valid_to`` is ever set after the fact, when a
later snapshot supersedes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single quality gate check.

    Attributes:
        gate_name: Stable identifier for the gate (matches the function
            name that produced it, e.g. ``"asset_count_delta"``).
        passed: Whether the candidate snapshot passed this gate.
        detail: Human-readable explanation, especially on failure — must be
            specific enough that a caller can report exactly what was wrong
            without re-deriving it (e.g. "finding-0042 attributed to
            unreachable scanner nmap_connector").
    """

    gate_name: str
    passed: bool
    detail: str


def check_asset_count_delta(
    candidate: dict[str, Any], previous: dict[str, Any] | None
) -> GateResult:
    """Gate 1: reject a candidate whose asset count changed implausibly.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped.
        previous: The current (soon to be previous) snapshot, or None if
            this is the first snapshot ever committed.

    Returns:
        A :class:`GateResult` for this gate.

    Must never:
        Pass a candidate whose asset population dropped or grew far beyond
        the tolerance appropriate to the organization's actual asset
        churn rate — a large delta usually means a connector failed
        partway through aggregation, not that the estate genuinely changed
        that fast. The tolerance itself is a modelling judgement call and
        belongs in ``core/assumptions.py``, not as a literal here.
    """
    raise NotImplementedError


def check_no_findings_from_unreachable_scanners(candidate: dict[str, Any]) -> GateResult:
    """Gate 2: reject a candidate containing findings attributed to a scanner
    listed in its own ``scan_scope.unreachable_scanners``.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped.

    Returns:
        A :class:`GateResult` for this gate.

    Must never:
        Pass a candidate where any ``findings[].provenance.connector``
        appears in ``scan_scope.unreachable_scanners`` — such a finding is
        internally inconsistent and indicates a bug in the aggregation
        pipeline, not real data.
    """
    raise NotImplementedError


def check_criticality_present_or_unknown(candidate: dict[str, Any]) -> GateResult:
    """Gate 3: reject a candidate with any finding whose criticality is null.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped.

    Returns:
        A :class:`GateResult` for this gate.

    Must never:
        Treat a null ``criticality`` as equivalent to the literal string
        ``"unknown"`` — null indicates the field was never evaluated at
        all (a defect), while ``"unknown"`` is a legitimate, explicit
        scanner outcome. Only null should fail this gate.
    """
    raise NotImplementedError


def check_provenance_non_null(candidate: dict[str, Any]) -> GateResult:
    """Gate 4: reject a candidate with any finding lacking provenance.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped.

    Returns:
        A :class:`GateResult` for this gate.

    Must never:
        Pass a candidate where any ``findings[].provenance`` is missing,
        or where ``provenance.connector``/``provenance.raw_source_id`` is
        null or empty — every finding must be traceable to the connector
        and raw record that produced it.
    """
    raise NotImplementedError


def check_no_ordinal_in_numeric_field(candidate: dict[str, Any]) -> GateResult:
    """Gate 5: reject a candidate storing an ordinal value in a numeric field.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped.

    Returns:
        A :class:`GateResult` for this gate.

    Must never:
        Pass a candidate where a field typed as numeric in
        ``schema/aggregated_assets.schema.json`` (e.g. ``epss_score``,
        ``rto_hours``) instead contains a string ordinal like ``"High"`` —
        this is the classic silent-corruption failure mode where a
        connector's normalization mapped a severity label into the wrong
        field.
    """
    raise NotImplementedError


def validate_snapshot(
    candidate: dict[str, Any], previous: dict[str, Any] | None
) -> list[GateResult]:
    """Run all 5 quality gates against a candidate snapshot.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped.
        previous: The current (soon to be previous) snapshot, or None if
            this is the first snapshot ever committed.

    Returns:
        The list of all 5 :class:`GateResult` objects, in the fixed order:
        asset-count delta, no findings from unreachable scanners,
        criticality present-or-unknown, provenance non-null, no ordinal in
        numeric field. Callers must report every gate's individual
        pass/fail, never a single collapsed boolean.

    Must never:
        Short-circuit on the first failing gate — a caller needs to know
        about every failure at once to fix the candidate, not just the
        first one encountered.
    """
    raise NotImplementedError


def commit_snapshot(candidate: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Promote a validated candidate to the current snapshot.

    Args:
        candidate: The candidate aggregated snapshot, schema-shaped. Must
            already have passed :func:`validate_snapshot` in full — this
            function does not re-validate.
        previous: The current snapshot being superseded, or None if this is
            the first snapshot ever committed.

    Returns:
        The committed snapshot, unchanged except that its ``snapshot_id``
        has been computed (content hash of the normalized payload) if not
        already set.

    Must never:
        Be called with a candidate that failed any gate in
        :func:`validate_snapshot` — the previous snapshot must remain
        current in that case (fail-safe, never fail-open). Must never
        mutate ``previous`` in place other than setting its ``valid_to``
        to mark it superseded — snapshots are immutable otherwise.
    """
    raise NotImplementedError
