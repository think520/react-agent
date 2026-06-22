"""GrepRetriever — exact text search with context expansion.

Finds "where does X appear in the source" using ripgrep or Python fallback.
Supports two intent modes: exact_lookup and coverage.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rag.schema import RetrievalHit, DocumentHit

logger = logging.getLogger(__name__)


@dataclass
class GrepMatch:
    """A single grep match with context."""
    document_id: str
    source: str
    text: str
    match_context: str
    match_type: str  # "exact_phrase" | "all_terms" | "partial"
    context_chars: int
    heading_text: str = ""


class GrepRetriever:
    """Exact text search with intent-aware evidence evaluation."""

    def __init__(self, workspace: str, config: dict | None = None):
        self.workspace = Path(workspace)

        rag_cfg = (config or {}).get("rag", {})
        ret_cfg = rag_cfg.get("retrieval", {})
        grep_cfg = ret_cfg.get("grep", {})
        self.window_chars = grep_cfg.get("window_chars", 500)
        self.expand_chars = grep_cfg.get("expand_chars", 1000)
        self.max_candidate_docs = grep_cfg.get("max_candidate_docs", 15)

    def search(
        self,
        query: str,
        documents: list[DocumentHit],
        intent: str = "exact_lookup",
        window_chars: int | None = None,
    ) -> list[RetrievalHit]:
        """Search for exact text matches in candidate documents.

        Args:
            query: Search text.
            documents: Candidate documents from DirectoryRetriever.
            intent: "exact_lookup" or "coverage".
            window_chars: Context window size (overrides config).

        Returns:
            List of RetrievalHits with match_context.
        """
        if not documents:
            return []

        window = window_chars or self.window_chars

        # Expansion ladder
        configs = [
            (documents[:8], window),
            (documents[:8], self.expand_chars),
            (documents[:self.max_candidate_docs], self.expand_chars),
        ]

        for candidate_docs, win in configs:
            matches = self._grep_candidates(query, candidate_docs, win)

            if not matches:
                continue

            total_context = sum(m.context_chars for m in matches)
            if not _is_evidence_thin(matches, total_context, intent):
                # Good enough evidence
                confidence = _assess_confidence(matches, intent, expanded=(win > window))
                return _matches_to_hits(matches, confidence, expanded=(win > window), window=win)

        # Still thin after expansion
        if matches:
            confidence = "low"
            return _matches_to_hits(matches, confidence, expanded=True, window=self.expand_chars)

        return []

    def _grep_candidates(
        self,
        query: str,
        documents: list[DocumentHit],
        window_chars: int,
    ) -> list[GrepMatch]:
        """Run grep on candidate documents."""
        matches: list[GrepMatch] = []

        for doc in documents:
            # Resolve file path
            file_path = self.workspace / doc.source
            if not file_path.exists():
                continue

            doc_matches = _grep_file(
                query=query,
                file_path=file_path,
                document_id=doc.document_id,
                source=doc.source,
                window_chars=window_chars,
            )
            matches.extend(doc_matches)

        return matches


def _grep_file(
    query: str,
    file_path: Path,
    document_id: str,
    source: str,
    window_chars: int,
) -> list[GrepMatch]:
    """Grep a single file for query matches."""
    # Try ripgrep first
    rg_matches = _try_rg(query, file_path, window_chars)
    if rg_matches is not None:
        return [
            GrepMatch(
                document_id=document_id,
                source=source,
                text=m["text"],
                match_context=m["context"],
                match_type=m["match_type"],
                context_chars=len(m["context"]),
            )
            for m in rg_matches
        ]

    # Python fallback
    return _python_grep(query, file_path, document_id, source, window_chars)


def _try_rg(query: str, file_path: Path, window_chars: int) -> list[dict] | None:
    """Try ripgrep for fast text search. Returns None if rg unavailable."""
    try:
        result = subprocess.run(
            [
                "rg",
                "--no-heading",
                "--line-number",
                f"--context={max(1, window_chars // 80)}",
                "--max-count=20",
                re.escape(query),
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode not in (0, 1):  # 0=found, 1=not found
            return None

        if not result.stdout.strip():
            return []

        return _parse_rg_output(result.stdout, query, window_chars)

    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return None


def _parse_rg_output(output: str, query: str, window_chars: int) -> list[dict]:
    """Parse ripgrep output into match dicts."""
    matches = []
    blocks = output.strip().split("\n--\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        context_text = "\n".join(lines)
        # Find the matching line
        match_line = ""
        for line in lines:
            if query.lower() in line.lower():
                match_line = line
                break

        if not match_line:
            match_line = lines[0] if lines else ""

        # Determine match type
        if query.lower() in match_line.lower():
            match_type = "exact_phrase"
        else:
            match_type = "partial"

        matches.append({
            "text": match_line,
            "context": context_text[:window_chars * 2],
            "match_type": match_type,
        })

    return matches


def _python_grep(
    query: str,
    file_path: Path,
    document_id: str,
    source: str,
    window_chars: int,
) -> list[GrepMatch]:
    """Python fallback for text search."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, Exception):
        return []

    query_lower = query.lower()
    text_lower = text.lower()
    matches: list[GrepMatch] = []

    # Find all occurrences
    start = 0
    while start < len(text_lower):
        pos = text_lower.find(query_lower, start)
        if pos == -1:
            break

        # Extract context window
        ctx_start = max(0, pos - window_chars)
        ctx_end = min(len(text), pos + len(query) + window_chars)
        context = text[ctx_start:ctx_end]

        # Determine match type
        # Check if all query words appear nearby
        query_words = set(query.lower().split())
        context_lower = context.lower()
        found_words = sum(1 for w in query_words if w in context_lower)

        if query_lower in context_lower:
            match_type = "exact_phrase"
        elif found_words == len(query_words):
            match_type = "all_terms"
        else:
            match_type = "partial"

        matches.append(GrepMatch(
            document_id=document_id,
            source=source,
            text=text[pos:pos + len(query) + 100],
            match_context=context,
            match_type=match_type,
            context_chars=len(context),
        ))

        start = pos + 1

        # Limit matches per file
        if len(matches) >= 20:
            break

    return matches


def _is_evidence_thin(
    matches: list[GrepMatch],
    total_context_chars: int,
    intent: str,
) -> bool:
    """Judge if evidence is too thin based on intent."""
    if not matches:
        return True
    if total_context_chars < 300:
        return True

    strong_matches = [
        m for m in matches
        if m.match_type in {"exact_phrase", "all_terms"}
        and m.context_chars >= 300
    ]

    if intent == "exact_lookup":
        return len(strong_matches) == 0

    # coverage
    unique_docs = {m.document_id for m in matches}
    unique_sections = {m.heading_text for m in matches if m.heading_text}
    if len(matches) < 2:
        return True
    if len(unique_docs) < 2 and len(unique_sections) < 2:
        return True

    return False


def _assess_confidence(
    matches: list[GrepMatch],
    intent: str,
    expanded: bool,
) -> str:
    """Assess confidence level of grep evidence."""
    strong_matches = [
        m for m in matches
        if m.match_type in {"exact_phrase", "all_terms"}
        and m.context_chars >= 300
    ]

    if intent == "exact_lookup":
        if strong_matches:
            return "high"
        if matches:
            return "medium"
        return "low"

    # coverage
    unique_docs = {m.document_id for m in matches}
    unique_sections = {m.heading_text for m in matches if m.heading_text}

    if len(unique_docs) >= 2 or len(unique_sections) >= 2:
        return "high"
    if matches and not expanded:
        return "medium"
    return "low"


def _matches_to_hits(
    matches: list[GrepMatch],
    confidence: str,
    expanded: bool,
    window: int,
) -> list[RetrievalHit]:
    """Convert GrepMatch list to RetrievalHit list."""
    hits = []
    for m in matches:
        hits.append(RetrievalHit(
            chunk_id=f"grep:{m.document_id}:{hash(m.match_context) & 0xFFFFFFFF:08x}",
            document_id=m.document_id,
            source=m.source,
            text=m.text,
            heading_text=m.heading_text,
            score=1.0 if m.match_type == "exact_phrase" else 0.7,
            retrievers=["grep"],
            match_context=m.match_context,
            debug={
                "match_type": m.match_type,
                "confidence": confidence,
                "expanded": expanded,
                "window_chars": window,
            },
        ))
    return hits
