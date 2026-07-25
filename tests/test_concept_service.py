"""Tests for service.concept_service.ConceptService (P5E.6)."""

from unittest.mock import MagicMock

import pytest

from service.concept_service import ConceptService


@pytest.fixture
def svc(tmp_path):
    return ConceptService(str(tmp_path))


# ------------------------------------------------------------------
# Concepts CRUD
# ------------------------------------------------------------------


def test_upsert_concept_ok(svc):
    result = svc.upsert_concept(name="梯度下降", level="core", definition="优化算法")
    assert result["ok"] is True
    assert result["concept"]["name"] == "梯度下降"


def test_upsert_concept_name_required(svc):
    result = svc.upsert_concept(name="   ", level="core")
    assert result["ok"] is False
    assert result["error"] == "name_required"


def test_upsert_concept_invalid_level(svc):
    result = svc.upsert_concept(name="Valid", level="unknown")
    assert result["ok"] is False
    assert result["error"] == "invalid_level"


def test_get_concept_not_found(svc):
    result = svc.get_concept("does-not-exist")
    assert result["ok"] is False
    assert result["error"] == "concept_not_found"


def test_get_concept_includes_rels_and_evidence(svc):
    r1 = svc.upsert_concept(name="A", level="core")
    r2 = svc.upsert_concept(name="B", level="core")
    cid_a = r1["concept"]["concept_id"]
    cid_b = r2["concept"]["concept_id"]
    svc.add_relationship(from_id=cid_a, to_id=cid_b, rel_type="属于")

    result = svc.get_concept(cid_a)
    assert result["ok"] is True
    assert len(result["relationships"]) == 1
    assert result["relationships"][0]["from_name"] == "A"
    assert result["relationships"][0]["to_name"] == "B"


def test_agent_queries_only_reviewed_concepts_and_reports_status(svc):
    reviewed = svc.upsert_concept(name="Transformer", level="core")["concept"]
    svc._store.add_candidate(name="Unreviewed candidate", source_doc_id="doc-1")

    status = svc.get_status()
    search = svc.search("Transform")

    assert status["concept_count"] == 1
    assert status["pending_count"] == 1
    assert [item["concept_id"] for item in search["concepts"]] == [reviewed["concept_id"]]
    assert all(item["name"] != "Unreviewed candidate" for item in search["concepts"])


def test_neighbors_return_structured_evidence_status_and_chunk_id(svc):
    first = svc.upsert_concept(name="Transformer", level="core")["concept"]
    second = svc.upsert_concept(name="Attention", level="core")["concept"]
    relation = svc.add_relationship(
        from_id=first["concept_id"],
        to_id=second["concept_id"],
        rel_type="user:uses",
    )["relationship"]
    svc._store.add_evidence(
        rel_id=relation["rel_id"],
        document_id="doc-1",
        chunk_id="chunk-1",
        excerpt="Transformer uses attention.",
    )

    result = svc.neighbors(concept="Transformer")

    assert result["ok"] is True
    assert result["relationships"][0]["evidence_status"] == "valid"
    assert result["relationships"][0]["evidence"][0]["chunk_id"] == "chunk-1"


def _add_document_evidence(svc, *, document_id, chunk_id, excerpt):
    first = svc.upsert_concept(name=f"First {document_id}", level="core")["concept"]
    second = svc.upsert_concept(name=f"Second {document_id}", level="core")["concept"]
    relation = svc.add_relationship(
        from_id=first["concept_id"],
        to_id=second["concept_id"],
        rel_type="user:uses",
    )["relationship"]
    return svc._store.add_evidence(
        rel_id=relation["rel_id"],
        document_id=document_id,
        chunk_id=chunk_id,
        excerpt=excerpt,
    )


def test_refresh_document_evidence_keeps_existing_chunk_valid(svc):
    evidence = _add_document_evidence(
        svc,
        document_id="doc-existing",
        chunk_id="chunk-current",
        excerpt="Current source text.",
    )
    svc._store.update_evidence_location(
        evidence["evidence_id"],
        chunk_id="chunk-current",
        location_stale=True,
    )

    result = svc.refresh_document_evidence(
        "doc-existing",
        [{"id": "chunk-current", "text": "Updated source text."}],
    )
    stored = svc._store.evidence_for_document("doc-existing")[0]

    assert result == {"ok": True, "repaired": 0, "stale": 0}
    assert stored["chunk_id"] == "chunk-current"
    assert stored["location_stale"] == 0


def test_refresh_document_evidence_repairs_chunk_from_excerpt(svc):
    _add_document_evidence(
        svc,
        document_id="doc-repaired",
        chunk_id="chunk-old",
        excerpt="Attention assigns a weight to each input token.",
    )

    result = svc.refresh_document_evidence(
        "doc-repaired",
        [{
            "id": "chunk-new",
            "text": "In this lesson, Attention assigns a weight to each input token.",
        }],
    )
    stored = svc._store.evidence_for_document("doc-repaired")[0]

    assert result == {"ok": True, "repaired": 1, "stale": 0}
    assert stored["chunk_id"] == "chunk-new"
    assert stored["location_stale"] == 0


def test_refresh_document_evidence_marks_unmatched_source_stale(svc):
    _add_document_evidence(
        svc,
        document_id="doc-changed",
        chunk_id="chunk-old",
        excerpt="This source text no longer exists.",
    )

    result = svc.refresh_document_evidence(
        "doc-changed",
        [{"id": "chunk-new", "text": "Completely different content."}],
    )
    stored = svc._store.evidence_for_document("doc-changed")[0]

    assert result == {"ok": True, "repaired": 0, "stale": 1}
    assert stored["chunk_id"] == "chunk-old"
    assert stored["location_stale"] == 1


def test_deleted_document_evidence_is_marked_stale(svc):
    _add_document_evidence(
        svc,
        document_id="doc-deleted",
        chunk_id="chunk-deleted",
        excerpt="Deleted source text.",
    )

    result = svc.mark_document_evidence_stale("doc-deleted")
    stored = svc._store.evidence_for_document("doc-deleted")[0]

    assert result == {"ok": True, "stale": 1}
    assert stored["chunk_id"] == "chunk-deleted"
    assert stored["location_stale"] == 1


def test_path_returns_shortest_reviewed_relationship_path(svc):
    first = svc.upsert_concept(name="A", level="core")["concept"]
    middle = svc.upsert_concept(name="B", level="core")["concept"]
    target = svc.upsert_concept(name="C", level="core")["concept"]
    svc.add_relationship(
        from_id=first["concept_id"], to_id=middle["concept_id"], rel_type="user:step"
    )
    svc.add_relationship(
        from_id=middle["concept_id"], to_id=target["concept_id"], rel_type="user:step"
    )

    result = svc.path(from_concept="A", to_concept="C")

    assert result["found"] is True
    assert [item["name"] for item in result["concepts"]] == ["A", "B", "C"]
    assert len(result["relationships"]) == 2


def test_delete_concept_ok(svc):
    c = svc.upsert_concept(name="要删除", level="detail")
    cid = c["concept"]["concept_id"]
    assert svc.delete_concept(cid)["ok"] is True
    assert svc.get_concept(cid)["ok"] is False


def test_delete_concept_not_found(svc):
    result = svc.delete_concept("ghost-id")
    assert result["ok"] is False
    assert result["error"] == "concept_not_found"


# ------------------------------------------------------------------
# Relationships
# ------------------------------------------------------------------


def _two(svc):
    a = svc.upsert_concept(name="节点A", level="core")["concept"]
    b = svc.upsert_concept(name="节点B", level="core")["concept"]
    return a, b


def test_add_relationship_ok(svc):
    a, b = _two(svc)
    result = svc.add_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="前置知识")
    assert result["ok"] is True
    assert result["relationship"]["rel_type"] == "前置知识"


def test_relationship_lookup_does_not_include_extraction_run_fields(svc):
    a, b = _two(svc)
    relationship = svc.add_relationship(
        from_id=a["concept_id"],
        to_id=b["concept_id"],
        rel_type="前置知识",
    )["relationship"]

    stored = svc._store.get_relationship(relationship["rel_id"])

    assert stored is not None
    assert "warnings" not in stored
    assert "failed_sections" not in stored


def test_add_relationship_invalid_type(svc):
    a, b = _two(svc)
    result = svc.add_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="无效类型")
    assert result["ok"] is False
    assert "invalid_rel_type" in result["error"]


def test_add_relationship_user_custom_type(svc):
    a, b = _two(svc)
    result = svc.add_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="user:衍生")
    assert result["ok"] is True


def test_add_relationship_from_not_found(svc):
    b = svc.upsert_concept(name="只有B", level="core")["concept"]
    result = svc.add_relationship(from_id="ghost", to_id=b["concept_id"], rel_type="属于")
    assert result["ok"] is False
    assert result["error"] == "from_concept_not_found"


def test_add_relationship_to_not_found(svc):
    a = svc.upsert_concept(name="只有A", level="core")["concept"]
    result = svc.add_relationship(from_id=a["concept_id"], to_id="ghost", rel_type="属于")
    assert result["ok"] is False
    assert result["error"] == "to_concept_not_found"


def test_delete_relationship_ok(svc):
    a, b = _two(svc)
    rel = svc.add_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="对比")
    rid = rel["relationship"]["rel_id"]
    assert svc.delete_relationship(rid)["ok"] is True


def test_delete_relationship_not_found(svc):
    result = svc.delete_relationship("no-rel")
    assert result["ok"] is False
    assert result["error"] == "relationship_not_found"


# ------------------------------------------------------------------
# Candidates
# ------------------------------------------------------------------


def test_list_candidates_empty(svc):
    result = svc.list_candidates()
    assert result["ok"] is True
    assert result["candidates"] == []
    assert result["count"] == 0


def test_list_candidates_can_filter_by_source_document(svc):
    svc._store.add_candidate(name="文档 A 概念", source_doc_id="doc-a")
    svc._store.add_candidate(name="文档 B 概念", source_doc_id="doc-b")

    result = svc.list_candidates(source_doc_id="doc-a")

    assert result["ok"] is True
    assert [item["name"] for item in result["candidates"]] == ["文档 A 概念"]


def test_confirm_candidate_creates_concept(svc):
    # Manually add a candidate via the underlying store
    store = svc._store
    cand = store.add_candidate(
        name="Attention机制", level="core", confidence="high",
        definition="注意力机制", excerpt="..."
    )
    cid = cand["candidate_id"]

    result = svc.confirm_candidate(cid)
    assert result["ok"] is True
    assert result["concept"]["name"] == "Attention机制"

    # Candidate should now be confirmed, not in pending list
    pending = svc.list_candidates(status="pending")
    assert all(c["name"] != "Attention机制" for c in pending["candidates"])


def test_confirm_candidate_with_suggested_rels(svc):
    """Confirm creates relationships where the target concept already exists."""
    # Pre-create the target concept
    target = svc.upsert_concept(name="深度学习", level="cluster")["concept"]

    store = svc._store
    cand = store.add_candidate(
        name="Transformer",
        level="core",
        confidence="high",
        definition="自注意力架构",
        suggested_rels=[{"rel_type": "属于", "to_name": "深度学习"}],
    )
    result = svc.confirm_candidate(cand["candidate_id"])
    assert result["ok"] is True
    assert len(result["relationships"]) == 1
    assert result["relationships"][0]["to_id"] == target["concept_id"]


def test_batch_confirmation_creates_candidate_to_candidate_relationship(svc):
    first = svc._store.add_candidate(
        name="提示词",
        source_doc_id="doc-prompt",
        suggested_rels=[{
            "rel_type": "优化",
            "to_name": "模型输出",
            "excerpt": "提示词可以优化模型输出",
        }],
    )
    second = svc._store.add_candidate(name="模型输出", source_doc_id="doc-prompt")

    result = svc.confirm_candidates([first["candidate_id"], second["candidate_id"]])

    assert result["ok"] is True
    assert len(result["concepts"]) == 2
    assert len(result["relationships"]) == 1
    assert result["relationships"][0]["rel_type"] == "优化"


def test_existing_relationship_accepts_evidence_from_another_document(svc):
    first = svc._store.add_candidate(
        name="提示词",
        source_doc_id="doc-a",
        source_doc_title="文档 A",
        suggested_rels=[{
            "rel_type": "优化",
            "to_name": "模型输出",
            "excerpt": "文档 A 说明提示词可以优化模型输出",
        }],
    )
    second = svc._store.add_candidate(name="模型输出", source_doc_id="doc-a")
    svc.confirm_candidates([first["candidate_id"], second["candidate_id"]])

    repeated = svc._store.add_candidate(
        name="提示词",
        source_doc_id="doc-b",
        source_doc_title="文档 B",
        suggested_rels=[{
            "rel_type": "优化",
            "to_name": "模型输出",
            "excerpt": "文档 B 也说明提示词影响模型输出质量",
        }],
    )
    svc.confirm_candidate(repeated["candidate_id"])

    relationships = svc._store.list_relationships()
    assert len(relationships) == 1
    evidence = svc._store.evidence_for_relationship(relationships[0]["rel_id"])
    assert {item["document_id"] for item in evidence} == {"doc-a", "doc-b"}


def test_batch_confirmation_respects_cancelled_relationship(svc):
    first = svc._store.add_candidate(
        name="Few-shot",
        source_doc_id="doc-cancel",
        suggested_rels=[{"rel_type": "示例", "to_name": "提示词"}],
    )
    second = svc._store.add_candidate(name="提示词", source_doc_id="doc-cancel")

    result = svc.confirm_candidates(
        [first["candidate_id"], second["candidate_id"]],
        relation_edits=[{
            "candidate_id": first["candidate_id"],
            "index": 0,
            "enabled": False,
            "rel_type": "示例",
            "direction": "outgoing",
        }],
    )

    assert result["ok"] is True
    assert result["relationships"] == []


def test_section_extraction_retries_failed_chapter_and_keeps_partial_result(svc):
    class SectionProvider:
        failed_calls = 0

        def complete(self, messages):
            prompt = messages[0]["content"]
            if "章节：失败章" in prompt:
                self.failed_calls += 1
                raise RuntimeError("chapter timeout")
            if "只扫描当前章节" in prompt:
                return MagicMock(content='{"core_concepts":[{"name":"提示词","definition":"输入指令","confidence":"high","excerpt":"提示词"},{"name":"模型输出","definition":"模型响应","confidence":"high","excerpt":"模型输出"}],"detail_concepts":[],"tags":[]}')
            return MagicMock(content='{"relationships":[{"from":"提示词","to":"模型输出","rel_type":"影响","excerpt":"提示词影响模型输出"}]}')

    provider = SectionProvider()
    result = svc.extract_from_document(
        document_id="doc-sections",
        document_title="分章节测试",
        content="备用正文",
        sections=[
            {"chunk_id": "c1", "heading": "失败章", "text": "会超时"},
            {"chunk_id": "c2", "heading": "成功章", "text": "提示词影响模型输出"},
        ],
        llm_provider=provider,
    )

    assert result["ok"] is True
    assert result["stored"] == 2
    assert len(result["failed_sections"]) == 1
    assert provider.failed_calls == 2
    assert result["warnings"]


def test_quality_gate_runs_only_one_targeted_supplement(svc):
    class SupplementProvider:
        calls = 0

        def complete(self, messages):
            self.calls += 1
            if "第一次章节扫描" in messages[0]["content"]:
                return MagicMock(content='{"core_concepts":[{"name":"上下文","definition":"输入上下文","confidence":"high","excerpt":"上下文"}],"detail_concepts":[],"tags":[]}')
            return MagicMock(content='{"core_concepts":[{"name":"提示词","definition":"输入指令","confidence":"high","excerpt":"提示词"}],"detail_concepts":[],"tags":[]}')

    provider = SupplementProvider()
    result = svc.extract_from_document(
        document_id="doc-supplement",
        document_title="补提测试",
        content="提示词和上下文共同构成模型输入。",
        llm_provider=provider,
    )

    assert result["ok"] is True
    assert provider.calls == 2
    assert result["supplemented"] is True
    assert result["quality"]["failure_type"] == "relationships"


def test_confirm_candidate_not_found(svc):
    result = svc.confirm_candidate("ghost-cand")
    assert result["ok"] is False
    assert result["error"] == "candidate_not_found"


def test_confirm_candidate_not_pending(svc):
    store = svc._store
    cand = store.add_candidate(name="已确认", confidence="high")
    store.update_candidate_status(cand["candidate_id"], "confirmed")

    result = svc.confirm_candidate(cand["candidate_id"])
    assert result["ok"] is False
    assert result["error"] == "candidate_not_pending"


def test_reject_candidate(svc):
    store = svc._store
    cand = store.add_candidate(name="要拒绝的", confidence="medium")
    result = svc.reject_candidate(cand["candidate_id"], suppress_days=7)
    assert result["ok"] is True

    # Should not appear in pending list (suppressed)
    pending = svc.list_candidates()
    assert all(c["name"] != "要拒绝的" for c in pending["candidates"])


def test_reject_candidate_not_found(svc):
    result = svc.reject_candidate("ghost", suppress_days=0)
    assert result["ok"] is False
    assert result["error"] == "candidate_not_found"


def test_demote_candidate_to_label(svc):
    store = svc._store
    cand = store.add_candidate(name="标签化", confidence="low")
    result = svc.demote_candidate_to_label(cand["candidate_id"])
    assert result["ok"] is True

    fetched = store.get_candidate(cand["candidate_id"])
    assert fetched["status"] == "label"


# ------------------------------------------------------------------
# Graph state
# ------------------------------------------------------------------


def test_get_graph_state_ok(svc):
    svc.upsert_concept(name="图节点", level="core")
    result = svc.get_graph_state()
    assert result["ok"] is True
    assert any(c["name"] == "图节点" for c in result["concepts"])


def test_get_subgraph_not_found(svc):
    result = svc.get_subgraph("no-concept")
    assert result["ok"] is False
    assert result["error"] == "concept_not_found"


def test_get_subgraph_ok(svc):
    a = svc.upsert_concept(name="Root", level="core")["concept"]
    b = svc.upsert_concept(name="Child", level="detail")["concept"]
    svc.add_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="组成部分")

    result = svc.get_subgraph(a["concept_id"])
    assert result["ok"] is True
    names = {c["name"] for c in result["concepts"]}
    assert "Root" in names
    assert "Child" in names


# ------------------------------------------------------------------
# Positions
# ------------------------------------------------------------------


def test_save_positions_ok(svc):
    c = svc.upsert_concept(name="位置", level="core")["concept"]
    result = svc.save_positions([{"concept_id": c["concept_id"], "x": 1.0, "y": 2.0}])
    assert result["ok"] is True
    assert result["saved"] == 1


# ------------------------------------------------------------------
# extract_from_document (mocked LLM)
# ------------------------------------------------------------------


def test_extract_from_document_ok(svc):
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(
        content="""
```json
{
  "core_concepts": [
    {"name": "卷积", "definition": "特征提取操作", "confidence": "high", "excerpt": "卷积用于..."}
  ],
  "detail_concepts": [],
  "relationships": [],
  "tags": ["CNN", "特征提取"]
}
```
""",
        tool_calls=[],
    )

    result = svc.extract_from_document(
        document_id="doc-test",
        document_title="CNN教材",
        content="卷积神经网络利用卷积操作提取特征...",
        llm_provider=mock_llm,
    )
    assert result["ok"] is True
    assert result["stored"] == 1
    assert "CNN" in result["tags"]


def test_extraction_run_exposes_completed_status(svc):
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(
        content='{"core_concepts":[{"name":"注意力","definition":"加权聚合","confidence":"high","excerpt":"注意力机制"}],"detail_concepts":[],"relationships":[],"tags":[]}',
        tool_calls=[],
    )
    created = svc.create_extraction_run(
        document_id="doc-run",
        document_title="运行状态测试",
    )["run"]

    result = svc.execute_extraction_run(
        run_id=created["run_id"],
        document_id="doc-run",
        document_title="运行状态测试",
        content="注意力机制会对输入进行加权聚合。",
        llm_provider=mock_llm,
    )
    status = svc.get_extraction_run(created["run_id"])["run"]

    assert result["ok"] is True
    assert status["status"] == "completed_with_warnings"
    assert status["warnings"]
    assert status["stored_count"] == 1


def test_extraction_run_reuses_same_document_version_and_reports_review(svc):
    created = svc.create_extraction_run(
        document_id="doc-versioned",
        document_title="版本测试",
        content_version="hash-a",
    )
    reused_active = svc.create_extraction_run(
        document_id="doc-versioned",
        document_title="版本测试",
        content_version="hash-a",
    )

    assert created["started"] is True
    assert reused_active["started"] is False
    assert reused_active["run"]["run_id"] == created["run"]["run_id"]

    svc._store.add_candidate(
        name="版本候选",
        source_doc_id="doc-versioned",
    )
    svc._store.update_extraction_run(
        created["run"]["run_id"],
        status="completed",
        stored_count=1,
    )
    reused_completed = svc.create_extraction_run(
        document_id="doc-versioned",
        document_title="版本测试",
        content_version="hash-a",
    )
    statuses = svc.list_extraction_statuses()["documents"]

    assert reused_completed["started"] is False
    assert statuses["doc-versioned"]["status"] == "review"
    assert statuses["doc-versioned"]["pending_count"] == 1

    forced = svc.create_extraction_run(
        document_id="doc-versioned",
        document_title="版本测试",
        content_version="hash-a",
        force=True,
    )
    assert forced["started"] is True
    assert forced["run"]["run_id"] != created["run"]["run_id"]


def test_repeated_candidate_for_same_document_updates_in_place(svc):
    first = svc._store.add_candidate(
        name="重复概念",
        definition="旧定义",
        source_doc_id="doc-dedupe",
    )
    second = svc._store.add_candidate(
        name="重复概念",
        definition="新定义",
        source_doc_id="doc-dedupe",
    )

    candidates = svc.list_candidates(source_doc_id="doc-dedupe")["candidates"]
    assert first["candidate_id"] == second["candidate_id"]
    assert len(candidates) == 1
    assert candidates[0]["definition"] == "新定义"


def test_reviewed_candidate_decision_precedes_newer_archived_candidate(svc):
    reviewed = svc._store.add_candidate(name="已审查概念", source_doc_id="doc-history")
    svc._store.update_candidate_status(reviewed["candidate_id"], "confirmed")
    archived = svc._store.add_candidate(name="已审查概念", source_doc_id="doc-history")
    svc._store.update_candidate_status(archived["candidate_id"], "archived")

    selected = svc._store.get_candidate_by_document_and_name("doc-history", "已审查概念")

    assert selected is not None
    assert selected["candidate_id"] == reviewed["candidate_id"]
    assert selected["status"] == "confirmed"


def test_extraction_run_exposes_failure_reason(svc):
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = RuntimeError("provider unavailable")
    created = svc.create_extraction_run(
        document_id="doc-failed-run",
        document_title="失败运行",
    )["run"]

    svc.execute_extraction_run(
        run_id=created["run_id"],
        document_id="doc-failed-run",
        document_title="失败运行",
        content="测试内容",
        llm_provider=mock_llm,
    )
    status = svc.get_extraction_run(created["run_id"])["run"]

    assert status["status"] == "failed"
    assert status["error"] == "provider unavailable"


def test_extract_from_document_llm_error(svc):
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = RuntimeError("provider unavailable")

    result = svc.extract_from_document(
        document_id="doc-err",
        document_title="失败测试",
        content="...",
        llm_provider=mock_llm,
    )
    assert result["ok"] is False
