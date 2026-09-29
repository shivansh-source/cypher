"""Bearer-token auth for the API.

Accounts live in Postgres (``accounts_store``); passwords are argon2-hashed.
Login issues a signed, expiring HS256 token; every other route requires it.
This module reads no database and computes nothing about risk.

Configuration (environment):
    AUTH_JWT_SECRET  Signing secret for session tokens (>= 32 bytes). Server-side only.
    AUTH_DISABLED=1  Turns the check off for local development and tests.

Fail-closed: with no secret configured (and auth not explicitly disabled)
every protected route answers 503, never "let it through".
"""

from __future__ import annotations

import os
import time
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request

#: Routes that do not need a session token. ``/snapshots`` has its own shared-secret
#: header (see ``snapshot_links.py``); health probes must work for load balancers;
#: register and login are how a token is obtained.
PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/snapshots",
    "/auth/register",
    "/auth/login",
)

TOKEN_AUDIENCE = "suraksha"
TOKEN_LIFETIME_SECONDS = 7 * 24 * 3600
MIN_SECRET_BYTES = 32
MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()
#: Verified against when the email is unknown, so login time doesn't reveal which emails exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def auth_disabled() -> bool:
    """True when ``AUTH_DISABLED=1``: development and tests only."""
    return os.environ.get("AUTH_DISABLED") == "1"


def is_public_path(path: str) -> bool:
    """Whether ``path`` is exempt from the session-token check."""
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PATH_PREFIXES)


def hash_password(password: str) -> str:
    """Argon2id hash of ``password``."""
    return _hasher.hash(password)


def check_password(stored_hash: str | None, password: str) -> bool:
    """Constant-effort password check; ``None`` (unknown user) always fails."""
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def _secret() -> str:
    secret = os.environ.get("AUTH_JWT_SECRET", "")
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise HTTPException(
            status_code=503,
            detail=f"Authentication is not configured (AUTH_JWT_SECRET must be >= {MIN_SECRET_BYTES} bytes).",
        )
    return secret


def issue_token(user_id: str, org_id: str) -> str:
    """A signed session token for ``user_id`` in ``org_id``."""
    now = int(time.time())
    claims = {"sub": user_id, "org": org_id, "aud": TOKEN_AUDIENCE, "iat": now, "exp": now + TOKEN_LIFETIME_SECONDS}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def verify_token(token: str) -> dict[str, Any]:
    """Validate a session token and return its claims (401 if invalid or expired)."""
    secret = _secret()
    try:
        claims: dict[str, Any] = jwt.decode(
            token, secret, algorithms=["HS256"], audience=TOKEN_AUDIENCE
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
    if not claims.get("sub") or not claims.get("org"):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return claims


async def require_user(request: Request) -> None:
    """FastAPI dependency: reject requests without a valid session token.

    Registered app-wide in ``create_app`` so a route added later is protected by
    default; public paths and CORS preflights are skipped.
    """
    if auth_disabled() or request.method == "OPTIONS" or is_public_path(request.url.path):
        return
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Sign in required.")
    request.state.user = verify_token(token.strip())
