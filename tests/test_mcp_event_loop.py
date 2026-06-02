"""Tests for mcp_client.event_loop: AsyncEventLoop singleton, run_sync, close."""

import asyncio
import time

import pytest

from mcp_client.event_loop import AsyncEventLoop


@pytest.fixture(autouse=True)
def _reset_loop():
    """Ensure each test starts with a fresh event loop singleton."""
    AsyncEventLoop.reset()
    yield
    AsyncEventLoop.reset()


def test_get_returns_singleton():
    a = AsyncEventLoop.get()
    b = AsyncEventLoop.get()
    assert a is b


def test_loop_thread_is_alive():
    loop = AsyncEventLoop.get()
    assert loop._thread.is_alive()


def test_run_sync_returns_value():
    loop = AsyncEventLoop.get()

    async def compute():
        await asyncio.sleep(0.01)
        return 42

    result = loop.run_sync(compute())
    assert result == 42


def test_run_sync_with_args_kwargs():
    loop = AsyncEventLoop.get()

    async def add(a, b, *, multiplier=1):
        return (a + b) * multiplier

    result = loop.run_sync(add(2, 3, multiplier=10))
    assert result == 50


def test_run_sync_raises_exception():
    loop = AsyncEventLoop.get()

    async def boom():
        raise ValueError("expected failure")

    with pytest.raises(ValueError, match="expected failure"):
        loop.run_sync(boom())


def test_run_sync_timeout():
    loop = AsyncEventLoop.get()

    async def slow():
        await asyncio.sleep(2.0)
        return "should not see this"

    with pytest.raises(TimeoutError):
        loop.run_sync(slow(), timeout=0.1)


def test_close_stops_thread():
    loop = AsyncEventLoop.get()
    loop.close()
    assert not loop._thread.is_alive()


def test_close_is_idempotent():
    loop = AsyncEventLoop.get()
    loop.close()
    loop.close()  # should not raise


def test_run_sync_after_close_raises():
    loop = AsyncEventLoop.get()
    loop.close()

    async def noop():
        return 1

    with pytest.raises(RuntimeError, match="closed"):
        loop.run_sync(noop())


def test_concurrent_run_sync():
    """Multiple threads can submit coroutines concurrently."""
    import threading

    loop = AsyncEventLoop.get()
    results: list[int] = []
    errors: list[Exception] = []

    async def task(n: int):
        await asyncio.sleep(0.05)
        return n * 2

    def worker(n: int):
        try:
            r = loop.run_sync(task(n), timeout=2.0)
            results.append(r)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert sorted(results) == [0, 2, 4, 6, 8]


def test_cross_thread_invocation_does_not_deadlock():
    """The whole point: calling from main thread into the loop thread works."""
    loop = AsyncEventLoop.get()

    async def ping():
        return "pong"

    # First call: warm up the event loop thread
    assert loop.run_sync(ping()) == "pong"
    # Second call: should still be fast (no need to spin up another thread)
    start = time.time()
    assert loop.run_sync(ping()) == "pong"
    assert time.time() - start < 0.5
