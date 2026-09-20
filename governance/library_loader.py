"""Loads, parses, and validates control library YAML files.

A control library file (``governance/control_library/*.yaml``) is the only
place regulatory/framework facts live in this codebase. This module turns
one into a typed :class:`ControlLibrary`, and enforces the invariants that
keep a stale or unverifiable library from silently being treated as
current, authoritative data:

- A framework whose ``effective_to`` has already passed is rejected outright
  (the RBI-2016 guard — see repo-root ``CLAUDE.md`` principle 8).
- Every ``telemetry_check`` field path referenced by an executable
  ``check_type`` must resolve against
  ``schema/aggregated_assets.schema.json`` — a control that claims to read a
  field the schema doesn't have is a bug in the control library, not a
  runtime surprise for ``governance/mapper.py``.
- A control marked ``verified_by_human: true`` with no ``source`` is
  rejected — nothing can be "verified" against nothing.
- Loading a library with any ``confidence: low`` entry, or any entry not yet
  ``verified_by_human``, emits a loud warning (never a silent pass) — see
  :func:`collect_confidence_warnings` and repo-root ``CLAUDE.md``.

This module never fetches anything over the network. All regulatory
research happens before a YAML file is written, not at load time.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

VALID_CONFIDENCE_LEVELS = ("high", "medium", "low")

# check_type values governance.mapper actually knows how to execute. A
# telemetry_check with derivable_from_telemetry=true and a check_type
# outside this set is a control-library authoring bug, not a runtime
# surprise.
KNOWN_CHECK_TYPES = (
    "all_assets_field_true",
    "all_services_field_true",
    "all_services_field_present",
    "all_edr_agents_healthy",
    "no_unremediated_findings",
    "backup_tested_within_days",
    "no_dangerous_ports_on_internet_facing_assets",
)

# Attribute names governance.mapper's no_unremediated_findings check
# understands in its `match` parameter. Anything else in `match` is an
# authoring bug in the control library YAML.
KNOWN_FINDING_MATCH_KEYS = (
    "type",
    "kev_listed",
    "criticality",
    "criticality_in",
    "cve_id",
    "provenance_connector",
)


@dataclass(frozen=True)
class SourceCitation:
    """One entry in a control library file's top-level bibliography.

    Attributes:
        url_or_citation: The URL, or a named document/section, this
            citation points to.
        retrieved: The date this session actually retrieved/read the source.
        covers: What part of the file this citation supports.
    """

    url_or_citation: str
    retrieved: date
    covers: str


@dataclass(frozen=True)
class TelemetryCheck:
    """How (or whether) a control can be evaluated from real telemetry.

    Attributes:
        derivable_from_telemetry: Whether this control has a real,
            executable telemetry check at all. False means the control is
            attestation-only (or a documented schema gap) — see
            ``manual_attestation_required``.
        source_field: Human-readable schema path(s) this check reads, for
            documentation only. Not executed — see ``check_type``.
        logic: Human-readable description of the rule. Not executed — see
            ``check_type``.
        check_type: Name of the executable check in ``governance.mapper``,
            or None if not derivable.
        check_params: Parameters for ``check_type``, shape depends on which
            check it names — see ``governance.mapper``'s check functions.
    """

    derivable_from_telemetry: bool
    source_field: str | None
    logic: str | None
    check_type: str | None
    check_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlEntry:
    """One control/parameter within a control library.

    Attributes:
        id: Stable snake_case identifier, unique within this framework.
        framework_ref: The framework's own clause/safeguard/subcategory
            reference (e.g. "A.8.5", "PR.AA-03", "6.5"), or a note that none
            was found.
        parameter_name: Short human-readable title.
        weight: Numeric weight this control contributes to a weighted
            composite score (e.g. SEBI's CCI), or None if this framework
            doesn't weight controls or the weight wasn't found.
        description: One or two sentences describing the control, in this
            project's own words — never verbatim copyrighted standard text.
        maturity_bands: Per-control maturity tiers, if the framework defines
            them at that granularity; usually None (see the framework-level
            comments in e.g. sebi_cscrf_cci.yaml for composite-score bands).
        source: Citation for this specific entry's value(s).
        confidence: ``"high"``, ``"medium"``, or ``"low"`` — see
            ``VALID_CONFIDENCE_LEVELS``.
        verified_by_human: Always False until a human reviews this entry
            against its source and flips it — never set True programmatically.
        telemetry_check: See :class:`TelemetryCheck`.
        manual_attestation_required: Whether this control needs a manual
            attestation (see ``governance/attestations.py``) to ever reach a
            "met"/"not_met" status.
        attestation_prompt: What to ask a human to provide as evidence, or
            None if not attestation-based.
        attestation_validity_months: Override for how long an attestation on
            this control stays current, or None to use
            ``core.assumptions.DEFAULT_ATTESTATION_VALIDITY_MONTHS``.
    """

    id: str
    framework_ref: str
    parameter_name: str
    weight: float | None
    description: str
    maturity_bands: list[dict[str, Any]] | None
    source: str
    confidence: str
    verified_by_human: bool
    telemetry_check: TelemetryCheck
    manual_attestation_required: bool
    attestation_prompt: str | None
    attestation_validity_months: int | None


@dataclass(frozen=True)
class ControlLibrary:
    """A fully parsed, versioned, effective-dated control library file.

    Attributes:
        framework: Stable framework key, matches the filename stem.
        version: The framework's own version/circular/notification string.
        effective_from: When this version took effect, or None if that
            date could not be sourced this session (see the file's own
            sourcing notes for why).
        effective_to: When this version was/will be superseded, or None if
            current.
        supersedes: The framework+version key this replaces, or None.
        sources: The file's top-level bibliography.
        controls: Every control entry in the file.
    """

    framework: str
    version: str
    effective_from: date | None
    effective_to: date | None
    supersedes: str | None
    sources: list[SourceCitation]
    controls: list[ControlEntry]


@dataclass(frozen=True)
class LoadWarning:
    """A single loud, non-fatal warning surfaced when loading a library.

    Attributes:
        control_id: Which control this warning is about.
        framework: Which framework the control belongs to.
        reason: Why this was flagged (e.g. "confidence=low").
    """

    control_id: str
    framework: str
    reason: str


def _parse_telemetry_check(raw: dict[str, Any]) -> TelemetryCheck:
    check_type = raw.get("check_type")
    if raw.get("derivable_from_telemetry") and check_type is not None:
        if check_type not in KNOWN_CHECK_TYPES:
            raise ValueError(
                f"Unknown telemetry_check.check_type {check_type!r} — "
                f"must be one of {KNOWN_CHECK_TYPES} or null."
            )
        if check_type == "no_unremediated_findings":
            match = raw.get("check_params", {}).get("match", {})
            bad_keys = set(match) - set(KNOWN_FINDING_MATCH_KEYS)
            if bad_keys:
                raise ValueError(
                    f"no_unremediated_findings match has unknown key(s) {bad_keys} — "
                    f"must be a subset of {KNOWN_FINDING_MATCH_KEYS}."
                )
    return TelemetryCheck(
        derivable_from_telemetry=bool(raw.get("derivable_from_telemetry", False)),
        source_field=raw.get("source_field"),
        logic=raw.get("logic"),
        check_type=check_type,
        check_params=raw.get("check_params") or {},
    )


def _parse_control_entry(raw: dict[str, Any], framework: str) -> ControlEntry:
    confidence = raw["confidence"]
    if confidence not in VALID_CONFIDENCE_LEVELS:
        raise ValueError(
            f"{framework}/{raw.get('id')}: confidence must be one of "
            f"{VALID_CONFIDENCE_LEVELS}, got {confidence!r}."
        )

    verified_by_human = bool(raw.get("verified_by_human", False))
    source = raw.get("source")
    if verified_by_human and not source:
        raise ValueError(
            f"{framework}/{raw.get('id')}: verified_by_human=true but no source is "
            "recorded — nothing can be verified against nothing."
        )

    return ControlEntry(
        id=raw["id"],
        framework_ref=raw["framework_ref"],
        parameter_name=raw["parameter_name"],
        weight=raw.get("weight"),
        description=raw["description"],
        maturity_bands=raw.get("maturity_bands"),
        source=source or "",
        confidence=confidence,
        verified_by_human=verified_by_human,
        telemetry_check=_parse_telemetry_check(raw["telemetry_check"]),
        manual_attestation_required=bool(raw.get("manual_attestation_required", False)),
        attestation_prompt=raw.get("attestation_prompt"),
        attestation_validity_months=raw.get("attestation_validity_months"),
    )


def load_control_library(path: Path, as_of: date) -> ControlLibrary:
    """Load and validate one control library YAML file.

    Args:
        path: Path to a file under ``governance/control_library/``.
        as_of: The date to evaluate ``effective_to`` against. Explicit
            rather than ``date.today()`` so this function is deterministic
            and testable.

    Returns:
        The parsed :class:`ControlLibrary`.

    Raises:
        ValueError: If ``effective_to`` is on or before ``as_of`` (the
            framework has lapsed and must not be treated as current — the
            RBI-2016 guard), if any entry has an invalid ``confidence``, if
            any ``verified_by_human: true`` entry lacks a ``source``, or if
            a ``telemetry_check`` names an unknown ``check_type`` or
            references an unknown finding-match key.

    Must never:
        Silently fall back to a previously-repealed or expired framework
        version if the requested file's ``effective_to`` has passed — that
        must be a loud error, not a quiet default. See repo-root
        ``CLAUDE.md`` principle 8.
    """
    raw = yaml.safe_load(path.read_text())

    effective_to = raw.get("effective_to")
    if effective_to is not None:
        effective_to = date.fromisoformat(effective_to)
        if effective_to <= as_of:
            raise ValueError(
                f"{raw['framework']}: effective_to={effective_to} is on or before "
                f"as_of={as_of} — this framework version has lapsed and must not "
                "be loaded as current."
            )

    sources = [
        SourceCitation(
            url_or_citation=s["url_or_citation"],
            retrieved=date.fromisoformat(s["retrieved"]),
            covers=s["covers"],
        )
        for s in raw.get("sources", [])
    ]
    controls = [_parse_control_entry(c, raw["framework"]) for c in raw.get("controls", [])]

    raw_effective_from = raw.get("effective_from")
    return ControlLibrary(
        framework=raw["framework"],
        version=raw["version"],
        effective_from=date.fromisoformat(raw_effective_from) if raw_effective_from else None,
        effective_to=effective_to,
        supersedes=raw.get("supersedes"),
        sources=sources,
        controls=controls,
    )


def load_all_control_libraries(directory: Path, as_of: date) -> dict[str, ControlLibrary]:
    """Load every control library YAML file in a directory.

    Args:
        directory: Path to ``governance/control_library/``.
        as_of: See :func:`load_control_library`.

    Returns:
        A dict of framework key -> :class:`ControlLibrary`, for every
        ``*.yaml`` file in ``directory`` that loads successfully.

    Raises:
        ValueError: Propagated from :func:`load_control_library` for any
            file that fails to load — one bad file must not silently
            exclude itself from the result.
    """
    libraries: dict[str, ControlLibrary] = {}
    for yaml_path in sorted(directory.glob("*.yaml")):
        library = load_control_library(yaml_path, as_of)
        libraries[library.framework] = library
    return libraries


def _resolve_relative_path(item_schema: dict[str, Any], dotted_path: str) -> bool:
    """Check that a dotted path (relative to one array item) resolves."""
    node = item_schema
    for part in dotted_path.split("."):
        props = node.get("properties", {})
        if part not in props:
            return False
        node = props[part]
    return True


def validate_source_fields(library: ControlLibrary, schema: dict[str, Any]) -> list[str]:
    """Check every executable telemetry check's field path(s) against the schema.

    Args:
        library: A loaded :class:`ControlLibrary`.
        schema: The parsed contents of
            ``schema/aggregated_assets.schema.json``.

    Returns:
        A list of human-readable error messages, one per control whose
        ``check_params`` references a field path that doesn't resolve
        against ``schema``. Empty if every reference resolves.

    Must never:
        Validate the free-text ``telemetry_check.source_field``/``logic``
        strings — those are documentation only. What actually runs is
        ``check_type``/``check_params``, and that is what must be checked
        against the real schema.
    """
    asset_item_schema = schema["properties"]["assets"]["items"]
    service_item_schema = schema["properties"]["services"]["items"]

    errors: list[str] = []
    for control in library.controls:
        check = control.telemetry_check
        if not check.derivable_from_telemetry or check.check_type is None:
            continue

        params = check.check_params
        field_paths: list[tuple[str, dict[str, Any]]] = []
        if check.check_type in ("all_assets_field_true",):
            field_paths.append((params.get("field_path", ""), asset_item_schema))
            only_where = params.get("only_where")
            if only_where:
                field_paths.append((only_where.get("field_path", ""), asset_item_schema))
        elif check.check_type in ("all_services_field_true", "all_services_field_present"):
            field_paths.append((params.get("field_path", ""), service_item_schema))

        for dotted_path, item_schema in field_paths:
            if not dotted_path or not _resolve_relative_path(item_schema, dotted_path):
                errors.append(
                    f"{library.framework}/{control.id}: field path {dotted_path!r} "
                    "does not resolve against schema/aggregated_assets.schema.json"
                )
    return errors


def collect_confidence_warnings(library: ControlLibrary) -> list[LoadWarning]:
    """Collect one warning per control that isn't yet settled evidence.

    Args:
        library: A loaded :class:`ControlLibrary`.

    Returns:
        A :class:`LoadWarning` for every control with ``confidence: low``
        and every control not yet ``verified_by_human`` (which, as of any
        research-only session, is every control) — both conditions are
        reported, since "unverified" and "low confidence" are different
        risks a caller should be able to distinguish.
    """
    warnings_out: list[LoadWarning] = []
    for control in library.controls:
        if control.confidence == "low":
            warnings_out.append(LoadWarning(control.id, library.framework, "confidence=low"))
        if not control.verified_by_human:
            warnings_out.append(
                LoadWarning(control.id, library.framework, "not yet verified_by_human")
            )
    return warnings_out


def emit_loud_confidence_warning(library: ControlLibrary) -> None:
    """Emit a single, loud Python warning summarizing a library's confidence state.

    Args:
        library: A loaded :class:`ControlLibrary`.

    Must never:
        Be skipped for a library that loaded successfully — a library
        loading without error must never be mistaken for a library whose
        content is settled/verified. See repo-root ``CLAUDE.md``: no
        magic-number-style unearned confidence anywhere in this codebase.
    """
    load_warnings = collect_confidence_warnings(library)
    low_confidence = sum(1 for w in load_warnings if w.reason == "confidence=low")
    unverified = sum(1 for w in load_warnings if w.reason == "not yet verified_by_human")
    total = len(library.controls)
    warnings.warn(
        f"governance control library '{library.framework}': {unverified}/{total} "
        f"controls are not yet verified_by_human, {low_confidence}/{total} are "
        "confidence=low. Treat every figure derived from this library as "
        "provisional until a human review flips verified_by_human.",
        stacklevel=2,
    )
