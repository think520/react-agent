"""Tests for Ollama embedding client and retriever legacy fallback."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from rag.ollama import OllamaEmbeddingClient
from rag.chunker import TextChunk


# --- Helpers ---

def _make_chunks(n=3):
    return [
        TextChunk(
            id=f"chunk-{i}",
            text=f"This is test chunk number {i} about algorithms.",
            source=f"test/file.md",
            metadata={"course": "CS101"},
        )
        for i in range(n)
    ]


def _mock_ollama_client(available=True, dim=8):
    """Create a mock OllamaEmbeddingClient that returns deterministic dense vectors."""
    client = MagicMock(spec=OllamaEmbeddingClient)
    client.model = "test-model"
    client.base_url = "http://localhost:11434"
    client._dim = dim
    client._available = available

    def mock_embed(texts):
        # Deterministic pseudo-embedding: hash-based
        result = []
        for text in texts:
            vec = [0.0] * dim
            for i, ch in enumerate(text[:dim]):
                vec[i % dim] += ord(ch) / 1000.0
            norm = _l2_norm(vec)
            if norm > 0:
                vec = [v / norm for v in vec]
            result.append(vec)
        return result

    client.embed = mock_embed
    client.is_available.return_value = available
    client.get_model_info.return_value = {
        "model": "test-model",
        "dim": dim,
        "backend": "ollama",
    }
    return client


# --- OllamaEmbeddingClient ---


class TestOllamaEmbeddingClient:

    def test_check_health_success(self):
        client = OllamaEmbeddingClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("rag.ollama.httpx.get", return_value=mock_resp):
            assert client.check_health() is True

    def test_check_health_connection_refused(self):
        import httpx
        client = OllamaEmbeddingClient()
        with patch("rag.ollama.httpx.get", side_effect=httpx.ConnectError("Connection refused")):
            assert client.check_health() is False

    def test_check_health_timeout(self):
        import httpx
        client = OllamaEmbeddingClient()
        with patch("rag.ollama.httpx.get", side_effect=httpx.TimeoutException("timeout")):
            assert client.check_health() is False

    def test_check_model_success(self):
        client = OllamaEmbeddingClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "capabilities": ["embedding"],
            "details": {"parameter_size": "0.6B"},
            "model_info": {"embedding_length": 1024},
        }
        with patch("rag.ollama.httpx.post", return_value=mock_resp):
            result = client.check_model()
            assert result is not None
            assert "embedding" in result["capabilities"]

    def test_check_model_no_embedding_capability(self):
        client = OllamaEmbeddingClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"capabilities": ["completion"]}
        with patch("rag.ollama.httpx.post", return_value=mock_resp):
            assert client.check_model() is None

    def test_check_model_connection_error(self):
        import httpx
        client = OllamaEmbeddingClient()
        with patch("rag.ollama.httpx.post", side_effect=httpx.ConnectError("Connection refused")):
            assert client.check_model() is None

    def test_is_available_full_chain(self):
        client = OllamaEmbeddingClient()
        health_resp = MagicMock()
        health_resp.status_code = 200

        show_resp = MagicMock()
        show_resp.status_code = 200
        show_resp.json.return_value = {
            "capabilities": ["embedding"],
            "model_info": {"embedding_length": 4},
        }

        embed_resp = MagicMock()
        embed_resp.status_code = 200
        embed_resp.json.return_value = {"embeddings": [[0.1, 0.2, 0.3, 0.4]]}
        embed_resp.raise_for_status = MagicMock()

        with patch("rag.ollama.httpx.get", return_value=health_resp), \
             patch("rag.ollama.httpx.post", side_effect=[show_resp, embed_resp]):
            assert client.is_available() is True
            assert client._dim == 4

    def test_is_available_caching(self):
        client = OllamaEmbeddingClient()
        client._available = True
        # Should return cached value without any HTTP calls
        assert client.is_available() is True
        assert client.is_available(force_refresh=False) is True

    def test_is_available_force_refresh(self):
        client = OllamaEmbeddingClient()
        client._available = True
        with patch.object(client, "check_health", return_value=False):
            assert client.is_available(force_refresh=True) is False

    def test_embed_success(self):
        client = OllamaEmbeddingClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        mock_resp.raise_for_status = MagicMock()
        with patch("rag.ollama.httpx.post", return_value=mock_resp):
            result = client.embed(["hello", "world"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2]

    def test_get_model_info(self):
        client = OllamaEmbeddingClient(model="my-model")
        client._dim = 512
        info = client.get_model_info()
        assert info["model"] == "my-model"
        assert info["dim"] == 512
        assert info["backend"] == "ollama"

    def test_refresh(self):
        client = OllamaEmbeddingClient()
        client._available = False
        with patch.object(client, "is_available", return_value=True) as mock_check:
            result = client.refresh(force=True)
            assert result is True
            mock_check.assert_called_once_with(force_refresh=True)


# --- retriever integration ---


class TestRetrieverIntegration:

    def test_search_index_with_config(self, tmp_path):
        """search_index with config falls back to the sparse JSON index."""
        from rag.retriever import search_index

        config = {"rag": {"embedding_backend": "local"}}
        knowledge_dir = os.path.join(str(tmp_path), ".knowledge")
        os.makedirs(knowledge_dir, exist_ok=True)

        # Write sparse index directly
        from rag.vector_store import LocalVectorStore
        sparse_path = os.path.join(knowledge_dir, "rag_index.json")
        store = LocalVectorStore(sparse_path)
        store.replace(_make_chunks(2))

        results = search_index(str(tmp_path), "test chunk", config=config)
        assert len(results) > 0

    def test_search_index_without_config(self, tmp_path):
        """search_index without config falls back to LocalVectorStore."""
        from rag.retriever import search_index

        knowledge_dir = os.path.join(str(tmp_path), ".knowledge")
        os.makedirs(knowledge_dir, exist_ok=True)

        from rag.vector_store import LocalVectorStore
        sparse_path = os.path.join(knowledge_dir, "rag_index.json")
        store = LocalVectorStore(sparse_path)
        store.replace(_make_chunks(2))

        results = search_index(str(tmp_path), "test chunk")
        assert len(results) > 0
