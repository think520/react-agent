"""W2-EVID-01：引用标签与运行时引用门禁。

门禁只回答一个问题：回答里写的每个 [Sxxxxxx] 是否对应本轮真实拿到的证据。
它不判断「引用是否支持结论」—— 那是后续的风险信号，不在这里冒充保证。
"""

from __future__ import annotations

from core.prompt_blocks import build_kb_seed_block
from rag.citations import cite_label, cited_labels, format_search_results, hit_source_id
from service.evidence_policy import CitationPolicy, CombinedResponsePolicy, LocalEvidencePolicy

HIT = {"chunk_id": "doc-1#0", "document_id": "doc-1", "source": "algo.md", "text": "Dijkstra 要求非负权。"}
LABEL = cite_label("doc-1#0")


def _rag(*hits):
    return [{"name": "rag_search", "ok": True, "data": {"results": list(hits), "evidence_status": "found"}}]


def test_labels_are_deterministic_and_shared_by_every_surface():
    assert cite_label("doc-1#0") == cite_label("doc-1#0")
    assert cite_label("doc-1#0") != cite_label("doc-1#1")
    assert hit_source_id({"source": "legacy.md"}) == "legacy.md"
    # 工具结果与预检索块给同一片段同一个标签 —— 否则模型引用预检索片段会被误判。
    assert f"[{LABEL}]" in format_search_results([HIT])
    assert f"[{LABEL}]" in build_kb_seed_block([HIT])


def test_cited_labels_ignores_ordinary_brackets():
    text = f"贪心 [{LABEL}]，数组下标 a[1]，Markdown [链接](x)，再次 [{LABEL}]。"
    assert cited_labels(text) == [LABEL]


def test_real_citation_passes():
    decision = CitationPolicy().validate(_rag(HIT), f"Dijkstra 要求非负权 [{LABEL}]。", 0)
    assert decision.allow


def test_answer_without_citations_is_not_this_policys_business():
    """有没有证据由 LocalEvidencePolicy 管；这里只核对写出来的标签。"""
    assert CitationPolicy().validate([], "这是一般性的解释。", 0).allow


def test_fabricated_citation_asks_for_a_rewrite_first():
    decision = CitationPolicy().validate(_rag(HIT), "Dijkstra 支持负权 [S1]。", 0)
    assert not decision.allow
    assert "[S1]" in decision.correction_prompt


def test_fabricated_citation_is_stripped_after_retries_without_losing_the_answer():
    text = f"Dijkstra 要求非负权 [{LABEL}]。它也能处理负权 [Sdeadbe]。"
    decision = CitationPolicy().validate(_rag(HIT), text, CitationPolicy.max_retries)
    assert not decision.allow
    assert f"[{LABEL}]" in decision.fallback_content, "real citations must survive"
    assert "[Sdeadbe]" not in decision.fallback_content
    assert "已移除 1 处" in decision.fallback_content


def test_citation_from_a_failed_search_is_not_evidence():
    history = [{"name": "rag_search", "ok": False, "data": {"results": [HIT]}}]
    assert not CitationPolicy().validate(history, f"x [{LABEL}]", 0).allow


def test_preset_evidence_counts_as_this_turns_evidence():
    seed = build_kb_seed_block([HIT])
    assert CitationPolicy(preset_text=seed).validate([], f"x [{LABEL}]", 0).allow


def test_web_research_snapshots_are_allowed():
    history = [{"name": "web_research", "ok": True, "data": {"sources": [{"source_id": "snap-1"}]}}]
    assert CitationPolicy().validate(history, f"x [{cite_label('snap-1')}]", 0).allow


def test_citation_from_another_turn_is_rejected():
    """上一轮的标签不在本轮 tool_history 里：资料可能已经变了，不能沿用。"""
    old = cite_label("doc-1#old-version")
    assert not CitationPolicy().validate(_rag(HIT), f"x [{old}]", 0).allow


def test_changed_material_changes_the_label():
    """chunk_id 由内容派生：资料改写后旧片段的标签不再对应任何当前证据。"""
    from rag.chunker_v2 import _make_chunk_id

    before = cite_label(_make_chunk_id("algo.md", 0, "Dijkstra 要求非负权。"))
    after_hit = {**HIT, "chunk_id": _make_chunk_id("algo.md", 0, "Dijkstra 要求边权非负，否则用 Bellman-Ford。")}
    assert not CitationPolicy().validate(_rag(after_hit), f"x [{before}]", 0).allow


def test_combined_policy_retries_citation_after_local_evidence_passes():
    guard = CombinedResponsePolicy(LocalEvidencePolicy(), CitationPolicy())
    decision = guard.validate(_rag(HIT), "Dijkstra 支持负权 [S1]。", 0)
    assert not decision.allow and decision.correction_prompt
