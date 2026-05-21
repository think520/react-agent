import json
import logging
import os
from dataclasses import dataclass, field

from graph.store import get_graph_store
from knowledge.documents import DocumentRecord, build_document_records
from knowledge.import_report import ImportReport, save_import_report
from knowledge.manifest import save_manifest
from rag.chunker import TextChunk, chunk_text
from rag.ingest import iter_documents
from rag.vector_store import LocalVectorStore

from .vault import scan_vault

logger = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    scanned_files: int
    updated_files: int
    chunk_count: int
    relationship_count: int
    graph_backend: str
    rag_index_path: str
    graph_store_path: str | None = None
    error_files: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scanned_files": self.scanned_files,
            "updated_files": self.updated_files,
            "chunk_count": self.chunk_count,
            "relationship_count": self.relationship_count,
            "graph_backend": self.graph_backend,
            "rag_index_path": self.rag_index_path,
            "graph_store_path": self.graph_store_path,
            "error_files": self.error_files,
            "errors": self.errors,
        }


def _knowledge_dir(workspace: str) -> str:
    path = os.path.join(workspace, ".knowledge")
    os.makedirs(path, exist_ok=True)
    return path


def _state_path(workspace: str) -> str:
    return os.path.join(_knowledge_dir(workspace), "sync_state.json")


def _load_state(workspace: str) -> dict:
    path = _state_path(workspace)
    if not os.path.exists(path):
        return {"files": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(workspace: str, files: dict) -> None:
    with open(_state_path(workspace), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "files": files}, f, ensure_ascii=False, indent=2)


def sync_sources(
    workspace: str,
    vault_path: str,
    course_dir: str | None = None,
    mode: str = "incremental",
) -> SyncSummary:
    """Parse source files, rebuild the local RAG index, and sync graph relations."""
    knowledge_dir = _knowledge_dir(workspace)
    old_state = _load_state(workspace).get("files", {})
    new_state: dict[str, str] = {}
    errors: list[dict] = []

    notes = scan_vault(vault_path)
    chunks: list[TextChunk] = []
    doc_records: list[DocumentRecord] = []

    for scanned in notes:
        source = f"obsidian/{scanned.rel_path}"
        try:
            new_state[source] = scanned.content_hash
            file_chunks = chunk_text(
                scanned.note.body,
                source=source,
                metadata={
                    "kind": "obsidian_note",
                    "title": scanned.note.title,
                    "tags": scanned.note.tags,
                    "course": scanned.note.course,
                    "chapter": scanned.note.chapter,
                    "path": scanned.rel_path,
                },
            )
            chunks.extend(file_chunks)
            doc_records.append(DocumentRecord(
                source=source,
                kind="obsidian_note",
                title=scanned.note.title or scanned.rel_path,
                course=scanned.note.course,
                status="ok",
                chunk_count=len(file_chunks),
                content_hash=scanned.content_hash,
            ))
        except Exception as e:
            logger.warning("Failed to process %s: %s", source, e)
            errors.append({"source": source, "error": str(e)})
            doc_records.append(DocumentRecord(
                source=source,
                kind="obsidian_note",
                title=scanned.rel_path,
                status="error",
                error=str(e),
                content_hash=scanned.content_hash,
            ))

    course_docs_list = []
    if course_dir:
        for document in iter_documents(course_dir):
            source = f"course/{document.source}"
            try:
                new_state[source] = document.content_hash
                metadata = dict(document.metadata)
                metadata["path"] = document.source
                file_chunks = chunk_text(document.text, source=source, metadata=metadata)
                chunks.extend(file_chunks)
                title = document.metadata.get("title", document.source)
                doc_records.append(DocumentRecord(
                    source=source,
                    kind="course_document",
                    title=title,
                    course=document.metadata.get("course"),
                    status="ok",
                    chunk_count=len(file_chunks),
                    content_hash=document.content_hash,
                ))
            except Exception as e:
                logger.warning("Failed to process %s: %s", source, e)
                errors.append({"source": source, "error": str(e)})
                doc_records.append(DocumentRecord(
                    source=source,
                    kind="course_document",
                    title=document.source,
                    status="error",
                    error=str(e),
                ))

    index_path = os.path.join(knowledge_dir, "rag_index.json")
    LocalVectorStore(index_path).replace(chunks)

    graph_store = get_graph_store(workspace)
    relationship_count = graph_store.replace_from_notes(notes)
    graph_store_path = getattr(graph_store, "graph_path", None)
    if hasattr(graph_store, "close"):
        graph_store.close()

    updated_files = sum(1 for path, digest in new_state.items() if old_state.get(path) != digest)
    if mode == "full":
        updated_files = len(new_state)
    _save_state(workspace, new_state)

    # Save manifest and import report
    sync_summary_dict = {
        "scanned_files": len(new_state),
        "updated_files": updated_files,
        "chunk_count": len(chunks),
        "relationship_count": relationship_count,
        "graph_backend": graph_store.backend_name,
        "mode": mode,
    }
    save_manifest(workspace, doc_records, sync_summary_dict, vault_path=vault_path)
    save_import_report(workspace, ImportReport(
        mode=mode,
        scanned_files=len(new_state),
        updated_files=updated_files,
        error_files=len(errors),
        chunk_count=len(chunks),
        relationship_count=relationship_count,
        graph_backend=graph_store.backend_name,
        errors=errors,
    ))

    return SyncSummary(
        scanned_files=len(new_state),
        updated_files=updated_files,
        chunk_count=len(chunks),
        relationship_count=relationship_count,
        graph_backend=graph_store.backend_name,
        rag_index_path=index_path,
        graph_store_path=graph_store_path,
        error_files=len(errors),
        errors=errors,
    )
