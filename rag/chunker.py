import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class TextChunk:
    """A source-grounded text chunk ready for indexing."""

    id: str
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


def _make_chunk_id(source: str, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{source}:{index}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"{source}#{index}-{digest}"


def _split_units(text: str) -> list[str]:
    units = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if units:
        return units
    return [text.strip()] if text.strip() else []


def chunk_text(
    text: str,
    source: str,
    metadata: dict | None = None,
    max_chars: int = 1000,
    overlap_chars: int = 160,
) -> list[TextChunk]:
    """Split text into stable, paragraph-aware chunks."""
    metadata = dict(metadata or {})
    chunks: list[TextChunk] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        clean = buffer.strip()
        if clean:
            index = len(chunks)
            chunks.append(
                TextChunk(
                    id=_make_chunk_id(source, index, clean),
                    text=clean,
                    source=source,
                    metadata=dict(metadata),
                )
            )
        buffer = clean[-overlap_chars:] if overlap_chars and len(clean) > overlap_chars else ""

    for unit in _split_units(text):
        if len(unit) > max_chars:
            if buffer.strip():
                flush()
            for start in range(0, len(unit), max_chars - overlap_chars):
                piece = unit[start:start + max_chars].strip()
                if piece:
                    index = len(chunks)
                    chunks.append(
                        TextChunk(
                            id=_make_chunk_id(source, index, piece),
                            text=piece,
                            source=source,
                            metadata=dict(metadata),
                        )
                    )
            buffer = ""
            continue

        candidate = f"{buffer}\n\n{unit}".strip() if buffer else unit
        if len(candidate) > max_chars and buffer.strip():
            flush()
            candidate = f"{buffer}\n\n{unit}".strip() if buffer else unit
        buffer = candidate

    if buffer.strip():
        clean = buffer.strip()
        index = len(chunks)
        chunks.append(
            TextChunk(
                id=_make_chunk_id(source, index, clean),
                text=clean,
                source=source,
                metadata=dict(metadata),
            )
        )

    return chunks
