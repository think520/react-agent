"""Format search results for LLM consumption.

Handles both legacy (dict-based) and new (RetrievalHit-based) result formats.
"""


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
    for index, result in enumerate(results, start=1):
        source = result.get("source", "")
        score = result.get("score", 0)
        text = result.get("text", "").strip()
        retrievers = result.get("retrievers", [])
        match_context = result.get("match_context")

        # Build header
        header_parts = [f"[{index}] source={source} score={score:.3f}"]

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

    return "\n\n".join(lines)
