"""Unit tests for core.event_bus (AG-0.1)."""

import threading

from core.event_bus import EventBus, get_default_bus


def test_publish_delivers_to_subscriber():
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    bus.publish({"type": "turn_start", "session_id": "s1"})
    assert seen == [{"type": "turn_start", "session_id": "s1"}]


def test_session_filter_isolation():
    bus = EventBus()
    a, b = [], []
    bus.subscribe(a.append, session_id="s1")
    bus.subscribe(b.append, session_id="s2")
    bus.publish({"type": "message_delta", "session_id": "s1", "content": "hi"})
    assert len(a) == 1
    assert b == []


def test_event_type_filter():
    bus = EventBus()
    deltas, tools = [], []
    bus.subscribe(deltas.append, event_types=["message_delta"])
    bus.subscribe(tools.append, event_types=["tool_start", "tool_end"])
    bus.publish({"type": "message_delta", "content": "x"})
    bus.publish({"type": "tool_start", "tool_name": "rag_search"})
    assert len(deltas) == 1
    assert len(tools) == 1


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    seen = []
    sub = bus.subscribe(seen.append)
    bus.publish({"type": "x"})
    assert bus.unsubscribe(sub) is True
    bus.publish({"type": "x"})
    assert len(seen) == 1
    assert bus.unsubscribe(sub) is False


def test_unsubscribe_all_by_session():
    bus = EventBus()
    a, b = [], []
    bus.subscribe(a.append, session_id="s1")
    bus.subscribe(b.append, session_id="s2")
    assert bus.unsubscribe_all(session_id="s1") == 1
    bus.publish({"type": "x", "session_id": "s1"})
    bus.publish({"type": "x", "session_id": "s2"})
    assert a == []
    assert len(b) == 1


def test_unsubscribe_all_everything():
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append, session_id="s1")
    bus.subscribe(seen.append, session_id="s2")
    assert bus.unsubscribe_all() == 2
    bus.publish({"type": "x"})
    assert seen == []


def test_listener_exception_does_not_break_dispatch():
    bus = EventBus()
    good = []

    def bad(_event):
        raise RuntimeError("boom")

    bus.subscribe(bad)
    bus.subscribe(good.append)
    bus.publish({"type": "x"})
    assert len(good) == 1


def test_no_session_filter_matches_all_sessions():
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    bus.publish({"type": "x", "session_id": "s9"})
    bus.publish({"type": "x"})
    assert len(seen) == 2


def test_listener_count():
    bus = EventBus()
    bus.subscribe(lambda e: None, session_id="s1", event_types=["a"])
    bus.subscribe(lambda e: None, session_id="s1", event_types=["b"])
    bus.subscribe(lambda e: None, session_id="s2")
    assert bus.listener_count() == 3
    assert bus.listener_count(session_id="s1") == 2
    assert bus.listener_count(event_type="a") == 1


def test_publish_is_thread_safe():
    bus = EventBus()
    received = []
    lock = threading.Lock()

    def collect(event):
        with lock:
            received.append(event["type"])

    bus.subscribe(collect)
    threads = [
        threading.Thread(target=bus.publish, args=({"type": "t", "session_id": str(i)},))
        for i in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(received) == 50


def test_default_bus_is_singleton():
    assert get_default_bus() is get_default_bus()
