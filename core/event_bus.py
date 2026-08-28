"""Filtered in-process event bus (AG-0.1).

A small, dependency-free pub/sub used to decouple the agent runtime from its
observers: the Web backend, trace writer, usage accounting, and tests all
subscribe to the same event stream instead of reaching into the loop.

Each event is a dict carrying at least a '"type"' key. Optional
'"session_id"' and '"stream_id"' keys allow multi-session isolation.

Indexes:

- _by_session: session_id -> set of subscription ids (None = all).
- _by_type: event type -> set of subscription ids (None = all).

Listener exceptions are caught per listener and never interrupt dispatch, so
one broken observer cannot break the loop or hide events from other observers.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Subscription:
    """Handle returned by EventBus.subscribe.

    Pass it to EventBus.unsubscribe to stop receiving events.
    """

    id: int
    callback: Callable[[dict], None]
    session_id: str | None
    event_types: frozenset[str] | None


class EventBus:
    """Thread-safe filtered event bus."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: dict[int, Subscription] = {}
        self._by_session: dict[str | None, set[int]] = {}
        self._by_type: dict[str | None, set[int]] = {}
        self._next_id = 1

    def subscribe(
        self,
        callback: Callable[[dict], None],
        session_id: str | None = None,
        event_types: Iterable[str] | None = None,
    ) -> Subscription:
        """Register callback for matching events.

        session_id=None matches every session (no session filter).
        event_types=None matches every event type; otherwise only the
        listed types are delivered.
        """
        types: frozenset[str] | None = (
            frozenset(event_types) if event_types is not None else None
        )
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            sub = Subscription(
                id=sub_id,
                callback=callback,
                session_id=session_id,
                event_types=types,
            )
            self._subscriptions[sub_id] = sub
            self._by_session.setdefault(session_id, set()).add(sub_id)
            if types is None:
                self._by_type.setdefault(None, set()).add(sub_id)
            else:
                for event_type in types:
                    self._by_type.setdefault(event_type, set()).add(sub_id)
            return sub

    def unsubscribe(self, subscription: Subscription) -> bool:
        """Remove a subscription. Returns True if it was registered."""
        with self._lock:
            sub = self._subscriptions.pop(subscription.id, None)
            if sub is None:
                return False
            self._remove_from_indexes(sub)
            return True

    def unsubscribe_all(self, session_id: str | None = None) -> int:
        """Remove every subscription (optionally restricted to a session).

        Returns the number of subscriptions removed. Useful for cleanup when
        a session ends or a client disconnects.
        """
        with self._lock:
            if session_id is None:
                ids = list(self._subscriptions.keys())
            else:
                ids = list(self._by_session.get(session_id, ()))
            removed = 0
            for sub_id in ids:
                if sub_id in self._subscriptions:
                    removed += 1
                    self._remove_from_indexes(self._subscriptions[sub_id])
            return removed

    def _remove_from_indexes(self, sub: Subscription) -> None:
        self._subscriptions.pop(sub.id, None)
        session_bucket = self._by_session.get(sub.session_id)
        if session_bucket is not None:
            session_bucket.discard(sub.id)
            if not session_bucket:
                del self._by_session[sub.session_id]
        if sub.event_types is None:
            type_bucket = self._by_type.get(None)
            if type_bucket is not None:
                type_bucket.discard(sub.id)
                if not type_bucket:
                    del self._by_type[None]
        else:
            for event_type in sub.event_types:
                type_bucket = self._by_type.get(event_type)
                if type_bucket is not None:
                    type_bucket.discard(sub.id)
                    if not type_bucket:
                        del self._by_type[event_type]

    def _matching_ids(self, event: dict) -> set[int]:
        event_type = event.get("type")
        session_id = event.get("session_id")
        by_type = self._by_type.get(event_type, set()) | self._by_type.get(None, set())
        by_session = self._by_session.get(session_id, set()) | self._by_session.get(None, set())
        return by_type & by_session

    def publish(self, event: dict) -> None:
        """Deliver event to every matching listener.

        Listener exceptions are caught and logged; they never propagate and
        never prevent other listeners from receiving the event.
        """
        with self._lock:
            subs = [self._subscriptions[i] for i in self._matching_ids(event)]
        for sub in subs:
            try:
                sub.callback(event)
            except Exception:  # noqa: BLE001 - observer failures must not break the bus
                logger.exception(
                    "EventBus listener %r failed for event %r", sub.id, event.get("type")
                )

    def listener_count(
        self, session_id: str | None = None, event_type: str | None = None
    ) -> int:
        """Count currently registered listeners (optionally filtered)."""
        with self._lock:
            if session_id is None and event_type is None:
                return len(self._subscriptions)
            ids: set[int] = set()
            if session_id is not None:
                ids = self._by_session.get(session_id, set()).copy()
            if event_type is not None:
                type_ids = self._by_type.get(event_type, set())
                ids = ids & type_ids if ids else type_ids.copy()
            return len(ids)


_default_bus = EventBus()


def get_default_bus() -> EventBus:
    """Return the process-wide event bus used by the runtime and Web layer."""
    return _default_bus

