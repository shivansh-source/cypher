"""Account routes: register, sign in, who am I, and the tool-selection step.

``/auth/register`` and ``/auth/login`` are public (see ``auth.PUBLIC_PATH_PREFIXES``);
everything else here needs the session token. Nothing here touches the risk engine.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from interfaces.api import accounts_store as store
from interfaces.api.auth import MIN_PASSWORD_LENGTH, check_password, hash_password, issue_token

EntityType = Literal["bank", "nbfc", "sebi", "other"]

#: Mirrors ToolCategory in interfaces/dashboard/src/lib/tool-catalog.ts.
TOOL_CATEGORIES = frozenset(
    {
        "Vulnerability scanning",
        "Cloud security posture",
        "Endpoint detection & response",
        "Identity & access",
        "Network exposure",
        "Asset inventory",
    }
)
CUSTOM_PREFIX = "custom:"
MAX_TOOLS = 200
MAX_NAME = 120
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegisterRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=MAX_NAME)
    email: str = Field(max_length=254)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)

    @field_validator("org_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter your organisation's name.")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid work email.")
        return v


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ToolIn(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=MAX_NAME)
    category: str | None = None


class SetupRequest(BaseModel):
    entity_type: EntityType | None = None
    tools: list[ToolIn] = Field(default_factory=list, max_length=MAX_TOOLS)


def _db_unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, store.DatabaseNotConfiguredError):
        return HTTPException(
            status_code=503, detail="The account database is not configured (DATABASE_URL)."
        )
    return HTTPException(status_code=503, detail="The account database is unavailable.")


def _token_for(user: store.UserRecord) -> str:
    return issue_token(user.id, user.org_id, user.org_name, user.entity_type, user.onboarded)


def register_account_routes(app: FastAPI) -> None:
    """Attach the ``/auth/*`` and ``/org/setup`` routes to ``app``."""

    @app.post("/auth/register", status_code=201)
    def register(body: RegisterRequest) -> dict[str, Any]:
        try:
            user = store.create_account(body.org_name, body.email, hash_password(body.password))
        except store.EmailTakenError:
            raise HTTPException(
                status_code=409, detail="An account with this email already exists."
            ) from None
        except Exception as exc:  # database down / misconfigured
            raise _db_unavailable(exc) from exc
        return {"token": _token_for(user)}

    @app.post("/auth/login")
    def login(body: LoginRequest) -> dict[str, Any]:
        try:
            user = store.find_user(body.email.strip().lower())
        except Exception as exc:
            raise _db_unavailable(exc) from exc
        # One message for every failure: never reveal whether the account exists.
        if not check_password(user.password_hash if user else None, body.password) or user is None:
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        return {"token": _token_for(user)}

    @app.get("/auth/me")
    def me(request: Request) -> dict[str, Any]:
        claims: dict[str, Any] | None = getattr(request.state, "user", None)
        if claims is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        try:
            account = store.load_account(str(claims["sub"]))
        except Exception as exc:
            raise _db_unavailable(exc) from exc
        if account is None:
            raise HTTPException(status_code=401, detail="Account no longer exists.")
        return account

    @app.post("/org/setup")
    def setup(body: SetupRequest, request: Request) -> dict[str, Any]:
        claims: dict[str, Any] | None = getattr(request.state, "user", None)
        if claims is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        org_id = str(claims["org"])
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tool in body.tools:
            if tool.id in seen:
                continue
            seen.add(tool.id)
            custom = tool.id.startswith(CUSTOM_PREFIX)
            name = (tool.name or "").strip()
            if custom and (not name or tool.category not in TOOL_CATEGORIES):
                raise HTTPException(
                    status_code=422, detail="A custom tool needs a name and a valid category."
                )
            rows.append(
                {
                    "tool_id": tool.id,
                    "is_custom": custom,
                    "custom_name": name if custom else None,
                    "category": tool.category if custom else None,
                }
            )
        try:
            org_name = store.save_setup(org_id, body.entity_type, rows)
        except Exception as exc:
            raise _db_unavailable(exc) from exc
        # Reissue the token: it carries the org's entity type and onboarded flag.
        return {
            "ok": True,
            "token": issue_token(str(claims["sub"]), org_id, org_name, body.entity_type, True),
        }
