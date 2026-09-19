"""`riskctl` — command-line interface for Su₹aksha.

Every command here is a thin adapter over ``core/``, ``governance/``, and
``ai/`` — no command may contain risk-computation, compliance-mapping, or
LLM logic of its own.
"""

from __future__ import annotations

from typing import Any


def validate_snapshot_command(candidate_path: str) -> None:
    """CLI command: validate a candidate snapshot file against the 5 quality gates.

    Args:
        candidate_path: Path to a candidate aggregated-snapshot JSON file.

    Must never:
        Commit the candidate itself — this command only reports gate
        results, matching ``.claude/commands/validate-snapshot.md``.
    """
    raise NotImplementedError


def run_engine_command(snapshot_path: str) -> None:
    """CLI command: run the engine against a committed snapshot file and print the risk figure.

    Args:
        snapshot_path: Path to a committed aggregated-snapshot JSON file.
    """
    raise NotImplementedError


def optimize_command(budget_inr: float, snapshot_path: str) -> None:
    """CLI command: run the optimizer against a committed snapshot and print the recommendation.

    Args:
        budget_inr: Total budget available, in INR.
        snapshot_path: Path to a committed aggregated-snapshot JSON file.
    """
    raise NotImplementedError


def framework_status_command(framework: str) -> None:
    """CLI command: print control-by-control status against a named regulatory framework.

    Args:
        framework: Framework key matching a filename under
            ``governance/control_library/``.
    """
    raise NotImplementedError


def build_cli() -> Any:
    """Construct the Typer application with all commands registered.

    Returns:
        A configured Typer app instance.
    """
    raise NotImplementedError
