"""Postgres access for accounts (organisations, users, tool selection).

Connects with ``DATABASE_URL`` (any Postgres, including Supabase's). Holds no
risk logic. Every query is parameterised, and every read or write of tools is
scoped by the ``org_id`` taken from the verified token, never from the request
body.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

_SCHEMA_FILE = Path(__file__).parent / "sql" / "0001_accounts.sql"
_schema_lock = threading.Lock()
_schema_ready_for: str | None = None


class DatabaseNotConfiguredError(RuntimeError):
    """``DATABASE_URL`` is not set."""


class EmailTakenError(Exception):
    """An account with this email already exists."""


@dataclass(frozen=True)
class UserRecord:
    """A user row joined with the organisation it belongs to."""

    id: str
    org_id: str
    email: str
    password_hash: str


def _connect() -> psycopg.Connection[dict[str, Any]]:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not set.")
    # prepare_threshold=None: safe behind PgBouncer / Supabase's transaction pooler.
    conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
        url, row_factory=dict_row, prepare_threshold=None
    )
    _ensure_schema(conn, url)
    return conn


def _ensure_schema(conn: psycopg.Connection[dict[str, Any]], url: str) -> None:
    global _schema_ready_for
    if _schema_ready_for == url:
        return
    with _schema_lock:
        if _schema_ready_for != url:
            conn.execute(_SCHEMA_FILE.read_text(encoding="utf-8").encode())
            conn.commit()
            _schema_ready_for = url


def reset_schema_cache() -> None:
    """Forget that the schema was applied (tests that swap databases)."""
    global _schema_ready_for
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
        return UserRecord(str(user["id"]), str(org["id"]), email, password_hash)


def find_user(email: str) -> UserRecord | None:
    """The user registered under ``email`` (already lower-cased), if any."""
    with _connect() as conn:
        row = conn.execute(
            "select id, org_id, email, password_hash from users where email = %s", (email,)
        ).fetchone()
    if row is None:
        return None
    return UserRecord(str(row["id"]), str(row["org_id"]), row["email"], row["password_hash"])


def load_account(user_id: str) -> dict[str, Any] | None:
    """The signed-in user's email, organisation and tool selection."""
    with _connect() as conn:
        row = conn.execute(
            "select u.email, o.id as org_id, o.name, o.entity_type, o.onboarded_at "
            "from users u join organizations o on o.id = u.org_id where u.id = %s",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        tools = conn.execute(
            "select tool_id, is_custom, custom_name, category from org_tools "
            "where org_id = %s order by created_at, tool_id",
            (row["org_id"],),
        ).fetchall()
    return {
        "email": row["email"],
        "org": {
            "name": row["name"],
            "entity_type": row["entity_type"],
            "onboarded": row["onboarded_at"] is not None,
        },
        "tools": [
            {
                "tool_id": t["tool_id"],
                "is_custom": t["is_custom"],
                "custom_name": t["custom_name"],
                "category": t["category"],
            }
            for t in tools
        ],
    }


def save_setup(org_id: str, entity_type: str | None, tools: list[dict[str, Any]]) -> None:
    """Replace the org's tool selection and mark onboarding complete, atomically."""
    with _connect() as conn:
        conn.execute(
            "update organizations set entity_type = %s, onboarded_at = coalesce(onboarded_at, now()) "
            "where id = %s",
            (entity_type, org_id),
        )
        conn.execute("delete from org_tools where org_id = %s", (org_id,))
        for t in tools:
            conn.execute(
                "insert into org_tools (org_id, tool_id, is_custom, custom_name, category) "
                "values (%s, %s, %s, %s, %s)",
                (org_id, t["tool_id"], t["is_custom"], t["custom_name"], t["category"]),
            )
