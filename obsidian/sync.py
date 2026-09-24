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

from core.atomic_io import atomic_write_json
from knowledge.documents import DocumentRecord, build_document_records
from knowledge.import_report import ImportReport, save_import_report
from knowledge.manifest import save_manifest
from knowledge.paths import knowledge_dir
from rag.source_section import SourceSection
from rag.embedding_signature import write_signature
from rag.parsers import parse_document, SUPPORTED_EXTENSIONS

from .scan_policy import is_repo_metadata

logger = logging.getLogger(__name__)

_COURSE_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".knowledge", ".bobodan", "templates"}

# Library-internal structure that must never be indexed as user material.
# (wiki pages are surfaced through the vault scan / wiki classification.)
_LIBRARY_INTERNAL_DIRS = _COURSE_SKIP_DIRS | {"wiki"}

#: Repository metadata rule lives in `scan_policy` so the vault scan and the
#: material scans cannot drift apart (2026-09-24, E17 ①).


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
    extraction_counts: dict = field(default_factory=dict)
    #: 2026-09-24: repo metadata files that were deliberately not indexed.
    skipped_files: list = field(default_factory=list)
    #: Sources that entered the index for the first time in this run.
    added_files: list = field(default_factory=list)
    #: Sources whose content changed in this run (excludes removals, so the
    #: summary can say 更新 N and 移除 N without double counting).
    changed_files: int = 0
    #: Sources removed from the index in this run (confirmed missing twice).
    removed_files: list = field(default_factory=list)
    #: Removed sources whose content is still indexed under another source
    #: (a duplicate record — or a rename/move, which ③ will migrate properly).
    duplicates_cleaned: list = field(default_factory=list)
    #: True when this scan could not see everything (an unreadable path or a
    #: registered source root that is currently unavailable). No deletions run.
    scan_incomplete: bool = False
    incomplete_reasons: list = field(default_factory=list)
    #: Sources that were missing this run but still wait for the second
    #: confirmation (P0-12). Surfaced so the UI can say "待确认移除 N".
    pending_removal: list = field(default_factory=list)
    #: P1-18: documents whose vectors were written by the backfill pass.
    vectors_backfilled: int = 0

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
            "extraction_counts": dict(self.extraction_counts),
            "skipped_files": list(self.skipped_files),
            "changed_files": int(self.changed_files),
            "scan_incomplete": bool(self.scan_incomplete),
            "incomplete_reasons": list(self.incomplete_reasons),
            "added_files": list(self.added_files),
            "removed_files": list(self.removed_files),
            "duplicates_cleaned": list(self.duplicates_cleaned),
            "pending_removal": list(self.pending_removal),
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


def _save_state(workspace: str, files: dict, missing: dict | None = None) -> None:
    state = {"version": 1, "files": files}
    if missing:
        # P0-12: remember how often a source has been missing so a single
        # failed scan cannot trigger deletion.
        state["missing"] = missing
    atomic_write_json(_state_path(workspace), state)


# P0-12: consecutive scans that must miss a source before it is deleted.
DELETION_CONFIRMATIONS = 2


def _resolve_deletions(
    old_state: dict,
    new_state: dict,
    previous_missing: dict,
    *,
    scan_failed: bool,
) -> tuple[list[str], dict[str, int]]:
    """Decide which sources are really gone (P0-12).

    A network share that blinks, a permission change or an unreadable
    directory all make files vanish from `new_state`, and the delete branch
    cascades through documents, chunks, vectors and concept evidence. So a
    source must be missing in DELETION_CONFIRMATIONS consecutive scans, and a
    scan that reported errors never deletes anything.
    """
    deleted: list[str] = []
    pending: dict[str, int] = {}
    # 2026-09-24 (E17 ①): `files` is overwritten by every scan, so a source
    # that goes missing leaves `old_state` after the *first* pass. Iterating
    # `old_state` alone meant the confirmation counter could never reach
    # DELETION_CONFIRMATIONS and nothing was ever removed — measured on the real
    # library: 29 stale records (7 duplicate sources + 17 wiki pages + …)
    # survived two syncs while `missing` was silently emptied. Previously
    # missing sources are therefore re-checked until they come back or the
    # confirmation count is reached.
    candidates = set(old_state) | {
        source for source in previous_missing if source not in old_state
    }
    for source in sorted(candidates):
        if source in new_state:
            continue
        seen = int(previous_missing.get(source, 0) or 0)
        if scan_failed:
            pending[source] = seen
            continue
        count = seen + 1
        if count >= DELETION_CONFIRMATIONS:
            deleted.append(source)
        else:
            pending[source] = count
    return sorted(deleted), pending


def _stable_hash(text: str) -> str:
    """Stable hash for document_id (source path)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _scan_course_files(
    root_dir: str,
    errors: list[str] | None = None,
    *,
    skip_roots: frozenset[str] = frozenset(),
    skipped: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Return supported course files as (relative source, path, content hash).

    P0-12: unreadable directories and files are recorded in `errors` instead of
    being swallowed, because a file that only *looks* absent must never be
    treated as deleted.

    2026-09-24 (E17 ①): `skip_roots` holds absolute paths of directories that
    another scan root already covers — walking into them would index the same
    file twice under two sources (two `document_id`s). `skipped` collects repo
    metadata files that were deliberately ignored so the summary can list them.
    """
    root_dir = os.path.abspath(root_dir)
    files = []

    def _on_error(exc: OSError) -> None:
        if errors is not None:
            errors.append(f"{getattr(exc, 'filename', root_dir)}: {exc}")

    for root, dirs, filenames in os.walk(root_dir, onerror=_on_error):
        dirs[:] = [
            name for name in dirs
            if name not in _COURSE_SKIP_DIRS
            and not name.startswith(".")
            and os.path.abspath(os.path.join(root, name)) not in skip_roots
        ]
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(root, filename)
            relative = os.path.relpath(path, root_dir).replace(os.sep, "/")
            if is_repo_metadata(filename):
                if skipped is not None:
                    skipped.append(relative)
                continue
            try:
                with open(path, "rb") as handle:
                    content_hash = hashlib.sha256(handle.read()).hexdigest()
            except OSError as exc:
                if errors is not None:
                    errors.append(f"{relative}: {exc}")
                continue
            source = relative
            files.append((source, path, content_hash))
    return sorted(files, key=lambda item: item[0].casefold())


def _course_prefix(root_dir: str, default: str) -> str:
    return "managed" if os.path.basename(os.path.normpath(root_dir)) == "sources" else default


def _scan_library_root(
    root_dir: str,
    errors: list[str] | None = None,
    *,
    skip_roots: frozenset[str] = frozenset(),
    skipped: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Scan a portable library root for materials of every supported format.

    The whole folder is the user-facing "throw files in here" directory
    (2026-08-12 design): files at the root and in any non-internal subfolder
    are indexed. Rules that keep sources stable and non-duplicated:

    - internal structure (`wiki/`, `.bobodan/`, `templates/`, dot-dirs) is
      never indexed as material;
    - markdown outside `raw/` is handled by the vault scan, so this pass
      skips it (avoids duplicate obsidian/course sources);
    - files under `raw/` keep their legacy relative path (no `raw/` prefix),
      so existing `course/inbox/...` sources and document ids stay stable;
    - 2026-09-24 (E17 ①) a registered extra source root that happens to live
      **inside** this folder is skipped: the vault scan already skips such
      roots (`obsidian/vault.py`), and without the same rule here the same
      file got two documents (measured: 7 pairs in the real library);
    - repo metadata files (README / CONTRIBUTING / requirements.txt / …) are
      skipped at any level and reported through `skipped`.
    """
    root_dir = os.path.abspath(root_dir)
    files: list[tuple[str, str, str]] = []

    def _on_error(exc: OSError) -> None:
        if errors is not None:
            errors.append(f"{getattr(exc, 'filename', root_dir)}: {exc}")

    for root, dirs, filenames in os.walk(root_dir, onerror=_on_error):
        dirs[:] = [
            name for name in dirs
            if name not in _LIBRARY_INTERNAL_DIRS
            and not name.startswith(".")
            and os.path.abspath(os.path.join(root, name)) not in skip_roots
        ]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(root, filename)
            relative = os.path.relpath(path, root_dir).replace(os.sep, "/")
            from_raw = relative.startswith("raw/")
            if from_raw:
                # Keep legacy course/inbox/... sources (and thus stable
                # document ids) for everything under raw/.
                relative = relative[len("raw/"):]
            if is_repo_metadata(filename):
                if skipped is not None:
                    skipped.append(relative)
                continue
            if ext == ".md" and not from_raw:
                # Root-level markdown is indexed by the vault scan.
                continue
            try:
                with open(path, "rb") as handle:
                    content_hash = hashlib.sha256(handle.read()).hexdigest()
            except OSError as exc:
                if errors is not None:
                    errors.append(f"{relative}: {exc}")
                continue
            files.append((relative, path, content_hash))
    return sorted(files, key=lambda item: item[0].casefold())


def _vector_payload(chunk: dict, *, document_id: str, source: str, title: str, course: str) -> dict:
    """Qdrant payload for one chunk; shared by the sync pass and the backfill."""
    return {
        "chunk_id": chunk["id"],
        "document_id": document_id,
        "source": source,
        "title": title,
        "course": course or "",
        "heading_path": chunk.get("heading_path", []),
        "heading_text": chunk.get("heading_text", ""),
        "section_id": chunk.get("section_id", ""),
        "chunk_index_in_section": chunk.get("chunk_index_in_section", 0),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "slide_start": chunk.get("slide_start"),
        "slide_end": chunk.get("slide_end"),
    }


def backfill_vectors(sqlite, qdrant, embedding, embedding_dim) -> int:
    """Embed documents whose vectors were never written (P1-18).

    Importing while the embedding backend is down records `pending`, and the
    next sync sees "content unchanged" and writes nothing - so semantic search
    stayed silently unavailable, with no error anywhere. Failures are recorded
    on the document instead of being swallowed.
    """
    if not embedding_dim or not embedding.is_available():
        return 0
    backfilled = 0
    for document in sqlite.get_pending_vector_documents():
        document_id = document["id"]
        chunks = sqlite.get_chunks_by_document(document_id)
        if not chunks:
            continue
        try:
            texts = [chunk.get("embedding_text") or chunk["text"] for chunk in chunks]
            vectors = embedding.embed_texts(texts)
            if not vectors or len(vectors) != len(chunks):
                sqlite.mark_vector_error(document_id, "embedding count mismatch")
                continue
            chunk_ids = [chunk["id"] for chunk in chunks]
            payloads = [
                _vector_payload(
                    chunk,
                    document_id=document_id,
                    source=document.get("source", ""),
                    title=document.get("title", ""),
                    course=document.get("course", ""),
                )
                for chunk in chunks
            ]
            qdrant.delete_by_filter(document_id)
            qdrant.upsert(chunk_ids, vectors, payloads)
            sqlite.mark_vector_indexed(document_id, document.get("content_hash") or "")
            backfilled += 1
        except Exception as exc:
            logger.warning("Vector backfill failed for %s: %s", document_id, exc)
            sqlite.mark_vector_error(document_id, str(exc))
    if backfilled:
        logger.info("Backfilled vectors for %d documents", backfilled)
    return backfilled


def sync_sources(
    workspace: str,
    vault_path: str,
    course_dir: str | None = None,
    extra_course_dirs: list[str] | None = None,
    missing_roots: list[str] | None = None,
    mode: str = "incremental",
    config: dict | None = None,
) -> SyncSummary:
    """Parse source files, rebuild RAG index (SQLite + Qdrant), and sync graph."""
    config = config or {}
    knowledge_dir = _knowledge_dir(workspace)
    state = _load_state(workspace)
    old_state = state.get("files", {})
    previous_missing = state.get("missing", {}) or {}
    new_state: dict[str, str] = {}
    errors: list[dict] = []
    # P0-12: anything the scan could not read lands here, and any error
    # suppresses deletion for this run (absence is not evidence when the scan
    # itself is incomplete).
    scan_errors: list[str] = []
    # 2026-09-24 (E17 ①): a registered source root that is not on disk right now
    # (unmounted drive, offline share) must never look like "the user deleted
    # these files" — an incomplete scan deletes nothing (P0-12).
    incomplete_reasons: list[str] = [
        f"来源根不可用：{root}" for root in (missing_roots or []) if root
    ]

    # ── Step 1: Scan vault ──────────────────────────────────────────────
    from .vault import scan_vault

    #: Repo metadata files that were deliberately not indexed (E17 ① summary).
    skipped_sources: list[str] = []
    vault_skipped: list[str] = []
    notes = scan_vault(vault_path, errors=scan_errors, skipped=vault_skipped)
    skipped_sources.extend(f"obsidian/{relative}" for relative in vault_skipped)

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

    # 2026-09-24 (E17 ①): an extra source root can live inside another root
    # (measured in the real library: `ai-agents-from-zero` is both a child of
    # the library root and a registered course dir, and `raw/notes` likewise).
    # The vault scan already skips registered roots; without the same skip here
    # every file under them got a second document with a second id.
    skip_roots = frozenset(
        os.path.abspath(path) for path in (extra_course_dirs or []) if path
    )

    for prefix, root_dir in course_roots:
        # A portable library root scans the whole user-facing folder
        # (root-level PDF/DOCX included); plain course dirs keep the
        # markdown-inclusive course scan.
        portable_root = os.path.isfile(os.path.join(root_dir, "BOBODAN_LIBRARY.yaml"))
        scanner = _scan_library_root if portable_root else _scan_course_files
        skipped_here: list[str] = []
        for relative_source, path, content_hash in scanner(
            root_dir, scan_errors, skip_roots=skip_roots, skipped=skipped_here
        ):
            source = f"{prefix}/{relative_source}"
            new_state[source] = content_hash
            if mode == "full" or old_state.get(source) != content_hash:
                changed_sources.append((source, path, content_hash, "course_document"))
        skipped_sources.extend(f"{prefix}/{relative}" for relative in skipped_here)

    # 2026-09-24 (E17 ①): self-healing for state drift. A source can drop out
    # of the scan state while its document stays in SQLite (scanner rule change,
    # an interrupted run, or the P0-12 counter defect above). Those orphans are
    # fed back into the same two-confirmation deletion path instead of being
    # indexed forever — measured on the real library: 29 such documents.
    # Only sources the scan actually indexed count as known. Repo metadata that
    # is *skipped* must NOT be treated as known: files indexed under the old
    # rule (README / requirements.txt / …) have to fall out of the index too.
    known_sources = set(new_state)
    from rag.sqlite_store import KBSQLiteStore

    probe = KBSQLiteStore(workspace)
    probe.init_db()
    try:
        indexed_sources = {row["source"] for row in probe.list_documents()}
    finally:
        probe.close()
    orphans = sorted(source for source in indexed_sources if source not in known_sources)
    if orphans:
        previous_missing = dict(previous_missing)
        for source in orphans:
            previous_missing.setdefault(source, 0)

    # P0-12: confirm deletions across scans and never delete on a failed scan.
    deleted_sources, pending_missing = _resolve_deletions(
        old_state,
        new_state,
        previous_missing,
        scan_failed=bool(scan_errors) or bool(incomplete_reasons),
    )
    for scan_error in scan_errors[:5]:
        errors.append({"source": "", "error": f"扫描不完整：{scan_error}"})
    incomplete_reasons.extend(f"扫描不完整：{item}" for item in scan_errors[:5])

    # ── Step 3: Initialize stores ───────────────────────────────────────
    from rag.sqlite_store import KBSQLiteStore
    from rag.qdrant_store import shared_qdrant_store
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

    # P0-15: reuse the retrieval pipeline client instead of opening a second one
    # on the same local directory (qdrant local mode locks it).
    qdrant = shared_qdrant_store(workspace, config)
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
    extraction_counts: dict[str, int] = {"complete": 0, "partial": 0, "empty": 0, "error": 0}

    for source, abs_path, content_hash, kind in changed_sources:
        try:
            # Parse document into sections + extraction report
            sections, extraction_report_obj = parse_document(abs_path, workspace)
            extraction_report = extraction_report_obj.to_dict()
            if not sections:
                # Fallback: use legacy chunker for simple text
                sections = _fallback_parse(source, abs_path, kind)
                if sections and not extraction_report.get("total_units"):
                    # Text fallback succeeded where the typed parser found
                    # nothing (e.g. scanned PDF with an embedded text layer
                    # the parser refused); keep the typed report otherwise.
                    extraction_report = {
                        "file_type": "txt",
                        "parser": "fallback",
                        "status": "complete",
                        "total_units": len(sections),
                        "extracted_units": len(sections),
                        "empty_units": 0,
                        "extracted_characters": sum(len(s.text) for s in sections),
                        "image_count": 0,
                        "warnings": [],
                    }

            # Override source path to use our canonical source prefix
            for section in sections:
                section.source = source

            # Chunk sections
            chunks = chunk_sections(sections, chunk_cfg)

            # Derive document metadata
            # 2026-09-24 (E17 ③): identity must survive a rename/move. The id is
            # derived from the source path, so a moved file would mint a new id
            # and break concept evidence, question sources, note references and
            # reading progress. Rename/move rewrites source in place *before*
            # the sync runs, so the row is already there: reuse its id.
            document_id = sqlite.get_document_id_by_source(source) or _stable_hash(source)
            title = _extract_title(source, sections, kind)
            course = _extract_course(source, sections, kind)
            tags = _extract_tags(sections)

            # Build summary (first 500 chars of clean text)
            summary_text = " ".join(c["text"] for c in chunks[:3])[:500]

            # SQLite: upsert document (registered even when zero chunks —
            # scanned PDFs must show up in the Library as not retrievable),
            # then chunks
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
                extraction=extraction_report,
            )
            sqlite.delete_chunks_by_document(document_id)
            status_key = extraction_report.get("status") or "error"
            extraction_counts[status_key] = extraction_counts.get(status_key, 0) + 1
            if not chunks:
                doc_records.append(DocumentRecord(
                    source=source,
                    kind=kind,
                    title=title,
                    course=course,
                    status="ok",
                    chunk_count=0,
                    content_hash=content_hash,
                ))
                continue

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
                            _vector_payload(
                                c,
                                document_id=document_id,
                                source=source,
                                title=title,
                                course=course or "",
                            )
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

    # ── Step 5b: Backfill vectors that were never written (P1-18) ───────
    # Documents imported while the embedding backend was down were marked
    # pending; because their content never changes again, a plain sync would
    # never write their vectors and semantic search stayed silently absent.
    vectors_backfilled = backfill_vectors(sqlite, qdrant, embedding, embedding_dim)
    if embedding.is_available() and embedding_dim:
        # G2: record which model these vectors belong to. A later provider or
        # model switch is then caught by the retriever instead of silently
        # mixing two vector spaces.
        write_signature(workspace, embedding.get_model_info())

    # ── Step 6: Read reviewed concept-map status ────────────────────────
    # Source sync no longer writes the retired JSON graph. Concepts only
    # enter the map through extraction candidates and explicit review.
    from service.concept_service import ConceptService

    graph_status = ConceptService(workspace).get_status()
    relationship_count = int(graph_status.get("relationship_count") or 0)
    graph_backend = "concept_sqlite"
    graph_store_path = None

    # ── Step 7: Save state ──────────────────────────────────────────────
    _save_state(workspace, new_state, pending_missing)

    updated_files = len(changed_sources) + len(deleted_sources)
    if mode == "full":
        updated_files = len(new_state)

    # 2026-09-24 (E17 ①): a summary the user can act on — added / updated /
    # removed / skipped / duplicates / failed, instead of one opaque number.
    added_sources = sorted(source for source in new_state if source not in old_state)
    live_hashes = set(new_state.values())
    duplicates_cleaned = sorted(
        source
        for source in deleted_sources
        if source in old_state and old_state[source] in live_hashes
    )

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
        extraction_counts=dict(extraction_counts),
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
        extraction_counts=dict(extraction_counts),
        skipped_files=sorted(set(skipped_sources)),
        changed_files=len(changed_sources),
        added_files=added_sources,
        scan_incomplete=bool(incomplete_reasons),
        incomplete_reasons=incomplete_reasons,
        removed_files=list(deleted_sources),
        duplicates_cleaned=duplicates_cleaned,
        pending_removal=sorted(pending_missing),
        vectors_backfilled=vectors_backfilled,
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
