"""FastAPI application entry point.

Every route here is a thin adapter over ``core/``, ``governance/``, and
``ai/`` — no route may contain risk-computation, compliance-mapping, or LLM
logic of its own. Any route that returns LLM-generated narration must pass
it through ``ai.numeric_guard.guard_narration`` before responding.
"""

from __future__ import annotations

from typing import Any


def create_app() -> Any:
    """Construct and configure the FastAPI application.

    Returns:
        A configured FastAPI app instance with all routes registered.

    Must never:
        Register a route that computes a risk figure inline instead of
        calling into ``core.engine``, or that returns LLM narration
        without first passing it through ``ai.numeric_guard``.
    """
    raise NotImplementedError


def get_exposure_route() -> Any:
    """HTTP route handler wrapping ``ai.tools.get_exposure.get_exposure``.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.
    """
    raise NotImplementedError


def optimize_investment_route() -> Any:
    """HTTP route handler wrapping ``ai.tools.optimize_investment.optimize_investment``.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.
    """
    raise NotImplementedError


def chat_route() -> Any:
    """HTTP route handler for natural-language chat, wiring together
    ``ai.intent_classifier``, the relevant ``ai.tools`` module, and
    ``ai.numeric_guard`` before returning a response.

    Returns:
        A route handler function/coroutine suitable for FastAPI
        registration.

    Must never:
        Return LLM-generated text to the client without first passing it
        through ``ai.numeric_guard.guard_narration``.
    """
    raise NotImplementedError
