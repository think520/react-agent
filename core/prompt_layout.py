"""KV-cache friendly prompt layout (AG-3.2).

Static prefix (identity / evidence contract / stable rules) must come first,
with the dynamic tail (memory, current context, checkpoint) after an explicit
cache boundary. The boundary is an HTML comment so it never changes visible
prompt semantics while making the cache cut point auditable.
"""

from __future__ import annotations

from typing import Sequence

CACHE_BOUNDARY_MARKER = "<!-- bobodan:cache-boundary -->"


def mark_dynamic_tail(text: str) -> str:
    """Prepend the cache-boundary marker to a dynamic prompt block."""
    if not text.strip():
        return text
    return f"{CACHE_BOUNDARY_MARKER}\n{text}"


def join_with_boundary(static_prefix: str, dynamic_tail: str | None) -> str:
    """Join a static prefix and dynamic tail with an explicit cache boundary."""
    if not static_prefix.strip():
        return (dynamic_tail or "").strip()
    if not (dynamic_tail or "").strip():
        return static_prefix.strip()
    return f"{static_prefix.strip()}\n{CACHE_BOUNDARY_MARKER}\n{dynamic_tail.strip()}"


def split_static_dynamic(parts: Sequence[str | None]) -> tuple[list[str], list[str]]:
    """Split prompt parts into static (before the first dynamic marker) vs tail.

    Parts that carry a dynamic marker (request scope, preferences, personal
    knowledge, session references, checkpoint) belong to the tail; everything
    before them is the stable prefix.
    """
    dynamic_markers = (
        "bobodan:request-scope",
        "bobodan:user-preferences",
        "bobodan:confirmed-personal-knowledge",
        "bobodan:session-references",
        "bobodan:checkpoint",
        "bobodan:concept-map-context",
    )
    static: list[str] = []
    dynamic: list[str] = []
    seen_dynamic = False
    for part in parts:
        text = part or ""
        if not text.strip():
            continue
        if not seen_dynamic and any(marker in text for marker in dynamic_markers):
            seen_dynamic = True
        if seen_dynamic:
            dynamic.append(text)
        else:
            static.append(text)
    return static, dynamic
