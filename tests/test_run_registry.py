"""A4 batch 3 phase 3: the disconnect grace period (P0-1, decision 3)."""

import time

from web.backend.run_registry import RunRegistry


def test_a_disconnect_starts_a_grace_timer_that_cancels(tmp_path=None):
    """Closing the tab must stop the run - but only after the grace window."""
    registry = RunRegistry(grace_seconds=0.2)
    handle = registry.start("s1")

    registry.note_disconnect("s1")

    assert handle.token.is_cancelled() is False, "not instantly - a refresh must survive"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not handle.token.is_cancelled():
        time.sleep(0.02)

    assert handle.token.is_cancelled() is True
    assert handle.token.reason == "client_disconnected"


def test_reconnecting_inside_the_window_keeps_the_run_alive():
    """A refresh reconnects in seconds; the run must not be thrown away."""
    registry = RunRegistry(grace_seconds=0.3)
    handle = registry.start("s1")

    registry.note_disconnect("s1")
    registry.note_reconnect("s1")
    time.sleep(0.5)

    assert handle.token.is_cancelled() is False


def test_disconnect_is_idempotent():
    registry = RunRegistry(grace_seconds=5)
    handle = registry.start("s1")
    registry.note_disconnect("s1")
    first_timer = handle.timer
    registry.note_disconnect("s1")

    assert handle.timer is first_timer, "a second disconnect must not restart the clock"
    registry.finish("s1")


def test_finishing_clears_the_pending_timer():
    registry = RunRegistry(grace_seconds=0.2)
    handle = registry.start("s1")
    registry.note_disconnect("s1")

    registry.finish("s1")
    time.sleep(0.4)

    assert handle.token.is_cancelled() is False, "a finished run is not cancelled"
    assert registry.get("s1") is None


def test_every_run_gets_its_own_token():
    registry = RunRegistry()
    first = registry.start("s1")
    second = registry.start("s2")
    assert first.token is not second.token
    registry.cancel_now("s1", "user_stopped")
    assert first.token.is_cancelled() is True
    assert second.token.is_cancelled() is False
