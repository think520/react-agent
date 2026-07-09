"""Rule-based Query Router for RAG v2.

Routes queries to the appropriate retrieval mode based on pattern matching.
Priority: directory_grep > directory > hybrid.

No LLM involved — pure regex rules.
"""

from __future__ import annotations

import re

# Patterns for directory_grep mode (exact source/context lookup)
_DIRECTORY_GREP_PATTERNS = [
    r"在哪里提到", r"哪里提到", r"在哪.*提到",
    r"原文怎么说", r"原文.*说", r"引用.*原文",
    r"出处", r"来源", r"引用",
    r"包含.*上下文", r"包含.*原文", r"查找.*出现",
    r"where.*mentioned", r"original.*text", r"quote",
    r"source.*of", r"reference",
]

# Patterns for directory mode (document-level routing)
_DIRECTORY_PATTERNS = [
    r"哪些文档", r"哪一章", r"哪些资料", r"文档列表",
    r"资料列表", r"目录", r"应该看哪些", r"看哪.*资料",
    r"which.*document", r"which.*chapter", r"document.*list",
    r"what.*materials",
]


def auto_route(query: str) -> str:
    """Route query to the appropriate retrieval mode.

    Returns: "directory_grep" | "directory" | "hybrid"
    """
    q = query.strip()
    if not q:
        return "hybrid"

    # Check directory_grep first (more specific)
    for pattern in _DIRECTORY_GREP_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return "directory_grep"

    # Check directory
    for pattern in _DIRECTORY_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return "directory"

    return "hybrid"
