"""A4 batch 3 / P0-1: run production must not depend on an SSE reader."""

from __future__ import annotations

import time

from core.event_log import EventLog
from web.backend.run_pump import (
    RunPump,
    get_live_pump,
    live_stream_ids,
    register_pump,
    unregister_pump,
)
from web.backend.run_registry import RunRegistry
from web.backend.sse import StreamStore, encode_sse


def _store(tmp_path):
    return StreamStore(log=EventLog(str(tmp_path)))


def _producer(store, stream_id, count, *, delay=0.0, error_after=None):
    """A stand-in for the event_stream() generator create_run builds."""
    def gen():
        for index in range(count):
            if error_after is not None and index == error_after:
                raise RuntimeError("producer exploded")
            data = {"index": index}
            seq = store.append(stream_id, "message_delta", data)
            yield encode_sse("message_delta", {**data, "seq": seq, "stream_id": stream_id})
            time.sleep(delay)
    return gen()


def test_the_pump_keeps_producing_after_every_reader_leaves(tmp_path):
    """The reproduction for P0-1.

    Before the pump the producer only ran while a reader pulled on it: a
    dropped client left the turn parked at its last yield, and the events it
    never emitted were simply lost.
    """
    store = _store(tmp_path)
    stream_id = "stream-decoupled"
    registry = RunRegistry(grace_seconds=30.0)
    handle = registry.start(stream_id)
    pump = register_pump(
        RunPump(stream_id, _producer(store, stream_id, 4), store=store, registry=registry)
    ).start()

    tail = pump.tail(0)
    first = next(tail)
    assert "message_delta" in first
    tail.close()  # the client is gone

    assert pump.join(5.0), "the pump must finish without any reader"
    frames = store.replay(stream_id, 0)
    assert [frame["data"]["index"] for frame in frames] == [0, 1, 2, 3]
    assert not handle.token.is_cancelled()
    assert get_live_pump(stream_id) is None


def test_a_tail_returns_only_after_the_log_is_drained(tmp_path):
    store = _store(tmp_path)
    stream_id = "stream-drain"
    registry = RunRegistry()
    pump = RunPump(
        stream_id, _producer(store, stream_id, 3), store=store, registry=registry
    ).start()

    frames = list(pump.tail(0))
    assert len(frames) == 3
    assert frames[0].startswith("event: message_delta")
    assert pump.finished


def test_a_tail_resumes_from_a_cursor(tmp_path):
    store = _store(tmp_path)
    stream_id = "stream-cursor"
    registry = RunRegistry()
    pump = RunPump(
        stream_id, _producer(store, stream_id, 3), store=store, registry=registry
    ).start()

    resumed = list(pump.tail(1))
    assert len(resumed) == 2
    assert '"index": 1' in resumed[0]
    assert "stream_id" in resumed[0]


def test_a_dead_producer_still_ends_the_tail(tmp_path):
    store = _store(tmp_path)
    stream_id = "stream-dead"
    registry = RunRegistry()
    registry.start(stream_id)
    pump = RunPump(
        stream_id,
        _producer(store, stream_id, 3, error_after=2),
        store=store,
        registry=registry,
    ).start()

    frames = list(pump.tail(0))
    assert len(frames) == 2, "frames emitted before the failure must survive"
    assert isinstance(pump.error, RuntimeError)
    assert registry.get(stream_id) is None, "a dead run must not leak a handle"
    assert get_live_pump(stream_id) is None


def test_a_reconnect_inside_the_grace_window_keeps_the_run_alive(tmp_path):
    store = _store(tmp_path)
    stream_id = "stream-grace"
    registry = RunRegistry(grace_seconds=0.4)
    handle = registry.start(stream_id)
    pump = register_pump(
        RunPump(
            stream_id,
            _producer(store, stream_id, 12, delay=0.05),
            store=store,
            registry=registry,
        )
    ).start()

    registry.note_disconnect(stream_id)
    time.sleep(0.1)
    registry.note_reconnect(stream_id)
    time.sleep(0.5)  # past the original deadline

    assert not handle.token.is_cancelled()
    assert pump.join(5.0)
    assert pump.error is None
    assert len(store.replay(stream_id, 0)) == 12


def test_an_expired_grace_window_cancels_a_run_that_is_still_producing(tmp_path):
    store = _store(tmp_path)
    stream_id = "stream-expire"
    registry = RunRegistry(grace_seconds=0.15)
    handle = registry.start(stream_id)
    register_pump(
        RunPump(
            stream_id,
            _producer(store, stream_id, 40, delay=0.05),
            store=store,
            registry=registry,
        )
    ).start()

    registry.note_disconnect(stream_id)
    assert handle.token.is_cancelled() is False
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not handle.token.is_cancelled():
        time.sleep(0.02)
    assert handle.token.is_cancelled(), "the grace timer must reach the token"
    assert handle.token.reason == "client_disconnected"


def test_live_stream_ids_lists_only_producing_pumps(tmp_path):
    """The retention sweep needs to know which streams it must not touch."""
    store = _store(tmp_path)
    registry = RunRegistry()
    slow = register_pump(
        RunPump(
            "stream-slow",
            _producer(store, "stream-slow", 6, delay=0.05),
            store=store,
            registry=registry,
        )
    ).start()
    done = register_pump(
        RunPump(
            "stream-done",
            _producer(store, "stream-done", 1),
            store=store,
            registry=registry,
        )
    ).start()
    assert done.join(5.0)

    ids = live_stream_ids()
    assert "stream-slow" in ids
    assert "stream-done" not in ids

    assert slow.join(5.0)
    assert "stream-slow" not in live_stream_ids()


def test_an_unregistered_pump_is_not_reported_as_live(tmp_path):
    store = _store(tmp_path)
    stream_id = "stream-unregister"
    registry = RunRegistry()
    pump = RunPump(
        stream_id, _producer(store, stream_id, 1), store=store, registry=registry
    ).start()
    pump.join(5.0)
    unregister_pump(pump)
    assert get_live_pump(stream_id) is None
