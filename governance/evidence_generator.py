"""Generates human-readable compliance evidence packages from control status.

Consumes :class:`governance.mapper.ControlStatus` results and renders them
into a form suitable for an auditor or regulator — never generates a
compliance verdict of its own beyond what ``governance/mapper.py`` already
derived from evidence.
"""

from __future__ import annotations

from typing import Any

from governance.mapper import ControlStatus


def generate_evidence_package(
    control_statuses: list[ControlStatus], framework: str
) -> dict[str, Any]:
    """Assemble a full evidence package for a framework from control statuses.

    Args:
        control_statuses: All :class:`~governance.mapper.ControlStatus`
            results for the controls in scope, already computed from
            findings and attestations.
        framework: The framework this package is being generated for (must
            match the framework recorded on each status).

    Returns:
        A structured evidence package (control-by-control status, cited
        evidence references, and the framework version each status was
        computed against) suitable for export to an auditor-facing
        document.

    Must never:
        Add, remove, or reinterpret a control's status — this function
        only formats what :func:`governance.mapper.compute_control_status`
        already determined. Must never include or reference any
        ``core.optimizer`` output.
    """
    raise NotImplementedError


def render_evidence_package_to_markdown(evidence_package: dict[str, Any]) -> str:
    """Render an evidence package into an auditor-readable Markdown document.

    Args:
        evidence_package: Output of :func:`generate_evidence_package`.

    Returns:
        A Markdown document listing each control, its status, its evidence
        references, and the framework version it was evaluated against.

    Must never:
        Summarize or round a status into a broader claim (e.g. rendering
        several "insufficient_evidence" controls as an overall "mostly
        compliant" statement) — the reader must be able to see every
        control's actual status.
    """
    raise NotImplementedError
