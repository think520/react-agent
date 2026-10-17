"""W2 G4：召回评测 —— 度量（hit@k / MRR）+ 一个能对着任意工作区跑的入口。
为什么先做度量：路线图要求「RRF 权重由数据决定」，但没有基线之前，「检索变好了」只是感觉。
设计取舍：度量是纯函数、检索通过回调注入；命中键用来源**文件名**（chunk id 会随重切变化）；
报告必须带**实际跑的模式**（要了 vector 却只能跑 fts_only 时要看得见）；用例文件没有期望就拒绝。
**运行时限制（2026-10-15 实测，写在这里免得下次再踩）**：本地 Qdrant 是**单进程**存储。

**自动生成用例的边界（2026-10-15 实测）**：`cases_from_workspace` 生成的是「标题 + 索引关键词」查询，
**区分不开 fts_only 与 hybrid** —— 实测两种配置都是 21/21（hit@5=1.000），因为关键词检索本来就能命中这些查询。
它能复现的是**修 FTS 转义前后的差别**（修前 0.720 → 修后 1.000），**不能**替代语义/换述类的评测集（那需要人工出题，目前不在仓库里）。
服务（或任何别的进程）已经打开该知识库时，外部再跑评测会得到
`Storage folder … is already accessed by another instance` —— 此时只有 FTS 腿能测，
向量腿必然报不可用。要测向量腿：**先停掉服务**，或把评测做成服务端入口（未做）。
另外评测进程要自己 `load_dotenv(.env)` 并传**整个** config 对象（只传 rag 那一段子字典会让
`EmbeddingService` 解析不出预设，从而把它误判成「没有可用的 embedding 后端」）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

DEFAULT_K = 5
#: 注意：这是**请求**词表（orchestrator 认识 auto/hybrid/directory/directory_grep）。
#: 「fts_only / vector / hybrid」是**上报**词表（status.retrieval_mode），两者不是一回事 ——
#: 传错模式会被回落成 hybrid 并在日志里告警，报告里的 resolved_modes 会如实显示实际跑了什么。
DEFAULT_MODES = ("auto", "hybrid")


#: 用例类型：keyword = 关键词型（FTS 就该能中，用来防回归）；paraphrase = 换述型（只有语义检索才可能中）。
KNOWN_KINDS = ("keyword", "paraphrase")
#: 用例来源：generated = 自动生成；human = 人工写。
KNOWN_SOURCES = ("generated", "human")


@dataclass(frozen=True)
class EvalCase:
    query: str
    expect_sources: tuple[str, ...] = ()
    #: 老用例没有这个字段 → 默认 keyword（向后兼容）。
    kind: str = "keyword"
    #: 老用例没有这个字段 → 默认 generated。
    source: str = "generated"


def load_cases(path: str) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number} 不是合法 JSON：{exc}") from exc
            query = str(payload.get("query") or "").strip()
            expect = tuple(str(item) for item in (payload.get("expect_sources") or []) if str(item).strip())
            if not query:
                raise ValueError(f"{path}:{number} 缺少 query")
            if not expect:
                raise ValueError(f"{path}:{number} 缺少 expect_sources（没有期望就没法评分）")
            kind = str(payload.get("kind") or "keyword").strip() or "keyword"
            if kind not in KNOWN_KINDS:
                raise ValueError(
                    f"{path}:{number} 的 kind 不认识：{kind}（允许：{'/'.join(KNOWN_KINDS)}）"
                )
            source = str(payload.get("source") or "generated").strip() or "generated"
            cases.append(EvalCase(query=query, expect_sources=expect, kind=kind, source=source))
    if not cases:
        raise ValueError(f"{path} 里没有任何用例")
    return cases


def _as_set(values: Iterable[str]) -> set[str]:
    return {str(value) for value in values if str(value)}


def hit_at_k(expected: Iterable[str], retrieved: Sequence[str], k: int = DEFAULT_K) -> bool:
    wanted = _as_set(expected)
    if not wanted:
        return False
    return bool(wanted & _as_set(retrieved[: max(0, int(k))]))


def reciprocal_rank(expected: Iterable[str], retrieved: Sequence[str]) -> float:
    wanted = _as_set(expected)
    if not wanted:
        return 0.0
    for index, item in enumerate(retrieved, 1):
        if str(item) in wanted:
            return 1.0 / index
    return 0.0


def evaluate(
    cases: Sequence[EvalCase],
    retrieve: Callable[[str, str], tuple[Sequence[str], str]],
    *,
    modes: Sequence[str] = DEFAULT_MODES,
    k: int = DEFAULT_K,
) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for mode in modes:
        hits = 0
        rr_total = 0.0
        resolved: dict[str, int] = {}
        # 按 kind 分组：关键词组是防回归，换述组才用来判断向量腿值不值。
        buckets: dict[str, dict[str, float]] = {}
        for case in cases:
            retrieved, resolved_mode = retrieve(case.query, mode)
            retrieved = [str(item) for item in retrieved]
            hit = hit_at_k(case.expect_sources, retrieved, k)
            rr = reciprocal_rank(case.expect_sources, retrieved)
            if hit:
                hits += 1
            rr_total += rr
            key = str(resolved_mode or "unknown")
            resolved[key] = resolved.get(key, 0) + 1
            bucket = buckets.setdefault(case.kind, {"cases": 0.0, "hits": 0.0, "mrr_total": 0.0})
            bucket["cases"] += 1
            bucket["hits"] += 1.0 if hit else 0.0
            bucket["mrr_total"] += rr
        total = len(cases) or 1
        by_kind = {
            name: {
                "cases": int(bucket["cases"]),
                "hits": int(bucket["hits"]),
                "hit_at_k": bucket["hits"] / (bucket["cases"] or 1),
                "mrr": bucket["mrr_total"] / (bucket["cases"] or 1),
            }
            for name, bucket in buckets.items()
        }
        report[str(mode)] = {
            "cases": len(cases),
            "hits": hits,
            # 键名带 k：报告自己说清楚这是 hit@几，别让读者去猜。
            "k": int(k),
            "hit_at_k": hits / total,
            "mrr": rr_total / total,
            "resolved_modes": resolved,
            "by_kind": by_kind,
        }
    return report


def summarize(report: dict[str, dict[str, Any]], *, k: int = DEFAULT_K) -> str:
    lines: list[str] = []
    for mode, metrics in report.items():
        resolved = ", ".join(
            f"{name}x{count}" for name, count in sorted(metrics.get("resolved_modes", {}).items())
        )
        hit = metrics.get("hit_at_k", 0.0)
        mrr = metrics.get("mrr", 0.0)
        hits = metrics.get("hits", 0)
        cases = metrics.get("cases", 0)
        lines.append(f"{mode}: hit@{int(k)}={hit:.3f} MRR={mrr:.3f} （命中 {hits}/{cases}；实际模式 {resolved or '无'}）")
        for kind in sorted(metrics.get("by_kind", {})):
            detail = metrics["by_kind"][kind]
            lines.append(
                f"  - {kind}: hit@{int(k)}={detail.get('hit_at_k', 0.0):.3f} "
                f"MRR={detail.get('mrr', 0.0):.3f}（{detail.get('hits', 0)}/{detail.get('cases', 0)}）"
            )
    return "\n".join(lines)


def cases_from_workspace(workspace: str, *, limit: int = 25) -> list[EvalCase]:
    # 盲区 A：从工作区**确定性**生成用例（标题 + 该资料的一个关键词 → 期望命中这份资料的来源文件）。
    # 只读打开索引；真实资料正文不会因此进仓库 —— 用例是运行时产物，不进 git。
    import sqlite3

    from knowledge.paths import knowledge_path

    db_path = os.path.join(knowledge_path(workspace), "knowledge.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"没有可评测的索引：{db_path}")

    con = sqlite3.connect("file:" + db_path.replace(chr(92), "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        # 只要有分段就能评"能不能检索到"（不要求已建向量：fts_only 也是要评的模式之一）。
        rows = list(con.execute(
            "SELECT id, source, title FROM documents "
            "WHERE id IN (SELECT DISTINCT document_id FROM chunks) ORDER BY id LIMIT ?",
            (max(1, int(limit)),),
        ))
        keywords = {
            row["document_id"]: row["keywords_json"]
            for row in con.execute("SELECT document_id, keywords_json FROM directory_entries")
        }
    finally:
        con.close()

    cases: list[EvalCase] = []
    for row in rows:
        terms: list[str] = []
        try:
            terms = [str(item) for item in json.loads(keywords.get(row["id"]) or "[]")]
        except (TypeError, ValueError):
            terms = []
        term = next((item.strip() for item in terms if item and item.strip()), "")
        if not term:
            continue
        title = str(row["title"] or "").strip()
        cases.append(EvalCase(
            query=(title + " " + term).strip(),
            expect_sources=(os.path.basename(str(row["source"] or "")),),
        ))
    return cases


def evaluate_workspace(
    workspace: str,
    cases: Sequence[EvalCase],
    *,
    modes: Sequence[str] = DEFAULT_MODES,
    k: int = DEFAULT_K,
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    import os

    from rag.retriever import search_index_with_status

    def retrieve(query: str, mode: str) -> tuple[list[str], str]:
        results, status = search_index_with_status(
            workspace, query=query, top_k=max(int(k), 1), config=config or {}, mode=mode,
        )
        sources = [os.path.basename(str(item.get("source") or "")) for item in results]
        return sources, str(status.get("retrieval_mode") or "")

    return evaluate(cases, retrieve, modes=modes, k=k)


def load_eval_config(
    *,
    embedding_backend: str | None = None,
    config_path: str = "config.yaml",
) -> dict[str, Any]:
    # 评测必须拿到**完整** config（只传 rag 子字典会让 EmbeddingService 解析不出预设，
    # 把「配了 provider」误判成「没有可用的 embedding 后端」——2026-10-15 踩过这个坑）。
    from dotenv import load_dotenv
    from providers.factory import ProviderFactory

    load_dotenv(".env", override=False)
    config = ProviderFactory.load_config(config_path)
    if embedding_backend:
        config.setdefault("rag", {})["embedding_backend"] = str(embedding_backend)
    return config


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Recall evaluation (hit@k / MRR)")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--cases", help="JSONL 用例文件")
    parser.add_argument(
        "--generate-cases", type=int, default=0,
        help="不读文件，直接从工作区确定性生成 N 条用例（正文不进仓库）",
    )
    parser.add_argument("--modes", default=",".join(DEFAULT_MODES))
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument(
        "--embedding-backend", default="",
        help="覆盖 rag.embedding_backend；对照用 local（= 关掉向量腿，跑 fts_only）",
    )
    args = parser.parse_args(argv)

    if args.generate_cases:
        cases = cases_from_workspace(args.workspace, limit=args.generate_cases)
    elif args.cases:
        cases = load_cases(args.cases)
    else:
        parser.error("需要 --cases 或 --generate-cases")
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    config = load_eval_config(embedding_backend=args.embedding_backend or None)
    report = evaluate_workspace(args.workspace, cases, modes=modes, k=args.k, config=config)
    print(summarize(report, k=args.k))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())