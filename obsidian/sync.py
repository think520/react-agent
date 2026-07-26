"""Sync source files to knowledge base.

RAG v2 pipeline:
1. Scan vault → ScannedNote list
2. Parse each file → SourceSection list (via rag/parsers)
3. Chunk sections → TextChunk list (via rag/chunker_v2)
4. Write to SQLite (KBSQLiteStore) + Qdrant (QdrantStore)
5. Preserve reviewed concept-map evidence
6. Save manifest + import report
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field

from knowledge.documents import DocumentRecord, build_document_records
from knowledge.import_report import ImportReport, save_import_report
from knowledge.manifest import save_manifest
from knowledge.paths import knowledge_dir
from rag.source_section import SourceSection
from rag.parsers import parse_document, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

_COURSE_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".knowledge", ".bobodan", "templates"}


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
    path = knowledge_dir(workspace)
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


def _stable_hash(text: str) -> str:
    """Stable hash for document_id (source path)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _scan_course_files(root_dir: str) -> list[tuple[str, str, str]]:
    """Return supported course files as (relative source, path, content hash)."""
    root_dir = os.path.abspath(root_dir)
    files = []
    for root, dirs, filenames in os.walk(root_dir):
        dirs[:] = [
            name for name in dirs
            if name not in _COURSE_SKIP_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(root, filename)
            relative = os.path.relpath(path, root_dir).replace(os.sep, "/")
            if os.path.basename(os.path.normpath(root_dir)) == "raw" and relative == "README.md":
                continue
            with open(path, "rb") as handle:
                content_hash = hashlib.sha256(handle.read()).hexdigest()
            source = relative
            files.append((source, path, content_hash))
    return sorted(files, key=lambda item: item[0].casefold())


def _course_prefix(root_dir: str, default: str) -> str:
    return "managed" if os.path.basename(os.path.normpath(root_dir)) == "sources" else default


def sync_sources(
    workspace: str,
    vault_path: str,
    course_dir: str | None = None,
    extra_course_dirs: list[str] | None = None,
    mode: str = "incremental",
    config: dict | None = None,
) -> SyncSummary:
    """Parse source files, rebuild RAG index (SQLite + Qdrant), and sync graph."""
    config = config or {}
    knowledge_dir = _knowledge_dir(workspace)
    old_state = _load_state(workspace).get("files", {})
    new_state: dict[str, str] = {}
    errors: list[dict] = []

    # ── Step 1: Scan vault ──────────────────────────────────────────────
    from .vault import scan_vault
    notes = scan_vault(vault_path)

    # ── Step 2: Determine which files changed ───────────────────────────
    changed_sources: list[tuple[str, str, str, str]] = []  # (source, abs_path, content_hash, kind)
    deleted_sources: list[str] = []

    for scanned in notes:
        source = f"obsidian/{scanned.rel_path}"
        new_state[source] = scanned.content_hash
        if mode == "full" or old_state.get(source) != scanned.content_hash:
            changed_sources.append((source, scanned.abs_path, scanned.content_hash, "obsidian_note"))

    course_roots: list[tuple[str, str]] = []
    if course_dir:
        course_roots.append((_course_prefix(course_dir, "course"), course_dir))
    for index, extra_dir in enumerate(extra_course_dirs or []):
        if not extra_dir or any(os.path.abspath(extra_dir) == os.path.abspath(path) for _, path in course_roots):
            continue
        prefix = _course_prefix(extra_dir, f"course-{index + 2}")
        course_roots.append((prefix, extra_dir))

    for prefix, root_dir in course_roots:
        for relative_source, path, content_hash in _scan_course_files(root_dir):
            source = f"{prefix}/{relative_source}"
            new_state[source] = content_hash
            if mode == "full" or old_state.get(source) != content_hash:
                changed_sources.append((source, path, content_hash, "course_document"))

    deleted_sources = [s for s in old_state if s not in new_state]

    # ── Step 3: Initialize stores ───────────────────────────────────────
    from rag.sqlite_store import KBSQLiteStore
    from rag.qdrant_store import QdrantStore
    from rag.chunker_v2 import chunk_sections, ChunkingConfig
    from rag.embedding_service import EmbeddingService

    sqlite = KBSQLiteStore(workspace)
    sqlite.init_db()

    rag_cfg = config.get("rag", {})
    chunk_cfg_dict = rag_cfg.get("chunking", {})
    chunk_cfg = ChunkingConfig(
        target_chars=chunk_cfg_dict.get("target_chars", 1800),
        max_chars=chunk_cfg_dict.get("max_chars", 2600),
        overlap_chars=chunk_cfg_dict.get("overlap_chars", 350),
        min_chars=chunk_cfg_dict.get("min_chars", 400),
    )

    qdrant = QdrantStore(workspace, config)
    embedding = EmbeddingService(config)

    # Initialize Qdrant collection if embedding is available
    embedding_dim = None
    if embedding.is_available():
        try:
            model_info = embedding.get_model_info()
            embedding_dim = model_info.get("dim")
            if embedding_dim:
                qdrant.init_collection(embedding_dim)
        except Exception as e:
            logger.warning("Failed to init Qdrant: %s", e)

    # ── Step 4: Process changed files ───────────────────────────────────
    total_chunks = 0
    doc_records: list[DocumentRecord] = []

    for source, abs_path, content_hash, kind in changed_sources:
        try:
            # Parse document into sections
            sections = parse_document(abs_path, workspace)
            if not sections:
                # Fallback: use legacy chunker for simple text
                sections = _fallback_parse(source, abs_path, kind)

            # Override source path to use our canonical source prefix
            for section in sections:
                section.source = source

            # Chunk sections
            chunks = chunk_sections(sections, chunk_cfg)
            if not chunks:
                continue

            # Derive document metadata
            document_id = _stable_hash(source)
            title = _extract_title(source, sections, kind)
            course = _extract_course(source, sections, kind)
            tags = _extract_tags(sections)

            # Build summary (first 500 chars of clean text)
            summary_text = " ".join(c["text"] for c in chunks[:3])[:500]

            # SQLite: upsert document + chunks
            sqlite.upsert_document(
                document_id=document_id,
                source=source,
                content_hash=content_hash,
                kind=kind,
                title=title,
                path=abs_path,
                course=course,
                tags=tags,
                summary=summary_text,
                vector_status="pending",
            )
            sqlite.delete_chunks_by_document(document_id)

            # Enrich chunks with document metadata
            for i, chunk in enumerate(chunks):
                chunk["document_id"] = document_id
                chunk["title"] = title
                chunk["course"] = course or ""
                chunk["chunk_index"] = i

            sqlite.insert_chunks(chunks)

            # Keep reviewed concept evidence aligned with the rebuilt RAG chunks.
            concept_db_path = os.path.join(knowledge_dir, "concept_graph.db")
            if os.path.exists(concept_db_path):
                try:
                    from service.concept_service import ConceptService

                    ConceptService(workspace).refresh_document_evidence(document_id, chunks)
                except Exception:
                    pass

            # Directory entry
            keywords = list(set(tags + _extract_keywords(chunks)))
            sqlite.upsert_directory_entry(
                document_id=document_id,
                title=title,
                summary=summary_text,
                keywords=keywords,
                source=source,
                course=course,
                chunk_count=len(chunks),
            )

            # Qdrant: upsert vectors
            if embedding.is_available() and embedding_dim:
                try:
                    texts_to_embed = [c.get("embedding_text", c["text"]) for c in chunks]
                    vectors = embedding.embed_texts(texts_to_embed)
                    if vectors and len(vectors) == len(chunks):
                        chunk_ids = [c["id"] for c in chunks]
                        payloads = [
                            {
                                "chunk_id": c["id"],
                                "document_id": document_id,
                                "source": source,
                                "title": title,
                                "course": course or "",
                                "heading_path": c.get("heading_path", []),
                                "heading_text": c.get("heading_text", ""),
                                "section_id": c.get("section_id", ""),
                                "chunk_index_in_section": c.get("chunk_index_in_section", 0),
                                "page_start": c.get("page_start"),
                                "page_end": c.get("page_end"),
                                "slide_start": c.get("slide_start"),
                                "slide_end": c.get("slide_end"),
                            }
                            for c in chunks
                        ]
                        # Delete old vectors first
                        qdrant.delete_by_filter(document_id)
                        qdrant.upsert(chunk_ids, vectors, payloads)
                        sqlite.mark_vector_indexed(document_id, content_hash)
                    else:
                        sqlite.mark_vector_error(document_id, "embedding count mismatch")
                except Exception as e:
                    logger.warning("Qdrant upsert failed for %s: %s", source, e)
                    sqlite.mark_vector_error(document_id, str(e))

            total_chunks += len(chunks)
            doc_records.append(DocumentRecord(
                source=source,
                kind=kind,
                title=title,
                course=course,
                status="ok",
                chunk_count=len(chunks),
                content_hash=content_hash,
            ))

        except Exception as e:
            logger.warning("Failed to process %s: %s", source, e)
            errors.append({"source": source, "error": str(e)})
            doc_records.append(DocumentRecord(
                source=source,
                kind=kind,
                title=os.path.basename(source),
                status="error",
                error=str(e),
                content_hash=content_hash,
            ))

    # ── Step 5: Delete removed documents ────────────────────────────────
    for source in deleted_sources:
        doc_id = sqlite.get_document_id_by_source(source)
        if doc_id:
            sqlite.delete_document(doc_id)  # cascades to chunks, directory
            concept_db_path = os.path.join(knowledge_dir, "concept_graph.db")
            if os.path.exists(concept_db_path):
                try:
                    from service.concept_service import ConceptService

                    ConceptService(workspace).mark_document_evidence_stale(doc_id)
                except Exception:
                    pass
            try:
                qdrant.delete_by_filter(doc_id)
            except Exception:
                pass

    # ── Step 6: Read reviewed concept-map status ────────────────────────
    # Source sync no longer writes the retired JSON graph. Concepts only
    # enter the map through extraction candidates and explicit review.
    from service.concept_service import ConceptService

    graph_status = ConceptService(workspace).get_status()
    relationship_count = int(graph_status.get("relationship_count") or 0)
    graph_backend = "concept_sqlite"
    graph_store_path = None

    # ── Step 7: Save state ──────────────────────────────────────────────
    _save_state(workspace, new_state)

    updated_files = len(changed_sources) + len(deleted_sources)
    if mode == "full":
        updated_files = len(new_state)

    # Merge doc_records: keep existing records for unchanged files
    from knowledge.manifest import load_manifest
    existing_manifest = load_manifest(workspace)
    existing_docs = {d["source"]: d for d in existing_manifest.get("documents", [])}
    changed_sources_set = {s for s, _, _, _ in changed_sources}
    deleted_set = set(deleted_sources)
    new_sources_set = {r.source for r in doc_records}

    # Add existing records for files that weren't changed or deleted
    for src, doc_dict in existing_docs.items():
        if src not in changed_sources_set and src not in deleted_set and src not in new_sources_set:
            doc_records.append(DocumentRecord(
                source=doc_dict.get("source", src),
                kind=doc_dict.get("kind", ""),
                title=doc_dict.get("title", ""),
                course=doc_dict.get("course"),
                status=doc_dict.get("status", "ok"),
                chunk_count=doc_dict.get("chunk_count", 0),
                content_hash=doc_dict.get("content_hash", ""),
            ))

    # Save manifest and import report
    sync_summary_dict = {
        "scanned_files": len(new_state),
        "updated_files": updated_files,
        "chunk_count": total_chunks,
        "relationship_count": relationship_count,
        "graph_backend": graph_backend,
        "mode": mode,
    }
    save_manifest(workspace, doc_records, sync_summary_dict, vault_path=vault_path)
    save_import_report(workspace, ImportReport(
        mode=mode,
        scanned_files=len(new_state),
        updated_files=updated_files,
        error_files=len(errors),
        chunk_count=total_chunks,
        relationship_count=relationship_count,
        graph_backend=graph_backend,
        errors=errors,
    ))

    sqlite.close()

    index_path = os.path.join(knowledge_dir, "knowledge.db")
    return SyncSummary(
        scanned_files=len(new_state),
        updated_files=updated_files,
        chunk_count=total_chunks,
        relationship_count=relationship_count,
        graph_backend=graph_backend,
        rag_index_path=index_path,
        graph_store_path=graph_store_path,
        error_files=len(errors),
        errors=errors,
    )


def _fallback_parse(source: str, abs_path: str, kind: str) -> list[SourceSection]:
    """Fallback parser for when rag/parsers returns empty."""
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            text = f.read()
    except (UnicodeDecodeError, FileNotFoundError):
        return []

    doc_title = os.path.splitext(os.path.basename(abs_path))[0]
    return [SourceSection(
        source=source,
        doc_title=doc_title,
        unit_type="paragraph",
        unit_range="",
        heading_path=[],
        text=text.strip(),
        metadata={"file_type": "txt"},
    )]


def _extract_title(source: str, sections: list[SourceSection], kind: str) -> str:
    """Extract document title from sections or source path."""
    if sections and sections[0].doc_title:
        return sections[0].doc_title
    return os.path.splitext(os.path.basename(source))[0]


def _extract_course(source: str, sections: list[SourceSection], kind: str) -> str | None:
    """Extract course from sections metadata."""
    if sections and sections[0].metadata.get("course"):
        return sections[0].metadata["course"]
    return None


def _extract_tags(sections: list[SourceSection]) -> list[str]:
    """Extract tags from sections metadata."""
    tags = set()
    for s in sections:
        for tag in s.metadata.get("tags", []):
            tags.add(tag)
    return sorted(tags)


def _extract_keywords(chunks: list[dict]) -> list[str]:
    """Extract keywords from chunk headings."""
    keywords = set()
    for c in chunks:
        heading_path = c.get("heading_path", [])
        for h in heading_path:
            if len(h) > 1:
                keywords.add(h)
    return sorted(keywords)[:20]
