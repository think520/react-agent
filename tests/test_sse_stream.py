"""Unit tests for the AG-0.3 stream store (web/backend/sse.py)."""

from web.backend.sse import (
    MAX_STREAM_BYTES,
    MAX_STREAM_ENTRIES,
    StreamBuffer,
    StreamStore,
    StreamEmitter,
    encode_sse,
)


def test_encode_sse_shape():
    frame = encode_sse("message_delta", {"content": "hi"})
    assert frame.startswith("event: message_delta\n")
    assert "\"content\": \"hi\"" in frame or '"content": "hi"' in frame
    assert frame.endswith("\n\n")


def test_stream_buffer_assigns_monotonic_seq():
    buffer = StreamBuffer()
    assert buffer.append("a", {"x": 1}) == 1
    assert buffer.append("b", {"x": 2}) == 2
    assert buffer.append("c", {"x": 3}) == 3


def test_stream_buffer_replay_cursor():
    buffer = StreamBuffer()
    buffer.append("a", {})
    buffer.append("b", {})
    buffer.append("c", {})
    frames = buffer.replay(1)
    assert [f["seq"] for f in frames] == [2, 3]


def test_stream_buffer_replay_none_after_latest():
    buffer = StreamBuffer()
    buffer.append("a", {})
    assert buffer.replay(1) == []


def test_stream_buffer_clear_resets_seq():
    buffer = StreamBuffer()
    buffer.append("a", {})
    buffer.append("b", {})
    buffer.clear()
    assert len(buffer) == 0
    assert buffer.append("c", {}) == 1


def test_stream_buffer_entry_cap():
    buffer = StreamBuffer()
    for i in range(MAX_STREAM_ENTRIES + 10):
        buffer.append("e", {"i": i})
    assert len(buffer) <= MAX_STREAM_ENTRIES


def test_stream_buffer_byte_cap():
    buffer = StreamBuffer()
    payload = {"blob": "x" * 1024}
    # Appending far more than the byte cap should evict old frames and
    # never let the retained byte size exceed the ceiling.
    for _ in range(20000):
        buffer.append("e", payload)
        assert buffer._bytes <= MAX_STREAM_BYTES


def test_stream_store_isolates_streams():
    store = StreamStore()
    store.append("s1", "a", {})
    store.append("s2", "a", {})
    assert [f["seq"] for f in store.replay("s1", 0)] == [1]
    assert [f["seq"] for f in store.replay("s2", 0)] == [1]


def test_stream_store_clear():
    store = StreamStore()
    store.append("s1", "a", {})
    store.clear("s1")
    assert store.replay("s1", 0) == []
    assert store.has("s1") is False


def test_stream_emitter_stamps_identity():
    store = StreamStore()
    emitter = StreamEmitter(store, "stream-9")
    frame = emitter.emit("message_delta", {"content": "x"})
    assert "stream-9" in frame
    assert '"seq": 1' in frame
    # Second emit increments seq.
    frame2 = emitter.emit("message_delta", {"content": "y"})
    assert '"seq": 2' in frame2


# --- SSE stream lane (dedicated pump for long-lived producers) -------------

def _consume(gen):
    import asyncio

    from web.backend.sse import iterate_on_stream_lane

    async def run():
        return [item async for item in iterate_on_stream_lane(gen)]

    return asyncio.run(run())


def test_iterate_on_stream_lane_preserves_order_and_completion():
    from web.backend.sse import iterate_on_stream_lane

    def producer():
        for index in range(5):
            yield f"frame-{index}"

    assert _consume(producer()) == [f"frame-{i}" for i in range(5)]


def test_iterate_on_stream_lane_empty_generator():
    from web.backend.sse import iterate_on_stream_lane

    def producer():
        return iter(())
        yield  # pragma: no cover - makes this a generator

    assert _consume(producer()) == []


def test_iterate_on_stream_lane_propagates_producer_errors():
    import pytest as _pytest
    from web.backend.sse import iterate_on_stream_lane

    def producer():
        yield "ok"
        raise ValueError("boom")

    with _pytest.raises(ValueError, match="boom"):
        _consume(producer())
