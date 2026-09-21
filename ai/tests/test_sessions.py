"""Tests for ai/sessions.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai.sessions import ChatSession, InMemorySessionStore


def test_create_returns_distinct_sessions() -> None:
    store = InMemorySessionStore()
    assert store.create().session_id != store.create().session_id


def test_get_or_create_continues_a_known_session() -> None:
    store = InMemorySessionStore()
    session = store.create()
    session.append({"role": "user", "content": "hello"})
    assert store.get_or_create(session.session_id) is session


def test_get_or_create_opens_a_new_session_for_an_unknown_id() -> None:
    """An unknown id must not be adopted — the client learns history was lost."""
    store = InMemorySessionStore()
    session = store.get_or_create("not-a-real-session")
    assert session.session_id != "not-a-real-session"
    assert session.messages == []


def test_expired_sessions_are_pruned() -> None:
    store = InMemorySessionStore(ttl_minutes=30)
    session = store.create()
    session.last_active_at = datetime.now(UTC) - timedelta(minutes=31)
    assert store.prune() == 1
    assert store.get(session.session_id) is None


def test_store_evicts_least_recently_active_beyond_the_cap() -> None:
    store = InMemorySessionStore(max_sessions=2)
    first = store.create()
    first.last_active_at = datetime.now(UTC) - timedelta(minutes=5)
    store.create()
    store.create()
    assert store.get(first.session_id) is None
    assert len(store.active_session_ids()) == 2


def test_delete_reports_whether_a_session_existed() -> None:
    store = InMemorySessionStore()
    session = store.create()
    assert store.delete(session.session_id) is True
    assert store.delete(session.session_id) is False


def test_recording_ground_truth_merges_across_turns() -> None:
    session = ChatSession(session_id="s1")
    session.record_ground_truth({"a": 1.0})
    session.record_ground_truth({"b": 2.0})
    assert session.ground_truth == {"a": 1.0, "b": 2.0}
