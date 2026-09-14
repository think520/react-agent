"""P0-15: one Qdrant client per workspace inside the process."""

import pytest


def test_shared_store_is_identical_for_one_workspace(tmp_path):
    from rag.qdrant_store import shared_qdrant_store

    workspace = str(tmp_path)
    first = shared_qdrant_store(workspace, {})
    second = shared_qdrant_store(workspace, {})
    assert first is second


def test_different_workspaces_get_different_stores(tmp_path):
    from rag.qdrant_store import shared_qdrant_store

    other = tmp_path / "other"
    other.mkdir()
    assert shared_qdrant_store(str(tmp_path), {}) is not shared_qdrant_store(str(other), {})


def test_retrieval_pipeline_uses_the_shared_store(tmp_path):
    """The pipeline used to construct its own client; the sync built another."""
    pytest.importorskip("qdrant_client")
    from rag.qdrant_store import shared_qdrant_store
    from rag.retriever import _retrieval_pipeline, clear_retrieval_cache

    workspace = str(tmp_path)
    store = shared_qdrant_store(workspace, {})
    pipeline = _retrieval_pipeline(workspace, {"rag": {}})
    try:
        assert pipeline.qdrant is store
    finally:
        clear_retrieval_cache(workspace)


def test_closing_the_shared_store_drops_it_from_the_registry(tmp_path):
    from rag.qdrant_store import close_shared_qdrant_store, shared_qdrant_store

    workspace = str(tmp_path)
    first = shared_qdrant_store(workspace, {})
    close_shared_qdrant_store(workspace, {})
    assert shared_qdrant_store(workspace, {}) is not first
