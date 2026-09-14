"""Cooperative cancellation (A4 batch 3, audit P0-1/P0-2/P0-3).

There was no cancellation primitive anywhere in production code: the client
aborted its fetch, and the server kept burning tokens. The design (see
docs/CANCELLATION_DESIGN.md) is cooperative cancellation rather than an asyncio
rewrite or subprocess isolation: the only places that can actually be
interrupted are a streaming read loop (break out and the response closes) and
the boundaries between iterations and tools.

Honest limits, stated once here so nobody over-claims later: Python cannot kill
a thread. Cancelling means "stop waiting, and tell it to stop at its next
checkpoint" - a non-streaming request finishes on its own timeout, and a tool
that ignores the token runs to completion.
"""

from __future__ import annotations

import threading


class RunCancelled(Exception):
    """Raised at a cooperative checkpoint; deliberately not a ProviderError.

    Cancellation is not a failure: it must not trigger a retry and must not be
    counted as an error.
    """

    def __init__(self, reason: str = "") -> None:
        super().__init__(reason or "cancelled")
        self.reason = reason or "cancelled"


class CancelToken:
    """A cancellable scope, with parent-to-child propagation. Thread safe."""

    def __init__(self, parent: "CancelToken | None" = None) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason = ""
        self._parent = parent
        self._children: list["CancelToken"] = []
        if parent is not None:
            parent._register(self)

    def _register(self, child: "CancelToken") -> None:
        with self._lock:
            if self._event.is_set():
                child.cancel(self._reason)
                return
            self._children.append(child)

    def cancel(self, reason: str = "") -> None:
        """Cancel this scope and everything under it. Idempotent."""
        with self._lock:
            if not self._reason:
                self._reason = reason
            if self._event.is_set():
                return
            self._event.set()
            children = list(self._children)
        for child in children:
            child.cancel(self._reason)

    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        return self._parent is not None and self._parent.is_cancelled()

    @property
    def reason(self) -> str:
        if self._reason:
            return self._reason
        if self._parent is not None:
            return self._parent.reason
        return ""

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise RunCancelled(self.reason)

    def child(self) -> "CancelToken":
        """A scope that follows this one but can also be cancelled alone."""
        return CancelToken(parent=self)
