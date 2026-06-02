"""Tests for Ollama embedding: OllamaEmbeddingClient, DenseVectorStore, VectorStoreRouter."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from rag.ollama import OllamaEmbeddingClient
from rag.dense_store import DenseVectorStore, _cosine_similarity, _l2_norm
from rag.chunker import TextChunk
from rag.router import VectorStoreRouter


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


# --- DenseVectorStore ---


class TestDenseVectorStore:

    def test_replace_and_search(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        chunks = _make_chunks(3)
        store.replace(chunks)

        assert len(store.chunks) == 3
        for c in store.chunks:
            assert "vector" in c
            assert "norm" in c
            assert len(c["vector"]) == 8

        # Search for something similar to chunk 0
        results = store.search("test chunk number 0 about algorithms", top_k=3)
        assert len(results) > 0
        assert results[0]["score"] > 0

    def test_search_empty_store(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        results = store.search("anything")
        assert results == []

    def test_search_course_filter(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        chunks = _make_chunks(2)
        chunks[1].metadata = {"course": "CS202"}
        store.replace(chunks)

        results = store.search("test chunk", course="CS101", top_k=5)
        for r in results:
            assert r["metadata"].get("course") == "CS101"

    def test_upsert_adds_new(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        store.replace(_make_chunks(2))
        assert len(store.chunks) == 2

        new_chunk = TextChunk(id="chunk-new", text="New content", source="test/new.md", metadata={})
        store.upsert([new_chunk])
        assert len(store.chunks) == 3

    def test_upsert_updates_existing(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        store.replace(_make_chunks(2))

        updated = TextChunk(id="chunk-0", text="Updated content for chunk 0", source="test/file.md", metadata={})
        store.upsert([updated])
        assert len(store.chunks) == 2
        texts = [c["text"] for c in store.chunks]
        assert "Updated content for chunk 0" in texts

    def test_remove_by_source(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        chunks = _make_chunks(3)
        chunks[2].source = "other/file.md"
        store.replace(chunks)

        removed = store.remove_by_source("test/")
        assert removed == 2
        assert len(store.chunks) == 1

    def test_get_stats(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        store.replace(_make_chunks(5))

        stats = store.get_stats()
        assert stats["chunk_count"] == 5
        assert stats["model"] == "test-model"
        assert stats["dim"] == 8
        assert stats["backend"] == "ollama"

    def test_check_model_match(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        store.replace(_make_chunks(1))

        assert store.check_model_match() is True

        # Simulate model change
        client.model = "different-model"
        assert store.check_model_match() is False

    def test_persistence(self, tmp_path):
        client = _mock_ollama_client()
        path = str(tmp_path / "dense.json")
        store = DenseVectorStore(path, client)
        store.replace(_make_chunks(2))

        # Load in a new store instance
        store2 = DenseVectorStore(path, client)
        store2.load()
        assert len(store2.chunks) == 2

    def test_search_embedding_failure_returns_empty(self, tmp_path):
        client = _mock_ollama_client()
        store = DenseVectorStore(str(tmp_path / "dense.json"), client)
        store.replace(_make_chunks(2))

        # Now make embed fail (simulating Ollama going down after indexing)
        client.embed = MagicMock(side_effect=Exception("Ollama down"))
        results = store.search("test query")
        assert results == []


# --- cosine similarity ---


class TestCosineSimilarity:

    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        assert _cosine_similarity(vec, vec, _l2_norm(vec)) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, b, _l2_norm(b)) == pytest.approx(0.0)

    def test_empty_vectors(self):
        assert _cosine_similarity([], [1.0], 1.0) == 0.0
        assert _cosine_similarity([1.0], [], 0.0) == 0.0

    def test_different_lengths(self):
        assert _cosine_similarity([1.0, 2.0], [1.0], 1.0) == 0.0

    def test_similar_vectors(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.9, 0.1]
        score = _cosine_similarity(a, b, _l2_norm(b))
        assert score > 0.9


# --- VectorStoreRouter ---


class TestVectorStoreRouter:

    def test_auto_mode_ollama_available(self, tmp_path):
        config = {
            "rag": {
                "embedding_backend": "auto",
                "ollama_url": "http://localhost:11434",
                "ollama_model": "test-model",
            }
        }
        with patch("rag.router.OllamaEmbeddingClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_available.return_value = True
            mock_instance.model = "test-model"
            mock_instance.get_model_info.return_value = {"model": "test-model", "dim": 8, "backend": "ollama"}
            mock_instance.embed.return_value = [[0.1] * 8]

            router = VectorStoreRouter(str(tmp_path), config)
            assert router._active == "dense"
            assert router._fallback == "sparse"

    def test_auto_mode_ollama_unavailable(self, tmp_path):
        config = {
            "rag": {
                "embedding_backend": "auto",
                "ollama_url": "http://localhost:11434",
                "ollama_model": "test-model",
            }
        }
        with patch("rag.router.OllamaEmbeddingClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_available.return_value = False
            mock_instance.base_url = "http://localhost:11434"
            mock_instance.model = "test-model"

            router = VectorStoreRouter(str(tmp_path), config)
            assert router._active == "sparse"
            assert router._fallback is None

    def test_local_mode(self, tmp_path):
        config = {"rag": {"embedding_backend": "local"}}
        router = VectorStoreRouter(str(tmp_path), config)
        assert router._active == "sparse"
        assert router._fallback is None

    def test_ollama_mode_unavailable_raises(self, tmp_path):
        config = {
            "rag": {
                "embedding_backend": "ollama",
                "ollama_url": "http://localhost:11434",
                "ollama_model": "test-model",
            }
        }
        with patch("rag.router.OllamaEmbeddingClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_available.return_value = False
            mock_instance.base_url = "http://localhost:11434"
            mock_instance.model = "test-model"

            with pytest.raises(RuntimeError, match="Ollama embedding unavailable"):
                VectorStoreRouter(str(tmp_path), config)

    def test_dual_write_in_auto_mode(self, tmp_path):
        config = {
            "rag": {
                "embedding_backend": "auto",
                "ollama_url": "http://localhost:11434",
                "ollama_model": "test-model",
            }
        }
        mock_client = _mock_ollama_client(available=True)

        with patch("rag.router.OllamaEmbeddingClient", return_value=mock_client):
            router = VectorStoreRouter(str(tmp_path), config)
            chunks = _make_chunks(2)
            router.replace(chunks)

            # Both stores should have data
            sparse_path = os.path.join(str(tmp_path), ".knowledge", "rag_index.json")
            dense_path = os.path.join(str(tmp_path), ".knowledge", "rag_index_dense.json")
            assert os.path.exists(sparse_path)
            assert os.path.exists(dense_path)

            with open(sparse_path, "r", encoding="utf-8") as f:
                sparse_data = json.load(f)
            assert len(sparse_data["chunks"]) == 2

            with open(dense_path, "r", encoding="utf-8") as f:
                dense_data = json.load(f)
            assert len(dense_data["chunks"]) == 2

    def test_search_with_fallback(self, tmp_path):
        config = {
            "rag": {
                "embedding_backend": "auto",
                "ollama_url": "http://localhost:11434",
                "ollama_model": "test-model",
            }
        }
        mock_client = _mock_ollama_client(available=True)

        with patch("rag.router.OllamaEmbeddingClient", return_value=mock_client):
            router = VectorStoreRouter(str(tmp_path), config)

            # Write to sparse store directly (simulate dense failing)
            from rag.vector_store import LocalVectorStore
            sparse_path = os.path.join(str(tmp_path), ".knowledge", "rag_index.json")
            sparse = LocalVectorStore(sparse_path)
            sparse.replace(_make_chunks(2))

            # Make dense search fail
            router.dense_store.search = MagicMock(side_effect=Exception("Ollama down"))

            results = router.search("test chunk", top_k=5)
            # Should have fallen back to sparse
            assert len(results) > 0

    def test_get_backend_info(self, tmp_path):
        config = {"rag": {"embedding_backend": "local"}}
        router = VectorStoreRouter(str(tmp_path), config)
        info = router.get_backend_info()
        assert info["active"] == "sparse"
        assert info["mode"] == "local"

    def test_no_config_defaults_to_auto(self, tmp_path):
        with patch("rag.router.OllamaEmbeddingClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.is_available.return_value = False
            mock_instance.base_url = "http://localhost:11434"
            mock_instance.model = "qwen3-embedding:0.6b"

            router = VectorStoreRouter(str(tmp_path), None)
            assert router._active == "sparse"

    def test_remove_by_source(self, tmp_path):
        config = {"rag": {"embedding_backend": "local"}}
        router = VectorStoreRouter(str(tmp_path), config)
        from rag.vector_store import LocalVectorStore
        sparse_path = os.path.join(str(tmp_path), ".knowledge", "rag_index.json")
        sparse = LocalVectorStore(sparse_path)
        sparse.replace(_make_chunks(3))

        removed = router.remove_by_source("test/")
        assert removed == 3


# --- retriever integration ---


class TestRetrieverIntegration:

    def test_search_index_with_config(self, tmp_path):
        """search_index with config uses VectorStoreRouter."""
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
