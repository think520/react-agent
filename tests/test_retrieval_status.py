"""检索降级必须**说出原因**，而且要能照着做。

核对现状：签名不匹配时 «rag/retriever.py» 会把 provider 置空、探活失败时
«_vector_available()» 返回 False —— 两者最终都只变成 **一行日志**
（«Semantic search disabled for …»），对外只有 «retrieval_mode=fts_only»。
用户看到的是「检索不到」，看不出是「后端没起来」还是「索引是别的模型建的」。
"""

from __future__ import annotations

from rag.retrieval_status import (
    PROVIDER_UNAVAILABLE,
    SIGNATURE_MISMATCH,
    SemanticStatus,
    UNKNOWN,
    build_semantic_status,
)


def test_available_says_ok_and_nothing_else():
    status = build_semantic_status(available=True, provider="ollama", model="qwen3-embedding", indexed_documents=46)

    assert status.code == "ok", status
    assert "语义" in status.title or "可用" in status.title, status


def test_a_signature_mismatch_names_both_sides_and_the_fix():
    status = build_semantic_status(
        available=False,
        provider="ollama",
        model="qwen3-embedding:0.6b",
        dim=None,
        signature_mismatch="embedding signature mismatch (provider, model, dim): stored {...} vs current {...}",
        indexed_documents=46,
    )

    assert status.code == SIGNATURE_MISMATCH, status
    # 事实：索引里的向量是别的模型建的（原文照抄签名信息，不编）。
    assert "signature mismatch" in status.detail, status.detail
    # 可行动：要么换回原模型，要么重建。
    assert "重建" in status.action or "重新同步" in status.action, status.action


def test_an_unavailable_provider_names_the_backend_and_the_next_step():
    status = build_semantic_status(
        available=False, provider="ollama", model="qwen3-embedding:0.6b", indexed_documents=46,
    )

    assert status.code == PROVIDER_UNAVAILABLE, status
    assert "ollama" in status.detail and "qwen3-embedding:0.6b" in status.detail, status.detail
    assert "设置" in status.action or "启动" in status.action, status.action


def test_no_vectors_at_all_is_a_different_reason():
    status = build_semantic_status(available=False, provider="openai_compat", model="embedding-3", indexed_documents=0)

    assert status.code == "no_vectors_indexed", status
    assert "同步" in status.action, status.action


def test_we_say_unknown_rather_than_guessing():
    status = build_semantic_status(available=False, indexed_documents=None)

    assert status.code == UNKNOWN, status
    assert status.action, status  # 仍然给一个可行动的建议


def test_status_is_json_friendly():
    status = build_semantic_status(available=False, provider="ollama", indexed_documents=3)

    payload = status.to_dict()
    assert set(payload) >= {"code", "title", "detail", "action"}, payload
    assert all(isinstance(value, str) for value in payload.values()), payload
    assert isinstance(status, SemanticStatus)


# --- 接线：状态字典里必须真的带上原因 -----------------------------------------


def test_a_missing_index_reports_why_in_the_search_status(tmp_path):
    from rag.retriever import search_index_with_status

    results, status = search_index_with_status(str(tmp_path), query="贪心", top_k=5)

    assert results == []
    assert status["retrieval_mode"] == "unavailable", status
    reason = status.get("semantic_reason")
    assert reason and reason["code"] == "no_vectors_indexed", status
    assert reason["action"], reason


def test_fts_only_search_reports_a_reason_with_an_action(tmp_path, monkeypatch):
    """有索引、但没有可用向量腿时，状态里要能看出是哪一类原因。"""
    from service.library_service import LibraryService
    from obsidian.sync import sync_sources
    from rag.retriever import clear_retrieval_cache, search_index_with_status

    from unittest.mock import MagicMock

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="ReasonLib")
    inbox = root / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "greedy.md").write_text("# 贪心策略\n\n贪心策略每次选局部最优。", encoding="utf-8")
    sync_sources(workspace=str(root), vault_path=str(root), course_dir=str(root / "raw"), mode="full")
    clear_retrieval_cache(str(root))

    results, status = search_index_with_status(str(root), query="贪心策略", top_k=5, config={})

    assert results, "FTS 腿应当仍然有结果"
    assert status["retrieval_mode"] == "fts_only", status
    reason = status.get("semantic_reason")
    assert reason, status
    assert reason["code"] in {"no_vectors_indexed", "embedding_provider_unavailable"}, reason
    assert reason["title"] and reason["action"], reason


def test_a_locked_vector_store_is_reported_as_such_not_as_a_bad_provider():
    """本地向量库被别的进程占用时，原因**不是**「后端探活失败」——两者下一步完全不同。"""
    status = build_semantic_status(
        available=False,
        provider="openai_compat",
        model="embedding-3",
        dim=2048,
        indexed_documents=46,
        vector_error="vector_store_locked",
        vector_error_detail="Storage folder … is already accessed by another instance of Qdrant client.",
    )

    assert status.code == "vector_store_locked", status
    assert "另一个进程" in status.title or "占用" in status.title, status.title
    assert "already accessed" in status.detail, status.detail
    assert "关掉" in status.action, status.action


def test_a_generic_vector_error_keeps_the_raw_message():
    status = build_semantic_status(
        available=False, indexed_documents=5, vector_error="vector_store_error",
        vector_error_detail="boom: collection missing",
    )

    assert status.code == "vector_store_error", status
    assert "boom: collection missing" in status.detail, status.detail
    assert status.action, status


def test_the_locked_store_reason_reaches_the_search_status(tmp_path, monkeypatch):
    """接线：hybrid 抛「已被占用」时，检索状态要说 locked，而不是 provider 不可用。"""
    from service.library_service import LibraryService
    from obsidian.sync import sync_sources
    from rag.retriever import clear_retrieval_cache, search_index_with_status

    class LockedQdrant:
        def search(self, *args, **kwargs):
            raise RuntimeError(
                "Storage folder C:/x/qdrant is already accessed by another instance of Qdrant client."
            )

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="LockedLib")
    inbox = root / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "greedy.md").write_text("# 贪心策略\n\n贪心策略每次选局部最优。", encoding="utf-8")
    sync_sources(workspace=str(root), vault_path=str(root), course_dir=str(root / "raw"), mode="full")
    clear_retrieval_cache(str(root))

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", lambda *a, **k: LockedQdrant())
    monkeypatch.setattr("rag.qdrant_store.shared_qdrant_store", lambda *a, **k: LockedQdrant())

    class AlwaysAvailable:
        def __init__(self, *args, **kwargs):
            # 检索流水线会拿 .provider 当向量腿的客户端，拿 get_model_info() 做签名比较。
            self.provider = self

        def is_available(self):
            return True

        def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

        def get_model_info(self):
            return {"name": "fake", "model": "fake-3", "dim": 3}

    monkeypatch.setattr("rag.embedding_service.EmbeddingService", AlwaysAvailable)
    clear_retrieval_cache(str(root))

    results, status = search_index_with_status(str(root), query="贪心策略", top_k=5, config={})

    assert status["retrieval_mode"] == "fts_only", status
    reason = status.get("semantic_reason") or {}
    assert reason.get("code") == "vector_store_locked", reason
