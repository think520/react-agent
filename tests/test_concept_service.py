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
