"""Format search results for LLM consumption.

Handles both legacy (dict-based) and new (RetrievalHit-based) result formats.

W2-EVID-01：每条证据有一个**引用标签**（``[S3fa9c1]``）。标签只由 source_id 决定，
所以同一片段在一轮里被检索多次、或既出现在预检索又出现在工具结果里，标签都一样；
运行时门禁（``service.evidence_policy.CitationPolicy``）据此核对回答里的引用
是否都来自本轮真实拿到的证据。
"""

import hashlib
import re

# 回答里任何长得像引用标签的东西都要被核对 —— 包括模型自己编的 [S1]。
CITATION_MARKER = re.compile(r"\[(S[0-9A-Za-z]{1,16})\]")

CITATION_INSTRUCTION = (
    "引用规则：句子依据了某条资料，就在句末原样照抄它的方括号引用标签（形如 [S 加 6 位字符]，见每条资料开头）。"
    "只能使用本轮给出的标签，不要自己编号；通用知识、概念地图和个人知识不加标签。"
)


def cite_label(source_id: str) -> str:
    """source_id → 引用标签。确定性：同一个 source_id 永远得到同一个标签。"""
    digest = hashlib.sha1(str(source_id or "").encode("utf-8")).hexdigest()[:6]
    return f"S{digest}"


def hit_source_id(hit: dict) -> str:
    """检索命中的稳定身份：优先 chunk_id，旧数据退回 source（与界面来源一致）。"""
    return str(hit.get("chunk_id") or hit.get("source") or "")


def cited_labels(text: str) -> list[str]:
    """按出现顺序列出回答里的引用标签（去重）。"""
    seen: list[str] = []
    for match in CITATION_MARKER.finditer(text or ""):
        label = match.group(1)
        if label not in seen:
            seen.append(label)
    return seen


def format_search_results(results: list[dict]) -> str:
    """Format search results for an LLM tool response.

    Each result dict may contain:
    - text, source, score (legacy)
    - metadata.heading_text, metadata.page_start, metadata.slide_start (new)
    - retrievers (new)
    - match_context (grep results)
    """
    if not results:
        return "No matching knowledge chunks found."

    lines = []
    for result in results:
        source = result.get("source", "")
        score = result.get("score", 0)
        text = result.get("text", "").strip()
        retrievers = result.get("retrievers", [])
        match_context = result.get("match_context")

        # Build header
        header_parts = [f"[{cite_label(hit_source_id(result))}] source={source} score={score:.3f}"]

        # Add heading info from metadata
        meta = result.get("metadata", {})
        heading_text = meta.get("heading_text", "")
        if heading_text:
            header_parts.append(f"heading={heading_text}")

        # Page/slide info
        page_start = meta.get("page_start")
        page_end = meta.get("page_end")
        if page_start:
            page_str = f"p{page_start}"
            if page_end and page_end != page_start:
                page_str += f"-p{page_end}"
            header_parts.append(f"page={page_str}")

        slide_start = meta.get("slide_start")
        slide_end = meta.get("slide_end")
        if slide_start:
            slide_str = f"slide {slide_start}"
            if slide_end and slide_end != slide_start:
                slide_str += f"-{slide_end}"
            header_parts.append(slide_str)

        # Retriever info
        if retrievers:
            header_parts.append(f"via={','.join(retrievers)}")

        header = " ".join(header_parts)

        # Build body
        body_parts = [text]

        # Add grep match context if available
        if match_context and match_context != text:
            body_parts.append(f"\n[match context]\n{match_context}")

        body = "\n".join(body_parts)
        lines.append(f"{header}\n{body}")

    return CITATION_INSTRUCTION + "\n\n" + "\n\n".join(lines)
