"""In-memory conversation state for the chat assistant.

A session holds two things: the content-block history (so a follow-up
question has the context of the turn before it), and every number real
tools produced during the conversation. The second is what lets
``ai.numeric_guard`` verify a narration that refers back to a figure
computed several turns ago — without it, "so that ₹4.2 crore figure" in
turn three would be flagged as invented.

Sessions live in this process only. They are lost on restart and are not
shared between API workers; a deployment running more than one worker needs
a shared store behind this same interface. That is a deliberate scope
choice, not an oversight — nothing here is a durable record, and no rupee
figure is ever read back out of a session as if it were current.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

#: How long a session survives without activity. An hour comfortably spans
#: a working conversation while keeping abandoned sessions from
#: accumulating in a long-lived process.
DEFAULT_SESSION_TTL_MINUTES = 60

#: Ceiling on concurrently tracked sessions. When exceeded, the least
#: recently used sessions are evicted — this is a memory bound, not a
#: quota, and an evicted session simply starts fresh.
DEFAULT_MAX_SESSIONS = 200


@dataclass
class ChatSession:
    """One conversation's state.

    Attributes:
        session_id: Opaque identifier the client passes back to continue
            the conversation.
        messages: Conversation history — user turns, assistant turns
            (content blocks preserved verbatim, including tool_use blocks), and tool_result turns.
        ground_truth: Every number produced by a real tool call in this
            conversation, keyed by dotted field path, for
            ``ai.numeric_guard``.
        created_at: When the session was opened (UTC).
        last_active_at: When it last saw a turn (UTC).
    """

    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    ground_truth: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def append(self, message: dict[str, Any]) -> None:
        """Append one conversation turn and mark the session active."""
        self.messages.append(message)
        self.last_active_at = datetime.now(UTC)

    def record_ground_truth(self, values: dict[str, float]) -> None:
        """Merge numbers a real tool produced into this session's ground truth.

        Must never:
            Be given values the model itself produced — see
            ``ai.numeric_guard.collect_ground_truth``.
        """
        self.ground_truth.update(values)


class InMemorySessionStore:
    """Thread-safe, TTL-bounded store of :class:`ChatSession` objects.

    Args:
        ttl_minutes: Inactivity window after which a session is dropped.
        max_sessions: Ceiling on tracked sessions; the least recently
            active are evicted first.
    """

    def __init__(
        self,
        ttl_minutes: int = DEFAULT_SESSION_TTL_MINUTES,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
    ) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_sessions = max_sessions
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def create(self) -> ChatSession:
        """Open a new session with a fresh identifier."""
        session = ChatSession(session_id=uuid.uuid4().hex)
        with self._lock:
            self._sessions[session.session_id] = session
            self._evict_locked()
        return session

    def get(self, session_id: str) -> ChatSession | None:
        """Return a live session, or None if it is unknown or expired."""
        with self._lock:
            self._prune_locked(datetime.now(UTC))
            return self._sessions.get(session_id)

    def get_or_create(self, session_id: str | None) -> ChatSession:
        """Return the named session, or open a new one.

        An unknown or expired ``session_id`` yields a *new* session rather
        than an error: the caller's own identifier is not reused, so a
        client always learns from the response's ``session_id`` that its
        history did not survive.
        """
        if session_id:
            existing = self.get(session_id)
            if existing is not None:
                return existing
        return self.create()

    def delete(self, session_id: str) -> bool:
        """Drop a session. Returns whether one was actually removed."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def prune(self, now: datetime | None = None) -> int:
        """Drop every expired session. Returns how many were dropped."""
        with self._lock:
            return self._prune_locked(now or datetime.now(UTC))

    def active_session_ids(self) -> Sequence[str]:
        """Return the identifiers of every currently tracked session."""
        with self._lock:
            return list(self._sessions)

    def _prune_locked(self, now: datetime) -> int:
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_active_at > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def _evict_locked(self) -> None:
        while len(self._sessions) > self._max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.last_active_at)
            del self._sessions[oldest.session_id]
