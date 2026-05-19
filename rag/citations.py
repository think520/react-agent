def format_search_results(results: list[dict]) -> str:
    """Format search results for an LLM tool response."""
    if not results:
        return "No matching knowledge chunks found."

    lines = []
    for index, result in enumerate(results, start=1):
        source = result.get("source", "")
        score = result.get("score", 0)
        text = result.get("text", "").strip()
        lines.append(f"[{index}] source={source} score={score}\n{text}")
    return "\n\n".join(lines)
