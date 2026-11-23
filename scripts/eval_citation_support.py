"""W2-EVID-02：引用支持度风险检测评测脚本。

用带标注的 JSONL 用例集（含正例矛盾/低重合与反例/让步表达/代码段屏蔽）计算
Precision / Recall / F1 / False Positive Rate，可输出 text / markdown / json，
用于回归门禁与毕业论文实验数据表生成。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from service.citation_support import EvidenceSnippet, check_citation_support

DEFAULT_CASES_PATH = REPO_ROOT / "tests" / "eval" / "citation_support_cases.jsonl"


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            item = json.loads(stripped)
            if not isinstance(item, dict) or not item.get("claim_text"):
                raise ValueError(f"{path}:{line_no} 缺少 claim_text")
            cases.append(item)
    return cases


def _build_evidence_map(raw: dict[str, Any]) -> dict[str, EvidenceSnippet]:
    result: dict[str, EvidenceSnippet] = {}
    for label, entry in (raw or {}).items():
        if not isinstance(entry, dict):
            continue
        result[str(label)] = EvidenceSnippet(
            cite_label=str(label),
            title=str(entry.get("title") or ""),
            text=str(entry.get("text") or ""),
        )
    return result


def evaluate_cases(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    reason_match = 0
    reason_total = 0
    by_category: dict[str, dict[str, int]] = {}
    errors: list[dict[str, Any]] = []

    for case in cases:
        case_id = str(case.get("id") or "")
        category = str(case.get("category") or "unknown")
        expected = bool(case.get("expect_warning"))
        expected_reason = case.get("expect_reason_code")
        warnings = check_citation_support(
            str(case.get("claim_text") or ""),
            _build_evidence_map(case.get("evidence") or {}),
        )
        predicted = len(warnings) > 0
        predicted_reasons = [w.reason_code for w in warnings]

        bucket = by_category.setdefault(category, {"total": 0, "correct": 0, "tp": 0, "fp": 0, "tn": 0, "fn": 0})
        bucket["total"] += 1

        if expected and predicted:
            tp += 1
            bucket["tp"] += 1
            bucket["correct"] += 1
        elif not expected and predicted:
            fp += 1
            bucket["fp"] += 1
            errors.append({"id": case_id, "type": "FP", "predicted_reasons": predicted_reasons})
        elif expected and not predicted:
            fn += 1
            bucket["fn"] += 1
            errors.append({"id": case_id, "type": "FN", "expected_reason": expected_reason})
        else:
            tn += 1
            bucket["tn"] += 1
            bucket["correct"] += 1

        if expected and expected_reason:
            reason_total += 1
            if expected_reason in predicted_reasons:
                reason_match += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    reason_accuracy = reason_match / reason_total if reason_total else 1.0

    return {
        "total": len(cases),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "reason_accuracy": reason_accuracy,
        "by_category": by_category,
        "errors": errors,
    }


def format_report(result: dict[str, Any], *, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)
    if fmt == "markdown":
        lines = [
            "| 指标 | 数值 |",
            "|---|---|",
            f"| 样本总数 | {result['total']}（TP={result['tp']}, FP={result['fp']}, TN={result['tn']}, FN={result['fn']}） |",
            f"| Precision（精确率） | {result['precision']:.3f} |",
            f"| Recall（召回率） | {result['recall']:.3f} |",
            f"| F1 | {result['f1']:.3f} |",
            f"| FPR（误报率） | {result['fpr']:.3f} |",
            f"| 原因码准确度 | {result['reason_accuracy']:.3f} |",
            "",
            "| 类别 | 样本数 | 正确 | TP | FP | TN | FN |",
            "|---|---|---|---|---|---|---|",
        ]
        for cat, detail in result["by_category"].items():
            lines.append(
                f"| {cat} | {detail['total']} | {detail['correct']} | "
                f"{detail['tp']} | {detail['fp']} | {detail['tn']} | {detail['fn']} |"
            )
        return "\n".join(lines)

    lines = [
        (
            f"Citation Support Eval ({result['total']} cases): "
            f"P={result['precision']:.3f} R={result['recall']:.3f} "
            f"F1={result['f1']:.3f} FPR={result['fpr']:.3f} "
            f"(TP={result['tp']} FP={result['fp']} TN={result['tn']} FN={result['fn']})"
        ),
    ]
    for cat, detail in result["by_category"].items():
        lines.append(
            f"  - {cat}: {detail['correct']}/{detail['total']} "
            f"(TP={detail['tp']} FP={detail['fp']} TN={detail['tn']} FN={detail['fn']})"
        )
    if result["errors"]:
        lines.append(f"  Misclassified: {result['errors']}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate W2-EVID-02 citation support warnings")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    result = evaluate_cases(cases)
    print(format_report(result, fmt=args.format))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
