"""W2-EVID-02：引用支持度风险提示（只作风险信号，不修改或阻断 CitationPolicy）。

职责边界：
- W2-EVID-01（CitationPolicy）负责核对「[Sxxxxxx] 引用标签是否真实存在于本轮证据」。
- 本模块只负责检测「引用真实，但断言结论与对应来源片段存在极性/约束矛盾或明显低重合」，
  产出结构化 advisory 警告（`support_warnings`），交由前端折叠展示「请核对原文」；
  绝不改写、删改 `response_text`，也不替代或放松任何原文证据门禁。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

from rag.citations import CITATION_MARKER, _mask_code, cite_label, hit_source_id

MAX_WARNINGS_PER_RESPONSE = 5
MAX_CLAIM_PREVIEW_CHARS = 160
MAX_EXCERPT_PREVIEW_CHARS = 140

_HEADER_LABEL_RE = re.compile(r"(?:^|\n)\s*(?:-\s*)?\[(S[0-9a-f]{6})\]")
_COMPLEXITY_RE = re.compile(r"O\s*\(([^()\n]{1,24})\)", re.IGNORECASE)
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:\r?\n+|[。！？!?；;]+|\.(?=\s|$)|"
    r"[，,]\s*(?=而|但(?:是)?|然而|相反|不过|unlike\b|whereas\b|while\b|however\b)|"
    r"\s+(?=whereas\b|while\b|however\b|unlike\b))",
    re.IGNORECASE,
)

# 礼貌/指代句过滤：如「详见讲义 [S111111]」「See source [S111111]」不算独立知识断言。
_DEICTIC_NOISE_RE = re.compile(
    r"(?:详见|参见|参考|请看|见原文|见上文|见下文|如下图|如下表|见资料|来源于|出自|"
    r"\b(?:see|refer\s+to|details?|source|above|below|reference)\b)",
    re.IGNORECASE,
)

# 让步/递进连词剥离：防止「不仅支持 A 还支持 B」「not only ... but also」把「不/not」误判为否定。
_CONCESSIVE_STRIP_RES = (
    re.compile(r"不仅(?:限于|只是|仅)?|不仅仅是?|不只是?|不止于|不光|不但"),
    re.compile(r"\bnot\s+only\b", re.IGNORECASE),
    re.compile(r"\bno\s+doubt\b|\bnotwithstanding\b", re.IGNORECASE),
    re.compile(r"(?:虽然|尽管|虽说)[^，。；\n]{0,30}[，,]?(?:但(?:是)?|然而)"),
)

_EN_STOPWORDS = frozenset({
    "the", "is", "are", "was", "were", "be", "been", "being", "a", "an", "and", "or",
    "of", "in", "on", "to", "for", "with", "by", "from", "that", "this", "these", "those",
    "it", "its", "as", "at", "into", "about", "can", "could", "will", "would", "may", "might",
    "should", "must", "have", "has", "had", "do", "does", "did", "using", "used", "use",
    "when", "where", "which", "who", "what", "why", "how", "while", "only", "also", "still",
    "not", "no", "never", "cannot", "cant", "doesnt", "dont", "isnt", "arent", "both", "but",
})

_CN_NOISE_CHARS = frozenset("的是在了有和与及或但而这那如果可以能够通过进行使用关于一个一些什么怎么为什么因此所以并且而且还是或者并都也就才把被让从向对给在等中上下内外表")

# 语义对立 / 硬约束矩阵：(category_id, side_a_re, side_b_re, human_reason)
_ANTONYM_PAIRS: tuple[tuple[str, re.Pattern[str], re.Pattern[str], str], ...] = (
    (
        "weight_sign",
        re.compile(
            r"(?:(?:只|仅)?(?:适用|允许|要求|限制)于?|必须为)?(?:非负|正)(?:权|权重|边权)|"
            r"(?:边权|权重|权值)[^，。；\n]{0,4}(?:均为?|是|为)?非负|"
            r"(?:不能|不可|无法|不允许|禁止|不支持|不能有|不存在|不可存在)[^，。；\n]{0,8}负(?:权|权重|边|环)|"
            r"\bnon-negative\s+(?:edge\s+)?weights?\b|"
            r"\b(?:cannot|can't|does\s+not|doesn't|fails?\s+with)\s+(?:handle|support|allow|work\s+with)\s+negative\s+(?:edge\s+)?(?:weights?|edges?|cycles?)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?<![非不无没未])(?:可|可以|能|能够|支持|允许|处理|包含|适用(?:于)?)[^，。；\n]{0,10}(?<![非不无没未])负(?:权|权重|边)|"
            r"(?<!non[- ])(?<!not\s)(?<!no\s)\b(?:supports?|allows?|handles?|works?\s+with)\s+negative\s+(?:edge\s+)?(?:weights?|edges?)\b",
            re.IGNORECASE,
        ),
        "关于负权边 / 非负权约束的表述与引用原文相反，请核对原文条件。",
    ),
    (
        "graph_cycles",
        re.compile(
            r"有向无环|(?<![有非])无环|\bDAG\b|\bacyclic\b|"
            r"(?:不能|不可|无法|不允许|禁止)[^，。；\n]{0,6}(?:存在|包含|有)?环|"
            r"\b(?:cannot|does\s+not|no)\s+(?:contain|have|allow)\s+cycles?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?<![不无没未])(?:支持|允许|包含|存在|适用|应用|带有|处理)[^，。；\n]{0,8}(?:有向|任意)?(?<![无非])环|"
            r"(?<!no\s)\b(?:supports?|allows?|works?\s+(?:on|with))\s+(?:arbitrary\s+)?cyclic\s+graphs?\b|"
            r"(?<!no\s)\ballows?\s+cycles?\b",
            re.IGNORECASE,
        ),
        "关于有环图 / 无环（DAG）前提的表述与引用原文不一致，请核对原文。",
    ),
    (
        "sortedness",
        re.compile(
            r"(?:必须|需要|要求|前提是?|仅适用于?)(?:保持|已)?(?:有序|排序|单调)|"
            r"\b(?:must\s+be|requires?\s+(?:a\s+)?)(?:sorted|ordered)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:无需|不需要|不必|不用)(?:提前|事先|预先)?(?:排序|有序)|"
            r"直接(?:用于|适用于|查找)(?<![已未不])无序|"
            r"(?<![已])无序(?:数组|列表|序列)?(?:也|同样|都)?(?:可以|能|适用|有效)|"
            r"\b(?:unsorted|without\s+sorting|does\s+not\s+require\s+sorting)\b",
            re.IGNORECASE,
        ),
        "关于「必须有序 / 可无序」前置条件的表述与引用原文矛盾，请核对原文。",
    ),
    (
        "mutability",
        re.compile(
            r"不可变|(?<![可])只读|无法(?:在)?原地修改|不能(?:被)?修改|"
            r"\bimmutable\b|\bread[- ]only\b|\bcannot\s+be\s+modified\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?<![不无未法])(?:可|可以|允许|支持)(?:在)?(?:原地)?(?:修改|变更|改写|增删|可变)|"
            r"(?<![不无])可变(?:序列|容器|对象|结构)|"
            r"(?<!im)\bmutable\b|\b(?:can|allows?)\s+(?:be\s+)?modif(?:ied|y)\b",
            re.IGNORECASE,
        ),
        "关于可变性 / 只读约束的表述与引用原文不一致，请核对原文。",
    ),
    (
        "sort_stability",
        re.compile(
            r"不稳定|\bnot\s+(?:a\s+)?stable\b|\bunstable\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?<![不非未])(?:属于|是|保持|具有)?稳定(?:排序|算法|性|的)|"
            r"(?<!un)(?<!not\s)(?<!not\s a\s)\b(?:is\s+(?:a\s+)?|guarantees?\s+)stable\s+(?:sort(?:ing)?|algorithm)\b|\bis\s+stable\b",
            re.IGNORECASE,
        ),
        "关于算法稳定性（稳定 vs 不稳定）的表述与引用原文不一致，请核对原文。",
    ),
    (
        "optimality",
        re.compile(
            r"(?:不|未能|不能|无法|并不)保证(?:一定|总是|必定|绝对)?(?:得到|找到|收敛到)?(?:全局)?最优|"
            r"启发式|近似解|可能陷入局部最优|"
            r"\b(?:does\s+not|doesn't|cannot|not)\s+guarantee\s+(?:the\s+)?(?:global\s+)?optimal\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?<![不未没无并])(?:一定|总是|必然|可以?|能够)?保证(?:一定|总是|必定|绝对)?(?:得到|找到|达到)?(?:全局)?最优|"
            r"(?<!not\s)\b(?:always\s+)?guarantees?\s+(?:the\s+)?(?:global\s+)?optimal\b",
            re.IGNORECASE,
        ),
        "关于最优性保证（全局最优 vs 启发式/不保证最优）的表述与引用原文相反，请核对原文。",
    ),
)

# 一般谓词正反极性对：(neg_re, pos_re, anchor_name) — 注意先匹配否定再匹配肯定，防止子串误判。
_PREDICATE_POLARITY_PAIRS: tuple[tuple[re.Pattern[str], re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?:不支持|无法支持|不能支持|\b(?:does\s+not|doesn't|cannot|can't)\s+support\b)", re.IGNORECASE),
        re.compile(r"(?<![不无没未])(?:支持|\bsupports?\b)", re.IGNORECASE),
        "支持度极性",
    ),
    (
        re.compile(r"(?:不适用|无法适用|不适合|\b(?:not\s+applicable|does\s+not\s+apply)\b)", re.IGNORECASE),
        re.compile(r"(?<![不无没未])(?:适用(?:于)?|\bapplies\b|\bapplicable\b)", re.IGNORECASE),
        "适用条件",
    ),
    (
        re.compile(r"(?:不需要|无需|不必|不用|\b(?:does\s+not|doesn't|no)\s+(?:require|need)\b)", re.IGNORECASE),
        re.compile(r"(?<![不无没未])(?:需要|必须|依赖|\b(?:requires?|must\s+have)\b)", re.IGNORECASE),
        "前置条件",
    ),
    (
        re.compile(r"(?:不允许|禁止|不可|不能|严禁|\b(?:forbids?|prohibits?|cannot|not\s+allowed)\b)", re.IGNORECASE),
        re.compile(r"(?<![不无没未])(?:允许|可以|\b(?:allows?|permits?)\b)", re.IGNORECASE),
        "权限/约束",
    ),
    (
        re.compile(r"(?:不阻塞|非阻塞|无需加锁|无锁|\b(?:non-blocking|lock-free|does\s+not\s+block)\b)", re.IGNORECASE),
        re.compile(r"(?<![不非无免])(?:必须)?阻塞|\bmust\s+block\b", re.IGNORECASE),
        "并发阻塞行为",
    ),
    (
        re.compile(r"(?:不收敛|无法收敛|不保证收敛|\b(?:does\s+not|fails?\s+to)\s+converge\b)", re.IGNORECASE),
        re.compile(r"(?<![不无没未])(?:一定|必然|总是|会)?收敛|\bconverges?\b", re.IGNORECASE),
        "收敛性质",
    ),
    (
        re.compile(r"(?:不开启|关闭|禁用|默认关闭|\b(?:disabled?|turned\s+off)\b)", re.IGNORECASE),
        re.compile(r"(?<![不未])(?:默认)?(?:开启|启用|打开)|\benabled?\b", re.IGNORECASE),
        "开关状态",
    ),
)


@dataclass(frozen=True)
class EvidenceSnippet:
    cite_label: str
    text: str
    title: str = ""
    source_type: str = "local"
    source_id: str = ""


@dataclass(frozen=True)
class SupportWarning:
    cite_label: str
    claim: str
    reason_code: str
    reason: str
    evidence_excerpt: str = ""
    source_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cite_label": self.cite_label,
            "claim": self.claim,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }
        if self.evidence_excerpt:
            payload["evidence_excerpt"] = self.evidence_excerpt
        if self.source_title:
            payload["source_title"] = self.source_title
        return payload


def _upsert_snippet(
    store: dict[str, EvidenceSnippet],
    candidate: EvidenceSnippet,
    *,
    prefer_meta: bool = False,
) -> None:
    label = str(candidate.cite_label or "").strip()
    if not label:
        return
    clean_text = " ".join((candidate.text or "").split())
    clean_title = (candidate.title or "").strip()
    clean_source_id = (candidate.source_id or "").strip()
    existing = store.get(label)
    if existing is None:
        store[label] = EvidenceSnippet(
            cite_label=label,
            text=clean_text,
            title=clean_title,
            source_type=(candidate.source_type or "local").strip() or "local",
            source_id=clean_source_id,
        )
        return
    chosen_text = clean_text if len(clean_text) > len(existing.text) else existing.text
    chosen_title = (clean_title or existing.title) if prefer_meta else (existing.title or clean_title)
    store[label] = EvidenceSnippet(
        cite_label=label,
        text=chosen_text,
        title=chosen_title,
        source_type=existing.source_type or (candidate.source_type or "local"),
        source_id=existing.source_id or clean_source_id,
    )


def _extract_source_from_header(header: str) -> tuple[str, str]:
    title = ""
    source_match = re.search(r"\bsource=([^\s]+)", header)
    if source_match:
        title = source_match.group(1)
    # _hit_line format: "Title · chunk_id：body"
    pre_colon = re.split(r"[：:]", header, maxsplit=1)[0].strip()
    if " · " in pre_colon and not title:
        title = pre_colon.split(" · ", 1)[0].strip()
    elif " — " in pre_colon and not title:
        title = pre_colon.split(" — ", 1)[0].strip()
    return title, pre_colon


def _extract_labeled_blocks(text: str, store: dict[str, EvidenceSnippet]) -> None:
    if not text:
        return
    matches = list(_HEADER_LABEL_RE.finditer(text))
    for index, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if not block:
            continue
        lines = block.splitlines()
        first_line = lines[0].strip() if lines else ""
        title, _ = _extract_source_from_header(first_line)
        body = ""
        # Two common single-line / multi-line formats:
        # 1) "- [Sxxxxxx] Title · chunk_id：Chunk text..."
        # 2) "[Sxxxxxx] source=foo score=0.9 ... \nChunk text..."
        if first_line.startswith("source=") or len(lines) > 1:
            body_lines = lines[1:] if len(lines) > 1 else []
            if not body_lines and ("：" in first_line or ": " in first_line):
                body = re.split(r"[：:]\s*", first_line, maxsplit=1)[1]
            else:
                body = "\n".join(body_lines)
        elif "：" in first_line or ": " in first_line:
            body = re.split(r"[：:]\s*", first_line, maxsplit=1)[1]
        else:
            body = first_line
        _upsert_snippet(
            store,
            EvidenceSnippet(cite_label=label, text=body or first_line, title=title),
        )


def _ingest_sources_list(sources: Any, store: dict[str, EvidenceSnippet]) -> None:
    if not isinstance(sources, list):
        return
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "")
        label = str(source.get("cite_label") or (cite_label(source_id) if source_id else ""))
        if not label:
            continue
        _upsert_snippet(
            store,
            EvidenceSnippet(
                cite_label=label,
                text=str(source.get("excerpt") or source.get("text") or ""),
                title=str(source.get("title") or ""),
                source_type=str(source.get("source_type") or "local"),
                source_id=source_id,
            ),
            prefer_meta=True,
        )


def collect_turn_evidence_map(
    *,
    preset_evidence: str = "",
    kb_seed: str = "",
    tool_events: Sequence[dict[str, Any]] = (),
    attribution: dict[str, Any] | None = None,
) -> dict[str, EvidenceSnippet]:
    """从本轮预检索、预设证据、工具输出与 attribution 中聚拢 [Sxxxxxx] 原文片段。"""
    store: dict[str, EvidenceSnippet] = {}
    if isinstance(attribution, dict):
        _ingest_sources_list(attribution.get("sources"), store)

    for text_block in (preset_evidence, kb_seed):
        if text_block:
            _extract_labeled_blocks(text_block, store)

    for event in tool_events:
        if not isinstance(event, dict):
            continue
        for artifact in event.get("artifacts") or ():
            if not isinstance(artifact, dict):
                continue
            atype = artifact.get("type")
            if atype == "citation":
                _ingest_sources_list((artifact.get("attribution") or {}).get("sources"), store)
            elif atype == "web_evidence":
                _ingest_sources_list(artifact.get("sources"), store)

        content = str(event.get("content") or "")
        if not content:
            continue
        stripped = content.lstrip()
        remainder = content
        if stripped.startswith("{"):
            try:
                payload, end_idx = json.JSONDecoder().raw_decode(stripped)
                remainder = stripped[end_idx:]
                if isinstance(payload, dict) and isinstance(payload.get("results"), list):
                    for item in payload["results"]:
                        if not isinstance(item, dict):
                            continue
                        sid = hit_source_id(item)
                        if not sid:
                            continue
                        metadata = item.get("metadata") or {}
                        _upsert_snippet(
                            store,
                            EvidenceSnippet(
                                cite_label=cite_label(sid),
                                text=str(item.get("text") or item.get("match_context") or ""),
                                title=str(item.get("title") or metadata.get("title") or item.get("source") or ""),
                                source_type="local",
                                source_id=sid,
                            ),
                            prefer_meta=True,
                        )
            except ValueError:
                remainder = content
        _extract_labeled_blocks(remainder, store)

    return store


def _strip_concessive(text: str) -> str:
    cleaned = text or ""
    for pattern in _CONCESSIVE_STRIP_RES:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def _extract_tokens(text: str, *, drop_deictic: bool = False) -> set[str]:
    work = _DEICTIC_NOISE_RE.sub(" ", text) if drop_deictic else (text or "")
    work = CITATION_MARKER.sub(" ", work)
    tokens: set[str] = set()
    for word in re.findall(r"[a-zA-Z0-9_+#.-]{2,}", work.lower()):
        cleaned = word.strip(".,:;!?\"'()")
        if len(cleaned) >= 2 and cleaned not in _EN_STOPWORDS:
            tokens.add(cleaned)
    for seq in re.findall(r"[\u4e00-\u9fff]+", work):
        filtered = "".join(ch for ch in seq if ch not in _CN_NOISE_CHARS)
        if not filtered:
            continue
        if len(filtered) == 1:
            tokens.add(filtered)
        else:
            for idx in range(len(filtered) - 1):
                tokens.add(filtered[idx : idx + 2])
    return tokens


def _normalize_complexities(text: str) -> set[str]:
    result: set[str] = set()
    for inner in _COMPLEXITY_RE.findall(text or ""):
        norm = inner.lower().strip()
        norm = norm.replace("²", "^2").replace("³", "^3").replace("₂", "2")
        norm = norm.replace("|", "").replace("*", "").replace("·", "")
        norm = re.sub(r"\s+", "", norm)
        if norm:
            result.add(f"o({norm})")
    return result


def _split_clauses(text: str) -> list[str]:
    return [chunk.strip() for chunk in _CLAUSE_SPLIT_RE.split(text or "") if chunk.strip()]


def _extract_claim_pairs(response_text: str) -> list[tuple[str, str]]:
    """把含 [Sxxxxxx] 的回答拆成 (断言文本, cite_label) 对，跳过代码与无实体指代句。"""
    masked = _mask_code(response_text or "")
    # 先按大句边界切分（注意句号可能在标签之前：「……。 [Sa1b2c3]」）
    segments = [seg.strip() for seg in re.split(r"(?:\r?\n+|[。！？!?]+|\.(?=\s|$|\[S[0-9a-f]{6}\]))", masked) if seg.strip()]
    claims_with_labels: list[tuple[str, str]] = []
    last_claim_text = ""

    for seg in segments:
        matches = list(CITATION_MARKER.finditer(seg))
        bare_text = CITATION_MARKER.sub("", seg).strip(" ；;，,、:：-–—")
        if not matches:
            if bare_text:
                last_claim_text = bare_text
            continue
        if not bare_text:
            # 句号后的挂靠引用，如 「……结论。[S111111]」
            if last_claim_text:
                for match in matches:
                    claims_with_labels.append((last_claim_text, match.group(1)))
            continue

        distinct_labels = {m.group(1) for m in matches}
        if len(distinct_labels) > 1:
            # 同句多引用：按分句归属每个子断言，避免左右互串。
            sub_clauses = [c.strip() for c in re.split(r"[，,;；]+", seg) if c.strip()]
            pending_text = ""
            for clause in sub_clauses:
                c_matches = list(CITATION_MARKER.finditer(clause))
                c_bare = CITATION_MARKER.sub("", clause).strip(" ：:")
                if not c_matches:
                    pending_text = f"{pending_text} {c_bare}".strip()
                    continue
                claim_body = f"{pending_text} {c_bare}".strip() if not c_bare else c_bare
                if pending_text and len(_extract_tokens(c_bare, drop_deictic=True)) < 2:
                    claim_body = f"{pending_text} {c_bare}".strip()
                pending_text = ""
                for m in c_matches:
                    claims_with_labels.append((claim_body, m.group(1)))
            last_claim_text = bare_text
            continue

        for m in matches:
            claims_with_labels.append((bare_text, m.group(1)))
        last_claim_text = bare_text

    return claims_with_labels


def _pick_best_clause(claim_tokens: set[str], evidence_text: str) -> str:
    clauses = _split_clauses(evidence_text)
    if not clauses:
        return evidence_text
    best_clause = clauses[0]
    best_score = -1
    for clause in clauses:
        score = len(claim_tokens & _extract_tokens(clause))
        if score > best_score:
            best_score = score
            best_clause = clause
    return best_clause


def _detect_antonym_conflict(claim_clean: str, evidence_clause_clean: str) -> str | None:
    for _, side_a, side_b, reason in _ANTONYM_PAIRS:
        c_a = bool(side_a.search(claim_clean))
        c_b = bool(side_b.search(claim_clean))
        e_a = bool(side_a.search(evidence_clause_clean))
        e_b = bool(side_b.search(evidence_clause_clean))
        # 单侧明确命中且双方落在对立阵营才报警（若同一分句两侧混用则不武断）
        if (c_a and not c_b and e_b and not e_a) or (c_b and not c_a and e_a and not e_b):
            return reason
    return None


def _detect_complexity_conflict(claim_clean: str, evidence_clause_clean: str) -> str | None:
    c_comp = _normalize_complexities(claim_clean)
    if not c_comp:
        return None
    e_comp = _normalize_complexities(evidence_clause_clean)
    if not e_comp or (c_comp & e_comp):
        return None
    claimed = ", ".join(sorted(c_comp))
    found = ", ".join(sorted(e_comp))
    return f"复杂度断言（{claimed}）与引用片段（{found}）不一致，请核对原文。"


def _detect_predicate_polarity_conflict(
    claim_clean: str,
    evidence_clause_clean: str,
    shared_count: int,
) -> str | None:
    if shared_count < 2:
        return None
    for neg_re, pos_re, label in _PREDICATE_POLARITY_PAIRS:
        c_neg = bool(neg_re.search(claim_clean))
        c_pos = bool(pos_re.search(claim_clean)) and not c_neg
        e_neg = bool(neg_re.search(evidence_clause_clean))
        e_pos = bool(pos_re.search(evidence_clause_clean)) and not e_neg
        if (c_neg and e_pos) or (c_pos and e_neg):
            return f"句子中的{label}（肯定/否定）与引用片段表述相反，请核对原文。"
    return None


def _preview(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def check_citation_support(
    response_text: str,
    evidence_map: dict[str, EvidenceSnippet],
) -> list[SupportWarning]:
    """检测回答正文里的 [Sxxxxxx] 断言是否与对应来源片段矛盾或明显缺少支撑。"""
    if not response_text or not evidence_map:
        return []

    warnings: list[SupportWarning] = []
    seen_keys: set[tuple[str, str]] = set()

    for claim, label in _extract_claim_pairs(response_text):
        snippet = evidence_map.get(label)
        if snippet is None or not snippet.text.strip():
            continue

        claim_tokens = _extract_tokens(claim, drop_deictic=True)
        # 过短的非实体陈述（「详见下文」「如下表」）跳过，避免无意义告警。
        if len(claim_tokens) < 3:
            continue

        evidence_all_tokens = _extract_tokens(f"{snippet.title} {snippet.text}")
        overlap = claim_tokens & evidence_all_tokens

        if not overlap and len(claim_tokens) >= 4:
            key = (label, "low_overlap")
            if key not in seen_keys:
                seen_keys.add(key)
                warnings.append(SupportWarning(
                    cite_label=label,
                    claim=_preview(claim, MAX_CLAIM_PREVIEW_CHARS),
                    reason_code="low_overlap",
                    reason="断言中的核心术语未在所引用的来源片段中出现，请核对原文是否真的包含该结论。",
                    evidence_excerpt=_preview(snippet.text, MAX_EXCERPT_PREVIEW_CHARS),
                    source_title=snippet.title,
                ))
            if len(warnings) >= MAX_WARNINGS_PER_RESPONSE:
                break
            continue

        best_clause = _pick_best_clause(claim_tokens, snippet.text)
        claim_clean = _strip_concessive(claim)
        clause_clean = _strip_concessive(best_clause)
        clause_overlap = len(claim_tokens & _extract_tokens(best_clause))

        reason = (
            _detect_antonym_conflict(claim_clean, clause_clean)
            or _detect_complexity_conflict(claim_clean, clause_clean)
            or _detect_predicate_polarity_conflict(claim_clean, clause_clean, clause_overlap)
        )
        if reason:
            key = (label, "polarity_contradiction")
            if key not in seen_keys:
                seen_keys.add(key)
                warnings.append(SupportWarning(
                    cite_label=label,
                    claim=_preview(claim, MAX_CLAIM_PREVIEW_CHARS),
                    reason_code="polarity_contradiction",
                    reason=reason,
                    evidence_excerpt=_preview(best_clause or snippet.text, MAX_EXCERPT_PREVIEW_CHARS),
                    source_title=snippet.title,
                ))
            if len(warnings) >= MAX_WARNINGS_PER_RESPONSE:
                break

    return warnings
