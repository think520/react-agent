import os

from rag.sqlite_store import KBSQLiteStore
from service.kb_service import KBService
from service.usage_service import UsageService
from wiki.repair import WikiRepairStore


def test_usage_ledger_does_not_store_prompt_content(tmp_path):
    service = UsageService(str(tmp_path))
    response = type("Response", (), {
        "request_id": "req-1", "provider": "deepseek", "model": "chat",
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 80, "cache_miss_tokens": 20, "cost_usd": 0.004},
    })()
    service.record(response, subsystem="wiki", operation="wiki_drafting", run_id="run-1")

    summary = service.summary(days=7, run_id="run-1")
    assert summary["requests"] == 1
    assert summary["cache_read_tokens"] == 80
    assert summary["cost_usd"] == 0.004
    assert summary["cost_reported"] is True
    assert summary["model_distribution"] == {"chat": 1}
    assert "prompt" not in str(summary).lower()


def test_wiki_estimate_uses_only_matching_real_provider_samples(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("BOBODAN_HOME", str(home))
    usage = UsageService(str(home))

    def record(request_id, operation, provider, model, duration_ms, input_tokens, output_tokens):
        response = type("Response", (), {
            "request_id": request_id,
            "provider": provider,
            "model": model,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        })()
        usage.record(
            response, subsystem="wiki", operation=operation, run_id="real-run",
            duration_ms=duration_ms,
        )

    record("discovery", "wiki_discovery", "deepseek", "deepseek-v4-flash", 12000, 8000, 1200)
    record("drafting", "wiki_drafting", "deepseek", "deepseek-v4-flash", 9000, 1800, 900)
    record("other-model", "wiki_drafting", "openai", "gpt-test", 900000, 900000, 900000)
    record("test-provider", "wiki_drafting", "RecordingProvider", "unknown", 0, 0, 0)

    service = KBService(str(tmp_path))
    documents = [{
        "document_id": "doc-1", "title": "资料 1", "source": "raw/1.md",
        "sections": [{"chunk_id": "chunk-1", "heading": "章节", "text": "正文" * 2000}],
    }]
    monkeypatch.setattr(service, "_wiki_run_documents", lambda *args, **kwargs: (documents, []))

    estimate = service.estimate_wiki_run(
        generation_mode="standard",
        provider_name="deepseek",
        model="deepseek-v4-flash",
        config={},
    )

    assert estimate["ok"] is True
    assert estimate["historical_sample_size"] == 2
    assert estimate["confidence"] == "low"
    assert estimate["duration_range_seconds"][1] < 1000
    assert estimate["input_token_range"][1] < 300000
    assert estimate["local_cache_reuse_included"] is False


def test_repair_plan_is_persistent_and_only_applies_local_items(tmp_path):
    concepts = tmp_path / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "A.md").write_text("---\ntype: wiki_concept\ntitle: A\n---\n\n# A\n", encoding="utf-8")
    health = {
        "ok": True, "healthy": False, "total_pages": 1,
        "vaults": [{
            "vault": ".", "index_mismatches": ["index"], "broken_links": [{"source": "A.md", "target": "B"}],
            "orphans": [], "missing": [], "stale": ["A"], "duplicate_candidates": [],
            "contradiction_candidates": [], "semantic_candidates": [],
        }],
    }
    store = WikiRepairStore(str(tmp_path), str(tmp_path))
    plan = store.create(health)
    for item in plan["items"]:
        if item["execution"] == "ai":
            item["status"] = "ready"
    store.save(plan)
    applied = store.apply(plan["plan_id"])

    assert store.get(plan["plan_id"])["status"] == "partial"
    assert applied["applied_count"] == 1
    assert applied["pending_count"] == 2
    assert any(item["execution"] == "manual" and item["status"] == "pending" for item in applied["items"])
    assert any(item["execution"] == "ai" and item["status"] == "ready" for item in applied["items"])


def test_user_wiki_edit_uses_revision_and_marks_ai_page_mixed(tmp_path, monkeypatch):
    from service.kb_service import KBService

    vault = tmp_path / "note" / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    page_path = concepts / "RAG.md"
    page_path.write_text(
        "---\ntype: wiki_concept\ntitle: RAG\ngenerated_by: bobodan\ncontent_revision: 1\n---\n\n# RAG\n\nOld body",
        encoding="utf-8",
    )
    store = KBSQLiteStore(str(tmp_path))
    store.init_db()
    store.upsert_document(
        document_id="wiki-1", source="obsidian/wiki/concepts/RAG.md", path=str(page_path),
        kind="wiki_concept", title="RAG", content_hash="hash",
    )
    store.close()
    service = KBService(str(tmp_path))
    summary = type("Summary", (), {"to_dict": lambda self: {"updated_files": 1, "errors": []}})()
    monkeypatch.setattr(service, "_sync_registered_sources", lambda **kwargs: summary)

    updated = service.update_wiki_page(
        "wiki-1", expected_revision=1, title="RAG", body="My corrected body", tags=["RAG"], related=[], config={},
    )
    conflict = service.update_wiki_page(
        "wiki-1", expected_revision=1, title="RAG", body="Stale edit", tags=[], related=[], config={},
    )

    assert updated["ok"] is True
    assert updated["page"]["managed_by"] == "mixed"
    assert updated["page"]["content_revision"] == 2
    assert conflict["ok"] is False
    assert "changed" in conflict["error"]
