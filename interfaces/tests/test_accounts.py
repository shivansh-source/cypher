"""Register / login / setup flow against a real, throwaway Postgres (pgserver)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pgserver = pytest.importorskip("pgserver")

from interfaces.api import accounts_store
from interfaces.api.app import create_app

SECRET = "test-secret-at-least-32-bytes-long-000000"


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_app() would refill the env vars these tests remove from the developer's real .env."""
    monkeypatch.setattr("interfaces.api.app.load_dotenv", lambda *a, **k: None)


PASSWORD = "Correct-Horse-9"


@pytest.fixture(scope="module")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    yield str(server.get_uri())
    server.cleanup()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, database_url: str, tmp_path: Path) -> TestClient:
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    accounts_store.reset_schema_cache()
    return TestClient(create_app())


def _register(client: TestClient, email: str, org: str = "LoanEase Finance") -> dict[str, Any]:
    response = client.post(
        "/auth/register", json={"org_name": org, "email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_setup_flow(client: TestClient) -> None:
    token = _register(client, "Ops@LoanEase.in")["token"]  # email is normalised to lower case

    import jwt as _jwt

    first = _jwt.decode(token, SECRET, algorithms=["HS256"], audience="suraksha")
    assert (first["onb"], first["etype"], first["org_name"]) == (False, None, "LoanEase Finance")

    me = client.get("/auth/me", headers=_auth(token)).json()
    assert me["email"] == "ops@loanease.in"
    assert me["org"] == {"name": "LoanEase Finance", "entity_type": None, "onboarded": False}
    assert me["tools"] == []

    saved = client.post(
        "/org/setup",
        headers=_auth(token),
        json={
            "entity_type": "nbfc",
            "tools": [
                {"id": "greenbone"},
                {"id": "custom:abc", "name": "Acme Scanner", "category": "Vulnerability scanning"},
                {"id": "greenbone"},  # duplicate ignored
            ],
        },
    )
    assert saved.json()["ok"] is True
    # The reissued token carries the new routing facts, so the dashboard needs no lookup.
    import jwt as _jwt

    fresh = _jwt.decode(saved.json()["token"], SECRET, algorithms=["HS256"], audience="suraksha")
    assert (fresh["onb"], fresh["etype"], fresh["org_name"]) == (True, "nbfc", "LoanEase Finance")

    me = client.get("/auth/me", headers=_auth(token)).json()
    assert me["org"]["onboarded"] is True and me["org"]["entity_type"] == "nbfc"
    assert {t["tool_id"] for t in me["tools"]} == {"greenbone", "custom:abc"}

    login = client.post("/auth/login", json={"email": "OPS@loanease.in", "password": PASSWORD})
    assert login.status_code == 200 and login.json()["token"]


def test_duplicate_email_conflicts_and_writes_nothing(client: TestClient) -> None:
    _register(client, "dup@example.in", org="First Org")
    again = client.post(
        "/auth/register",
        json={"org_name": "Second Org", "email": "dup@example.in", "password": PASSWORD},
    )
    assert again.status_code == 409
    with accounts_store._connect() as conn:
        row = conn.execute(
            "select count(*) as n from organizations where name = 'Second Org'"
        ).fetchone()
    assert row is not None and row["n"] == 0  # the org insert rolled back with the failed user


def test_login_failures_are_indistinguishable(client: TestClient) -> None:
    _register(client, "real@example.in")
    wrong = client.post(
        "/auth/login", json={"email": "real@example.in", "password": "nope-nope-nope"}
    )
    unknown = client.post("/auth/login", json={"email": "ghost@example.in", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"org_name": "", "email": "a@b.in", "password": PASSWORD},
        {"org_name": "X", "email": "not-an-email", "password": PASSWORD},
        {"org_name": "X", "email": "a@b.in", "password": "short"},
    ],
)
def test_register_validation(client: TestClient, payload: dict[str, str]) -> None:
    assert client.post("/auth/register", json=payload).status_code == 422


def test_setup_validation_and_isolation(client: TestClient) -> None:
    a = _register(client, "a@one.in", org="Org A")["token"]
    b = _register(client, "b@two.in", org="Org B")["token"]
    bad = client.post(
        "/org/setup",
        headers=_auth(a),
        json={"tools": [{"id": "custom:x", "name": "T", "category": "Bogus"}]},
    )
    assert bad.status_code == 422
    client.post("/org/setup", headers=_auth(a), json={"tools": [{"id": "wazuh"}]})
    assert client.get("/auth/me", headers=_auth(b)).json()["tools"] == []  # B never sees A's tools


def test_account_routes_need_a_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.post("/org/setup", json={"tools": []}).status_code == 401


def test_database_not_configured_is_503(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))
    response = TestClient(create_app()).post(
        "/auth/register", json={"org_name": "X", "email": "a@b.in", "password": PASSWORD}
    )
    assert response.status_code == 503
