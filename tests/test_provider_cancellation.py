"""A4 batch 3 (P0-1): a cancelled stream must really stop the request."""

import json

import httpx

from core.cancellation import CancelToken, RunCancelled
from providers.openai_compat import OpenAICompatibleProvider


def _sse(text: str) -> bytes:
    payload = {"choices": [{"delta": {"content": text}}]}
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _install_transport(monkeypatch, handler, seen: list):
    """Keep the real httpx client, swap only the transport."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        seen.append(kwargs.get("base_url"))
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("providers.openai_compat.httpx.Client", factory)


def _provider():
    return OpenAICompatibleProvider(
        api_key="k", model="m", base_url="http://test", provider_name="test", max_retries=3,
    )


def test_a_cancelled_stream_stops_mid_response(monkeypatch):
    """The read loop must leave so the `with` blocks close the response: that is
    the only place where a streaming request can actually be interrupted."""
    seen: list = []

    def handler(request):
        body = b"".join(_sse(str(index)) for index in range(50))
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    _install_transport(monkeypatch, handler, seen)
    token = CancelToken()
    chunks = []

    for chunk in _provider().complete_stream([{"role": "user", "content": "hi"}], cancel_token=token):
        chunks.append(chunk)
        token.cancel("client_disconnected")

    assert len(chunks) == 1, "the remaining deltas must not be parsed"
    assert len(seen) == 1, "a cancelled stream must not be retried"


def test_an_already_cancelled_stream_never_opens_a_connection(monkeypatch):
    seen: list = []

    def handler(request):
        return httpx.Response(200, content=_sse("x"), headers={"content-type": "text/event-stream"})

    _install_transport(monkeypatch, handler, seen)
    token = CancelToken()
    token.cancel("client_disconnected")

    try:
        list(_provider().complete_stream([{"role": "user", "content": "hi"}], cancel_token=token))
        raise AssertionError("expected RunCancelled")
    except RunCancelled:
        pass

    assert seen == []


def test_cancelling_before_a_retry_does_not_spend_another_request(monkeypatch):
    """A 500 is retryable, but not when the user already pressed stop."""
    seen: list = []
    token = CancelToken()

    def handler(request):
        token.cancel("client_disconnected")
        return httpx.Response(500, content=b"boom")

    _install_transport(monkeypatch, handler, seen)

    try:
        _provider().complete([{"role": "user", "content": "hi"}], cancel_token=token)
        raise AssertionError("expected RunCancelled")
    except RunCancelled:
        pass

    assert len(seen) == 1, "no retry after cancellation"
