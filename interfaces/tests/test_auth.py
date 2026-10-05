"""Tests for the bearer-token guard (interfaces/api/auth.py). No database needed."""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.api.auth import (
    check_password,
    hash_password,
    is_public_path,
    issue_token,
    verify_token,
)

SECRET = "test-secret-at-least-32-bytes-long-000000"


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_app() would refill the env vars these tests remove from the developer's real .env."""
    monkeypatch.setattr("interfaces.api.app.load_dotenv", lambda *a, **k: None)


def _token(secret: str = SECRET, *, exp_in: int = 3600, aud: str = "suraksha") -> str:
    claims: dict[str, Any] = {
        "sub": "u-1",
        "org": "o-1",
        "aud": aud,
        "exp": int(time.time()) + exp_in,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> TestClient:
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    return TestClient(create_app())


def test_health_is_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_data_route_requires_token(client: TestClient) -> None:
    assert client.get("/snapshot").status_code == 401
    assert client.get("/assets", headers={"Authorization": "Basic abc"}).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        _token("wrong-secret-wrong-secret-wrong-secret"),
        _token(exp_in=-10),
        _token(aud="anon"),
        "garbage",
    ],
)
def test_bad_tokens_rejected(client: TestClient, token: str) -> None:
    assert client.get("/snapshot", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_valid_token_passes_guard(client: TestClient) -> None:
    # Empty store => the route's own 404, which proves the guard let it through.
    assert (
        client.get("/snapshot", headers={"Authorization": f"Bearer {_token()}"}).status_code == 404
    )


def test_fails_closed_when_unconfigured(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    response = TestClient(create_app()).get(
        "/snapshot", headers={"Authorization": f"Bearer {_token()}"}
    )
    assert response.status_code == 503


def test_short_secret_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", "too-short")
    with pytest.raises(Exception, match="not configured"):
        issue_token("u", "o", "Org", None, False)


def test_auth_disabled_bypasses(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    assert TestClient(create_app()).get("/snapshot").status_code == 404


def test_issued_token_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    claims = verify_token(issue_token("u-9", "o-9", "Org Nine", "nbfc", True))
    assert (claims["sub"], claims["org"]) == ("u-9", "o-9")
    assert (claims["org_name"], claims["etype"], claims["onb"]) == ("Org Nine", "nbfc", True)


def test_password_hashing() -> None:
    stored = hash_password("correct horse battery")
    assert stored != "correct horse battery"
    assert check_password(stored, "correct horse battery")
    assert not check_password(stored, "wrong")
    assert not check_password(None, "anything")


def test_public_path_matching() -> None:
    for path in (
        "/health",
        "/health/snapshot-sync",
        "/snapshots/abc/download-url",
        "/auth/login",
        "/auth/register",
    ):
        assert is_public_path(path), path
    for path in ("/snapshot", "/auth/me", "/org/setup", "/healthz-not-real"):
        assert not is_public_path(path), path
