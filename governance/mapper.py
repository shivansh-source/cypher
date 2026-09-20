"""Evaluates control status and weighted framework scores from a validated snapshot.

Reads only from a validated, schema-shaped snapshot (see
``core/snapshot.py``) plus manual attestations (see
``governance/attestations.py``) — never raw connector output, never
``interfaces/`` output, and never ``core.optimizer`` output. See repo-root
``CLAUDE.md`` principle 6: compliance maps to findings and controls, never
to optimizer output.

The executable evaluation logic lives here, dispatched by each control's
``telemetry_check.check_type`` (see ``governance/library_loader.py``) — the
YAML's ``source_field``/``logic`` strings are documentation only. A missing
or null field always resolves to ``"unknown"``, never ``"not_met"``; an
attestation past its validity window resolves to ``"expired_attestation"``,
never ``"met"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from core.assumptions import BACKUP_TEST_RECENCY_DAYS, DANGEROUS_INTERNET_FACING_PORTS
from governance.attestations import Attestation, is_expired, most_recent_attestation_even_if_expired
from governance.library_loader import ControlEntry, ControlLibrary

StatusValue = Literal["met", "not_met", "unknown", "expired_attestation"]


@dataclass(frozen=True)
class ControlStatus:
    """The evidence-derived status of a single control against one snapshot.

    Attributes:
        control_id: Identifier of the control as defined in the relevant
            control library YAML file.
        framework: Which framework this control belongs to.
        framework_version: The effective version string of the framework
            this status was computed against.
        status: One of ``"met"``, ``"not_met"``, ``"unknown"``, or
            ``"expired_attestation"`` — never a synonym for "recommended" or
            "planned", and never collapsed to a single "compliant" verdict
            elsewhere in this codebase.
        evidence_refs: asset_id / service_id / finding_id / attestation
            references that justify ``status``. May be empty when
            ``status`` is ``"unknown"`` — there being no evidence is
            exactly why it's unknown.
        confidence: Copied from the control library entry, so a status
            always carries its own epistemic caveat forward.
        verified_by_human: Copied from the control library entry.
    """

    control_id: str
    framework: str
    framework_version: str
    status: StatusValue
    evidence_refs: list[str]
    confidence: str
    verified_by_human: bool


def _get_nested(obj: dict[str, Any] | None, dotted_path: str) -> Any:
    node: Any = obj
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _matches_filter(value: Any, op: str, target: Any) -> bool:
    if value is None:
        return False
    if op == "eq":
        return bool(value == target)
    if op == "gt":
        return bool(value > target)
    raise ValueError(f"Unknown filter op {op!r}")


def _check_all_assets_field_true(
    snapshot: dict[str, Any], params: dict[str, Any]
) -> tuple[StatusValue, list[str]]:
    field_path = params["field_path"]
    only_where = params.get("only_where")

    applicable_ids: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []
    for asset in snapshot["assets"]:
        if only_where is not None:
            filter_value = _get_nested(asset, only_where["field_path"])
            if not _matches_filter(filter_value, only_where["op"], only_where["value"]):
                continue
        applicable_ids.append(asset["asset_id"])
        value = _get_nested(asset, field_path)
        if value is False:
            failing.append(asset["asset_id"])
        elif value is None:
            unknown.append(asset["asset_id"])

    if not applicable_ids:
        return "unknown", []
    if failing:
        return "not_met", failing
    if unknown:
        return "unknown", unknown
    return "met", applicable_ids


def _check_all_services_field_true(
    snapshot: dict[str, Any], params: dict[str, Any]
) -> tuple[StatusValue, list[str]]:
    field_path = params["field_path"]
    service_ids: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []
    for service in snapshot["services"]:
        service_ids.append(service["service_id"])
        value = _get_nested(service, field_path)
        if value is False:
            failing.append(service["service_id"])
        elif value is None:
            unknown.append(service["service_id"])

    if not service_ids:
        return "unknown", []
    if failing:
        return "not_met", failing
    if unknown:
        return "unknown", unknown
    return "met", service_ids


def _check_all_services_field_present(
    snapshot: dict[str, Any], params: dict[str, Any]
) -> tuple[StatusValue, list[str]]:
    field_path = params["field_path"]
    service_ids: list[str] = []
    missing: list[str] = []
    for service in snapshot["services"]:
        service_ids.append(service["service_id"])
        if _get_nested(service, field_path) is None:
            missing.append(service["service_id"])

    if not service_ids:
        return "unknown", []
    if missing:
        return "unknown", missing
    return "met", service_ids


def _check_all_edr_agents_healthy(
    snapshot: dict[str, Any], params: dict[str, Any]
) -> tuple[StatusValue, list[str]]:
    asset_ids: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []
    for asset in snapshot["assets"]:
        asset_ids.append(asset["asset_id"])
        installed = asset["edr"].get("agent_installed")
        healthy = asset["edr"].get("agent_healthy")
        if installed is False:
            failing.append(asset["asset_id"])
        elif installed is None:
            unknown.append(asset["asset_id"])
        elif healthy is False:
            failing.append(asset["asset_id"])
        elif healthy is None:
            unknown.append(asset["asset_id"])

    if not asset_ids:
        return "unknown", []
    if failing:
        return "not_met", failing
    if unknown:
        return "unknown", unknown
    return "met", asset_ids


def _finding_field(finding: dict[str, Any], key: str) -> Any:
    if key == "provenance_connector":
        return finding.get("provenance", {}).get("connector")
    if key == "criticality_in":
        return finding.get("criticality")
    return finding.get(key)


def _finding_matches(finding: dict[str, Any], match: dict[str, Any]) -> bool:
    for key, expected in match.items():
        actual = _finding_field(finding, key)
        if key == "criticality_in":
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _check_no_unremediated_findings(
    snapshot: dict[str, Any], params: dict[str, Any]
) -> tuple[StatusValue, list[str]]:
    match = params["match"]
    violating: list[str] = []
    ambiguous = False
    for asset in snapshot["assets"]:
        for finding in asset["findings"]:
            if any(_finding_field(finding, key) is None for key in match) and not _finding_matches(
                finding, match
            ):
                ambiguous = True
                continue
            if _finding_matches(finding, match) and finding.get("remediated_at") is None:
                violating.append(finding["finding_id"])

    if violating:
        return "not_met", violating
    if ambiguous:
        return "unknown", []
    return "met", []


def _check_no_dangerous_ports_on_internet_facing_assets(
    snapshot: dict[str, Any], params: dict[str, Any]
) -> tuple[StatusValue, list[str]]:
    applicable_ids: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []
    for asset in snapshot["assets"]:
        network = asset["network"]
        if network.get("internet_facing") is not True:
            continue
        applicable_ids.append(asset["asset_id"])
        open_ports = network.get("open_ports")
        if open_ports is None:
            unknown.append(asset["asset_id"])
            continue
        if set(open_ports) & set(DANGEROUS_INTERNET_FACING_PORTS):
            failing.append(asset["asset_id"])

    if not applicable_ids:
        return "unknown", []
    if failing:
        return "not_met", failing
    if unknown:
        return "unknown", unknown
    return "met", applicable_ids


def _check_backup_tested_within_days(
    snapshot: dict[str, Any], params: dict[str, Any], as_of: datetime
) -> tuple[StatusValue, list[str]]:
    days = params.get("days") or BACKUP_TEST_RECENCY_DAYS
    service_ids: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []
    for service in snapshot["services"]:
        service_ids.append(service["service_id"])
        backup = service["backup"]
        exists = backup.get("exists")
        if exists is False:
            failing.append(service["service_id"])
            continue
        if exists is None:
            unknown.append(service["service_id"])
            continue
        last_tested_at = backup.get("last_tested_at")
        if last_tested_at is None:
            unknown.append(service["service_id"])
            continue
        tested_dt = datetime.fromisoformat(last_tested_at)
        reference = as_of if as_of.tzinfo else as_of.replace(tzinfo=tested_dt.tzinfo)
        if (reference - tested_dt) > timedelta(days=days):
            failing.append(service["service_id"])

    if not service_ids:
        return "unknown", []
    if failing:
        return "not_met", failing
    if unknown:
        return "unknown", unknown
    return "met", service_ids


_CHECK_DISPATCH = {
    "all_assets_field_true": _check_all_assets_field_true,
    "all_services_field_true": _check_all_services_field_true,
    "all_services_field_present": _check_all_services_field_present,
    "all_edr_agents_healthy": _check_all_edr_agents_healthy,
    "no_unremediated_findings": _check_no_unremediated_findings,
    "no_dangerous_ports_on_internet_facing_assets": _check_no_dangerous_ports_on_internet_facing_assets,
}


def evaluate_telemetry_check(
    snapshot: dict[str, Any], control: ControlEntry, as_of: datetime
) -> tuple[StatusValue, list[str]]:
    """Run a single control's executable telemetry check against a snapshot.

    Args:
        snapshot: A validated, schema-shaped aggregated snapshot.
        control: The control whose ``telemetry_check`` to evaluate. Must
            have ``derivable_from_telemetry=True`` and a known
            ``check_type``.
        as_of: Current time, used only by time-window checks (e.g.
            ``backup_tested_within_days``).

    Returns:
        A ``(status, evidence_refs)`` tuple.

    Must never:
        Return ``"not_met"`` from a field that was never evaluated (null) —
        that must always resolve to ``"unknown"``, and only an explicit
        False/violating value may produce ``"not_met"``.
    """
    check = control.telemetry_check
    if check.check_type is None:
        raise ValueError(f"{control.id}: derivable_from_telemetry=true but check_type is None.")
    if check.check_type == "backup_tested_within_days":
        return _check_backup_tested_within_days(snapshot, check.check_params, as_of)
    return _CHECK_DISPATCH[check.check_type](snapshot, check.check_params)


def compute_control_status(
    snapshot: dict[str, Any],
    library: ControlLibrary,
    control: ControlEntry,
    attestations: list[Attestation],
    as_of: datetime,
) -> ControlStatus:
    """Derive a single control's status from telemetry and/or attestation evidence.

    Args:
        snapshot: A validated, schema-shaped aggregated snapshot.
        library: The control library ``control`` belongs to.
        control: The control to evaluate.
        attestations: All attestation records available (see
            ``governance.attestations.load_attestations``).
        as_of: Current time, for attestation-expiry and time-window checks.

    Returns:
        A :class:`ControlStatus` reflecting only the underlying evidence.

    Must never:
        Consider any output of ``core.optimizer`` as evidence toward a
        control's status — this function's inputs are a snapshot and
        attestations only. Must never return ``"met"`` for an expired
        attestation. See repo-root ``CLAUDE.md`` principle 6.
    """
    if control.telemetry_check.derivable_from_telemetry and control.telemetry_check.check_type:
        status, evidence = evaluate_telemetry_check(snapshot, control, as_of)
        return ControlStatus(
            control.id,
            library.framework,
            library.version,
            status,
            evidence,
            control.confidence,
            control.verified_by_human,
        )

    if control.manual_attestation_required:
        record = most_recent_attestation_even_if_expired(
            attestations, control.id, library.framework
        )
        if record is None:
            return ControlStatus(
                control.id,
                library.framework,
                library.version,
                "unknown",
                [],
                control.confidence,
                control.verified_by_human,
            )
        evidence_ref = f"attestation:{record.attested_at.isoformat()}"
        if is_expired(record, as_of):
            return ControlStatus(
                control.id,
                library.framework,
                library.version,
                "expired_attestation",
                [evidence_ref],
                control.confidence,
                control.verified_by_human,
            )
        status_map: dict[str, StatusValue] = {
            "met": "met",
            "not_met": "not_met",
            "insufficient_evidence": "unknown",
        }
        return ControlStatus(
            control.id,
            library.framework,
            library.version,
            status_map[record.status],
            [evidence_ref],
            control.confidence,
            control.verified_by_human,
        )

    return ControlStatus(
        control.id,
        library.framework,
        library.version,
        "unknown",
        [],
        control.confidence,
        control.verified_by_human,
    )


def compute_all_control_statuses(
    snapshot: dict[str, Any],
    library: ControlLibrary,
    attestations: list[Attestation],
    as_of: datetime,
) -> list[ControlStatus]:
    """Evaluate every control in a library against one snapshot.

    Args:
        snapshot: A validated, schema-shaped aggregated snapshot.
        library: The control library to evaluate.
        attestations: All attestation records available.
        as_of: Current time.

    Returns:
        One :class:`ControlStatus` per control in ``library.controls``, in
        the same order.
    """
    return [
        compute_control_status(snapshot, library, control, attestations, as_of)
        for control in library.controls
    ]


@dataclass(frozen=True)
class WeightedScoreResult:
    """A weighted composite score (e.g. SEBI's CCI) with honesty metadata.

    Attributes:
        framework: Which framework this score is for.
        score: Fraction (0-1) of ``total_weight`` whose controls are
            ``"met"``, or None if no control in the library has a weight at
            all (nothing to score).
        total_weight: Sum of ``weight`` across every control that has one.
        determined_weight: Sum of ``weight`` across controls whose status
            is ``"met"`` or ``"not_met"`` (i.e. actually determinable, not
            ``"unknown"``/``"expired_attestation"``).
        coverage_fraction: ``determined_weight / total_weight`` — what
            fraction of the total weight this score is actually able to
            speak to. None if ``total_weight`` is 0.
        low_confidence_weight_among_determined: Sum of ``weight`` among
            determined controls whose control-library ``confidence`` is
            ``"low"``.
        low_confidence_fraction_of_determined: ``
            low_confidence_weight_among_determined / determined_weight``,
            answering "of the part of this score I can actually speak to,
            how much rests on low-confidence regulatory data?". None if
            ``determined_weight`` is 0.
        controls_excluded_no_weight: control_ids with no weight, excluded
            from every computation above.
    """

    framework: str
    score: float | None
    total_weight: float
    determined_weight: float
    coverage_fraction: float | None
    low_confidence_weight_among_determined: float
    low_confidence_fraction_of_determined: float | None
    controls_excluded_no_weight: list[str]


def compute_weighted_score(
    library: ControlLibrary, statuses: list[ControlStatus]
) -> WeightedScoreResult:
    """Compute a weighted composite score, reporting coverage and confidence honestly.

    Args:
        library: The control library ``statuses`` were computed from.
        statuses: Output of :func:`compute_all_control_statuses` for the
            same library.

    Returns:
        A :class:`WeightedScoreResult`. Never a bare percentage — always
        paired with how much of that percentage is actually determinable
        and how much of the determinable part rests on low-confidence data.

    Must never:
        Report a score without ``coverage_fraction``, or silently include a
        control with no weight in the denominator.
    """
    status_by_id = {s.control_id: s for s in statuses}
    total_weight = 0.0
    determined_weight = 0.0
    met_weight = 0.0
    low_confidence_determined_weight = 0.0
    excluded: list[str] = []

    for control in library.controls:
        if control.weight is None:
            excluded.append(control.id)
            continue
        total_weight += control.weight
        status = status_by_id[control.id]
        if status.status in ("met", "not_met"):
            determined_weight += control.weight
            if control.confidence == "low":
                low_confidence_determined_weight += control.weight
            if status.status == "met":
                met_weight += control.weight

    return WeightedScoreResult(
        framework=library.framework,
        score=(met_weight / total_weight) if total_weight > 0 else None,
        total_weight=total_weight,
        determined_weight=determined_weight,
        coverage_fraction=(determined_weight / total_weight) if total_weight > 0 else None,
        low_confidence_weight_among_determined=low_confidence_determined_weight,
        low_confidence_fraction_of_determined=(
            low_confidence_determined_weight / determined_weight if determined_weight > 0 else None
        ),
        controls_excluded_no_weight=excluded,
    )
