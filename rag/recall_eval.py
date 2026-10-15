"""W2 G4：召回评测 —— 度量（hit@k / MRR）+ 一个能对着任意工作区跑的入口。
为什么先做度量：路线图要求「RRF 权重由数据决定」，但没有基线之前，「检索变好了」只是感觉。
设计取舍：度量是纯函数、检索通过回调注入；命中键用来源**文件名**（chunk id 会随重切变化）；
报告必须带**实际跑的模式**（要了 vector 却只能跑 fts_only 时要看得见）；用例文件没有期望就拒绝。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

DEFAULT_K = 5
#: 注意：这是**请求**词表（orchestrator 认识 auto/hybrid/directory/directory_grep）。
#: 「fts_only / vector / hybrid」是**上报**词表（status.retrieval_mode），两者不是一回事 ——
#: 传错模式会被回落成 hybrid 并在日志里告警，报告里的 resolved_modes 会如实显示实际跑了什么。
DEFAULT_MODES = ("auto", "hybrid")


@dataclass(frozen=True)
class EvalCase:
    query: str
    expect_sources: tuple[str, ...] = ()


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
            cases.append(EvalCase(query=query, expect_sources=expect))
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
        for case in cases:
            retrieved, resolved_mode = retrieve(case.query, mode)
            retrieved = [str(item) for item in retrieved]
            if hit_at_k(case.expect_sources, retrieved, k):
                hits += 1
            rr_total += reciprocal_rank(case.expect_sources, retrieved)
            key = str(resolved_mode or "unknown")
            resolved[key] = resolved.get(key, 0) + 1
        total = len(cases) or 1
        report[str(mode)] = {
            "cases": len(cases),
            "hits": hits,
            # 键名带 k：报告自己说清楚这是 hit@几，别让读者去猜。
            "k": int(k),
            "hit_at_k": hits / total,
            "mrr": rr_total / total,
            "resolved_modes": resolved,
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
    return "\n".join(lines)


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


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Recall evaluation (hit@k / MRR)")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--modes", default=",".join(DEFAULT_MODES))
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    report = evaluate_workspace(args.workspace, cases, modes=modes, k=args.k)
    print(summarize(report, k=args.k))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())