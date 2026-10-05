"""A shared demo sign-in, so anyone evaluating the dashboard can look around without registering.

Configured by ``DEMO_ACCOUNT_EMAIL`` and ``DEMO_ACCOUNT_PASSWORD`` (both, or it is off). When
on, the API makes sure that account exists at start-up, already onboarded, and publishes the
credentials at the public ``GET /auth/demo`` so the sign-in and register pages can show them.
The password is public by design: never configure it for an account holding anything real.

It signs in to the same data every account sees (the snapshot store is not yet per
organisation), so it reveals nothing a self-registered account could not already see.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from fastapi import FastAPI, HTTPException

from interfaces.api import accounts_store as store
from interfaces.api.auth import MIN_PASSWORD_LENGTH, check_password, hash_password, issue_token

_DEFAULT_ORG_NAME = "Demo Lender (sample data)"
#: Entity type and tools the demo organisation is onboarded with: an NBFC (RBI Directions
#: apply) running tools the repo has connectors for. Declared setup choices, not telemetry.
_DEMO_ENTITY_TYPE = "nbfc"
_DEMO_TOOLS = ("greenbone", "prowler", "wazuh", "aws-iam", "nmap", "cmdb")

_logger = logging.getLogger(__name__)


def demo_credentials() -> tuple[str, str] | None:
    """``(email, password)`` from the environment, or None when the demo account is off."""
    email = os.environ.get("DEMO_ACCOUNT_EMAIL", "").strip().lower()
    password = os.environ.get("DEMO_ACCOUNT_PASSWORD", "")
    if not email or len(password) < MIN_PASSWORD_LENGTH:
        return None
    return email, password


def _default_tools() -> list[dict[str, Any]]:
    return [
        {"tool_id": tool, "is_custom": False, "custom_name": None, "category": None}
        for tool in _DEMO_TOOLS
    ]


def ensure_demo_account() -> bool:
    """Create the demo account (onboarded) if missing; reset its password if it changed.

    Returns:
        Whether a demo account is configured and now exists.
    """
    credentials = demo_credentials()
    if credentials is None:
        return False
    email, password = credentials
    user = store.find_user(email)
    if user is None:
        org_name = os.environ.get("DEMO_ACCOUNT_ORG", "").strip() or _DEFAULT_ORG_NAME
        try:
            user = store.create_account(org_name, email, hash_password(password))
        except store.EmailTakenError:  # another API process created it first
            return True
        store.save_setup(user.org_id, _DEMO_ENTITY_TYPE, _default_tools())
        _logger.info("created demo account %s", email)
    elif not check_password(user.password_hash, password):
        store.set_password_hash(user.id, hash_password(password))
        _logger.info("reset demo account password for %s", email)
    return True


def start_demo_seeding() -> None:
    """Run :func:`ensure_demo_account` in the background (a remote database can take seconds)."""
    if demo_credentials() is None:
        return

    def run() -> None:
        try:
            ensure_demo_account()
        except Exception as exc:  # noqa: BLE001 - a database outage must not stop the API
            _logger.warning("could not seed the demo account: %s", exc)

    threading.Thread(target=run, name="demo-account-seed", daemon=True).start()


def register_demo_routes(app: FastAPI) -> None:
    """Attach the public ``GET /auth/demo`` route."""

    @app.get("/auth/demo")
    def demo() -> dict[str, Any]:
        credentials = demo_credentials()
        if credentials is None:
            raise HTTPException(status_code=404, detail="No demo account is configured.")
        email, password = credentials
        return {"email": email, "password": password}

    @app.post("/auth/demo/login")
    def demo_login() -> dict[str, Any]:
        """Sign in as the demo account, with its default entity type and tools restored."""
        credentials = demo_credentials()
        if credentials is None:
            raise HTTPException(status_code=404, detail="No demo account is configured.")
        try:
            ensure_demo_account()
            user = store.find_user(credentials[0])
            if user is None:
                raise HTTPException(
                    status_code=503, detail="The demo account could not be created."
                )
            org_name = store.save_setup(user.org_id, _DEMO_ENTITY_TYPE, _default_tools())
        except HTTPException:
            raise
        except Exception as exc:  # database down / misconfigured
            raise HTTPException(
                status_code=503, detail="The account database is unavailable."
            ) from exc
        return {"token": issue_token(user.id, user.org_id, org_name, _DEMO_ENTITY_TYPE, True)}
