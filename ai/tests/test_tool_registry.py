"""Tests for ai/tool_registry.py.

The behaviour that matters here is what happens when a tool cannot answer:
an unimplemented wrapper must surface as an explicit "unavailable", never
as an empty result the model could narrate as a figure.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from ai import tool_registry
from ai.tool_registry import (
    anthropic_tool_definitions,
    available_frameworks,
    execute_tool,
    tool_names,
    tool_specs,
)


def test_every_declared_tool_has_a_schema_and_a_handler() -> None:
    for name, spec in tool_specs().items():
        assert spec.name == name
        assert spec.description.strip()
        assert spec.input_schema["type"] == "object"
        assert callable(spec.handler)
        assert spec.unavailable_hint.strip()


def test_tool_definitions_match_the_modules_under_ai_tools() -> None:
    """The registry is the single list of tools; nothing may be declared twice."""
    definitions = anthropic_tool_definitions()
    assert [definition["name"] for definition in definitions] == tool_names()
    assert len({definition["name"] for definition in definitions}) == len(definitions)


def test_framework_tool_enumerates_the_real_control_library() -> None:
    """get_framework_status offers only frameworks that exist on disk."""
    schema = tool_specs()["get_framework_status"].input_schema
    assert schema["properties"]["framework"]["enum"] == available_frameworks()
    assert "rbi_2026_directions" in available_frameworks()


def test_unimplemented_tool_reports_unavailable_not_a_figure() -> None:
    """A wrapper that raises NotImplementedError must never look like a result."""
    execution = execute_tool("get_exposure", {})
    assert execution.status == "unavailable"
    assert execution.result is None
    assert execution.ground_truth == {}
    assert execution.detail
    assert execution.is_error


def test_unavailable_result_tells_the_model_not_to_fill_the_gap() -> None:
    content = execute_tool("get_exposure", {}).to_model_content()
    assert '"retry": false' in content
    assert "Do not estimate" in content


def test_unknown_tool_is_an_error_naming_the_real_tools() -> None:
    execution = execute_tool("get_the_answer", {})
    assert execution.status == "error"
    assert "get_exposure" in (execution.detail or "")


def test_missing_required_argument_is_rejected_before_the_handler_runs() -> None:
    execution = execute_tool("get_framework_status", {})
    assert execution.status == "error"
    assert "framework" in (execution.detail or "")


def test_unknown_arguments_are_dropped_rather_than_passed_through() -> None:
    """The model's arguments are untrusted; an extra key must not become a TypeError."""
    execution = execute_tool("get_exposure", {"scope": "svc-1", "made_up": 1})
    assert execution.arguments == {"scope": "svc-1"}


def test_successful_tool_output_becomes_ground_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every number a real tool returns is available to the numeric guard."""

    def fake_exposure(**_: Any) -> dict[str, Any]:
        return {"snapshot_id": "snap-1", "expected_annual_loss_inr": 4_200_000.0}

    spec = tool_specs()["get_exposure"]
    monkeypatch.setitem(
        tool_registry.tool_specs(), "get_exposure", replace(spec, handler=fake_exposure)
    )
    execution = execute_tool("get_exposure", {})
    assert execution.status == "ok"
    assert 4_200_000.0 in execution.ground_truth.values()


def test_handler_exception_is_reported_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_: Any) -> dict[str, Any]:
        raise RuntimeError("snapshot store unreachable")

    spec = tool_specs()["get_exposure"]
    monkeypatch.setitem(tool_registry.tool_specs(), "get_exposure", replace(spec, handler=boom))
    execution = execute_tool("get_exposure", {})
    assert execution.status == "error"
    assert "snapshot store unreachable" in (execution.detail or "")
