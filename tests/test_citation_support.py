"""W2-EVID-02：引用支持度风险检测单元测试与评测基准回归。"""

from __future__ import annotations

import json
from pathlib import Path

from rag.citations import cite_label
from scripts.eval_citation_support import evaluate_cases, format_report, load_cases
from service.citation_support import (
    EvidenceSnippet,
    check_citation_support,
    collect_turn_evidence_map,
)
from web.backend.routers.chat import _merge_attribution, _public_attribution

EVAL_CASES_PATH = Path(__file__).parent / "eval" / "citation_support_cases.jsonl"


def test_review_repro_dijkstra_negative_weight_contradiction_triggers_warning():
    label = cite_label("chunk-dijkstra-1")
    evidence = {
        label: EvidenceSnippet(
            cite_label=label,
            title="algo/dijkstra.md",
            text="Dijkstra 算法基于贪心策略求解最短路径，要求图中所有边权均为非负；出现负权边时贪心失效。",
        )
    }
    response = f"Dijkstra 算法可以直接处理带有负权边的有向图 [{label}]。"

    warnings = check_citation_support(response, evidence)

    assert len(warnings) == 1
    assert warnings[0].cite_label == label
    assert warnings[0].reason_code == "polarity_contradiction"
    assert warnings[0].source_title == "algo/dijkstra.md"


def test_contrastive_chunk_picks_matching_subject_clause_without_false_positive():
    label = cite_label("chunk-summary-1")
    evidence = {
        label: EvidenceSnippet(
            cite_label=label,
            title="algo/summary.md",
            text="Dijkstra 要求边权非负、不支持负权边，而 Bellman-Ford 支持负权边图的松弛求解。",
        )
    }
    ok_bellman = f"Bellman-Ford 算法能够支持负权边图的松弛求解 [{label}]。"
    ok_dijkstra = f"Dijkstra 要求边权非负且不支持负权边 [{label}]。"
    bad_dijkstra = f"Dijkstra 能够直接支持负权边 [{label}]。"

    assert check_citation_support(ok_bellman, evidence) == []
    assert check_citation_support(ok_dijkstra, evidence) == []
    bad_warnings = check_citation_support(bad_dijkstra, evidence)
    assert len(bad_warnings) == 1
    assert bad_warnings[0].reason_code == "polarity_contradiction"


def test_concessive_not_only_and_code_blocks_do_not_false_positive():
    label = cite_label("chunk-ingest-1")
    evidence = {
        label: EvidenceSnippet(
            cite_label=label,
            title="sys/ingest.md",
            text="系统不仅支持 Markdown 文档解析，还支持 PDF 文本提取与增量索引。",
        )
    }
    response = (
        f"系统不仅支持 Markdown 解析，还支持 PDF 文本提取 [{label}]。\n\n"
        f"代码里示例 `\"不支持负权 [{label}]\"` 与\n```python\nx = \"支持负权 [{label}]\"\n``` 应忽略。\n\n"
        f"详见原文 [{label}]。"
    )

    assert check_citation_support(response, evidence) == []


def test_low_overlap_triggers_for_unrelated_substantive_claim():
    label = cite_label("chunk-git-1")
    evidence = {
        label: EvidenceSnippet(
            cite_label=label,
            title="tools/git.md",
            text="Git 使用三方合并解决分支冲突，并保存提交对象的 SHA-1 校验。",
        )
    }
    response = f"TCP 三次握手通过 SYN 与 ACK 报文确立双端序列号 [{label}]。"

    warnings = check_citation_support(response, evidence)
    assert len(warnings) == 1
    assert warnings[0].reason_code == "low_overlap"


def test_collect_turn_evidence_map_aggregates_tool_events_and_kb_seed():
    chunk_id = "chunk-wal-1"
    label = cite_label(chunk_id)
    kb_seed = f"- [{label}] sqlite.md · {chunk_id}：短预览内容"
    tool_content = (
        json.dumps({
            "results": [{
                "chunk_id": chunk_id,
                "source": "sys/sqlite.md",
                "title": "SQLite WAL",
                "text": "SQLite 在 WAL 模式下允许读事务与写事务并发执行，不需要阻塞读者。",
            }]
        }, ensure_ascii=False)
        + f"\n\n[{label}] source=sys/sqlite.md score=0.920\nSQLite 在 WAL 模式下允许读事务与写事务并发执行，不需要阻塞读者。"
    )
    web_label = cite_label("web-1")
    evidence = collect_turn_evidence_map(
        kb_seed=kb_seed,
        tool_events=[
            {
                "type": "tool_end",
                "name": "rag_search",
                "content": tool_content,
                "artifacts": [{
                    "type": "citation",
                    "attribution": {
                        "kind": "local",
                        "sources": [{"source_type": "local", "source_id": chunk_id, "cite_label": label, "title": "SQLite WAL", "excerpt": "短预览"}],
                    },
                }],
            },
            {
                "type": "tool_end",
                "name": "web_research",
                "content": f"[{web_label}] RFC 9110 — rfc-editor.org\nETag headers support conditional HTTP caching.",
                "artifacts": [{
                    "type": "citation",
                    "attribution": {
                        "kind": "web",
                        "sources": [{"source_type": "web", "source_id": "web-1", "cite_label": web_label, "title": "RFC 9110"}],
                    },
                }],
            },
        ],
    )

    assert "不需要阻塞读者" in evidence[label].text
    assert evidence[label].title == "SQLite WAL"
    assert "conditional HTTP caching" in evidence[web_label].text


def test_citation_support_benchmark_meets_quality_floor():
    cases = load_cases(EVAL_CASES_PATH)
    assert len(cases) >= 24

    result = evaluate_cases(cases)
    assert result["precision"] >= 0.85, format_report(result)
    assert result["recall"] >= 0.85, format_report(result)
    assert result["f1"] >= 0.85, format_report(result)
    assert result["fpr"] <= 0.15, format_report(result)


def test_chat_attribution_preserves_and_merges_support_warnings():
    raw = {
        "kind": "local",
        "sources": [{"source_type": "local", "source_id": "c1", "title": "讲义", "cite_label": "Sa10001"}],
        "support_warnings": [{
            "cite_label": "Sa10001",
            "claim": "支持负权边",
            "reason_code": "polarity_contradiction",
            "reason": "与原文非负权要求矛盾",
            "evidence_excerpt": "要求非负权",
            "source_title": "讲义",
        }],
    }
    public = _public_attribution(raw)
    assert public is not None
    assert len(public["support_warnings"]) == 1
    assert public["support_warnings"][0]["cite_label"] == "Sa10001"

    merged = _merge_attribution(
        {"kind": "local", "sources": [{"source_type": "local", "source_id": "c1", "title": "讲义"}]},
        public,
    )
    assert len(merged["support_warnings"]) == 1
