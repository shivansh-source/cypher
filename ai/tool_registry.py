"""The catalogue of ``ai/tools/`` wrappers, as the LLM sees and calls them.

One place declares, for every module in ``ai/tools/``: the JSON schema the
model fills in, and the callable that schema dispatches to. ``ai/chat.py``
and ``ai/intent_classifier.py`` both read this registry, so a tool is added
to the assistant by adding one :class:`ToolSpec` here — never by teaching
the chat loop about a specific tool.

Execution is fail-explicit. Most of ``ai/tools/`` is still signatures and
docstrings (``core/`` is unimplemented), so a call into one raises
``NotImplementedError``. That is reported to the model as a structured
"unavailable" result naming what would make it available — never as an
empty result, a zero, or anything the model could narrate as a figure. See
repo-root ``CLAUDE.md`` principles 1 and 2.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ai.numeric_guard import collect_ground_truth
from ai.tools.explain_number import explain_number
from ai.tools.get_control_posture import get_control_posture
from ai.tools.get_exposure import get_exposure
from ai.tools.get_framework_status import get_framework_status
from ai.tools.get_top_contributors import get_top_contributors
from ai.tools.optimize_investment import optimize_investment
from ai.tools.simulate_scenario import simulate_scenario

#: Where the versioned, effective-dated control libraries live. Used to
#: enumerate the framework keys ``get_framework_status`` will accept, so
#: the model is never free to invent a framework name.
CONTROL_LIBRARY_DIR = Path(__file__).resolve().parent.parent / "governance" / "control_library"

ToolStatus = Literal["ok", "unavailable", "error"]


@dataclass(frozen=True)
class ToolSpec:
    """One ``ai/tools/`` module, as declared to the LLM.

    Attributes:
        name: Tool name as the model calls it — matches the module name
            under ``ai/tools/``.
        description: What the tool returns and, critically, what it does
            not do. Shown to the model verbatim.
        input_schema: JSON Schema for the tool's arguments, mirroring the
            wrapped function's signature.
        handler: The ``ai.tools`` callable this dispatches to.
        unavailable_hint: What a user would have to do to make this tool
            answer, surfaced when the handler is not yet implemented.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    unavailable_hint: str


@dataclass(frozen=True)
class ToolExecution:
    """The outcome of one tool call, in a shape both the model and the API can read.

    Attributes:
        tool_name: Which tool ran.
        arguments: The arguments it ran with, after validation.
        status: ``"ok"`` when the tool returned data, ``"unavailable"``
            when the underlying computation does not exist yet,
            ``"error"`` when it existed and failed.
        result: The tool's structured output, or None unless
            ``status == "ok"``.
        detail: Human-readable explanation, always present for
            ``"unavailable"`` and ``"error"``.
        ground_truth: Every number in ``result``, flattened for
            ``ai.numeric_guard``. Empty unless ``status == "ok"`` — a tool
            that did not compute anything contributes no number a
            narration is entitled to use.
    """

    tool_name: str
    arguments: dict[str, Any]
    status: ToolStatus
    result: dict[str, Any] | None = None
    detail: str | None = None
    ground_truth: dict[str, float] = field(default_factory=dict)

    def to_model_content(self) -> str:
        """Render this execution as the ``tool_result`` content the model reads.

        Returns:
            A compact JSON object. For a non-``ok`` status it carries
            ``retry: false`` and the reason, so the model relays the gap
            instead of re-calling the tool or filling it in itself.
        """
        payload: dict[str, Any]
        if self.status == "ok":
            payload = {"status": "ok", "result": self.result}
        else:
            payload = {
                "status": self.status,
                "detail": self.detail,
                "retry": False,
                "instruction": (
                    "Tell the user plainly that this figure has not been computed "
                    "and why. Do not estimate, approximate or substitute a number."
                ),
            }
        return json.dumps(payload, default=str)

    @property
    def is_error(self) -> bool:
        """Whether the provider should mark this ``tool_result`` as an error."""
        return self.status != "ok"


def available_frameworks() -> list[str]:
    """List the framework keys ``get_framework_status`` accepts.

    Returns:
        One key per ``*.yaml`` file in
        ``governance/control_library/``, sorted. Empty if the directory is
        missing — the schema then omits the enum rather than inventing one.
    """
    if not CONTROL_LIBRARY_DIR.is_dir():
        return []
    return sorted(path.stem for path in CONTROL_LIBRARY_DIR.glob("*.yaml"))


def _framework_schema() -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "string",
        "description": "Framework key matching a control library file.",
    }
    frameworks = available_frameworks()
    if frameworks:
        schema["enum"] = frameworks
    return schema


def _build_specs() -> dict[str, ToolSpec]:
    """Declare every tool. Called once, lazily, by :func:`tool_specs`."""
    engine_hint = (
        "The FAIR + Monte Carlo engine in core/ is not implemented yet, and no "
        "snapshot has been committed, so no rupee figure exists to report."
    )
    specs = [
        ToolSpec(
            name="get_exposure",
            description=(
                "Return the current Expected Annual Loss and Value at Risk for the "
                "estate, or for one service or asset, as computed by the "
                "deterministic engine against the current committed snapshot. "
                "Returns the snapshot_id the figure came from. This tool does not "
                "compute or estimate anything itself."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": (
                            "Optional service_id or asset_id to restrict the figure "
                            "to. Omit for the whole estate."
                        ),
                    }
                },
                "required": [],
            },
            handler=get_exposure,
            unavailable_hint=engine_hint,
        ),
        ToolSpec(
            name="get_top_contributors",
            description=(
                "Return the loss-event scenarios that drive Expected Annual Loss, "
                "ranked largest first, with the snapshot_id they were computed "
                "from. Use this whenever you report an EAL — a bottom-line number "
                "without its drivers cannot be defended."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "How many contributors to return, largest first.",
                    }
                },
                "required": [],
            },
            handler=get_top_contributors,
            unavailable_hint=engine_hint,
        ),
        ToolSpec(
            name="get_control_posture",
            description=(
                "Return control posture recorded in the current snapshot — EDR "
                "agent state, identity/access posture, network exposure, backup "
                "posture — for one asset or summarized across the estate. Fields "
                "the snapshot does not record come back null, meaning unknown, "
                "never a guess."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": (
                            "Optional single asset to scope to. Omit to summarize "
                            "across the whole snapshot."
                        ),
                    }
                },
                "required": [],
            },
            handler=get_control_posture,
            unavailable_hint=(
                "No snapshot store exists yet, so there is no committed snapshot to "
                "read posture from."
            ),
        ),
        ToolSpec(
            name="get_framework_status",
            description=(
                "Return control-by-control status against one regulatory framework, "
                "plus that framework's version and effective_from date. Each "
                "control carries its own status (met / not_met / unknown / "
                "expired_attestation), its evidence references and its confidence. "
                "There is deliberately no overall compliant/non-compliant verdict — "
                "do not derive one."
            ),
            input_schema={
                "type": "object",
                "properties": {"framework": _framework_schema()},
                "required": ["framework"],
            },
            handler=get_framework_status,
            unavailable_hint=(
                "No snapshot store exists yet, so there is no committed snapshot to "
                "evaluate the control library against."
            ),
        ),
        ToolSpec(
            name="optimize_investment",
            description=(
                "Recommend which controls to fund within a budget, in INR. The "
                "reported risk reduction comes from re-simulating the selected "
                "portfolio as a whole, so it is smaller than the sum of the "
                "individual controls' benefits — never add control benefits "
                "together yourself."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "budget_inr": {
                        "type": "number",
                        "minimum": 0,
                        "description": "Total budget available, in INR.",
                    },
                    "candidate_control_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional restriction to specific candidate controls. "
                            "Omit to consider every control with cost/effect data."
                        ),
                    },
                },
                "required": ["budget_inr"],
            },
            handler=optimize_investment,
            unavailable_hint=(
                "The budget optimizer in core/ is not implemented yet, and it "
                "depends on the engine, which is also unimplemented."
            ),
        ),
        ToolSpec(
            name="simulate_scenario",
            description=(
                "Answer a 'what if we did X' question by applying hypothetical "
                "controls to the current snapshot and re-running the real "
                "simulation on the result, returning both the baseline and the "
                "post-hypothetical figures. Use this instead of reasoning about "
                "what a control might save."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "hypothetical_controls": {
                        "type": "array",
                        "description": "The controls to hypothetically apply together.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "control_id": {"type": "string"},
                                "control_category": {"type": "string"},
                                "estimated_cost_inr": {"type": "number"},
                                "affected_asset_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["control_id", "control_category"],
                        },
                    }
                },
                "required": ["hypothetical_controls"],
            },
            handler=simulate_scenario,
            unavailable_hint=(
                "Joint re-simulation needs both core.optimizer and core.engine, "
                "neither of which is implemented yet."
            ),
        ),
        ToolSpec(
            name="explain_number",
            description=(
                "Return the derivation trail behind a figure already shown in this "
                "conversation — the FAIR parameters, the named assumptions used "
                "with their justification text, and the snapshot data that fed it. "
                "Use this when the user asks where a number came from."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "figure_reference": {
                        "type": "string",
                        "description": (
                            "A scenario_id or control_id from a figure already "
                            "produced in this conversation."
                        ),
                    }
                },
                "required": ["figure_reference"],
            },
            handler=explain_number,
            unavailable_hint=(
                "No figure has been computed yet, so there is no derivation trail "
                "to explain."
            ),
        ),
    ]
    return {spec.name: spec for spec in specs}


_specs: dict[str, ToolSpec] | None = None


def tool_specs() -> dict[str, ToolSpec]:
    """Return every registered tool, keyed by name (built once per process)."""
    global _specs
    if _specs is None:
        _specs = _build_specs()
    return _specs


def tool_names() -> list[str]:
    """Return the names of every registered tool, in declaration order."""
    return list(tool_specs())


def anthropic_tool_definitions() -> list[dict[str, Any]]:
    """Render the registry as Messages API tool definitions.

    Returns:
        One definition per registered tool, in a stable order so the tool
        block stays byte-identical across requests and caches cleanly.
    """
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
        for spec in tool_specs().values()
    ]


def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop unknown keys and check required ones, before calling the handler.

    The model's arguments are untrusted input: an unexpected key would be a
    TypeError inside the wrapper, and a missing required key would be a
    silently wrong call.
    """
    properties: dict[str, Any] = spec.input_schema.get("properties", {})
    required: list[str] = spec.input_schema.get("required", [])
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    return {key: value for key, value in arguments.items() if key in properties}


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> ToolExecution:
    """Run one registered tool and report the outcome structurally.

    Args:
        tool_name: Name of a tool in this registry.
        arguments: Arguments the model supplied, validated here against the
            tool's declared schema before the handler is called.

    Returns:
        A :class:`ToolExecution`. ``NotImplementedError`` from a wrapper
        becomes ``status="unavailable"`` carrying the tool's
        ``unavailable_hint``; any other exception becomes
        ``status="error"``.

    Must never:
        Substitute a default, a zero, or a remembered previous value for a
        tool that did not return one — the caller (and ultimately the
        model) must see that nothing was computed. See repo-root
        ``CLAUDE.md`` principle 1.
    """
    spec = tool_specs().get(tool_name)
    if spec is None:
        return ToolExecution(
            tool_name=tool_name,
            arguments=arguments,
            status="error",
            detail=f"Unknown tool '{tool_name}'. Available: {', '.join(tool_names())}.",
        )
    try:
        validated = _validate_arguments(spec, arguments)
    except ValueError as exc:
        return ToolExecution(
            tool_name=tool_name, arguments=arguments, status="error", detail=str(exc)
        )
    try:
        result = spec.handler(**validated)
    except NotImplementedError:
        return ToolExecution(
            tool_name=tool_name,
            arguments=validated,
            status="unavailable",
            detail=spec.unavailable_hint,
        )
    except Exception as exc:  # noqa: BLE001 - reported structurally, never swallowed
        return ToolExecution(
            tool_name=tool_name,
            arguments=validated,
            status="error",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return ToolExecution(
        tool_name=tool_name,
        arguments=validated,
        status="ok",
        result=result,
        ground_truth=collect_ground_truth(result, prefix=tool_name),
    )
