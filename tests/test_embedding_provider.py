"""rag_design B2: user-configured embedding providers.

The product decision is "no bundled ONNX model, Ollama as the offline option, a
user-configured OpenAI-compatible API as the normal path". Before this module the
only provider was Ollama, so a machine without Ollama could not build a single
vector - which is the state the real vault was found in.

The HTTP tests keep the real httpx client and swap only the transport, so the
request shape (path, header, body, batching) is exercised for real.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from rag.embedding_provider import (
    OpenAICompatibleEmbeddingProvider,
    PRESETS,
    create_embedding_provider,
)
from rag.embedding_service import EmbeddingService

KEY = "sk-test-key-not-a-real-secret"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _vectors(count: int, dim: int = 3) -> list[list[float]]:
    return [[float(i)] * dim for i in range(count)]


def _ok(vectors: list[list[float]], *, reverse: bool = False) -> httpx.Response:
    rows = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    if reverse:
        rows = list(reversed(rows))
    return httpx.Response(200, json={"data": rows})


def _service_with(monkeypatch, handler, rag: dict) -> EmbeddingService:
    """Build a real EmbeddingService whose provider uses a mock transport."""
    real = OpenAICompatibleEmbeddingProvider

    def factory(**kwargs):
        return real(client=_client(handler), **kwargs)

    monkeypatch.setattr("rag.embedding_provider.OpenAICompatibleEmbeddingProvider", factory)
    service = EmbeddingService({"rag": rag})
    assert service.name == "openai_compat"
    return service


def test_a_preset_expands_into_a_configured_provider(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)

    provider = create_embedding_provider({"rag": {"embedding_preset": "siliconflow"}})

    assert provider.name == "openai_compat"
    assert provider.model == PRESETS["siliconflow"]["model"]
    assert provider.base_url == "https://api.siliconflow.cn/v1"
    assert provider.is_available() is True


def test_auto_prefers_a_configured_api_and_otherwise_uses_ollama(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)

    assert create_embedding_provider({"rag": {}}).name == "ollama"
    assert create_embedding_provider(
        {"rag": {"embedding_preset": "siliconflow"}}
    ).name == "openai_compat"
    # An explicit choice is honoured even when the API is configured.
    assert create_embedding_provider(
        {"rag": {"embedding_backend": "ollama", "embedding_preset": "siliconflow"}}
    ).name == "ollama"


def test_no_provider_is_better_than_a_silent_downgrade(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    local = create_embedding_provider({"rag": {"embedding_backend": "local"}})
    assert local.is_available() is False
    assert "not bundled" in local.get_model_info()["reason"]

    # Explicitly asking for the API without a key must not fall back to Ollama.
    api = create_embedding_provider(
        {"rag": {"embedding_backend": "openai_compat", "embedding_preset": "siliconflow"}}
    )
    assert api.name == "openai_compat"
    assert api.is_available() is False

    service = EmbeddingService({"rag": {"embedding_backend": "local"}})
    assert service.is_available() is False
    assert service.embed_texts(["x"]) is None
    assert service.embed_query("x") is None


def test_the_key_travels_in_a_header_and_never_in_the_url(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(_vectors(1))

    service = _service_with(monkeypatch, handler, {"embedding_preset": "siliconflow"})
    assert service.embed_texts(["你好"]) is not None

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.siliconflow.cn/v1/embeddings"
    assert KEY not in str(request.url)
    assert request.headers["authorization"] == "Bearer " + KEY
    assert json.loads(request.content) == {
        "model": PRESETS["siliconflow"]["model"],
        "input": ["你好"],
    }


def test_long_inputs_are_batched_and_keep_their_order(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["input"])
        return _ok([[float(payload["input"][0])] * 2 for _ in payload["input"]])

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://example.invalid/v1",
        model="m",
        api_key=KEY,
        batch_size=2,
        client=_client(handler),
    )

    vectors = provider.embed(["0", "1", "2", "3", "4"])

    assert [call[0] for call in calls] == ["0", "2", "4"]
    assert len(vectors) == 5


def test_rows_are_read_in_index_order(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], reverse=True)

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://example.invalid/v1",
        model="m",
        api_key=KEY,
        client=_client(handler),
    )

    assert provider.embed(["a", "b", "c"]) == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]


def test_a_failing_provider_degrades_to_none_without_leaking_the_key(monkeypatch, caplog):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)
    # A hostile server echoing the credential back in the body and the mismatch
    # case both have to stay out of logs and out of model info.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"echo": request.headers.get("authorization")})

    service = _service_with(monkeypatch, handler, {"embedding_preset": "siliconflow"})
    with caplog.at_level(logging.WARNING):
        assert service.embed_texts(["x"]) is None

    assert KEY not in caplog.text
    assert KEY not in json.dumps(service.get_model_info(), ensure_ascii=False)
    assert service.get_model_info()["key_present"] is True


def test_a_short_response_is_rejected(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok(_vectors(1))

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://example.invalid/v1",
        model="m",
        api_key=KEY,
        client=_client(handler),
    )

    with pytest.raises(RuntimeError, match="1 vectors for 2 inputs"):
        provider.embed(["a", "b"])


def test_dim_comes_from_config_without_a_request(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _ok(_vectors(1, dim=7))

    service = _service_with(
        monkeypatch, handler, {"embedding_preset": "siliconflow", "embedding_dim": 1024}
    )

    assert service.get_model_info()["dim"] == 1024
    assert calls == []


def test_a_preset_carries_its_dimension_without_a_request(monkeypatch):
    """The recommended tier must not need a probe: the preset knows bge-m3 is 1024."""
    monkeypatch.setenv("SILICONFLOW_API_KEY", KEY)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _ok(_vectors(1, dim=7))

    service = _service_with(monkeypatch, handler, {"embedding_preset": "siliconflow"})

    assert service.get_model_info()["dim"] == 1024
    assert calls == []


def test_an_unknown_dimension_is_probed_once_and_then_cached(monkeypatch):
    monkeypatch.setenv("CUSTOM_EMBED_KEY", KEY)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _ok(_vectors(1, dim=7))

    service = _service_with(monkeypatch, handler, {
        "embedding_backend": "openai_compat",
        "embedding_base_url": "https://example.invalid/v1",
        "embedding_model": "custom-embed",
        "embedding_api_key_env": "CUSTOM_EMBED_KEY",
    })

    assert service.get_model_info()["dim"] == 7
    assert service.get_model_info()["dim"] == 7
    assert len(calls) == 1
