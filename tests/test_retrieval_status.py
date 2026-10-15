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
def test_without_a_specific_vector_error_we_do_not_claim_a_probe_failure():
    """审查 F1：没有 vector_error 证据时不能断言"探活失败"——只能说不知道（并给出排查动作）。"""
    status = build_semantic_status(
        available=False, provider="ollama", model="qwen3-embedding:0.6b", indexed_documents=46,
    )

    assert status.code == UNKNOWN, status
    assert "探活" not in status.detail, status.detail
    assert "ollama" in status.detail and "46" in status.detail, status.detail
    assert status.action, status.action


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


# --- 审查修复 F1：不要把「探活失败」当万能兜底 ---------------------------------


def test_no_backend_configured_says_so_and_tells_you_to_configure():
    """没配后端（UnavailableEmbeddingProvider）时，"探活失败 / 启动该服务"是错的事实与错的下一步。"""
    status = build_semantic_status(
        available=False,
        provider="unavailable",
        model="",
        provider_reason="local embeddings are not bundled by design",
        vector_error="embedding_provider_unavailable",
        indexed_documents=0,
    )

    assert status.code == "embedding_not_configured", status
    # 事实：把 provider 自己说的原因原样带上，不转述。
    assert "local embeddings are not bundled by design" in status.detail, status.detail
    assert "探活失败" not in status.detail, status.detail
    # 下一步是"去配置"，不是"去启动一个不存在的服务"。
    assert "配置" in status.action, status.action
    assert "Ollama" not in status.action, status.action


def test_an_empty_embedding_response_is_not_a_probe_failure():
    status = build_semantic_status(
        available=False,
        provider="openai_compat",
        model="embedding-3",
        vector_error="embedding_returned_nothing",
        indexed_documents=12,
    )

    assert status.code == "embedding_returned_nothing", status
    assert "探活失败" not in status.detail, status.detail
    assert "空" in status.detail, status.detail
    assert status.action, status.action


def test_a_real_provider_that_fails_its_probe_still_says_probe_failed():
    status = build_semantic_status(
        available=False,
        provider="ollama",
        model="qwen3-embedding:0.6b",
        vector_error="embedding_provider_unavailable",
        indexed_documents=40,
    )

    assert status.code == "embedding_provider_unavailable", status
    assert "探活" in status.detail or "没有响应" in status.detail, status.detail
    assert "ollama" in status.detail, status.detail


def test_the_fallback_never_claims_a_probe_failure():
    """兜底分支只能承认"不知道"，不能断言一个我们没验证过的事实。"""
    status = build_semantic_status(available=False, provider="mystery", model="m", indexed_documents=7)

    assert status.code == "unknown", status
    assert "探活" not in status.detail, status.detail
    assert status.action, status.action


# --- 审查 F2：原始报错进用户可见载荷前必须脱敏 ---------------------------------


def test_a_key_echoed_in_an_error_body_never_reaches_the_user():
    """审查 F2 的复现：把 Authorization 回显到 401 body 的 provider，key 会一路渲染给用户。"""
    status = build_semantic_status(
        available=False,
        provider="openai_compat",
        model="embedding-3",
        indexed_documents=12,
        vector_error="vector_store_error",
        vector_error_detail=(
            '401 Unauthorized: {"error":"invalid api key sk-SECRET-abcdef1234567890"} '
            "header=Bearer sk-SECRET-abcdef1234567890"
        ),
    )

    assert "sk-SECRET-abcdef1234567890" not in status.detail, status.detail
    assert "***" in status.detail, status.detail
    # 有用的部分要留着（不然这条 detail 就没价值了）。
    assert "401 Unauthorized" in status.detail, status.detail


def test_redaction_covers_the_common_shapes():
    from rag.retrieval_status import redact_secrets

    for raw in (
        "key=sk-abcdef1234567890",
        "Authorization: Bearer abcdef1234567890.xyz",
        'api_key: "abcdefghijklmnopqrstuvwx"',
        "X-API-Key=abcdefghijklmnopqrstuvwx",
        "token: abcdefghijklmnopqrstuvwxyz012345",
    ):
        redacted = redact_secrets(raw)
        assert "abcdef1234567890" not in redacted, (raw, redacted)
        assert "abcdefghijklmnopqrstuvwx" not in redacted, (raw, redacted)


def test_redaction_leaves_ordinary_text_alone():
    from rag.retrieval_status import redact_secrets

    ordinary = "Storage folder C:/x/qdrant is already accessed by another instance of Qdrant client."
    assert redact_secrets(ordinary) == ordinary


def test_the_redaction_holds_end_to_end_through_the_search_status(tmp_path, monkeypatch):
    """链路验证：假 qdrant 抛出的报错里带 key，最终 status 里不能出现。"""
    from service.library_service import LibraryService
    from obsidian.sync import sync_sources
    from rag.retriever import clear_retrieval_cache, search_index_with_status

    class LeakyQdrant:
        def search(self, *args, **kwargs):
            raise RuntimeError(
                "already accessed by another instance of Qdrant client; "
                "retry with Authorization: Bearer sk-LEAK-0123456789abcdef"
            )

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    class AlwaysAvailable:
        def __init__(self, *args, **kwargs):
            self.provider = self

        def is_available(self):
            return True

        def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

        def get_model_info(self):
            return {"name": "fake", "model": "fake-3", "dim": 3}

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="LeakLib")
    inbox = root / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "greedy.md").write_text("# 贪心策略\n\n贪心策略每次选局部最优。", encoding="utf-8")
    sync_sources(workspace=str(root), vault_path=str(root), course_dir=str(root / "raw"), mode="full")
    clear_retrieval_cache(str(root))

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", lambda *a, **k: LeakyQdrant())
    monkeypatch.setattr("rag.qdrant_store.shared_qdrant_store", lambda *a, **k: LeakyQdrant())
    monkeypatch.setattr("rag.embedding_service.EmbeddingService", AlwaysAvailable)
    clear_retrieval_cache(str(root))

    _, status = search_index_with_status(str(root), query="贪心策略", top_k=5, config={})

    reason = status.get("semantic_reason") or {}
    blob = " ".join(str(value) for value in reason.values())
    assert "sk-LEAK-0123456789abcdef" not in blob, reason
    assert reason.get("code") == "vector_store_locked", reason


# --- 审查 F3/F4/F5：文案纯文本、锁库判定收紧、状态不残留 -----------------------


def test_no_reason_text_carries_markdown_markup():
    """审查 F3：界面是纯文本渲染，detail 里的 ** 会原样显示成星号。"""
    samples = [
        build_semantic_status(available=True),
        build_semantic_status(available=False, signature_mismatch="mismatch", indexed_documents=3),
        build_semantic_status(available=False, provider="unavailable", vector_error="embedding_provider_unavailable"),
        build_semantic_status(available=False, provider="openai_compat", vector_error="embedding_returned_nothing"),
        build_semantic_status(available=False, provider="ollama", vector_error="embedding_provider_unavailable", indexed_documents=9),
        build_semantic_status(available=False, vector_error="vector_store_locked", indexed_documents=9),
        build_semantic_status(available=False, vector_error="vector_store_error", indexed_documents=9),
        build_semantic_status(available=False, indexed_documents=0),
        build_semantic_status(available=False, indexed_documents=None),
    ]
    for status in samples:
        for field in (status.title, status.detail, status.action):
            assert "**" not in field, (status.code, field)


def test_a_path_that_merely_contains_storage_folder_is_not_a_lock():
    """审查 F4：只匹配 Storage folder 会把"不可写"之类的错误误诊成"另一个进程占用"。"""
    from rag.hybrid import classify_vector_error

    unrelated = "PermissionError: [WinError 5] Storage folder C:/Storage folder/qdrant is not writable"
    assert classify_vector_error(unrelated) == "vector_store_error", unrelated
    assert classify_vector_error(
        "Storage folder C:/x is already accessed by another instance of Qdrant client."
    ) == "vector_store_locked"


def test_vector_error_does_not_leak_across_searches():
    """审查 F5：vector_error 只在 __init__ 初始化的话，会在同一实例的后续查询里残留。"""
    from unittest.mock import MagicMock

    from rag.hybrid import HybridRetriever
    from rag.schema import RetrievalHit

    class FlakyQdrant:
        def __init__(self):
            self.fail = True

        def search(self, *args, **kwargs):
            if self.fail:
                raise RuntimeError("Storage folder C:/x is already accessed by another instance of Qdrant client.")
            return [RetrievalHit(
                chunk_id="c1", document_id="doc-1", text="hit", source="a.md", score=0.9,
            )]

    class Provider:
        def is_available(self):
            return True

        def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    sqlite = MagicMock()
    sqlite.search_fts5.return_value = []
    sqlite.get_chunks_by_ids.return_value = {}
    qdrant = FlakyQdrant()
    retriever = HybridRetriever(sqlite, qdrant, Provider(), {})

    first = retriever.search("贪心", top_k=3)
    assert first.vector_available is False and first.vector_error == "vector_store_locked", first

    qdrant.fail = False
    second = retriever.search("贪心", top_k=3)

    # 上一次的失败不能粘在这一次的结果上（否则 UI/日志会自相矛盾）。
    assert second.vector_available is True, (second, retriever.vector_error_detail)
    assert second.vector_error == "", second
