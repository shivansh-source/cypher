"""Postgres access for accounts (organisations, users, tool selection).

Connects with ``DATABASE_URL`` (any Postgres, including Supabase's) through a
small connection pool: opening a connection to a remote database costs over a
second, so connections are reused rather than opened per request. Holds no
risk logic. Every query is parameterised, and every read or write of tools is
scoped by the ``org_id`` taken from the verified token, never from the request
body.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_SCHEMA_FILE = Path(__file__).parent / "sql" / "0001_accounts.sql"

#: Small on purpose: the account routes are low-traffic, and a hosted database's
#: pooler caps total connections.
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5
#: Seconds to wait for a free connection before failing the request.
POOL_CHECKOUT_TIMEOUT_SECONDS = 15.0
#: Idle connections are recycled after this long, before a remote pooler drops them.
POOL_MAX_IDLE_SECONDS = 240.0

_lock = threading.Lock()
_pools: dict[str, ConnectionPool[Any]] = {}
_schema_ready_for: str | None = None


class DatabaseNotConfiguredError(RuntimeError):
    """``DATABASE_URL`` is not set."""


class EmailTakenError(Exception):
    """An account with this email already exists."""


@dataclass(frozen=True)
class UserRecord:
    """A user joined with the organisation it belongs to (everything a token carries)."""

    id: str
    org_id: str
    email: str
    password_hash: str
    org_name: str
    entity_type: str | None
    onboarded: bool


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not set.")
    return url


def _pool(url: str) -> ConnectionPool[Any]:
    with _lock:
        pool = _pools.get(url)
        if pool is None:
            pool = ConnectionPool(
                url,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
                max_idle=POOL_MAX_IDLE_SECONDS,
                timeout=POOL_CHECKOUT_TIMEOUT_SECONDS,
                # prepare_threshold=None: safe behind PgBouncer / Supabase's transaction pooler.
                kwargs={"row_factory": dict_row, "prepare_threshold": None},
                # Validate on checkout so a connection the remote end dropped is replaced,
                # not handed to a request. Account routes are off the hot path, so the
                # extra round trip is affordable.
                check=ConnectionPool.check_connection,
                open=False,
            )
            pool.open(wait=True, timeout=POOL_CHECKOUT_TIMEOUT_SECONDS)
            _pools[url] = pool
        return pool


@contextmanager
def _connect() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """A pooled connection: commits on success, rolls back on error, then returns to the pool."""
    global _schema_ready_for
    url = _database_url()
    with _pool(url).connection() as conn:
        if _schema_ready_for != url:
            with _lock:
                if _schema_ready_for != url:
                    conn.execute(_SCHEMA_FILE.read_text(encoding="utf-8").encode())
                    conn.commit()
                    _schema_ready_for = url
        yield conn


def reset_schema_cache() -> None:
    """Forget the applied schema and close every pool (tests that swap databases)."""
    global _schema_ready_for
    with _lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()
        _schema_ready_for = None


def create_account(org_name: str, email: str, password_hash: str) -> UserRecord:
    """Insert an organisation and its first user in one transaction.

    Raises:
        EmailTakenError: the email is already registered (nothing is written).
    """
    with _connect() as conn:
        try:
            org = conn.execute(
                "insert into organizations (name) values (%s) returning id", (org_name,)
            ).fetchone()
            assert org is not None
            user = conn.execute(
                "insert into users (org_id, email, password_hash) values (%s, %s, %s) returning id",
                (org["id"], email, password_hash),
            ).fetchone()
            assert user is not None
        except UniqueViolation as exc:
            raise EmailTakenError(email) from exc
        return UserRecord(
            str(user["id"]), str(org["id"]), email, password_hash, org_name, None, False
        )


def find_user(email: str) -> UserRecord | None:
    """The user registered under ``email`` (already lower-cased), if any."""
    with _connect() as conn:
        row = conn.execute(
            "select u.id, u.org_id, u.email, u.password_hash, "
            "o.name, o.entity_type, o.onboarded_at is not null as onboarded "
            "from users u join organizations o on o.id = u.org_id where u.email = %s",
            (email,),
        ).fetchone()
    if row is None:
        return None
    return UserRecord(
        str(row["id"]),
        str(row["org_id"]),
        row["email"],
        row["password_hash"],
        row["name"],
        row["entity_type"],
        row["onboarded"],
    )


def load_account(user_id: str) -> dict[str, Any] | None:
    """The signed-in user's email, organisation and tool selection (one round trip)."""
    with _connect() as conn:
        row = conn.execute(
            "select u.email, o.name, o.entity_type, o.onboarded_at is not null as onboarded, "
            "coalesce((select json_agg(json_build_object("
            "'tool_id', t.tool_id, 'is_custom', t.is_custom, "
            "'custom_name', t.custom_name, 'category', t.category) "
            "order by t.created_at, t.tool_id) from org_tools t where t.org_id = o.id), "
            "'[]'::json) as tools "
            "from users u join organizations o on o.id = u.org_id where u.id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "email": row["email"],
        "org": {
            "name": row["name"],
            "entity_type": row["entity_type"],
            "onboarded": row["onboarded"],
        },
        "tools": row["tools"],
    }


def save_setup(org_id: str, entity_type: str | None, tools: list[dict[str, Any]]) -> str:
    """Replace the org's tool selection and mark onboarding complete, atomically.

    Returns:
        The organisation's name (so the caller can reissue a session token).
    """
    with _connect() as conn:
        org = conn.execute(
            "update organizations set entity_type = %s, "
            "onboarded_at = coalesce(onboarded_at, now()) where id = %s returning name",
            (entity_type, org_id),
        ).fetchone()
        assert org is not None
        conn.execute("delete from org_tools where org_id = %s", (org_id,))
        if tools:
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into org_tools (org_id, tool_id, is_custom, custom_name, category) "
                    "values (%s, %s, %s, %s, %s)",
                    [
                        (org_id, t["tool_id"], t["is_custom"], t["custom_name"], t["category"])
                        for t in tools
                    ],
                )
    return str(org["name"])
