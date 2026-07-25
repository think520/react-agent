"""Tests for graph.concept_store.ConceptStore (P5E.6)."""

import time

import pytest

from graph.concept_store import ConceptStore


@pytest.fixture
def store(tmp_path):
    return ConceptStore(str(tmp_path / "concept_graph.db"))


# ------------------------------------------------------------------
# Schema / DDL
# ------------------------------------------------------------------


def test_schema_created(tmp_path):
    """ConceptStore creates all 5 tables without error."""
    s = ConceptStore(str(tmp_path / "schema_test.db"))
    # If DDL ran without raising, the store is functional
    assert s.pending_candidates_count() == 0


# ------------------------------------------------------------------
# Concepts CRUD
# ------------------------------------------------------------------


def test_upsert_concept_creates_and_returns(store):
    c = store.upsert_concept(name="梯度下降", level="core", definition="优化算法")
    assert c["name"] == "梯度下降"
    assert c["level"] == "core"
    assert c["definition"] == "优化算法"
    assert c["concept_id"].startswith("c-")


def test_upsert_concept_idempotent(store):
    c1 = store.upsert_concept(name="Adam", level="detail")
    c2 = store.upsert_concept(concept_id=c1["concept_id"], name="Adam", level="core", definition="自适应矩估计")
    assert c2["concept_id"] == c1["concept_id"]
    assert c2["level"] == "core"
    assert c2["definition"] == "自适应矩估计"


def test_upsert_concept_aliases_and_topic_ids(store):
    c = store.upsert_concept(
        name="BP",
        aliases=["反向传播", "backprop"],
        topic_ids=["cluster-nn"],
    )
    assert "反向传播" in c["aliases"]
    assert "cluster-nn" in c["topic_ids"]


def test_get_concept_not_found(store):
    assert store.get_concept("nonexistent") is None


def test_get_concept_by_name_case_insensitive(store):
    store.upsert_concept(name="ReLU")
    c = store.get_concept_by_name("relu")
    assert c is not None
    assert c["name"] == "ReLU"


def test_list_concepts_filter_by_level(store):
    store.upsert_concept(name="神经网络", level="cluster")
    store.upsert_concept(name="感知机", level="core")
    store.upsert_concept(name="激活函数", level="detail")

    clusters = store.list_concepts(level="cluster")
    cores = store.list_concepts(level="core")
    assert all(c["level"] == "cluster" for c in clusters)
    assert all(c["level"] == "core" for c in cores)


def test_list_concepts_filter_by_topic_id(store):
    cluster = store.upsert_concept(name="深度学习", level="cluster")
    c1 = store.upsert_concept(name="CNN", topic_ids=[cluster["concept_id"]])
    c2 = store.upsert_concept(name="RNN", topic_ids=[cluster["concept_id"]])
    store.upsert_concept(name="决策树")  # different topic

    result = store.list_concepts(topic_id=cluster["concept_id"])
    names = {c["name"] for c in result}
    assert "CNN" in names
    assert "RNN" in names
    assert "决策树" not in names


def test_delete_concept(store):
    c = store.upsert_concept(name="要删除的", level="core")
    deleted = store.delete_concept(c["concept_id"])
    assert deleted is True
    assert store.get_concept(c["concept_id"]) is None


def test_delete_concept_not_found(store):
    assert store.delete_concept("no-such-id") is False


# ------------------------------------------------------------------
# Relationships
# ------------------------------------------------------------------


def _two_concepts(store):
    a = store.upsert_concept(name="概念A", level="core")
    b = store.upsert_concept(name="概念B", level="core")
    return a, b


def test_upsert_relationship_creates_and_returns(store):
    a, b = _two_concepts(store)
    rel = store.upsert_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="属于")
    assert rel["from_id"] == a["concept_id"]
    assert rel["to_id"] == b["concept_id"]
    assert rel["rel_type"] == "属于"
    assert rel["rel_id"].startswith("r-")


def test_relationships_for_concept_both_directions(store):
    a, b = _two_concepts(store)
    store.upsert_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="前置知识")
    rels_a = store.relationships_for_concept(a["concept_id"])
    rels_b = store.relationships_for_concept(b["concept_id"])
    assert len(rels_a) == 1
    assert len(rels_b) == 1


def test_delete_relationship(store):
    a, b = _two_concepts(store)
    rel = store.upsert_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="对比")
    deleted = store.delete_relationship(rel["rel_id"])
    assert deleted is True
    assert store.get_relationship(rel["rel_id"]) is None


def test_delete_relationship_not_found(store):
    assert store.delete_relationship("no-such-rel") is False


# ------------------------------------------------------------------
# Evidence
# ------------------------------------------------------------------


def test_add_evidence_and_retrieve(store):
    a, b = _two_concepts(store)
    rel = store.upsert_relationship(from_id=a["concept_id"], to_id=b["concept_id"], rel_type="应用于")
    ev = store.add_evidence(
        rel_id=rel["rel_id"],
        document_id="doc-001",
        document_title="深度学习教材",
        excerpt="梯度下降被应用于...",
        location_type="page",
        location_value="42",
    )
    assert ev["evidence_id"].startswith("e-")
    assert ev["document_id"] == "doc-001"

    items = store.evidence_for_relationship(rel["rel_id"])
    assert len(items) == 1
    assert items[0]["excerpt"] == "梯度下降被应用于..."


def test_evidence_empty_for_unknown_rel(store):
    assert store.evidence_for_relationship("unknown-rel") == []


# ------------------------------------------------------------------
# Candidates
# ------------------------------------------------------------------


def test_add_candidate_and_list_pending(store):
    c = store.add_candidate(name="Transformer", level="core", confidence="high")
    assert c["status"] == "pending"
    assert c["candidate_id"].startswith("cand-")

    pending = store.list_candidates(status="pending")
    assert any(p["name"] == "Transformer" for p in pending)


def test_candidate_sorted_by_confidence(store):
    store.add_candidate(name="低置信", level="detail", confidence="low")
    store.add_candidate(name="高置信", level="core", confidence="high")
    store.add_candidate(name="中置信", level="core", confidence="medium")

    pending = store.list_candidates()
    confidences = [p["confidence"] for p in pending]
    # high should come first
    assert confidences[0] == "high"


def test_update_candidate_status(store):
    c = store.add_candidate(name="BERT", confidence="high")
    ok = store.update_candidate_status(c["candidate_id"], "confirmed")
    assert ok is True
    updated = store.get_candidate(c["candidate_id"])
    assert updated["status"] == "confirmed"


def test_candidate_suppressed_not_in_pending(store):
    c = store.add_candidate(name="暂时压制", confidence="medium")
    suppress_until = time.time() + 3600  # 1 hour from now
    store.update_candidate_status(c["candidate_id"], "pending", suppressed_until=suppress_until)
    pending = store.list_candidates(status="pending")
    assert not any(p["name"] == "暂时压制" for p in pending)


def test_pending_candidates_count(store):
    store.add_candidate(name="候选1", confidence="high")
    store.add_candidate(name="候选2", confidence="low")
    assert store.pending_candidates_count() == 2

    c3 = store.add_candidate(name="候选3", confidence="medium")
    store.update_candidate_status(c3["candidate_id"], "confirmed")
    assert store.pending_candidates_count() == 2


def test_candidate_suggested_rels_roundtrip(store):
    rels = [{"rel_type": "属于", "to_name": "机器学习"}]
    c = store.add_candidate(name="SVM", suggested_rels=rels)
    fetched = store.get_candidate(c["candidate_id"])
    assert fetched["suggested_rels"] == rels


# ------------------------------------------------------------------
# Positions
# ------------------------------------------------------------------


def test_save_and_get_positions(store):
    c = store.upsert_concept(name="位置测试")
    positions = [{"concept_id": c["concept_id"], "x": 123.4, "y": 56.7}]
    store.save_positions(positions)
    saved = store.get_positions()
    assert c["concept_id"] in saved
    assert saved[c["concept_id"]]["x"] == pytest.approx(123.4)
    assert saved[c["concept_id"]]["y"] == pytest.approx(56.7)


def test_save_positions_upsert(store):
    c = store.upsert_concept(name="位置更新")
    store.save_positions([{"concept_id": c["concept_id"], "x": 1.0, "y": 2.0}])
    store.save_positions([{"concept_id": c["concept_id"], "x": 99.0, "y": 88.0}])
    saved = store.get_positions()
    assert saved[c["concept_id"]]["x"] == pytest.approx(99.0)


def test_positions_view_id_isolation(store):
    c = store.upsert_concept(name="视图隔离")
    store.save_positions([{"concept_id": c["concept_id"], "x": 10.0, "y": 20.0}], view_id="view_a")
    store.save_positions([{"concept_id": c["concept_id"], "x": 30.0, "y": 40.0}], view_id="view_b")
    a = store.get_positions(view_id="view_a")
    b = store.get_positions(view_id="view_b")
    assert a[c["concept_id"]]["x"] == pytest.approx(10.0)
    assert b[c["concept_id"]]["x"] == pytest.approx(30.0)


# ------------------------------------------------------------------
# get_graph_state
# ------------------------------------------------------------------


def test_get_graph_state_empty(store):
    state = store.get_graph_state()
    assert state["concepts"] == []
    assert state["relationships"] == []
    assert state["pending_count"] == 0


def test_get_graph_state_with_data(store):
    a = store.upsert_concept(name="集群", level="cluster")
    b = store.upsert_concept(name="核心概念", level="core", topic_ids=[a["concept_id"]])
    store.upsert_relationship(from_id=b["concept_id"], to_id=a["concept_id"], rel_type="属于")
    store.add_candidate(name="候选A", confidence="high")

    state = store.get_graph_state(include_candidates=True)
    concept_names = {c["name"] for c in state["concepts"]}
    assert "集群" in concept_names
    assert "核心概念" in concept_names
    assert len(state["relationships"]) == 1
    assert state["pending_count"] == 1
    assert len(state["candidates"]) == 1


def test_get_graph_state_positions_injected(store):
    c = store.upsert_concept(name="有位置")
    store.save_positions([{"concept_id": c["concept_id"], "x": 5.0, "y": 6.0}])
    state = store.get_graph_state()
    node = next(n for n in state["concepts"] if n["concept_id"] == c["concept_id"])
    assert node["x"] == pytest.approx(5.0)
    assert node["y"] == pytest.approx(6.0)


# ------------------------------------------------------------------
# get_subgraph
# ------------------------------------------------------------------


def test_get_subgraph_not_found(store):
    assert store.get_subgraph("no-such-id") is None


def test_get_subgraph_returns_neighbours(store):
    root = store.upsert_concept(name="根节点", level="core")
    n1 = store.upsert_concept(name="邻居1", level="detail")
    n2 = store.upsert_concept(name="邻居2", level="detail")
    store.upsert_concept(name="无关节点", level="detail")

    rel1 = store.upsert_relationship(from_id=root["concept_id"], to_id=n1["concept_id"], rel_type="组成部分")
    store.upsert_relationship(from_id=n2["concept_id"], to_id=root["concept_id"], rel_type="前置知识")

    # Add evidence on rel1
    store.add_evidence(rel_id=rel1["rel_id"], document_id="doc-x", excerpt="...")

    sub = store.get_subgraph(root["concept_id"])
    assert sub is not None
    names = {c["name"] for c in sub["concepts"]}
    assert "根节点" in names
    assert "邻居1" in names
    assert "邻居2" in names
    assert "无关节点" not in names
    assert len(sub["relationships"]) == 2
    assert len(sub["evidence"]) == 1
