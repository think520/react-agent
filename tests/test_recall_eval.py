"""W2 G4：召回评测集 —— 先把**度量**做对，再谈调权重。

为什么先做度量：路线图要求「RRF 权重由数据决定」，而在没有 hit@5 / MRR 基线之前，
"检索变好了"只是感觉。这里交付纯函数度量 + 一个能对着**任意工作区**跑的评测入口，
并用一份**合成语料**做端到端自检（真实资料库的内容不进仓库、不进夹具）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rag.recall_eval import (
    EvalCase,
    RetrievalHit,
    evaluate,
    evaluate_workspace,
    format_report,
    hit_at_k,
    judge_hybrid_decision,
    load_cases,
    main as recall_main,
    reciprocal_rank,
    source_matches,
    summarize,
)

EVAL_DIR = Path(__file__).parent / "eval"
SAMPLE_CORPUS = EVAL_DIR / "sample_corpus"
SAMPLE_CASES = EVAL_DIR / "recall_cases.jsonl"
SAMPLE_CORPUS_V2 = EVAL_DIR / "sample_corpus_v2"
SAMPLE_CASES_V2 = EVAL_DIR / "recall_cases_v2.jsonl"


# --- 度量本身 ---------------------------------------------------------------


def test_hit_at_k_respects_the_cutoff():
    assert hit_at_k({"b"}, ["a", "b", "c"], 2) is True
    assert hit_at_k({"c"}, ["a", "b", "c"], 2) is False
    assert hit_at_k({"c"}, ["a", "b", "c"], 3) is True
    assert hit_at_k(set(), ["a"], 5) is False


def test_reciprocal_rank_is_honest_about_position_and_absence():
    assert reciprocal_rank({"a"}, ["a", "b"]) == 1.0
    assert reciprocal_rank({"b"}, ["a", "b"]) == 0.5
    assert reciprocal_rank({"c"}, ["a", "b", "c"]) == pytest.approx(1 / 3)
    assert reciprocal_rank({"z"}, ["a", "b"]) == 0.0


def test_evaluate_aggregates_and_reports_what_mode_really_ran():
    cases = [EvalCase(query="q1", expect_sources=["a.md"]), EvalCase(query="q2", expect_sources=["b.md"])]

    def retrieve(query, mode):
        if query == "q1":
            return ["a.md", "x.md"], mode
        return ["x.md"], mode

    report = evaluate(cases, retrieve, modes=["fts_only"], k=5)

    assert report["fts_only"]["cases"] == 2
    assert report["fts_only"]["hits"] == 1
    assert report["fts_only"]["hit_at_k"] == 0.5
    assert report["fts_only"]["mrr"] == pytest.approx(0.5)


def test_a_downgraded_mode_is_reported_not_hidden():
    """要了 vector 却只能跑 fts_only —— 报告里必须看得见，不能假装跑过。"""
    def retrieve(query, mode):
        return ["a.md"], "fts_only"

    report = evaluate([EvalCase(query="q", expect_sources=["a.md"])], retrieve, modes=["vector"], k=5)

    assert report["vector"]["resolved_modes"] == {"fts_only": 1}, report["vector"]


def test_summarize_prints_a_readable_line_per_mode():
    def retrieve(query, mode):
        return ["a.md"], mode

    report = evaluate([EvalCase(query="q", expect_sources=["a.md"])], retrieve, modes=["fts_only", "hybrid"], k=5)
    text = summarize(report)

    assert "fts_only" in text and "hybrid" in text
    assert "hit@5" in text and "MRR" in text


# --- 用例文件 ---------------------------------------------------------------


def test_load_cases_reads_jsonl_and_keeps_expectations():
    cases = load_cases(str(SAMPLE_CASES))

    assert len(cases) == 5
    assert all(case.query and case.expect_sources for case in cases)
    assert any("Dijkstra" in case.query for case in cases)


def test_load_cases_refuses_a_case_without_an_expectation(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"query": "没有问题就没有期望"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_cases(str(bad))


# --- 端到端（合成语料） ------------------------------------------------------


@pytest.fixture
def sample_library(tmp_path):
    """把合成语料拷成一个临时资料库并建好索引（不碰真实资料库）。"""
    from obsidian.sync import sync_sources
    from service.library_service import LibraryService

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="EvalSample")
    inbox = root / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for path in SAMPLE_CORPUS.glob("*.md"):
        (inbox / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    sync_sources(
        workspace=str(root), vault_path=str(root), course_dir=str(root / "raw"), mode="full",
    )
    return root


def test_the_sample_corpus_is_retrievable_in_fts_and_hybrid(sample_library, monkeypatch):
    """合成语料上的真评测：fts_only 能命中，hybrid 至少不差，vector 如实降级。"""
    from unittest.mock import MagicMock

    from rag.retriever import clear_retrieval_cache, search_index_with_status

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    clear_retrieval_cache(str(sample_library))

    def retrieve(query, mode):
        results, status = search_index_with_status(
            str(sample_library), query=query, top_k=5, config={}, mode=mode,
        )
        sources = [os.path.basename(str(item.get("source") or "")) for item in results]
        return sources, str(status.get("retrieval_mode") or "")

    cases = load_cases(str(SAMPLE_CASES))
    report = evaluate(cases, retrieve, modes=["fts_only", "hybrid", "vector"], k=5)

    assert report["fts_only"]["hit_at_k"] == 1.0, report["fts_only"]
    assert report["fts_only"]["mrr"] == 1.0, report["fts_only"]
    # hybrid 在向量不可用时应该退化成 fts_only：命中率不能比它差，而且要**说出来**。
    assert report["hybrid"]["hit_at_k"] >= report["fts_only"]["hit_at_k"]
    assert "fts_only" in report["hybrid"]["resolved_modes"], report["hybrid"]
    # vector 单独要的时候，要么真跑，要么如实报告降级 —— 不能假装。
    assert report["vector"]["resolved_modes"], report["vector"]


# --- 盲区 A：让「真实库基线」可复现（用例运行时生成，正文不进仓库） -------------


def test_cases_can_be_generated_deterministically_from_a_workspace(sample_library):
    """审查盲区 A：0.720→1.000 这种数字必须能被人重跑，而不是只存在于对话里。"""
    from rag.recall_eval import cases_from_workspace

    first = cases_from_workspace(str(sample_library), limit=5)
    second = cases_from_workspace(str(sample_library), limit=5)

    assert first, "样例库里应当能生成用例"
    assert [(case.query, case.expect_sources) for case in first] == [
        (case.query, case.expect_sources) for case in second
    ], "同一个库两次生成必须一致（否则数字不可复现）"
    # 每条都要有期望，否则没法评分。
    assert all(case.expect_sources for case in first), first


def test_generating_cases_without_an_index_says_so(tmp_path):
    from rag.recall_eval import cases_from_workspace

    with pytest.raises(FileNotFoundError):
        cases_from_workspace(str(tmp_path), limit=3)


def test_the_generated_cases_are_actually_retrievable(sample_library, monkeypatch):
    """生成出来的用例要能真的命中 —— 否则这些数字没有意义。"""
    from unittest.mock import MagicMock

    from rag.recall_eval import cases_from_workspace
    from rag.retriever import clear_retrieval_cache, search_index_with_status

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    clear_retrieval_cache(str(sample_library))

    def retrieve(query, mode):
        results, status = search_index_with_status(
            str(sample_library), query=query, top_k=5, config={}, mode=mode,
        )
        return [os.path.basename(str(item.get("source") or "")) for item in results], str(
            status.get("retrieval_mode") or ""
        )

    cases = cases_from_workspace(str(sample_library), limit=5)
    report = evaluate(cases, retrieve, modes=["auto"], k=5)

    assert report["auto"]["hit_at_k"] == 1.0, report["auto"]


# --- L3 人工集：kind/source 分组与 CLI 配置覆盖（2026-10-17）

def test_cases_carry_kind_and_source_with_backward_compatible_defaults(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"query":"问一","expect_sources":["a.md"]}\n'
        '{"query":"问二","expect_sources":["b.md"],"kind":"paraphrase","source":"human"}\n',
        encoding="utf-8",
    )

    cases = load_cases(str(path))

    # 老用例没有新字段 → 必须仍然可用（向后兼容）。
    assert cases[0].kind == "keyword"
    assert cases[0].source == "generated"
    assert cases[1].kind == "paraphrase"
    assert cases[1].source == "human"


def test_unknown_case_kind_is_rejected(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text('{"query":"问","expect_sources":["a.md"],"kind":"vibes"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="kind"):
        load_cases(str(path))


def test_report_breaks_down_by_kind():
    from rag.recall_eval import EvalCase, evaluate, summarize

    cases = [
        EvalCase(query="关键词题", expect_sources=("a.md",), kind="keyword"),
        EvalCase(query="换述题", expect_sources=("b.md",), kind="paraphrase"),
    ]

    def retrieve(query, mode):
        if query == "关键词题":
            return (["a.md"], "fts_only")
        return ([], "fts_only")

    report = evaluate(cases, retrieve, modes=["auto"], k=5)

    assert report["auto"]["by_kind"]["keyword"]["hit_at_k"] == 1.0
    assert report["auto"]["by_kind"]["paraphrase"]["hit_at_k"] == 0.0
    assert report["auto"]["by_kind"]["paraphrase"]["cases"] == 1
    # 汇总文本要能让人一眼看到分组差别，而不是只有一个总数。
    text = summarize(report)
    assert "keyword" in text and "paraphrase" in text


def test_eval_config_can_switch_embedding_backend(monkeypatch):
    import rag.recall_eval as ev

    monkeypatch.setattr(
        "providers.factory.ProviderFactory.load_config",
        staticmethod(lambda path="config.yaml": {"rag": {"embedding_backend": "openai_compat"}}),
    )

    assert ev.load_eval_config(embedding_backend="local")["rag"]["embedding_backend"] == "local"
    assert ev.load_eval_config()["rag"]["embedding_backend"] == "openai_compat"


# --- W2-G4.2：相对路径消歧、片段级指标、冻结判据、v2 40 题语料 ---------------


def test_source_matches_disambiguates_relative_paths_and_preserves_basename():
    assert source_matches("algo/summary.md", "course/algo/summary.md") is True
    assert source_matches("algo/summary.md", "F:\\vault\\raw\\algo\\summary.md") is True
    assert source_matches("algo/summary.md", "course/ml/summary.md") is False
    # 不含 "/" 时保持按 basename 兼容旧用例
    assert source_matches("summary.md", "course/ml/summary.md") is True


def test_evaluate_computes_hit_at_1_3_k_and_chunk_level_metrics():
    cases = [
        EvalCase(
            query="q1",
            expect_sources=("algo/summary.md",),
            kind="keyword",
            expect_headings=("拓扑排序",),
            expect_snippets=("入度",),
        ),
        EvalCase(
            query="q2",
            expect_sources=("ml/summary.md",),
            kind="paraphrase",
            expect_headings=("召回与排序指标口径",),
        ),
        EvalCase(
            query="q3",
            expect_sources=("systems/sqlite_wal.md",),
            kind="paraphrase",
        ),
    ]

    def retrieve(query, mode):
        if query == "q1":
            return ([
                RetrievalHit(source="course/ml/summary.md", heading="其他小节", text="无关正文"),
                RetrievalHit(source="course/algo/summary.md", heading="拓扑排序与环路判定", text="计算顶点入度即可排课"),
            ], mode)
        if query == "q2":
            return ([
                RetrievalHit(source="course/ml/summary.md", heading="实验基线", text="随机种子固定"),
                RetrievalHit(source="course/ml/summary.md", heading="召回与排序指标口径", text="片段级命中率"),
            ], mode)
        return ([
            RetrievalHit(source="course/systems/sqlite_wal.md", heading="预写日志", text="并发读写"),
        ], mode)

    report = evaluate(cases, retrieve, modes=["hybrid"], k=5)
    m = report["hybrid"]
    assert m["hit_at_1"] == pytest.approx(2 / 3)
    assert m["hit_at_3"] == pytest.approx(1.0)
    assert m["hit_at_k"] == pytest.approx(1.0)
    assert m["chunk_cases"] == 2
    assert m["chunk_hits"] == 2
    assert m["chunk_hit_at_k"] == pytest.approx(1.0)
    # q1 第 2 个片段才对、q2 第 1 个命中了同文档不同小节，第 2 个命中目标小节 → (0.5 + 0.5) / 2 = 0.5
    assert m["chunk_mrr"] == pytest.approx(0.5)


def test_judge_hybrid_decision_covers_all_frozen_rules():
    def run_for(fts_hits, hyb_hits):
        cases = [
            EvalCase(query="k1", expect_sources=("k1.md",), kind="keyword"),
            EvalCase(query="p1", expect_sources=("p1.md",), kind="paraphrase"),
            EvalCase(query="p2", expect_sources=("p2.md",), kind="paraphrase"),
            EvalCase(query="p3", expect_sources=("p3.md",), kind="paraphrase"),
        ]
        fts_rep = evaluate(cases, lambda q, m: (fts_hits[q], "fts_only"), modes=["fts_only"], k=5)["fts_only"]
        hyb_rep = evaluate(cases, lambda q, m: (hyb_hits[q], "hybrid"), modes=["hybrid"], k=5)["hybrid"]
        return judge_hybrid_decision(fts_rep, hyb_rep)

    # 全满足：keyword 1.0→1.0，换述找回 2 / 弄丢 0，MRR 从 0.333→0.667
    pass_dec = run_for(
        {"k1": ["k1.md"], "p1": ["p1.md"], "p2": ["other.md"], "p3": ["other.md"]},
        {"k1": ["k1.md"], "p1": ["p1.md"], "p2": ["p2.md"], "p3": ["p3.md"]},
    )
    assert pass_dec["keep_vector_leg"] is True
    assert pass_dec["paraphrase_net_recovered"] == 2

    # 规则 1 失败：keyword 退化
    kw_fail = run_for(
        {"k1": ["k1.md"], "p1": ["p1.md"], "p2": ["other.md"], "p3": ["other.md"]},
        {"k1": ["other.md"], "p1": ["p1.md"], "p2": ["p2.md"], "p3": ["p3.md"]},
    )
    assert kw_fail["keyword_non_regression"] is False
    assert kw_fail["keep_vector_leg"] is False

    # 规则 2 失败：仅净找回 1（< +2）
    rec_fail = run_for(
        {"k1": ["k1.md"], "p1": ["p1.md"], "p2": ["other.md"], "p3": ["other.md"]},
        {"k1": ["k1.md"], "p1": ["p1.md"], "p2": ["p2.md"], "p3": ["other.md"]},
    )
    assert rec_fail["paraphrase_recovery_ok"] is False
    assert rec_fail["keep_vector_leg"] is False

    # 规则 3 失败：MRR 提升不足 10%
    mrr_fail = run_for(
        {"k1": ["k1.md"], "p1": ["p1.md"], "p2": ["other.md"], "p3": ["other.md"]},
        {"k1": ["k1.md"], "p1": ["other.md", "other2.md", "other3.md", "other4.md", "p1.md"], "p2": ["other.md", "other2.md", "other3.md", "p2.md"], "p3": ["other.md", "other2.md", "other3.md", "p3.md"]},
    )
    assert mrr_fail["paraphrase_recovery_ok"] is True
    assert mrr_fail["paraphrase_mrr_ok"] is False
    assert mrr_fail["keep_vector_leg"] is False


def test_format_report_supports_markdown_json_csv():
    cases = [EvalCase(query="q", expect_sources=("algo/summary.md",), kind="paraphrase", expect_headings=("H",))]
    rep = evaluate(cases, lambda q, m: ([RetrievalHit("algo/summary.md", "H", "body")], m), modes=["hybrid"], k=5)

    md = format_report(rep, k=5, fmt="markdown")
    assert "| 配置 | 分组 | hit@1 | hit@3 | hit@5 |" in md
    assert "algo/summary.md" not in md  # table summarizes metrics cleanly
    assert "paraphrase" in md

    parsed = json.loads(format_report(rep, k=5, fmt="json"))
    assert parsed["report"]["hybrid"]["chunk_hit_at_k"] == 1.0

    csv_text = format_report(rep, k=5, fmt="csv")
    assert "mode,kind,cases,hits,hit_at_1,hit_at_3,hit_at_5,mrr" in csv_text


@pytest.fixture
def sample_library_v2(tmp_path):
    """按原始多级子目录拷贝 sample_corpus_v2 并建库，校验同名文件消歧。"""
    from obsidian.sync import sync_sources
    from service.library_service import LibraryService

    root = tmp_path / "library_v2"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="EvalV2")
    raw = root / "raw"
    for src in SAMPLE_CORPUS_V2.rglob("*.md"):
        rel = src.relative_to(SAMPLE_CORPUS_V2)
        dest = raw / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    sync_sources(workspace=str(root), vault_path=str(root), course_dir=str(raw), mode="full")
    return root


def test_sample_corpus_v2_and_cli_compare_fts(sample_library_v2, monkeypatch, capsys):
    from unittest.mock import MagicMock

    from rag.recall_eval import cases_from_workspace
    from rag.retriever import clear_retrieval_cache

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    clear_retrieval_cache(str(sample_library_v2))

    cases = load_cases(str(SAMPLE_CASES_V2))
    assert len(cases) == 40
    assert sum(1 for c in cases if c.kind == "keyword") == 12
    assert sum(1 for c in cases if c.kind == "paraphrase") == 28
    assert sum(1 for c in cases if c.expect_headings or c.expect_snippets) >= 24

    report = evaluate_workspace(str(sample_library_v2), cases, modes=["hybrid"], k=5, config={})
    m = report["hybrid"]
    assert m["by_kind"]["keyword"]["hit_at_k"] == 1.0, m["by_kind"]["keyword"]
    assert m["chunk_cases"] >= 24
    assert m["chunk_hit_at_k"] is not None

    # 同名 summary.md 存在多个时，自动生成用例也应带相对路径消歧
    auto_cases = cases_from_workspace(str(sample_library_v2), limit=10)
    summary_refs = [c.expect_sources[0] for c in auto_cases if c.expect_sources[0].endswith("summary.md")]
    assert len(summary_refs) == 2
    assert all("/" in ref for ref in summary_refs), summary_refs

    # CLI --compare-fts + --format json 单命令跑通
    monkeypatch.setattr("rag.recall_eval.load_eval_config", lambda **kwargs: {})
    rc = recall_main([
        "--workspace", str(sample_library_v2),
        "--cases", str(SAMPLE_CASES_V2),
        "--modes", "hybrid",
        "--compare-fts",
        "--format", "json",
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "fts_only" in out["report"]
    assert "hybrid" in out["report"]
    assert "decision" in out

