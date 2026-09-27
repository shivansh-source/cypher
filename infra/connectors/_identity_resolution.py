"""Cross-connector asset-identity reconciliation: graph, evidence, and decisions.

Not a connector itself and not part of the schema contract — like
``_object_store.py``/``_env.py``, this is a shared implementation detail,
here for the ingestion pipeline's identity-resolution step (see
``infra/README.md``). It has exactly one job: given the placeholder
``host:``/``cloud:``-prefixed asset ids every non-CMDB connector mints (see
``base.py``'s and e.g. ``wazuh_connector.py``'s docstrings on
``_identity_hint``) and the canonical identity records
``cmdb_connector.py`` produces, find candidate merges and describe the
evidence for each — never decide a merge itself.

This module never imports from ``ai/`` (repo-root ``CLAUDE.md``: ``infra/``
must never import from ``ai/``). The actual Jev call and the
merge/no-merge decision happen in ``interfaces/cli/cypher.py``, which is
allowed to see both ``infra/`` and ``ai/`` — the same bridging pattern
``ingest_command`` already uses for ``core.snapshot`` (see its own
docstring: "core.snapshot is imported here rather than in infra/ because
infra/connectors/ may never import from core/ ... interfaces/ is the layer
allowed to bridge the two").

Every merge decision — merged or not — is recorded via
:func:`record_merge_decision`, append-only, mirroring
``governance/attestations.py``'s store (never overwritten; a decision
revisited later gets a new record, not an edit).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Merge confidence threshold
# ---------------------------------------------------------------------------
# ASSUMPTION: minimum Jev confidence, in [0, 1], required to merge a
# candidate placeholder asset id into a CMDB canonical asset id
# automatically. Below this, the candidate is left unmerged and recorded
# for human reconciliation instead (see ReconciliationRecord). The boundary
# is INCLUSIVE of merging: confidence == MERGE_CONFIDENCE_THRESHOLD merges.
# This is deliberately NOT in core/assumptions.py: it is an ingestion-layer
# parameter governing how aggressively infra/ collapses two observed
# identifiers into one asset before core/ ever sees a snapshot, not a FAIR
# risk-modelling parameter — core/ never sees the unmerged/merged
# distinction as a choice, only ever a finished snapshot.
# JUSTIFICATION: PLACEHOLDER — no source yet. 0.85 is chosen deliberately
# high: a false merge (two different real assets collapsed into one) is
# worse than a false non-merge (two records for one real asset, corrected
# later) — a false merge can hide risk (one asset's findings get attributed
# to a machine that isn't exposed the same way) rather than just
# duplicating it. See the "when an asset's risk looks wrong, the first
# question is whether it's actually one machine" principle this module
# exists to serve.
# CALIBRATION: requires a labeled set of real candidate-merge pairs (known
# same-asset vs known different-asset) to measure Jev's actual precision/
# recall at this threshold for this organization's evidence patterns, and
# to tune the threshold against a real cost ratio between false-merge and
# false-non-merge, rather than the asymmetric-but-unmeasured judgement call
# above.
MERGE_CONFIDENCE_THRESHOLD: float = 0.85


@dataclass(frozen=True)
class CMDBIdentityRecord:
    """One CMDB-known asset and every identifier CMDB has on file for it.

    Attributes:
        canonical_asset_id: The stable, CMDB-authoritative asset id (e.g.
            ``"cmdb:AST-04821"``) — this is the identity every candidate
            merge below resolves *toward*; it is never itself a candidate,
            since CMDB is this system's identity authority.
        known_identifiers: Every identifier value CMDB has on file for this
            asset, keyed by kind (``"host"`` for hostnames, ``"ip"`` for IP
            addresses, ``"cloud"`` for cloud instance ids) to a list of
            values, all already lowercased for comparison.
    """

    canonical_asset_id: str
    known_identifiers: dict[str, list[str]]


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence supporting a candidate merge.

    Attributes:
        placeholder_kind: The kind parsed from the placeholder asset id's
            prefix (``"host"`` or ``"cloud"``).
        value: The shared identifier value.
        matched_cmdb_kind: Which of the CMDB record's identifier kinds this
            matched against.
        same_kind: Whether ``placeholder_kind`` and ``matched_cmdb_kind``
            are the same kind of identifier (strong evidence) or different
            kinds that happened to share a value (weak evidence — kept
            distinct so a reader, or Jev, can weigh it accordingly).
    """

    placeholder_kind: str
    value: str
    matched_cmdb_kind: str
    same_kind: bool


@dataclass(frozen=True)
class CandidateMerge:
    """One placeholder asset id that shares evidence with one CMDB canonical asset.

    Attributes:
        placeholder_asset_id: The non-CMDB, connector-minted asset id (e.g.
            ``"host:10.0.0.5"``).
        source_connector: Which connector's fragment carried
            ``placeholder_asset_id`` (for the evidence description only;
            never used to special-case behavior — see repo-root
            ``CLAUDE.md`` principle 3).
        canonical_asset_id: The CMDB asset id this placeholder might
            resolve to.
        evidence: Every shared identifier found between the two, in the
            order discovered. Never empty — a candidate with no evidence is
            not produced at all (see :func:`find_candidate_merges`).
    """

    placeholder_asset_id: str
    source_connector: str
    canonical_asset_id: str
    evidence: list[EvidenceItem] = field(default_factory=list)


#: Placeholder asset id prefix -> the CMDB identifier kind it's naturally
#: compared against as a same-kind match. wazuh_connector.py/
#: greenbone_connector.py mint "host:" ids from a hostname-or-IP value (see
#: their own docstrings); prowler_connector.py/scoutsuite_connector.py mint
#: "cloud:" ids from a cloud resource identifier. Both CMDB identifier kinds
#: ("host"/"cloud") are still checked regardless — see
#: :func:`find_candidate_merges` — this table only decides same_kind vs not.
_PLACEHOLDER_PREFIX_TO_CMDB_KIND: dict[str, str] = {"host": "host", "cloud": "cloud"}


def parse_placeholder_asset_id(asset_id: str) -> tuple[str, str] | None:
    """Split a connector-minted placeholder asset id into (kind, value).

    Args:
        asset_id: An asset id as it appears in a candidate snapshot's
            ``assets[]``.

    Returns:
        ``(kind, value)`` if ``asset_id`` matches the ``host:``/``cloud:``
        placeholder scheme (see ``base.py``'s and each implemented
        connector's ``resolve_asset_id`` docstrings), or ``None`` if it
        does not — including for an already-canonical ``cmdb:``-prefixed
        id, which is never itself a merge candidate.
    """
    if ":" not in asset_id:
        return None
    kind, _, value = asset_id.partition(":")
    if kind not in _PLACEHOLDER_PREFIX_TO_CMDB_KIND:
        return None
    return kind, value


#: schema/aggregated_assets.schema.json's endpoints[].address_type
#: vocabulary -> the identifier kind used throughout this module. The
#: inverse of cmdb_connector.py's own (private)
#: _IDENTIFIER_KIND_TO_ADDRESS_TYPE — kept as its own public table here
#: rather than imported from that connector, since this module must stay
#: usable against any endpoints[] data, not only cmdb_connector.py's own
#: output.
_ADDRESS_TYPE_TO_IDENTIFIER_KIND: dict[str, str] = {
    "hostname": "host",
    "ipv4": "ip",
    "cloud_instance_id": "cloud",
}


def cmdb_records_from_endpoints(endpoints: list[dict[str, Any]]) -> list[CMDBIdentityRecord]:
    """Group a candidate snapshot's ``endpoints[]`` into one record per CMDB asset.

    Args:
        endpoints: A candidate snapshot's ``endpoints[]`` list (schema-shaped:
            ``endpoint_id``/``address_type``/``address``/``resolved_asset_id``).
            Entries with ``resolved_asset_id: null`` (not yet resolved to any
            asset) are skipped — they carry no CMDB identity to match against.

    Returns:
        One :class:`CMDBIdentityRecord` per distinct ``resolved_asset_id``,
        with every matching endpoint's ``address`` bucketed by identifier
        kind. An ``address_type`` outside
        :data:`_ADDRESS_TYPE_TO_IDENTIFIER_KIND` is skipped rather than
        raising — this module only needs to know about the identifier
        kinds it can actually match a placeholder against.
    """
    records: dict[str, dict[str, list[str]]] = {}
    for endpoint in endpoints:
        resolved_asset_id = endpoint.get("resolved_asset_id")
        kind = _ADDRESS_TYPE_TO_IDENTIFIER_KIND.get(endpoint.get("address_type", ""))
        if resolved_asset_id is None or kind is None:
            continue
        by_kind = records.setdefault(resolved_asset_id, {})
        by_kind.setdefault(kind, []).append(str(endpoint["address"]))
    return [
        CMDBIdentityRecord(canonical_asset_id=asset_id, known_identifiers=by_kind)
        for asset_id, by_kind in records.items()
    ]


def find_candidate_merges(
    placeholder_asset_ids: dict[str, str], cmdb_records: list[CMDBIdentityRecord]
) -> list[CandidateMerge]:
    """Find every (placeholder, CMDB canonical asset) pair with shared evidence.

    Args:
        placeholder_asset_ids: Every non-CMDB asset id observed in a
            candidate snapshot's ``assets[]``, mapped to the connector name
            that produced it (from that asset's findings' own
            ``provenance.connector`` — the caller resolves this; see
            ``interfaces/cli/cypher.py``). Ids that don't parse as a
            ``host:``/``cloud:`` placeholder (e.g. an id already resolved
            to ``cmdb:...``) are skipped.
        cmdb_records: Every CMDB-known asset and its identifiers.

    Returns:
        One :class:`CandidateMerge` per (placeholder, CMDB record) pair
        that shares at least one identifier value — never a pair with no
        shared evidence, and never every possible pair (this is not a
        blind cross-join).

    Must never:
        Emit a candidate for a pair with zero shared evidence — a merge
        decision (even a "no" from Jev) must always be backed by at least
        one concrete piece of evidence to reason about.
    """
    candidates: list[CandidateMerge] = []
    for placeholder_asset_id, source_connector in placeholder_asset_ids.items():
        parsed = parse_placeholder_asset_id(placeholder_asset_id)
        if parsed is None:
            continue
        placeholder_kind, value = parsed
        for record in cmdb_records:
            evidence: list[EvidenceItem] = []
            for cmdb_kind, values in record.known_identifiers.items():
                if value.lower() in (v.lower() for v in values):
                    evidence.append(
                        EvidenceItem(
                            placeholder_kind=placeholder_kind,
                            value=value,
                            matched_cmdb_kind=cmdb_kind,
                            same_kind=(
                                _PLACEHOLDER_PREFIX_TO_CMDB_KIND[placeholder_kind] == cmdb_kind
                            ),
                        )
                    )
            if evidence:
                candidates.append(
                    CandidateMerge(
                        placeholder_asset_id=placeholder_asset_id,
                        source_connector=source_connector,
                        canonical_asset_id=record.canonical_asset_id,
                        evidence=evidence,
                    )
                )
    return candidates


def render_evidence_state(candidate: CandidateMerge) -> str:
    """Render a candidate merge's evidence into the ``state`` string sent to Jev.

    Args:
        candidate: A candidate produced by :func:`find_candidate_merges`.

    Returns:
        A human-readable (and Jev-readable) description of what identifiers
        are shared, from which sources, and how strong each piece of
        evidence is — never just the boolean outcome. See
        :func:`record_merge_decision` for why this string is also what
        gets persisted alongside the decision.
    """
    lines = [
        (
            f"Candidate merge: placeholder asset '{candidate.placeholder_asset_id}' "
            f"(observed by {candidate.source_connector}) vs CMDB canonical asset "
            f"'{candidate.canonical_asset_id}'."
        ),
        "Shared identifiers:",
    ]
    for item in candidate.evidence:
        strength = "same-kind, strong" if item.same_kind else "cross-kind, weak"
        lines.append(
            f"  - value '{item.value}': placeholder kind '{item.placeholder_kind}' "
            f"matched CMDB identifier kind '{item.matched_cmdb_kind}' ({strength})"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class MergeDecision:
    """One inspectable record of a merge decision — merged or not.

    Attributes:
        placeholder_asset_id: See :class:`CandidateMerge`.
        canonical_asset_id: See :class:`CandidateMerge`.
        evidence_state: The exact string sent to Jev (from
            :func:`render_evidence_state`), stored verbatim so the decision
            is re-inspectable without recomputing it against a possibly
            different snapshot later.
        jev_confidence: Jev's confidence in "same asset", in ``[0, 1]``.
        threshold_at_decision: :data:`MERGE_CONFIDENCE_THRESHOLD` at the
            time of this decision — stored explicitly (not re-read from the
            constant later) so a threshold change never silently
            reinterprets a past decision.
        merged: Whether ``jev_confidence >= threshold_at_decision``.
        decided_at: When this decision was made.
    """

    placeholder_asset_id: str
    canonical_asset_id: str
    evidence_state: str
    jev_confidence: float
    threshold_at_decision: float
    merged: bool
    decided_at: datetime


def decide_merge(
    candidate: CandidateMerge, jev_confidence: float, as_of: datetime
) -> MergeDecision:
    """Apply :data:`MERGE_CONFIDENCE_THRESHOLD` to one candidate's Jev answer.

    Args:
        candidate: The candidate this decision is about.
        jev_confidence: Jev's confidence that ``candidate``'s two ids name
            the same asset (the ``confidence`` of a
            ``ai.jev_transport.TypedAnswer`` whose ``value`` was ``True``
            for a "same asset?" bool question; a ``False``-valued answer
            must be passed as its own confidence *in the false direction*
            — i.e. the caller decides "same asset" vs not before calling
            this, this function only applies the threshold to how sure
            that decision was).
        as_of: When this decision is being made.

    Returns:
        A :class:`MergeDecision` recording the outcome and its full
        evidence trail.

    Must never:
        Merge below :data:`MERGE_CONFIDENCE_THRESHOLD` — the boundary is
        inclusive (``>=`` merges), and this must be the only place that
        comparison happens.
    """
    merged = jev_confidence >= MERGE_CONFIDENCE_THRESHOLD
    return MergeDecision(
        placeholder_asset_id=candidate.placeholder_asset_id,
        canonical_asset_id=candidate.canonical_asset_id,
        evidence_state=render_evidence_state(candidate),
        jev_confidence=jev_confidence,
        threshold_at_decision=MERGE_CONFIDENCE_THRESHOLD,
        merged=merged,
        decided_at=as_of,
    )


def load_merge_decisions(store_path: Path) -> list[MergeDecision]:
    """Load every merge decision ever recorded, oldest first.

    Args:
        store_path: Path to the JSON merge-decision store (e.g.
            ``IDENTITY_RECONCILIATION_STORE_PATH``).

    Returns:
        Every :class:`MergeDecision` ever recorded, in file order. Returns
        an empty list if the store doesn't exist yet.
    """
    if not store_path.exists():
        return []
    raw = json.loads(store_path.read_text())
    return [
        MergeDecision(
            placeholder_asset_id=d["placeholder_asset_id"],
            canonical_asset_id=d["canonical_asset_id"],
            evidence_state=d["evidence_state"],
            jev_confidence=d["jev_confidence"],
            threshold_at_decision=d["threshold_at_decision"],
            merged=d["merged"],
            decided_at=datetime.fromisoformat(d["decided_at"]),
        )
        for d in raw.get("decisions", [])
    ]


def record_merge_decision(store_path: Path, decision: MergeDecision) -> None:
    """Append one merge decision to the store — every decision, merged or not.

    Args:
        store_path: Path to the JSON merge-decision store.
        decision: The decision to record.

    Must never:
        Overwrite or remove any existing record — this function only ever
        appends, mirroring ``governance.attestations.record_attestation``.
        A candidate revisited on a later ingest run gets a new record, not
        an edit to the old one, so the full history of what was decided,
        on what evidence, and when, is always reconstructable.
    """
    existing = load_merge_decisions(store_path)
    existing.append(decision)
    payload: dict[str, Any] = {
        "decisions": [{**asdict(d), "decided_at": d.decided_at.isoformat()} for d in existing]
    }
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(payload, indent=2) + "\n")
