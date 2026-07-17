import os

from rag.sqlite_store import KBSQLiteStore
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
