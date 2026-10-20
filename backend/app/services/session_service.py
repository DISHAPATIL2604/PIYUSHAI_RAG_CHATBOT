"""SessionStore interface + in-memory implementation.

To persist sessions later (e.g. with Google login + chat history), implement SessionStore on top of
SQLite/Postgres keyed by (user_id, session_id) and pass it to the Container. Chat code only uses this interface.
"""
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class SessionStore(ABC):
    @abstractmethod
    def append(self, session_id: str, role: str, content: str, answer_mode: str | None = None, **kwargs) -> None: ...

    @abstractmethod
    def history(self, session_id: str) -> list[dict] | None:
        """All messages in order, or None if the session does not exist."""

    @abstractmethod
    def recent(self, session_id: str, turns: int) -> list[dict]: ...

    @abstractmethod
    def delete(self, session_id: str) -> bool: ...


class InMemorySessionStore(SessionStore):
    def __init__(self, max_messages: int = 200, max_sessions: int = 1000, ttl_seconds: int = 6 * 3600, clock=time.time):
        self.max_messages, self.max_sessions, self.ttl, self._clock = max_messages, max_sessions, ttl_seconds, clock
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        now = self._clock()
        for sid in [s for s, v in self._data.items() if now - v["touched"] > self.ttl]:
            del self._data[sid]
        while len(self._data) > self.max_sessions:
            del self._data[min(self._data, key=lambda s: self._data[s]["touched"])]

    def append(self, session_id, role, content, answer_mode=None, **kwargs):
        with self._lock:
            self._evict()
            s = self._data.setdefault(session_id, {"messages": [], "touched": self._clock()})
            msg = {
                "role": role,
                "content": content,
                "answer_mode": answer_mode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            msg.update(kwargs)
            s["messages"].append(msg)
            del s["messages"][: -self.max_messages]
            s["touched"] = self._clock()
            self._evict()

    def history(self, session_id):
        with self._lock:
            self._evict()
            s = self._data.get(session_id)
            return [dict(m) for m in s["messages"]] if s else None

    def recent(self, session_id, turns):
        with self._lock:
            s = self._data.get(session_id)
            return [dict(m) for m in s["messages"][-turns * 2:]] if s and turns > 0 else []

    def delete(self, session_id):
        with self._lock:
            return self._data.pop(session_id, None) is not None
