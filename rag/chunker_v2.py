"""Heading-aware adaptive chunking for RAG v2.

Converts SourceSection objects into TextChunk objects with:
- heading_path inheritance
- Long section secondary split
- Short section merge
- Embedding text injection (heading context prepended for indexing)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from rag.source_section import SourceSection


@dataclass
class ChunkingConfig:
    """Chunking parameters."""
    target_chars: int = 1800
    max_chars: int = 2600
    overlap_chars: int = 350
    min_chars: int = 400


def chunk_sections(
    sections: list[SourceSection],
    config: ChunkingConfig | None = None,
) -> list[dict]:
    """Convert SourceSections into chunk dicts ready for SQLite + Qdrant.

    Returns list of dicts with keys matching KBSQLiteStore.insert_chunks() schema.
    """
    cfg = config or ChunkingConfig()

    # Step 1: Split each section into chunks
    raw_chunks: list[dict] = []
    for section in sections:
        section_chunks = _split_section(section, cfg)
        raw_chunks.extend(section_chunks)

    if not raw_chunks:
        return []

    # Step 2: Merge short chunks with neighbors
    merged = _merge_short_chunks(raw_chunks, cfg)

    # Step 3: Add embedding text (heading context injection)
    for chunk in merged:
        chunk["embedding_text"] = _build_embedding_text(chunk)

    # Step 4: Assign final chunk indices
    for i, chunk in enumerate(merged):
        chunk["chunk_index"] = i

    return merged


def _split_section(section: SourceSection, cfg: ChunkingConfig) -> list[dict]:
    """Split a single section into chunks."""
    text = section.text.strip()
    if not text:
        return []

    heading_path = section.heading_path
    heading_text = " > ".join(heading_path) if heading_path else ""
    heading_level = section.metadata.get("heading_level", len(heading_path))
    source = section.source
    doc_title = section.doc_title
    file_type = section.metadata.get("file_type", "unknown")

    # Build base metadata for all chunks from this section
    base_meta = {
        "file_type": file_type,
        "doc_title": doc_title,
    }

    # Copy source-location metadata
    for key in ("page_start", "page_end", "slide_start", "slide_end",
                "tags", "course", "needs_ocr"):
        if key in section.metadata:
            base_meta[key] = section.metadata[key]

    if len(text) <= cfg.max_chars:
        # Short enough — single chunk
        chunk_id = _make_chunk_id(source, 0, text)
        return [_make_chunk_dict(
            chunk_id=chunk_id,
            source=source,
            text=text,
            heading_path=heading_path,
            heading_text=heading_text,
            heading_level=heading_level,
            section_id=_make_section_id(heading_path, source),
            chunk_index_in_section=0,
            char_start=0,
            char_end=len(text),
            metadata=base_meta,
            page_start=section.metadata.get("page_start"),
            page_end=section.metadata.get("page_end"),
            slide_start=section.metadata.get("slide_start"),
            slide_end=section.metadata.get("slide_end"),
        )]

    # Long section — split by paragraphs with overlap
    paragraphs = _split_paragraphs(text)
    chunks: list[dict] = []
    buffer = ""
    buffer_start = 0
    chunk_idx_in_section = 0

    for para in paragraphs:
        if len(buffer) + len(para) + 1 > cfg.target_chars and buffer:
            # Flush buffer as a chunk
            chunk_id = _make_chunk_id(source, chunk_idx_in_section, buffer)
            chunks.append(_make_chunk_dict(
                chunk_id=chunk_id,
                source=source,
                text=buffer.strip(),
                heading_path=heading_path,
                heading_text=heading_text,
                heading_level=heading_level,
                section_id=_make_section_id(heading_path, source),
                chunk_index_in_section=chunk_idx_in_section,
                char_start=buffer_start,
                char_end=buffer_start + len(buffer),
                metadata=base_meta,
                page_start=section.metadata.get("page_start"),
                page_end=section.metadata.get("page_end"),
                slide_start=section.metadata.get("slide_start"),
                slide_end=section.metadata.get("slide_end"),
            ))
            chunk_idx_in_section += 1

            # Start new buffer with overlap
            overlap_text = buffer[-cfg.overlap_chars:] if cfg.overlap_chars > 0 else ""
            buffer_start += len(buffer) - len(overlap_text)
            buffer = overlap_text + "\n\n" + para if overlap_text else para
        else:
            buffer = buffer + "\n\n" + para if buffer else para

    # Flush remaining buffer
    if buffer.strip():
        chunk_id = _make_chunk_id(source, chunk_idx_in_section, buffer)
        chunks.append(_make_chunk_dict(
            chunk_id=chunk_id,
            source=source,
            text=buffer.strip(),
            heading_path=heading_path,
            heading_text=heading_text,
            heading_level=heading_level,
            section_id=_make_section_id(heading_path, source),
            chunk_index_in_section=chunk_idx_in_section,
            char_start=buffer_start,
            char_end=buffer_start + len(buffer),
            metadata=base_meta,
            page_start=section.metadata.get("page_start"),
            page_end=section.metadata.get("page_end"),
            slide_start=section.metadata.get("slide_start"),
            slide_end=section.metadata.get("slide_end"),
        ))

    # Hard-split any chunks that exceed max_chars
    final_chunks: list[dict] = []
    for chunk in chunks:
        if len(chunk["text"]) > cfg.max_chars:
            sub_chunks = _hard_split(chunk, cfg)
            final_chunks.extend(sub_chunks)
        else:
            final_chunks.append(chunk)

    return final_chunks


def _hard_split(chunk: dict, cfg: ChunkingConfig) -> list[dict]:
    """Hard-split an oversized chunk at max_chars boundaries."""
    text = chunk["text"]
    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + cfg.max_chars, len(text))

        # Try to break at paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + cfg.min_chars:
                end = para_break
            else:
                # Sentence-boundary fallback chain: strong punctuation first
                # (。.!！?？), then weak (；;), then comma (，,). Only when
                # none exists in range do we hard-cut (code/formulas/raw text).
                for seps in (("。", ".", "！", "!", "？", "?", "\n"), ("；", ";"), ("，", ",")):
                    sent_break = max(
                        (text.rfind(sep, start + cfg.min_chars, end) for sep in seps),
                        default=-1,
                    )
                    if sent_break > start:
                        end = sent_break + 1
                        break

        sub_text = text[start:end].strip()
        if sub_text:
            new_chunk = dict(chunk)
            new_chunk["text"] = sub_text
            new_chunk["id"] = _make_chunk_id(chunk["source"], idx, sub_text)
            new_chunk["chunk_index_in_section"] = idx
            new_chunk["char_start"] = start
            new_chunk["char_end"] = end
            chunks.append(new_chunk)
            idx += 1

        # Move forward — ensure progress even with overlap
        if end >= len(text):
            break
        next_start = end - cfg.overlap_chars
        # Guarantee forward progress
        if next_start <= start:
            next_start = start + max(cfg.max_chars // 2, 1)
        start = next_start

    return chunks


def _merge_short_chunks(chunks: list[dict], cfg: ChunkingConfig) -> list[dict]:
    """Merge chunks shorter than min_chars with adjacent chunks."""
    if not chunks:
        return []

    merged: list[dict] = []
    buffer: dict | None = None

    for chunk in chunks:
        if buffer is None:
            buffer = chunk
            continue

        # Merge if: same heading, buffer is short
        same_heading = chunk.get("heading_path") == buffer.get("heading_path")
        buffer_short = len(buffer["text"]) < cfg.min_chars

        if same_heading and buffer_short:
            # Merge into buffer
            buffer["text"] = buffer["text"] + "\n\n" + chunk["text"]
            buffer["char_end"] = chunk.get("char_end", buffer["char_end"])
        else:
            merged.append(buffer)
            buffer = chunk

    if buffer:
        merged.append(buffer)

    return merged


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newline."""
    import re
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _build_embedding_text(chunk: dict) -> str:
    """Build text for embedding with heading context injection.

    The embedding text includes heading context so that searches for
    "激活函数" will match chunks about "ReLU" that belong to that section.
    The raw chunk text (without heading prefix) is stored separately.
    """
    parts = []

    # metadata_json is a JSON string in the chunk dict
    meta_json = chunk.get("metadata_json", "{}")
    if isinstance(meta_json, str):
        import json as _json
        try:
            meta = _json.loads(meta_json)
        except (ValueError, TypeError):
            meta = {}
    else:
        meta = meta_json

    doc_title = meta.get("doc_title", "")
    if doc_title:
        parts.append(f"文档：{doc_title}")

    heading_text = chunk.get("heading_text", "")
    if heading_text:
        parts.append(f"章节：{heading_text}")

    if parts:
        parts.append("")

    parts.append(chunk["text"])

    return "\n".join(parts)


def _make_chunk_id(source: str, index: int, text: str) -> str:
    """Generate deterministic chunk ID."""
    digest = hashlib.sha1(f"{source}:{index}:{text}".encode("utf-8")).hexdigest()[:16]
    return digest


def _make_section_id(heading_path: list[str], source: str) -> str:
    """Generate section ID from heading path."""
    if not heading_path:
        # Use source path as fallback
        return source.replace("/", "-").replace("\\", "-").replace(".", "-")
    return "/".join(
        h.lower().replace(" ", "-").replace("/", "-")
        for h in heading_path
    )


def _make_chunk_dict(
    chunk_id: str,
    source: str,
    text: str,
    heading_path: list[str],
    heading_text: str,
    heading_level: int,
    section_id: str,
    chunk_index_in_section: int,
    char_start: int,
    char_end: int,
    metadata: dict,
    page_start: int | None = None,
    page_end: int | None = None,
    slide_start: int | None = None,
    slide_end: int | None = None,
) -> dict:
    """Build a chunk dict with all fields needed for SQLite + Qdrant."""
    return {
        "id": chunk_id,
        "document_id": "",  # filled by caller
        "source": source,
        "chunk_index": 0,  # assigned later
        "text": text,
        "title": "",  # filled by caller
        "course": "",  # filled by caller
        "heading_path": heading_path,  # list for merge/compare
        "heading_path_json": json.dumps(heading_path, ensure_ascii=False),
        "heading_text": heading_text,
        "heading_level": heading_level,
        "section_id": section_id,
        "chunk_index_in_section": chunk_index_in_section,
        "page_start": page_start,
        "page_end": page_end,
        "slide_start": slide_start,
        "slide_end": slide_end,
        "char_start": char_start,
        "char_end": char_end,
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }
