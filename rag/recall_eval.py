"""W2 G4 / G4.2：召回评测 —— 文档级与片段级度量、相对路径消歧、对比对比与冻结判据。

为什么先做度量：路线图要求「RRF 权重由数据决定」，没有基线与结构化指标之前，「检索变好了」只是感觉。
设计取舍：
- 度量是纯函数、检索通过回调注入；
- 命中键支持 basename（向后兼容旧用例）与相对路径后缀消歧（如 `algo/summary.md` vs `ml/summary.md`）；
- 支持片段/章节级指标（`expect_headings` / `expect_snippets` → `chunk_hit@k` / `chunk_MRR`）；
- 报告必须带**实际跑的模式**（要了 vector 却只能跑 fts_only 时要看得见）；
- `--compare-fts` 可单命令对比 `fts_only` 基线与目标检索配置并执行 §6 冻结判据（`judge_hybrid_decision`）。
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections import Counter
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
class RetrievalHit:
    source: str
    heading: str = ""
    text: str = ""
    chunk_id: str = ""
    score: float = 0.0


@dataclass(frozen=True)
class EvalCase:
    query: str
    expect_sources: tuple[str, ...] = ()
    #: 老用例没有这个字段 → 默认 keyword（向后兼容）。
    kind: str = "keyword"
    #: 老用例没有这个字段 → 默认 generated。
    source: str = "generated"
    #: 片段级期望：任意标题子串或原文子串（为空时不计入 chunk 分母）。
    expect_headings: tuple[str, ...] = ()
    expect_snippets: tuple[str, ...] = ()
    note: str = ""


def normalize_source_path(path: str) -> str:
    """规范化路径分隔符，移除前导 `/` 或 `./`。"""
    cleaned = str(path or "").replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


def source_matches(expected: str, retrieved: str) -> bool:
    """判断检索命中来源是否匹配期望来源；期望含 `/` 时做相对路径消歧，否则比较 basename。"""
    exp = normalize_source_path(expected)
    ret = normalize_source_path(retrieved)
    if not exp or not ret:
        return False
    if "/" in exp:
        return ret == exp or ret.endswith("/" + exp)
    return os.path.basename(ret) == exp


def _coerce_hit(item: Any) -> RetrievalHit:
    if isinstance(item, RetrievalHit):
        return item
    if isinstance(item, dict):
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        return RetrievalHit(
            source=str(item.get("source") or ""),
            heading=str(item.get("heading") or item.get("heading_text") or meta.get("heading_text") or ""),
            text=str(item.get("text") or ""),
            chunk_id=str(item.get("chunk_id") or item.get("id") or ""),
            score=float(item.get("score") or 0.0),
        )
    return RetrievalHit(source=str(item))


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
            expect = tuple(str(item).strip() for item in (payload.get("expect_sources") or []) if str(item).strip())
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
            expect_headings = tuple(
                str(item).strip() for item in (payload.get("expect_headings") or []) if str(item).strip()
            )
            expect_snippets = tuple(
                str(item).strip() for item in (payload.get("expect_snippets") or []) if str(item).strip()
            )
            note = str(payload.get("note") or "").strip()
            cases.append(EvalCase(
                query=query,
                expect_sources=expect,
                kind=kind,
                source=source,
                expect_headings=expect_headings,
                expect_snippets=expect_snippets,
                note=note,
            ))
    if not cases:
        raise ValueError(f"{path} 里没有任何用例")
    return cases


def _as_list(values: Iterable[str]) -> list[str]:
    return [str(value) for value in values if str(value)]


def hit_at_k(expected: Iterable[str], retrieved: Sequence[Any], k: int = DEFAULT_K) -> bool:
    wanted = _as_list(expected)
    if not wanted:
        return False
    cutoff = max(0, int(k))
    for item in retrieved[:cutoff]:
        hit = _coerce_hit(item)
        if any(source_matches(exp, hit.source) for exp in wanted):
            return True
    return False


def reciprocal_rank(expected: Iterable[str], retrieved: Sequence[Any]) -> float:
    wanted = _as_list(expected)
    if not wanted:
        return 0.0
    for index, item in enumerate(retrieved, 1):
        hit = _coerce_hit(item)
        if any(source_matches(exp, hit.source) for exp in wanted):
            return 1.0 / index
    return 0.0


def _hit_matches_chunk(case: EvalCase, hit: RetrievalHit) -> bool:
    if not case.expect_headings and not case.expect_snippets:
        return False
    if not any(source_matches(exp, hit.source) for exp in case.expect_sources):
        return False
    if case.expect_headings:
        heading_pool = f"{hit.heading}\n{hit.text[:240]}".lower()
        if not any(expected_h.lower() in heading_pool for expected_h in case.expect_headings):
            return False
    if case.expect_snippets:
        body_lower = hit.text.lower()
        if not any(expected_s.lower() in body_lower for expected_s in case.expect_snippets):
            return False
    return True


def chunk_hit_and_rr(case: EvalCase, retrieved: Sequence[Any], k: int = DEFAULT_K) -> tuple[bool | None, float | None]:
    if not case.expect_headings and not case.expect_snippets:
        return None, None
    hits = [_coerce_hit(item) for item in retrieved]
    cutoff = max(0, int(k))
    matched_k = any(_hit_matches_chunk(case, item) for item in hits[:cutoff])
    rr = 0.0
    for index, item in enumerate(hits, 1):
        if _hit_matches_chunk(case, item):
            rr = 1.0 / index
            break
    return matched_k, rr


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    cases_count = int(bucket["cases"]) or 1
    chunk_cases = int(bucket["chunk_cases"])
    return {
        "cases": int(bucket["cases"]),
        "hits": int(bucket["hits"]),
        "hit_at_1": bucket["hits_1"] / cases_count,
        "hit_at_3": bucket["hits_3"] / cases_count,
        "hit_at_k": bucket["hits"] / cases_count,
        "mrr": bucket["mrr_total"] / cases_count,
        "chunk_cases": chunk_cases,
        "chunk_hits": int(bucket["chunk_hits"]),
        "chunk_hit_at_k": (bucket["chunk_hits"] / chunk_cases) if chunk_cases else None,
        "chunk_mrr": (bucket["chunk_mrr_total"] / chunk_cases) if chunk_cases else None,
    }


def evaluate(
    cases: Sequence[EvalCase],
    retrieve: Callable[[str, str], tuple[Sequence[Any], str]],
    *,
    modes: Sequence[str] = DEFAULT_MODES,
    k: int = DEFAULT_K,
) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for mode in modes:
        hits_1 = 0
        hits_3 = 0
        hits = 0
        rr_total = 0.0
        chunk_cases = 0
        chunk_hits = 0
        chunk_rr_total = 0.0
        resolved: dict[str, int] = {}
        buckets: dict[str, dict[str, float]] = {}
        per_case: list[dict[str, Any]] = []

        for idx, case in enumerate(cases):
            raw_retrieved, resolved_mode = retrieve(case.query, mode)
            retrieved = [_coerce_hit(item) for item in raw_retrieved]
            hit_1 = hit_at_k(case.expect_sources, retrieved, 1)
            hit_3 = hit_at_k(case.expect_sources, retrieved, 3)
            hit = hit_at_k(case.expect_sources, retrieved, k)
            rr = reciprocal_rank(case.expect_sources, retrieved)
            c_hit, c_rr = chunk_hit_and_rr(case, retrieved, k)

            if hit_1:
                hits_1 += 1
            if hit_3:
                hits_3 += 1
            if hit:
                hits += 1
            rr_total += rr
            if c_hit is not None and c_rr is not None:
                chunk_cases += 1
                chunk_hits += 1 if c_hit else 0
                chunk_rr_total += c_rr

            key = str(resolved_mode or "unknown")
            resolved[key] = resolved.get(key, 0) + 1
            bucket = buckets.setdefault(
                case.kind,
                {
                    "cases": 0.0,
                    "hits_1": 0.0,
                    "hits_3": 0.0,
                    "hits": 0.0,
                    "mrr_total": 0.0,
                    "chunk_cases": 0.0,
                    "chunk_hits": 0.0,
                    "chunk_mrr_total": 0.0,
                },
            )
            bucket["cases"] += 1
            bucket["hits_1"] += 1.0 if hit_1 else 0.0
            bucket["hits_3"] += 1.0 if hit_3 else 0.0
            bucket["hits"] += 1.0 if hit else 0.0
            bucket["mrr_total"] += rr
            if c_hit is not None and c_rr is not None:
                bucket["chunk_cases"] += 1
                bucket["chunk_hits"] += 1.0 if c_hit else 0.0
                bucket["chunk_mrr_total"] += c_rr

            per_case.append({
                "index": idx,
                "kind": case.kind,
                "hit": hit,
                "hit_at_1": hit_1,
                "rr": rr,
                "chunk_hit": c_hit,
                "chunk_rr": c_rr,
            })

        total = len(cases) or 1
        by_kind = {name: _finalize_bucket(bucket) for name, bucket in buckets.items()}
        report[str(mode)] = {
            "cases": len(cases),
            "hits": hits,
            # 键名带 k：报告自己说清楚这是 hit@几，别让读者去猜。
            "k": int(k),
            "hit_at_1": hits_1 / total,
            "hit_at_3": hits_3 / total,
            "hit_at_k": hits / total,
            "mrr": rr_total / total,
            "chunk_cases": chunk_cases,
            "chunk_hits": chunk_hits,
            "chunk_hit_at_k": (chunk_hits / chunk_cases) if chunk_cases else None,
            "chunk_mrr": (chunk_rr_total / chunk_cases) if chunk_cases else None,
            "resolved_modes": resolved,
            "by_kind": by_kind,
            "per_case": per_case,
        }
    return report


def judge_hybrid_decision(
    fts_metrics: dict[str, Any],
    hybrid_metrics: dict[str, Any],
    *,
    min_net_recovered: int = 2,
    min_paraphrase_mrr_gain: float = 0.10,
) -> dict[str, Any]:
    """按 docs/RAG_EVAL.md §6 冻结判据决定是否保留向量腿。"""
    fts_by_kind = fts_metrics.get("by_kind") or {}
    hyb_by_kind = hybrid_metrics.get("by_kind") or {}

    fts_kw = fts_by_kind.get("keyword") or {}
    hyb_kw = hyb_by_kind.get("keyword") or {}
    kw_cases = int(fts_kw.get("cases") or 0)
    if kw_cases > 0:
        kw_fts_hit = float(fts_kw.get("hit_at_k", 0.0))
        kw_hyb_hit = float(hyb_kw.get("hit_at_k", 0.0))
        kw_ok = kw_hyb_hit >= kw_fts_hit
    else:
        kw_fts_hit = float(fts_metrics.get("hit_at_k", 0.0))
        kw_hyb_hit = float(hybrid_metrics.get("hit_at_k", 0.0))
        kw_ok = True

    fts_per_case = fts_metrics.get("per_case") or []
    hyb_per_case = hybrid_metrics.get("per_case") or []
    fts_p_cases = [item for item in fts_per_case if item.get("kind") == "paraphrase"] or fts_per_case
    hyb_p_cases = [item for item in hyb_per_case if item.get("kind") == "paraphrase"] or hyb_per_case

    recovered = 0
    lost = 0
    if fts_p_cases and len(fts_p_cases) == len(hyb_p_cases):
        for f_item, h_item in zip(fts_p_cases, hyb_p_cases):
            f_hit = bool(f_item.get("hit"))
            h_hit = bool(h_item.get("hit"))
            if not f_hit and h_hit:
                recovered += 1
            elif f_hit and not h_hit:
                lost += 1
    else:
        fts_hits = int((fts_by_kind.get("paraphrase") or fts_metrics).get("hits") or 0)
        hyb_hits = int((hyb_by_kind.get("paraphrase") or hybrid_metrics).get("hits") or 0)
        recovered = max(0, hyb_hits - fts_hits)
        lost = max(0, fts_hits - hyb_hits)

    recovery_ok = recovered >= lost + int(min_net_recovered)

    fts_p = fts_by_kind.get("paraphrase") or fts_metrics
    hyb_p = hyb_by_kind.get("paraphrase") or hybrid_metrics
    fts_mrr = float(fts_p.get("mrr", 0.0))
    hyb_mrr = float(hyb_p.get("mrr", 0.0))
    if fts_mrr > 0:
        mrr_rel_gain = (hyb_mrr - fts_mrr) / fts_mrr
        mrr_ok = mrr_rel_gain >= min_paraphrase_mrr_gain
    else:
        mrr_rel_gain = hyb_mrr
        mrr_ok = hyb_mrr > 0

    return {
        "keep_vector_leg": bool(kw_ok and recovery_ok and mrr_ok),
        "keyword_cases": kw_cases,
        "keyword_fts_hit": kw_fts_hit,
        "keyword_hybrid_hit": kw_hyb_hit,
        "keyword_non_regression": kw_ok,
        "paraphrase_recovered": recovered,
        "paraphrase_lost": lost,
        "paraphrase_net_recovered": recovered - lost,
        "paraphrase_recovery_ok": recovery_ok,
        "paraphrase_fts_mrr": fts_mrr,
        "paraphrase_hybrid_mrr": hyb_mrr,
        "paraphrase_mrr_relative_gain": mrr_rel_gain,
        "paraphrase_mrr_ok": mrr_ok,
    }


def _fmt_opt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def summarize(report: dict[str, dict[str, Any]], *, k: int = DEFAULT_K) -> str:
    lines: list[str] = []
    for mode, metrics in report.items():
        resolved = ", ".join(
            f"{name}x{count}" for name, count in sorted(metrics.get("resolved_modes", {}).items())
        )
        hit = metrics.get("hit_at_k", 0.0)
        hit1 = metrics.get("hit_at_1", 0.0)
        hit3 = metrics.get("hit_at_3", 0.0)
        mrr = metrics.get("mrr", 0.0)
        hits = metrics.get("hits", 0)
        cases = metrics.get("cases", 0)
        chunk_part = ""
        if metrics.get("chunk_cases"):
            chunk_part = (
                f" chunk_hit@{int(k)}={_fmt_opt(metrics.get('chunk_hit_at_k'))}"
                f" chunk_MRR={_fmt_opt(metrics.get('chunk_mrr'))}"
                f"（{metrics.get('chunk_hits', 0)}/{metrics['chunk_cases']}）"
            )
        lines.append(
            f"{mode}: hit@1={hit1:.3f} hit@3={hit3:.3f} hit@{int(k)}={hit:.3f} "
            f"MRR={mrr:.3f}{chunk_part} （命中 {hits}/{cases}；实际模式 {resolved or '无'}）"
        )
        for kind in sorted(metrics.get("by_kind", {})):
            detail = metrics["by_kind"][kind]
            kind_chunk = ""
            if detail.get("chunk_cases"):
                kind_chunk = (
                    f" chunk_hit@{int(k)}={_fmt_opt(detail.get('chunk_hit_at_k'))}"
                    f" chunk_MRR={_fmt_opt(detail.get('chunk_mrr'))}"
                )
            lines.append(
                f"  - {kind}: hit@{int(k)}={detail.get('hit_at_k', 0.0):.3f} "
                f"MRR={detail.get('mrr', 0.0):.3f}{kind_chunk}（{detail.get('hits', 0)}/{detail.get('cases', 0)}）"
            )
    return "\n".join(lines)


def format_report(
    report: dict[str, dict[str, Any]],
    *,
    k: int = DEFAULT_K,
    fmt: str = "text",
    decision: dict[str, Any] | None = None,
) -> str:
    if fmt == "json":
        payload: dict[str, Any] = {"report": report}
        if decision is not None:
            payload["decision"] = decision
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "mode", "kind", "cases", "hits",
            "hit_at_1", "hit_at_3", f"hit_at_{int(k)}", "mrr",
            "chunk_cases", "chunk_hits", f"chunk_hit_at_{int(k)}", "chunk_mrr",
            "resolved_modes",
        ])
        for mode, metrics in report.items():
            resolved = ";".join(f"{n}:{c}" for n, c in sorted((metrics.get("resolved_modes") or {}).items()))
            writer.writerow([
                mode, "all", metrics.get("cases", 0), metrics.get("hits", 0),
                f"{metrics.get('hit_at_1', 0.0):.4f}", f"{metrics.get('hit_at_3', 0.0):.4f}",
                f"{metrics.get('hit_at_k', 0.0):.4f}", f"{metrics.get('mrr', 0.0):.4f}",
                metrics.get("chunk_cases", 0), metrics.get("chunk_hits", 0),
                _fmt_opt(metrics.get("chunk_hit_at_k")), _fmt_opt(metrics.get('chunk_mrr')),
                resolved,
            ])
            for kind, detail in sorted((metrics.get("by_kind") or {}).items()):
                writer.writerow([
                    mode, kind, detail.get("cases", 0), detail.get("hits", 0),
                    f"{detail.get('hit_at_1', 0.0):.4f}", f"{detail.get('hit_at_3', 0.0):.4f}",
                    f"{detail.get('hit_at_k', 0.0):.4f}", f"{detail.get('mrr', 0.0):.4f}",
                    detail.get("chunk_cases", 0), detail.get("chunk_hits", 0),
                    _fmt_opt(detail.get("chunk_hit_at_k")), _fmt_opt(detail.get("chunk_mrr")),
                    resolved,
                ])
        return buf.getvalue().strip()

    if fmt == "markdown":
        lines = [
            f"| 配置 | 分组 | hit@1 | hit@3 | hit@{int(k)} | MRR | chunk_hit@{int(k)} | chunk_MRR | 命中 | 实际模式 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for mode, metrics in report.items():
            resolved = ", ".join(f"{n}×{c}" for n, c in sorted((metrics.get("resolved_modes") or {}).items())) or "-"
            lines.append(
                f"| {mode} | 全部 | {metrics.get('hit_at_1', 0.0):.3f} | {metrics.get('hit_at_3', 0.0):.3f} | "
                f"{metrics.get('hit_at_k', 0.0):.3f} | {metrics.get('mrr', 0.0):.3f} | "
                f"{_fmt_opt(metrics.get('chunk_hit_at_k'))} | {_fmt_opt(metrics.get('chunk_mrr'))} | "
                f"{metrics.get('hits', 0)}/{metrics.get('cases', 0)} | {resolved} |"
            )
            for kind, detail in sorted((metrics.get("by_kind") or {}).items()):
                lines.append(
                    f"| {mode} | {kind} | {detail.get('hit_at_1', 0.0):.3f} | {detail.get('hit_at_3', 0.0):.3f} | "
                    f"{detail.get('hit_at_k', 0.0):.3f} | {detail.get('mrr', 0.0):.3f} | "
                    f"{_fmt_opt(detail.get('chunk_hit_at_k'))} | {_fmt_opt(detail.get('chunk_mrr'))} | "
                    f"{detail.get('hits', 0)}/{detail.get('cases', 0)} | - |"
                )
        if decision is not None:
            verdict = "保留向量腿" if decision["keep_vector_leg"] else "暂不保留向量腿"
            lines.extend([
                "",
                "| 冻结判据 | 结果 | 实测详情 |",
                "|---|---|---|",
                f"| 综合结论 | **{verdict}** | keep_vector_leg={decision['keep_vector_leg']} |",
                f"| 关键词不退化 | {'✓' if decision['keyword_non_regression'] else '✗'} | "
                f"fts={decision['keyword_fts_hit']:.3f} → hybrid={decision['keyword_hybrid_hit']:.3f} |",
                f"| 换述净找回（≥+2） | {'✓' if decision['paraphrase_recovery_ok'] else '✗'} | "
                f"找回 {decision['paraphrase_recovered']} / 弄丢 {decision['paraphrase_lost']}（净 {decision['paraphrase_net_recovered']:+d}） |",
                f"| 换述 MRR 相对提升（≥10%） | {'✓' if decision['paraphrase_mrr_ok'] else '✗'} | "
                f"{decision['paraphrase_fts_mrr']:.3f} → {decision['paraphrase_hybrid_mrr']:.3f} ({decision['paraphrase_mrr_relative_gain']:+.1%}) |",
            ])
        return "\n".join(lines)

    base = summarize(report, k=k)
    if decision is not None:
        verdict = "保留向量腿" if decision["keep_vector_leg"] else "暂不保留向量腿"
        base += (
            f"\n[冻结判据] {verdict}: "
            f"kw={decision['keyword_non_regression']} "
            f"recovered={decision['paraphrase_recovered']} lost={decision['paraphrase_lost']} "
            f"mrr_gain={decision['paraphrase_mrr_relative_gain']:+.1%}"
        )
    return base


def _disambiguated_source_expectation(raw_source: str, basename_counts: Counter[str]) -> str:
    norm = normalize_source_path(raw_source)
    base = os.path.basename(norm)
    if basename_counts.get(base, 0) <= 1:
        return base
    for prefix in ("course/", "obsidian/", "raw/"):
        if norm.startswith(prefix):
            return norm[len(prefix):]
    return norm


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

    basename_counts = Counter(
        os.path.basename(normalize_source_path(str(row["source"] or "")))
        for row in rows
        if str(row["source"] or "").strip()
    )

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
        expect_ref = _disambiguated_source_expectation(str(row["source"] or ""), basename_counts)
        cases.append(EvalCase(
            query=(title + " " + term).strip(),
            expect_sources=(expect_ref,),
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
    from rag.retriever import search_index_with_status

    def retrieve(query: str, mode: str) -> tuple[list[RetrievalHit], str]:
        results, status = search_index_with_status(
            workspace, query=query, top_k=max(int(k), 1), config=config or {}, mode=mode,
        )
        hits = [
            RetrievalHit(
                source=normalize_source_path(str(item.get("source") or "")),
                heading=str(
                    item.get("heading_text")
                    or (item.get("metadata") or {}).get("heading_text")
                    or ""
                ),
                text=str(item.get("text") or ""),
                chunk_id=str(item.get("chunk_id") or item.get("id") or ""),
                score=float(item.get("score") or 0.0),
            )
            for item in results
        ]
        return hits, str(status.get("retrieval_mode") or "")

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

    parser = argparse.ArgumentParser(description="Recall evaluation (hit@k / MRR / chunk metrics)")
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
    parser.add_argument(
        "--compare-fts", action="store_true",
        help="单命令先后运行 fts_only 基线与当前目标配置，并按 §6 冻结判据给出结论",
    )
    parser.add_argument(
        "--format", choices=("text", "markdown", "json", "csv"), default="text",
        help="输出格式：text（默认）/ markdown / json / csv",
    )
    args = parser.parse_args(argv)

    if args.generate_cases:
        cases = cases_from_workspace(args.workspace, limit=args.generate_cases)
    elif args.cases:
        cases = load_cases(args.cases)
    else:
        parser.error("需要 --cases 或 --generate-cases")
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()] or list(DEFAULT_MODES)

    decision: dict[str, Any] | None = None
    if args.compare_fts:
        fts_config = load_eval_config(embedding_backend="local")
        fts_report = evaluate_workspace(args.workspace, cases, modes=["hybrid"], k=args.k, config=fts_config)
        target_config = load_eval_config(embedding_backend=args.embedding_backend or None)
        target_report = evaluate_workspace(args.workspace, cases, modes=modes, k=args.k, config=target_config)
        report: dict[str, dict[str, Any]] = {"fts_only": fts_report["hybrid"]}
        for mode_name, metrics in target_report.items():
            key = mode_name if mode_name != "fts_only" else f"target_{mode_name}"
            report[key] = metrics
        decision = judge_hybrid_decision(fts_report["hybrid"], target_report[modes[0]])
    else:
        config = load_eval_config(embedding_backend=args.embedding_backend or None)
        report = evaluate_workspace(args.workspace, cases, modes=modes, k=args.k, config=config)

    print(format_report(report, k=args.k, fmt=args.format, decision=decision))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
