"""A4 batch 3: the cancellation primitive (P0-1/P0-2/P0-3)."""

import threading
import time

import pytest

from core.cancellation import CancelToken, RunCancelled


def test_a_fresh_token_is_not_cancelled():
    token = CancelToken()
    assert token.is_cancelled() is False
    assert token.reason == ""
    token.raise_if_cancelled()  # must not raise


def test_cancel_is_idempotent_and_keeps_the_first_reason():
    token = CancelToken()
    token.cancel("client_disconnected")
    token.cancel("something_else")
    assert token.is_cancelled() is True
    assert token.reason == "client_disconnected"


def test_raise_carries_the_reason():
    token = CancelToken()
    token.cancel("tool_timeout")
    with pytest.raises(RunCancelled) as excinfo:
        token.raise_if_cancelled()
    assert excinfo.value.reason == "tool_timeout"


def test_parent_cancel_reaches_existing_children():
    """A specialist must stop when the turn it belongs to stops (P0-2)."""
    parent = CancelToken()
    child = parent.child()
    parent.cancel("client_disconnected")
    assert child.is_cancelled() is True
    assert child.reason == "client_disconnected"


def test_a_child_created_after_cancellation_starts_cancelled():
    parent = CancelToken()
    parent.cancel("stopped")
    assert parent.child().is_cancelled() is True


def test_a_child_can_be_cancelled_alone():
    parent = CancelToken()
    child = parent.child()
    child.cancel("tool_timeout")
    assert child.is_cancelled() is True
    assert parent.is_cancelled() is False


def test_another_thread_sees_the_cancellation():
    """The web cancels from the request thread while the agent runs in a worker."""
    token = CancelToken()
    observed: list[bool] = []

    def poll() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if token.is_cancelled():
                observed.append(True)
                return
            time.sleep(0.01)

    worker = threading.Thread(target=poll)
    worker.start()
    time.sleep(0.05)
    token.cancel("client_disconnected")
    worker.join(timeout=5)

    assert observed == [True]
