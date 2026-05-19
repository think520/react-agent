import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DocumentRecord:
    source: str
    kind: str  # "obsidian_note" | "course_document"
    title: str
    course: str | None = None
    status: str = "ok"
    chunk_count: int = 0
    error: str | None = None
    content_hash: str = ""


def build_document_records(notes=None, course_docs=None) -> list[DocumentRecord]:
    """Build document records from scanned notes and course documents.

    Args:
        notes: list of ScannedNote from obsidian/vault.scan_vault()
        course_docs: list of SourceDocument from rag/ingest.iter_documents()

    Returns:
        List of DocumentRecord with per-file status.
    """
    records: list[DocumentRecord] = []

    if notes:
        for scanned in notes:
            try:
                source = f"obsidian/{scanned.rel_path}"
                records.append(DocumentRecord(
                    source=source,
                    kind="obsidian_note",
                    title=scanned.note.title or scanned.rel_path,
                    course=scanned.note.course,
                    status="ok",
                    chunk_count=0,
                    content_hash=scanned.content_hash,
                ))
            except Exception as e:
                source = f"obsidian/{getattr(scanned, 'rel_path', '?')}"
                logger.warning("Failed to process %s: %s", source, e)
                records.append(DocumentRecord(
                    source=source,
                    kind="obsidian_note",
                    title=getattr(scanned, "rel_path", "?"),
                    status="error",
                    error=str(e),
                ))

    if course_docs:
        for doc in course_docs:
            try:
                source = f"course/{doc.source}"
                title = doc.metadata.get("title", doc.source)
                records.append(DocumentRecord(
                    source=source,
                    kind="course_document",
                    title=title,
                    course=doc.metadata.get("course"),
                    status="ok",
                    chunk_count=0,
                    content_hash=doc.content_hash,
                ))
            except Exception as e:
                source = f"course/{getattr(doc, 'source', '?')}"
                logger.warning("Failed to process %s: %s", source, e)
                records.append(DocumentRecord(
                    source=source,
                    kind="course_document",
                    title=getattr(doc, "source", "?"),
                    status="error",
                    error=str(e),
                ))

    return records


def document_records_to_dict(records: list[DocumentRecord]) -> list[dict]:
    """Serialize document records to dict list."""
    from dataclasses import asdict
    return [asdict(r) for r in records]
