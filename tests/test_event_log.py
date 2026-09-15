"""P1-17: the reconnect log must outlive the run and the process."""

import threading

from core.event_log import EventLog


def test_append_assigns_monotonic_seq_per_stream(tmp_path):
    log = EventLog(str(tmp_path))
    assert log.append("s1", "message_delta", {"content": "a"}) == 1
    assert log.append("s1", "message_delta", {"content": "b"}) == 2
    assert log.append("s2", "message_delta", {"content": "c"}) == 1


def test_read_after_is_a_cursor(tmp_path):
    log = EventLog(str(tmp_path))
    for index in range(5):
        log.append("s1", "message_delta", {"content": str(index)})

    frames = log.read_after("s1", after_seq=2)

    assert [frame["seq"] for frame in frames] == [3, 4, 5]
    assert frames[0]["event"] == "message_delta"
    assert frames[0]["data"] == {"content": "2"}


def test_events_survive_a_new_instance(tmp_path):
    """The old buffer lived in memory and was cleared when the run ended, so a
    reconnect - let alone a restart - could never replay anything."""
    first = EventLog(str(tmp_path))
    first.append("s1", "run_started", {"run_id": "r1"})
    first.append("s1", "message_delta", {"content": "半句"})

    reopened = EventLog(str(tmp_path))

    assert reopened.max_seq("s1") == 2
    assert [frame["data"]["content"] for frame in reopened.read_after("s1", 1)] == ["半句"]


def test_concurrent_appends_get_unique_seqs(tmp_path):
    log = EventLog(str(tmp_path))
    seen: list[int] = []
    lock = threading.Lock()

    def writer(index: int) -> None:
        seq = log.append("s1", "message_delta", {"content": str(index)})
        with lock:
            seen.append(seq)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert sorted(seen) == list(range(1, 13))


def test_prune_drops_old_streams(tmp_path):
    log = EventLog(str(tmp_path), retention_days=0, max_streams=2)
    for stream in ("s1", "s2", "s3"):
        log.append(stream, "message_delta", {"content": stream})

    removed = log.prune(now=10 ** 9)

    assert removed >= 1
    live = [stream for stream in ("s1", "s2", "s3") if log.max_seq(stream) > 0]
    assert len(live) <= 2


def test_prune_never_deletes_a_stream_that_is_still_live(tmp_path):
    """Retention must not delete the frames a live run is still reading.

    The SSE response tails this log, so pruning a live stream would drop the
    rest of the turn and restart its seq at 1 - leaving its reader waiting on a
    cursor it can never reach again.
    """
    aged = EventLog(str(tmp_path / "aged"), retention_days=1)
    aged.append("live", "message_delta", {"content": "chunk"})
    aged.append("dead", "message_delta", {"content": "old"})

    aged.prune(now=10 ** 12, exempt=["live"])

    assert aged.max_seq("live") == 1, "the live stream must survive the sweep"
    assert aged.max_seq("dead") == 0

    capped = EventLog(str(tmp_path / "capped"), retention_days=999, max_streams=1)
    for stream in ("live", "s1", "s2"):
        capped.append(stream, "message_delta", {"content": stream})

    capped.prune(exempt=["live"])

    assert capped.max_seq("live") == 1
    assert capped.max_seq("s1") + capped.max_seq("s2") == 1, "the cap still applies"
