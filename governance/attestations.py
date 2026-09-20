"""Append-only storage and expiry logic for manual attestations.

Manual attestations cover controls that cannot be evidenced by automated
findings alone (e.g. board-level policy sign-off, a vendor risk review, an
incident-response exercise). This module never overwrites or deletes a
prior attestation record — the store is append-only, so the full history of
what was attested, by whom, and when is always reconstructable.

Every attestation expires. A control's own
``attestation_validity_months`` (see ``governance/library_loader.py``)
overrides ``core.assumptions.DEFAULT_ATTESTATION_VALIDITY_MONTHS`` /
``core.assumptions.ATTESTATION_VALIDITY_MONTHS`` when set.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from core.assumptions import ATTESTATION_VALIDITY_MONTHS, DEFAULT_ATTESTATION_VALIDITY_MONTHS

AttestationStatus = Literal["met", "not_met", "insufficient_evidence"]
VALID_ATTESTATION_STATUSES = ("met", "not_met", "insufficient_evidence")


@dataclass(frozen=True)
class Attestation:
    """A single, immutable manual attestation record.

    Attributes:
        control_id: The control this attestation is evidence for.
        framework: Which framework's control library the control belongs to.
        attested_by: Name or role of whoever attested.
        attested_at: When the attestation was made.
        expires_at: When this attestation stops counting as current
            evidence, computed at write time from the control's validity
            window — stored explicitly so a stored record never depends on
            re-deriving it from a possibly-changed assumption later.
        evidence_description: Free-text description of what was reviewed.
        evidence_document_refs: References to supporting documents.
        status: One of ``met``, ``not_met``, ``insufficient_evidence``.
    """

    control_id: str
    framework: str
    attested_by: str
    attested_at: datetime
    expires_at: datetime
    evidence_description: str
    evidence_document_refs: list[str]
    status: AttestationStatus


def compute_expiry(
    control_id: str, attested_at: datetime, validity_months_override: int | None
) -> datetime:
    """Compute when an attestation for a given control expires.

    Args:
        control_id: The control being attested, used to look up a
            control-specific validity window if one exists in
            ``core.assumptions.ATTESTATION_VALIDITY_MONTHS``.
        attested_at: When the attestation is being made.
        validity_months_override: The control library entry's own
            ``attestation_validity_months``, if set — takes priority over
            both ``core.assumptions.ATTESTATION_VALIDITY_MONTHS`` and the
            default.

    Returns:
        The computed expiry datetime.

    Must never:
        Treat an attestation as valid indefinitely — every attestation must
        resolve to a concrete expiry, falling back through
        ``validity_months_override`` ->
        ``core.assumptions.ATTESTATION_VALIDITY_MONTHS[control_id]`` ->
        ``core.assumptions.DEFAULT_ATTESTATION_VALIDITY_MONTHS`` in that
        order.
    """
    months = (
        validity_months_override
        if validity_months_override is not None
        else ATTESTATION_VALIDITY_MONTHS.get(control_id, DEFAULT_ATTESTATION_VALIDITY_MONTHS)
    )
    # Calendar-month arithmetic without a third-party dependency: walk
    # year/month forward by `months`, clamping the day for shorter target
    # months (e.g. Jan 31 + 1 month -> Feb 28/29, never Mar 3).
    total_month_index = attested_at.month - 1 + months
    target_year = attested_at.year + total_month_index // 12
    target_month = total_month_index % 12 + 1
    last_day_of_target_month = calendar.monthrange(target_year, target_month)[1]
    target_day = min(attested_at.day, last_day_of_target_month)
    return attested_at.replace(year=target_year, month=target_month, day=target_day)


def record_attestation(
    store_path: Path,
    control_id: str,
    framework: str,
    attested_by: str,
    attested_at: datetime,
    evidence_description: str,
    evidence_document_refs: list[str],
    status: AttestationStatus,
    validity_months_override: int | None = None,
) -> Attestation:
    """Append a new attestation record to the store.

    Args:
        store_path: Path to the JSON attestation store (e.g.
            ``governance/manual_attestation.json``).
        control_id: The control being attested.
        framework: Which framework's control library the control belongs to.
        attested_by: Name or role of whoever attested.
        attested_at: When the attestation is being made.
        evidence_description: Free-text description of what was reviewed.
        evidence_document_refs: References to supporting documents.
        status: One of ``met``, ``not_met``, ``insufficient_evidence``.
        validity_months_override: The control's own
            ``attestation_validity_months``, if known by the caller.

    Returns:
        The newly recorded :class:`Attestation`, with its computed
        ``expires_at``.

    Raises:
        ValueError: If ``status`` is not one of
            :data:`VALID_ATTESTATION_STATUSES`.

    Must never:
        Overwrite, remove, or modify any existing record in the store —
        this function only ever appends. A control being re-attested gets
        a new record; the old one remains in the file as history.
    """
    if status not in VALID_ATTESTATION_STATUSES:
        raise ValueError(f"status must be one of {VALID_ATTESTATION_STATUSES}, got {status!r}.")

    attestation = Attestation(
        control_id=control_id,
        framework=framework,
        attested_by=attested_by,
        attested_at=attested_at,
        expires_at=compute_expiry(control_id, attested_at, validity_months_override),
        evidence_description=evidence_description,
        evidence_document_refs=list(evidence_document_refs),
        status=status,
    )

    existing = load_attestations(store_path)
    existing.append(attestation)
    _write_all(store_path, existing)
    return attestation


def load_attestations(store_path: Path) -> list[Attestation]:
    """Load every attestation record from the store, oldest first.

    Args:
        store_path: Path to the JSON attestation store.

    Returns:
        Every :class:`Attestation` ever recorded, in file order. Returns an
        empty list if the store doesn't exist yet or has no records.
    """
    if not store_path.exists():
        return []
    raw = json.loads(store_path.read_text())
    return [
        Attestation(
            control_id=a["control_id"],
            framework=a["framework"],
            attested_by=a["attested_by"],
            attested_at=datetime.fromisoformat(a["attested_at"]),
            expires_at=datetime.fromisoformat(a["expires_at"]),
            evidence_description=a["evidence_description"],
            evidence_document_refs=list(a["evidence_document_refs"]),
            status=a["status"],
        )
        for a in raw.get("attestations", [])
    ]


def _write_all(store_path: Path, attestations: list[Attestation]) -> None:
    payload = {
        "attestations": [
            {
                **asdict(a),
                "attested_at": a.attested_at.isoformat(),
                "expires_at": a.expires_at.isoformat(),
            }
            for a in attestations
        ]
    }
    store_path.write_text(json.dumps(payload, indent=2) + "\n")


def is_expired(attestation: Attestation, as_of: datetime) -> bool:
    """Whether an attestation has expired as of a given time.

    Args:
        attestation: The attestation to check.
        as_of: The time to check expiry against.

    Returns:
        True if ``as_of`` is at or after ``attestation.expires_at``.
    """
    return as_of >= attestation.expires_at


def current_attestation(
    attestations: list[Attestation], control_id: str, framework: str, as_of: datetime
) -> Attestation | None:
    """Find the most recent, non-expired attestation for a control.

    Args:
        attestations: All attestation records (e.g. from
            :func:`load_attestations`).
        control_id: The control to look up.
        framework: The framework the control belongs to.
        as_of: The time to evaluate expiry against.

    Returns:
        The most recently attested record for ``(control_id, framework)``
        that is not expired as of ``as_of``, or None if there isn't one —
        callers must treat None as "unknown", never as "not_met". An
        18-month-old attestation past its validity window must never be
        returned here even if it's the most recent record on file.
    """
    matching = [a for a in attestations if a.control_id == control_id and a.framework == framework]
    if not matching:
        return None
    most_recent = max(matching, key=lambda a: a.attested_at)
    if is_expired(most_recent, as_of):
        return None
    return most_recent


def most_recent_attestation_even_if_expired(
    attestations: list[Attestation], control_id: str, framework: str
) -> Attestation | None:
    """Find the most recent attestation for a control, expired or not.

    Args:
        attestations: All attestation records.
        control_id: The control to look up.
        framework: The framework the control belongs to.

    Returns:
        The most recent record for ``(control_id, framework)`` regardless
        of expiry, or None if none exists. Used by
        ``governance.mapper`` to distinguish "no attestation was ever made"
        (status: unknown) from "an attestation exists but has expired"
        (status: expired_attestation) — see repo-root ``CLAUDE.md``'s
        fail-safe philosophy: these are different facts and must be
        reported differently, not collapsed into one "unknown".
    """
    matching = [a for a in attestations if a.control_id == control_id and a.framework == framework]
    if not matching:
        return None
    return max(matching, key=lambda a: a.attested_at)
