"""Tests for reviewed concept-map auto seeding in service.turn_policy."""

from core.prompt_blocks import CONCEPT_MAP_CONTEXT_HEADER, build_concept_map_seed_block
from service.concept_service import ConceptService
from service.evidence_policy import CitationPolicy, LocalEvidencePolicy
from service.turn_policy import prepare_turn


def test_prepare_turn_without_concept_db_does_not_create_db(tmp_path):
    turn = prepare_turn("什么是注意力机制？", workspace=str(tmp_path), config={})
    assert turn.concept_map_seed == ""
    assert turn.concept_map_context is None
    assert not (tmp_path / ".knowledge" / "concept_graph.db").exists()


def test_prepare_turn_matches_reviewed_concepts_ignores_candidates_and_respects_boundaries(tmp_path):
    svc = ConceptService(str(tmp_path))
    c_attn = svc.upsert_concept(name="Attention", level="core", definition="权重分配机制")["concept"]
    c_trans = svc.upsert_concept(name="Transformer", level="core", definition="自注意力架构")["concept"]
    c_ai = svc.upsert_concept(name="AI", level="core", definition="人工智能")["concept"]
    svc.add_relationship(
        from_id=c_attn["concept_id"],
        to_id=c_trans["concept_id"],
        rel_type="前置知识",
    )
    # Pending candidate must never be surfaced into auto-seed.
    svc._store.add_candidate(
        name="未审查概念",
        level="core",
        definition="尚未批准",
        source_doc_id="doc-1",
    )

    # Normal study turn matching reviewed concepts.
    turn = prepare_turn("为什么 Transformer 需要 Attention？", workspace=str(tmp_path), config={})
    assert CONCEPT_MAP_CONTEXT_HEADER in turn.concept_map_seed
    assert "Attention --[前置知识]--> Transformer" in turn.concept_map_seed
    assert "[S" not in turn.concept_map_seed
    assert turn.concept_map_context is not None
    assert {c["name"] for c in turn.concept_map_context["concepts"]} == {"Attention", "Transformer"}

    # Pending candidate must not match.
    cand_turn = prepare_turn("讲讲未审查概念", workspace=str(tmp_path), config={})
    assert cand_turn.concept_map_seed == ""
    assert cand_turn.concept_map_context is None

    # ASCII boundary guard: "AI" must not match "email" or "detail".
    false_ascii = prepare_turn("Please check my email detail", workspace=str(tmp_path), config={})
    assert false_ascii.concept_map_seed == ""
    true_ascii = prepare_turn("Explain AI basics", workspace=str(tmp_path), config={})
    assert true_ascii.concept_map_context is not None
    assert true_ascii.concept_map_context["root"]["concept_id"] == c_ai["concept_id"]

    # Practice / bypass turns skip concept-map seeding.
    practice_turn = prepare_turn("给我出几道关于 Transformer 的练习题", workspace=str(tmp_path), config={})
    assert practice_turn.concept_map_seed == ""
    bypass_turn = prepare_turn("不查资料讲讲 Transformer", workspace=str(tmp_path), config={})
    assert bypass_turn.concept_map_seed == ""


def test_concept_map_seed_never_substitutes_source_citations_or_evidence(tmp_path):
    svc = ConceptService(str(tmp_path))
    c1 = svc.upsert_concept(name="梯度下降", level="core", definition="一阶优化方法")["concept"]
    c2 = svc.upsert_concept(name="反向传播", level="core", definition="梯度计算算法")["concept"]
    svc.add_relationship(from_id=c2["concept_id"], to_id=c1["concept_id"], rel_type="前置知识")

    turn = prepare_turn("根据资料解释梯度下降", workspace=str(tmp_path), config={})
    assert turn.concept_map_seed != ""

    # CitationPolicy must reject fabricated [S123456] tags even when concept seed is present.
    citation_check = CitationPolicy(preset_text=turn.kb_seed).validate([], "参考 [S123456] 梯度下降。", retry_count=0)
    assert citation_check.allow is False

    # LocalEvidencePolicy must remain unsatisfied without rag_search.
    local_check = LocalEvidencePolicy().validate([], "梯度下降依赖反向传播。", retry_count=0)
    assert local_check.allow is False

    # Direct block builder check: no citation tags in block.
    block = build_concept_map_seed_block(turn.concept_map_context or {})
    assert "[S" not in block
