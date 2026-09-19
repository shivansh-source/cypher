"""Tests for governance/mapper.py.

The most important property to test is negative: control status must never
be influenced by anything from core.optimizer.
"""

from __future__ import annotations


def test_load_control_library_rejects_missing_framework_version() -> None:
    """load_control_library must error loudly rather than fall back to a stale or repealed framework version."""
    raise NotImplementedError


def test_map_finding_to_controls_uses_only_explicit_library_mappings() -> None:
    """map_finding_to_controls must not apply any mapping not explicitly present in the control library file."""
    raise NotImplementedError


def test_compute_control_status_ignores_optimizer_output() -> None:
    """compute_control_status must produce the same status regardless of any core.optimizer recommendation touching the same control."""
    raise NotImplementedError


def test_compute_control_status_requires_evidence_refs() -> None:
    """A ControlStatus must never be returned with an empty evidence_refs list."""
    raise NotImplementedError


def test_compute_control_status_uses_manual_attestation_when_present() -> None:
    """A control with no automated findings but a valid, unexpired manual attestation must reflect that attestation's status."""
    raise NotImplementedError


def test_compute_control_status_ignores_expired_attestation() -> None:
    """An expired manual attestation must not be treated as current evidence."""
    raise NotImplementedError
