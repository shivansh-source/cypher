"""Maps findings and controls to entries in the regulatory control library.

This module answers "which controls, in which frameworks, does this
finding/asset touch, and what is their current status" — it never answers
"is this organization compliant" as a single verdict, and it never
considers optimizer recommendations as evidence of anything. See repo-root
``CLAUDE.md`` principle 6: compliance maps to findings and controls, never
to optimizer output.

Reads control definitions from ``governance/control_library/*.yaml``, each
of which is versioned and effective-dated (see repo-root ``CLAUDE.md``
principle 8 re: RBI's 2016 framework being repealed and replaced by
entity-specific Directions, 2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ControlStatus:
    """The evidence-derived status of a single control for a single asset/finding.

    Attributes:
        control_id: Identifier of the control as defined in the relevant
            control library YAML file.
        framework: Which framework this control belongs to (e.g.
            "rbi_2026_directions", "cis_controls").
        framework_version: The effective version/date of the framework
            entry used, so a status is never reported against a framework
            version that has since lapsed.
        status: One of a fixed vocabulary describing evidence state (e.g.
            "met", "not_met", "insufficient_evidence") — never a synonym
            for "recommended" or "planned".
        evidence_refs: References to the underlying findings/attestations
            that justify ``status`` — a status without evidence_refs is not
            trustworthy and should not be produced.
    """

    control_id: str
    framework: str
    framework_version: str
    status: str
    evidence_refs: list[str]


def load_control_library(framework: str) -> dict[str, Any]:
    """Load and parse a versioned, effective-dated control library file.

    Args:
        framework: Framework key matching a filename under
            ``governance/control_library/`` (e.g. "rbi_2026_directions").

    Returns:
        The parsed control library, including each control's effective
        date range.

    Must never:
        Silently fall back to a hardcoded or previously-repealed framework
        version (e.g. RBI's 2016 Cyber Security Framework) if the
        requested file or version is missing — that must be a loud error.
    """
    raise NotImplementedError


def map_finding_to_controls(finding: dict[str, Any], framework: str) -> list[str]:
    """Identify which controls in a framework a given finding is relevant to.

    Args:
        finding: A single schema-shaped finding from
            ``assets[].findings[]``.
        framework: Framework key matching a filename under
            ``governance/control_library/``.

    Returns:
        A list of control_ids from that framework's control library that
        this finding provides evidence for or against.

    Must never:
        Infer a mapping from finding type to control based on anything
        other than the explicit mapping data in the control library file —
        no implicit or hardcoded heuristic mappings.
    """
    raise NotImplementedError


def compute_control_status(
    control_id: str,
    framework: str,
    findings: list[dict[str, Any]],
    manual_attestations: dict[str, Any],
) -> ControlStatus:
    """Derive a control's status from findings and manual attestation evidence.

    Args:
        control_id: The control to evaluate.
        framework: Framework the control belongs to.
        findings: All schema-shaped findings currently relevant to this
            control (from :func:`map_finding_to_controls` across the
            current snapshot).
        manual_attestations: Parsed contents of
            ``governance/manual_attestation.json``, used for controls that
            cannot be evidenced by automated findings alone.

    Returns:
        A :class:`ControlStatus` reflecting only the underlying evidence.

    Must never:
        Consider any output of ``core.optimizer`` (a recommendation,
        selected portfolio, or projected risk reduction) as evidence
        toward a control's status. Compliance status reflects facts about
        the present state of controls and findings only. See repo-root
        ``CLAUDE.md`` principle 6.
    """
    raise NotImplementedError
