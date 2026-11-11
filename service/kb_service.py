"""KBService — business logic for knowledge base sync, search, graph, status, reset.

Used by CLI, local RAG tools, and the Web backend.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import os
import json
import logging
import shutil
import hashlib
import re
import unicodedata
from typing import Any

from core.cancellation import RunCancelled
from knowledge.paths import knowledge_dir, knowledge_path
from service._result import err as _err, ok as _ok
from service.library_files import LibraryFilesMixin
from service.wiki_maintenance import WikiMaintenanceMixin

logger = logging.getLogger(__name__)


def _canonical_wiki_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _document_classification(source: str, kind: str = "", title: str = "") -> dict[str, Any]:
    normalized_source = source.replace("\\", "/").casefold()
    is_wiki = normalized_source.startswith("obsidian/wiki/") or "/wiki/" in normalized_source
    metadata_names = {"index.md", "log.md"}
    basename = os.path.basename(normalized_source)
    content_role = "metadata" if is_wiki and basename in metadata_names else "content"
    wiki_type = None
    if is_wiki:
        if "/sources/" in normalized_source or kind == "wiki_source":
            wiki_type = "source"
        elif "/entities/" in normalized_source or kind == "wiki_entity":
            wiki_type = "entity"
        elif "/concepts/" in normalized_source or kind == "wiki_concept":
            wiki_type = "concept"
        elif "/analyses/" in normalized_source or kind == "wiki_analysis":
            wiki_type = "analysis"
        elif "/questions/" in normalized_source or kind == "wiki_question":
            wiki_type = "question"
        elif "/notes/" in normalized_source or kind == "wiki_note":
            wiki_type = "note"
    canonical_title = _canonical_wiki_key(title or os.path.splitext(os.path.basename(source))[0])
    canonical_family = "source" if wiki_type == "source" else "knowledge"
    canonical_key = f"{canonical_family}:{canonical_title}"
    canonical_id = f"wiki-{hashlib.sha256(canonical_key.encode('utf-8')).hexdigest()[:16]}" if is_wiki else None
    return {
        "collection": "wiki" if is_wiki else "material",
        "wiki_type": wiki_type,
        "canonical_id": canonical_id,
        "content_role": content_role,
    }


class KBService(WikiMaintenanceMixin, LibraryFilesMixin):
    """Stateless service: each method creates its own stores/managers."""

    def __init__(self, workspace: str = "."):
        self.workspace = os.path.abspath(workspace)

    @property
    def is_portable_library(self) -> bool:
        return os.path.isfile(os.path.join(self.workspace, "BOBODAN_LIBRARY.yaml"))

    @property
    def managed_sources_dir(self) -> str:
        if self.is_portable_library:
            return os.path.join(self.workspace, "raw", "inbox")
        return os.path.join(self.workspace, ".bobodan", "sources")

    @property
    def managed_vault_dir(self) -> str:
        return self.workspace if self.is_portable_library else os.path.join(self.workspace, ".bobodan", "managed-vault")

    @property
    def source_roots_path(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "source_roots.json")

    def _load_source_roots(self) -> dict[str, Any]:
        if not os.path.exists(self.source_roots_path):
            return {"vault_path": None, "course_dirs": []}
        try:
            with open(self.source_roots_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"vault_path": None, "course_dirs": []}
        return {
            "vault_path": data.get("vault_path"),
            "course_dirs": data.get("course_dirs") or [],
        }

    def _save_source_roots(self, roots: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.source_roots_path), exist_ok=True)
        with open(self.source_roots_path, "w", encoding="utf-8") as handle:
            json.dump(roots, handle, ensure_ascii=False, indent=2)

    def _registered_roots(self) -> tuple[str, list[str]]:
        if self.is_portable_library:
            roots = self._load_source_roots()
            course_dirs = []
            for stored_path in roots.get("course_dirs", []):
                path = str(stored_path)
                candidate = path if os.path.isabs(path) else os.path.join(self.workspace, path)
                candidate = os.path.abspath(candidate)
                if not os.path.isdir(candidate) and os.path.isabs(path):
                    candidate = os.path.join(self.workspace, os.path.basename(os.path.normpath(path)))
                if os.path.isdir(candidate) and self._is_within_workspace(candidate, self.workspace):
                    course_dirs.append(candidate)
            # 2026-08-12 design: the library root itself is the user-facing
            # "throw files in here" folder. Registering it (instead of raw/)
            # lets root-level PDF/DOCX be indexed; raw/ is covered as its
            # subdirectory, internal structure is excluded by the scanner.
            if not any(os.path.abspath(d) == os.path.abspath(self.workspace) for d in course_dirs):
                course_dirs.insert(0, self.workspace)
            return self.workspace, list(dict.fromkeys(os.path.abspath(path) for path in course_dirs))
        roots = self._load_source_roots()
        vault_path = roots.get("vault_path")
        if not vault_path or not os.path.isdir(vault_path):
            os.makedirs(self.managed_vault_dir, exist_ok=True)
            vault_path = self.managed_vault_dir

        course_dirs = [
            path for path in roots.get("course_dirs", [])
            if os.path.isdir(path)
        ]
        if os.path.isdir(self.managed_sources_dir):
            course_dirs.append(self.managed_sources_dir)
        course_dirs = list(dict.fromkeys(os.path.abspath(path) for path in course_dirs))
        return vault_path, course_dirs

    @staticmethod
    def _is_within_workspace(path: str, workspace: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(workspace)]) == os.path.abspath(workspace)
        except ValueError:
            return False

    # --- Sync ---

    def sync(
        self,
        vault_path: str,
        course_dir: str | None = None,
        mode: str = "incremental",
        config: dict | None = None,
    ) -> dict[str, Any]:
        if mode not in {"incremental", "full"}:
            return _err("mode must be either 'incremental' or 'full'")
        if not self._is_within_workspace(vault_path, self.workspace):
            return _err(f"Access denied: {vault_path} is outside workspace")
        if not os.path.isdir(vault_path):
            return _err(f"Vault directory not found: {vault_path}")
        if course_dir:
            if not self._is_within_workspace(course_dir, self.workspace):
                return _err(f"Access denied: {course_dir} is outside workspace")
            if not os.path.isdir(course_dir):
                return _err(f"Course directory not found: {course_dir}")

        roots = self._load_source_roots()
        roots["vault_path"] = None if self.is_portable_library else os.path.abspath(vault_path)
        if course_dir:
            course_dirs = [os.path.abspath(path) for path in roots.get("course_dirs", [])]
            abs_course_dir = os.path.abspath(course_dir)
            if abs_course_dir not in course_dirs:
                course_dirs.append(abs_course_dir)
            roots["course_dirs"] = course_dirs
        self._save_source_roots(roots)

        summary = self._sync_registered_sources(mode=mode, config=config or {})
        data = summary.to_dict()
        return _ok(**data)

    def _missing_declared_roots(self) -> list[str]:
        """已登记、但磁盘上找不到的来源根（外接盘未挂载、网络盘掉线…）。

        2026-09-24（E17 ①）：这些根下的资料会整批从扫描结果里消失，而自愈
        机制会把「索引里有、扫描里没有」的记录当成删除候选——所以必须先知道
        有根不见了，并按 P0-12 的「扫描不完整就绝不删除」处理，而不是把用户
        的资料当成"被删掉了"。
        """
        roots = self._load_source_roots()
        missing: list[str] = []
        for stored in roots.get("course_dirs") or []:
            path = str(stored)
            if not path:
                continue
            candidate = path if os.path.isabs(path) else os.path.join(self.workspace, path)
            if os.path.isdir(os.path.abspath(candidate)):
                continue
            # 资料库被移动过：旧绝对路径失效，但同名子目录还在。
            if os.path.isabs(path) and os.path.isdir(
                os.path.join(self.workspace, os.path.basename(os.path.normpath(path)))
            ):
                continue
            missing.append(path)
        vault = roots.get("vault_path")
        if vault and not os.path.isdir(str(vault)):
            missing.append(str(vault))
        return missing

    def _sync_registered_sources(self, mode: str, config: dict, cancel_token=None, progress=None):
        from obsidian.sync import sync_sources

        vault_path, course_dirs = self._registered_roots()
        primary_course = course_dirs[0] if course_dirs else None
        extra_courses = course_dirs[1:] if len(course_dirs) > 1 else []
        return sync_sources(
            workspace=self.workspace,
            vault_path=vault_path,
            course_dir=primary_course,
            extra_course_dirs=extra_courses,
            missing_roots=self._missing_declared_roots(),
            mode=mode,
            config=config,
            cancel_token=cancel_token,
            progress=progress,
        )

    def import_files(
        self,
        files: list[tuple[str, bytes]],
        config: dict | None = None,
        duplicate_strategy: str = "keep_existing",
        cancel_token=None,
        progress=None,
    ) -> dict[str, Any]:
        """收文件 + 建索引。`cancel_token`（E8）在**文件边界**协作式检查：

        - 已经收进来/已经解析的保持原样，剩下的如实报成 `cancelled`；
        - 不再写新文件，也不删除任何东西（取消不是失败，不该丢资料）。
        """
        if duplicate_strategy not in {"keep_existing", "save_copy"}:
            return _err(
                "duplicate_strategy must be keep_existing or save_copy",
                code="invalid_duplicate_strategy",
            )
        allowed = {".md", ".txt", ".pdf", ".docx", ".pptx"}
        os.makedirs(self.managed_sources_dir, exist_ok=True)
        upload_hashes = {
            hashlib.sha256(content).hexdigest()
            for _filename, content in files
        }

        # 去重有**两个**来源，职责不同（审查 F08 修的就是第一个只扫 inbox 的问题）：
        #   1. 索引里的内容哈希 —— 资料被移动/改名后依然认得出来；
        #   2. inbox 里"盘上有、索引里没有"的文件 —— 上次同步失败留下的那一份（审查 F04）。
        indexed_hashes = (
            self._indexed_content_hashes(upload_hashes)
            if duplicate_strategy == "keep_existing"
            else {}
        )
        inbox_hashes: dict[str, str] = {}
        if duplicate_strategy == "keep_existing":
            for root, _dirs, names in os.walk(self.managed_sources_dir):
                for name in names:
                    path = os.path.join(root, name)
                    try:
                        with open(path, "rb") as handle:
                            inbox_hashes.setdefault(
                                hashlib.sha256(handle.read()).hexdigest(),
                                os.path.relpath(path, self.managed_sources_dir).replace(os.sep, "/"),
                            )
                    except OSError:
                        continue

        imported: list[str] = []
        duplicates: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []

        def record(filename: str, status: str, absolute: str, **extra: Any) -> None:
            outcomes.append({
                "filename": filename,
                "status": status,
                "path": self._relative_to_workspace(absolute) if absolute else "",
                **extra,
            })
            # E8：每个文件恰好在这里报一次进度（done 以"已处理数"为准，UI 才能画进度条）。
            report({
                "phase": "receiving",
                "done": len(outcomes),
                "total": len(files),
                "filename": filename,
                "status": status,
            })

        def report(event: dict[str, Any]) -> None:
            """E8：进度事件只在有人听的时候发，发送失败绝不影响导入本身。"""
            if progress is None:
                return
            try:
                progress(event)
            except Exception:  # 监听方的问题不该让导入失败
                logger.warning("import progress listener failed", exc_info=True)

        cancelled = False
        for filename, content in files:
            if cancel_token is not None and cancel_token.is_cancelled():
                # E8：到这里为止的都算数，剩下的不再写盘、如实报成 cancelled。
                cancelled = True
                record(filename, "cancelled", "")
                continue
            safe_name = os.path.basename(filename).strip()
            extension = os.path.splitext(safe_name)[1].lower()
            if not safe_name or extension not in allowed:
                rejected.append({"filename": filename, "reason": "unsupported_file_type"})
                record(filename, "rejected", "", reason="unsupported_file_type")
                continue
            content_digest = hashlib.sha256(content).hexdigest()
            if duplicate_strategy == "keep_existing":
                known = indexed_hashes.get(content_digest)
                if known is not None and known.get("indexed"):
                    duplicates.append({
                        "filename": filename,
                        "existing": known.get("path", ""),
                        "reason": "identical_content",
                    })
                    record(filename, "duplicate", os.path.join(self.workspace, str(known.get("path") or "")),
                           existing=known.get("path", ""), reason="identical_content")
                    continue
                on_disk = inbox_hashes.get(content_digest)
                if on_disk is not None or known is not None:
                    # 字节已经在库里，但**索引没建完**（上次同步失败 / 只切了行没有片段）：
                    # 不再写一份副本，直接把这份重新送进同步（审查 F04）。
                    existing_relative = on_disk or str(known.get("path") or "")
                    existing_absolute = (
                        os.path.join(self.managed_sources_dir, on_disk)
                        if on_disk is not None
                        else os.path.join(self.workspace, existing_relative)
                    )
                    pending.append({
                        "filename": filename,
                        "existing": existing_relative,
                        "reason": "awaiting_index",
                    })
                    record(filename, "pending", existing_absolute,
                           existing=existing_relative, reason="awaiting_index")
                    continue
            target = os.path.join(self.managed_sources_dir, safe_name)
            stem, extension = os.path.splitext(safe_name)
            counter = 2
            while os.path.exists(target):
                target = os.path.join(self.managed_sources_dir, f"{stem} ({counter}){extension}")
                counter += 1
            with open(target, "wb") as handle:
                handle.write(content)
            imported.append(os.path.basename(target))
            inbox_hashes.setdefault(
                content_digest,
                os.path.relpath(target, self.managed_sources_dir).replace(os.sep, "/"),
            )
            record(filename, "imported", target)

        if not imported and not duplicates and not pending and not cancelled:
            return _err("No supported files were provided")

        # 逐文件结果要**绑定到本次批次**：这一批里哪些能检索、哪些还在等索引（审查 F09）。
        def results_for_batch(
            documents: dict[str, dict[str, Any]],
            sync_summary: Any = None,
        ) -> list[dict[str, Any]]:
            described: list[dict[str, Any]] = []
            sync_errors = [
                str(item.get("source") or "")
                for item in (getattr(sync_summary, "errors", None) or [])
                if isinstance(item, dict)
            ]
            for outcome in outcomes:
                document = documents.get(os.path.abspath(os.path.join(self.workspace, outcome["path"]))) if outcome["path"] else None
                chunks = int((document or {}).get("chunk_count") or 0)
                status = outcome["status"]
                if status == "pending" and chunks > 0:
                    status = "indexed"
                extraction = (document or {}).get("extraction_status") or None
                if extraction is None and outcome["path"]:
                    # 同步报错的 source 用同步自己的命名（vault 是 obsidian/…，inbox/课程是
                    # course/…），与资料库相对路径（raw/inbox/…）不是同一个名字；而且**解析
                    # 失败时压根没有文档行**可查。所以按"最后两段路径"匹配：既容得下前缀差异，
                    # 又不会像裸 basename 那样让不同目录的同名文件互相串错误归因。
                    tail = outcome["path"].replace(os.sep, "/").strip("/").split("/")[-2:]
                    if any(
                        source.replace(os.sep, "/").strip("/").split("/")[-2:] == tail
                        for source in sync_errors
                    ):
                        extraction = "error"
                described.append({
                    **outcome,
                    "status": status,
                    "searchable": chunks > 0,
                    "chunks": chunks,
                    "extraction": extraction,
                })
            return described

        summary = None
        if imported or pending:
            try:
                summary = self._sync_registered_sources(
                    mode="incremental", config=config or {},
                    cancel_token=cancel_token, progress=progress,
                )
            except RunCancelled:
                # 取消**不是失败**（docs/CANCELLATION_DESIGN.md §2）：已经收下的保持收下，
                # 如实标成 cancelled，绝不能落到 import_sync_failed 上。
                return _ok(
                    imported=imported,
                    duplicates=duplicates,
                    rejected=rejected,
                    pending=pending,
                    cancelled=True,
                    results=results_for_batch(self._documents_by_path()),
                    library_sync={"extraction_counts": {}, "error_files": 0},
                )
            except Exception as exc:  # 同步失败要**如实结构化返回**，而不是把 500 抛给界面（审查 F04）
                return _err(
                    f"文件已经收进资料库，但建立索引失败：{exc}",
                    code="import_sync_failed",
                    imported=imported,
                    duplicates=duplicates,
                    rejected=rejected,
                    pending=pending,
                    cancelled=cancelled,
                    results=results_for_batch(self._documents_by_path()),
                    library_sync={"extraction_counts": {}, "error_files": 0},
                )
        return _ok(
            imported=imported,
            duplicates=duplicates,
            rejected=rejected,
            pending=pending,
            cancelled=cancelled,
            results=results_for_batch(self._documents_by_path(), summary),
            # 全库增量同步单独一个字段：它可以比这批大（资料库里别的文件也变了），
            # 但**不能**拿来当本次上传的计数（审查 F09）。
            library_sync=summary.to_dict() if summary else {"extraction_counts": {}, "error_files": 0},
        )

    # --- Status ---

    def status(self) -> dict[str, Any]:
        storage_dir = knowledge_dir(self.workspace)
        if not os.path.exists(storage_dir):
            return _err("No knowledge base found. Run obsidian_sync first.")

        from knowledge.library import build_library_summary
        from knowledge.import_report import load_import_report

        summary = build_library_summary(self.workspace)
        report = load_import_report(self.workspace)

        result: dict[str, Any] = {
            "total_files": summary.total_files,
            "total_chunks": summary.total_chunks,
            "total_errors": summary.total_errors,
            "graph_nodes": summary.graph_nodes,
            "graph_relationships": summary.graph_relationships,
            "graph_nodes_by_type": summary.graph_nodes_by_type,
            "graph_relationships_by_type": summary.graph_relationships_by_type,
            "graph_backend": summary.graph_backend,
            "last_sync": summary.last_sync,
            "courses": [
                {
                    "name": cs.name,
                    "file_count": cs.file_count,
                    "chunk_count": cs.chunk_count,
                    "error_count": cs.error_count,
                }
                for cs in summary.courses
            ],
        }

        if report:
            result["last_import"] = {
                "timestamp": report.timestamp,
                "mode": report.mode,
                "error_files": report.error_files,
                "extraction_counts": report.extraction_counts or {},
                "errors": report.errors[:10],
            }

        return _ok(**result)

    def list_documents(
        self,
        course: str | None = None,
        collection: str = "all",
    ) -> dict[str, Any]:
        if collection not in {"all", "material", "wiki"}:
            return _err("collection must be all, material, or wiki")
        db_path = knowledge_path(self.workspace, "knowledge.db")
        documents = []
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore
            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                documents = store.list_documents(course=course)
            finally:
                store.close()

        public = [self._public_document(item) for item in documents]
        public = self._visible_documents(public)
        if collection != "all":
            public = [item for item in public if item["collection"] == collection]
        public.sort(key=lambda item: (item.get("title") or item.get("source") or "").casefold())
        return _ok(documents=public)

    def get_document(self, document_id: str) -> dict[str, Any]:
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore
            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                document = store.get_document(document_id)
                if document is not None:
                    chunks = store.get_chunks_by_document(document_id)
                    return _ok(
                        document=self._public_document(document),
                        sections=[self._public_section(chunk) for chunk in chunks],
                    )
            finally:
                store.close()

        return _err(f"Document not found: {document_id}")

    def get_document_extraction(self, document_id: str) -> dict[str, Any]:
        """Return the stored extraction report for one document (P5G.0)."""
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore
            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                report = store.get_extraction_report(document_id)
            finally:
                store.close()
            if report is not None:
                return _ok(report=report)
        return _err(f"Document not found: {document_id}", code="document_not_found")

    def delete_document(self, document_id: str, config: dict | None = None) -> dict[str, Any]:
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return _err(f"Document not found: {document_id}", code="document_not_found")

        from rag.sqlite_store import KBSQLiteStore
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document = store.get_document(document_id)
        finally:
            store.close()
        if document is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")

        impact = self.document_impact(document_id, document=document)
        if not impact.get("ok"):
            return impact

        path = document.get("path")
        # 没有原件（旧索引条目 / 外部来源）或原件在资料库之外：依旧只读。
        if not path or not self._is_within_workspace(path, self.workspace) or self._is_internal_path(path):
            return _err("只能归档资料库里的资料", code="document_read_only")

        # E17 ③：所有资料都能归档（不只是 raw/ 里的）；保留原目录层级，条目可恢复。
        # 文件已经不在磁盘上时不拦：那条记录交给 P0-12 的两次确认通道清掉。
        archived = None
        if os.path.isfile(path):
            result = self.archive_path(path, reason="user", document=document)
            if not result.get("ok"):
                return result
            archived = result.get("entry")
            self._mark_wiki_sources_stale(document_id, document.get("source") or path)

        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(
            document_id=document_id,
            impact=impact.get("affected_pages", []),
            archive=archived,
            sync=summary.to_dict(),
        )

    def document_impact(self, document_id: str, document: dict[str, Any] | None = None) -> dict[str, Any]:
        if document is None:
            detail = self.get_document(document_id)
            if not detail.get("ok") or detail.get("document", {}).get("collection") != "material":
                return _err(f"Document not found: {document_id}")
            document = detail["document"]
        source = str(document.get("source") or "").replace("\\", "/")
        affected = []
        wiki_dir = os.path.join(self._wiki_target_vault(), "wiki")
        if os.path.isdir(wiki_dir):
            import yaml

            for root, dirs, files in os.walk(wiki_dir):
                dirs[:] = [name for name in dirs if name != "templates"]
                for filename in files:
                    if not filename.endswith(".md") or filename in {"index.md", "log.md"}:
                        continue
                    path = os.path.join(root, filename)
                    try:
                        with open(path, "r", encoding="utf-8") as handle:
                            content = handle.read()
                    except OSError:
                        continue
                    if not content.startswith("---"):
                        continue
                    end = content.find("---", 3)
                    if end < 0:
                        continue
                    try:
                        metadata = yaml.safe_load(content[3:end]) or {}
                    except yaml.YAMLError:
                        continue
                    refs = [item for item in metadata.get("source_refs") or [] if isinstance(item, dict)]
                    sources = [str(item).replace("\\", "/") for item in metadata.get("sources") or []]
                    matches = any(str(item.get("document_id") or "") == document_id for item in refs)
                    matches = matches or source in sources or any(
                        source.endswith(item) or item.endswith(source) for item in sources if item and source
                    )
                    if not matches:
                        continue
                    identities = {
                        str(item.get("document_id") or item.get("source") or "").strip()
                        for item in refs
                        if item.get("document_id") or item.get("source")
                    } or set(sources)
                    affected.append({
                        "title": str(metadata.get("title") or os.path.splitext(filename)[0]),
                        "page_type": str(metadata.get("type") or ""),
                        "target": os.path.relpath(path, wiki_dir).replace("\\", "/"),
                        "source_count": len(identities),
                        "action": "archive_candidate" if len(identities) <= 1 else "mark_needs_update",
                    })
        return _ok(
            document_id=document_id,
            title=document.get("title") or document.get("source") or "",
            affected_pages=affected,
            affected_count=len(affected),
        )

    def _mark_wiki_sources_stale(self, document_id: str, source: str) -> None:
        """Mark generated pages for review when an original source is archived."""
        import yaml

        wiki_dir = os.path.join(self._wiki_target_vault(), "wiki")
        if not os.path.isdir(wiki_dir):
            return
        normalized = str(source).replace("\\", "/")
        for root, _dirs, files in os.walk(wiki_dir):
            if os.path.basename(root) == "templates":
                continue
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                path = os.path.join(root, filename)
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        content = handle.read()
                except OSError:
                    continue
                if not content.startswith("---"):
                    continue
                end = content.find("---", 3)
                if end < 0:
                    continue
                try:
                    metadata = yaml.safe_load(content[3:end]) or {}
                except yaml.YAMLError:
                    continue
                refs = [item for item in metadata.get("source_refs") or [] if isinstance(item, dict)]
                sources = [str(item).replace("\\", "/") for item in metadata.get("sources") or []]
                referenced = any(str(item.get("document_id") or "") == document_id for item in refs)
                if not referenced and normalized not in sources and not any(normalized.endswith(item) or item.endswith(normalized) for item in sources):
                    continue
                metadata["status"] = "needs_update"
                rendered = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
                from wiki.reliability import atomic_text

                atomic_text(path, f"---\n{rendered}\n---{content[end + 3:]}")

    @staticmethod
    def _public_section(chunk: dict[str, Any]) -> dict[str, Any]:
        return {
            "chunk_id": chunk.get("id"),
            "heading": chunk.get("heading_text", ""),
            "page_start": chunk.get("page_start"),
            "slide_start": chunk.get("slide_start"),
            "text": chunk.get("text", ""),
            # W1 E7：分段内的字符偏移 —— 划线锚点要用它（以前这里把它丢掉了，
            # 阅读器只剩 quote 可存，重锚定会弱很多）。
            "char_start": chunk.get("char_start"),
            "char_end": chunk.get("char_end"),
        }

    def _public_document(self, document: dict[str, Any]) -> dict[str, Any]:
        path = document.get("path")
        managed = bool(path and self._is_within_workspace(path, self.managed_sources_dir))
        # 原文视图按"有没有原件"决定（而不是按类型白名单），但绝不把路径交给前端。
        candidate = path or ""
        if candidate and not os.path.isabs(candidate):
            candidate = os.path.join(self.workspace, candidate)
        # 显示层用的**真实相对路径**（E17 ②）：`source` 是索引身份，由扫描根
        # 前缀决定（`course-2/…`、`course/inbox/…`），对用户毫无意义；树和
        # 列表要显示的是文件在资料库里的真实位置。绝对路径依旧不外泄。
        relative_path = ""
        if candidate:
            resolved = os.path.abspath(candidate)
            if self._is_within_workspace(resolved, self.workspace):
                relative_path = os.path.relpath(resolved, self.workspace).replace(os.sep, "/")
        public = {
            "document_id": document.get("id"),
            "source": document.get("source", ""),
            "relative_path": relative_path,
            "kind": document.get("kind", ""),
            "title": document.get("title", ""),
            "course": document.get("course"),
            "summary": document.get("summary", ""),
            "vector_status": document.get("vector_status", ""),
            "vector_error": document.get("vector_error"),
            "extraction_status": document.get("extraction_status", "complete"),
            "extraction_total_units": document.get("extraction_total_units", 0),
            "extraction_extracted_units": document.get("extraction_extracted_units", 0),
            "extraction_empty_units": document.get("extraction_empty_units", 0),
            "chunk_count": int(document.get("chunk_count") or 0),
            "updated_at": document.get("updated_at", ""),
            "content_hash": document.get("content_hash", ""),
            "managed": managed,
            "origin": "managed" if managed else "workspace",
            "has_original": bool(candidate) and os.path.isfile(candidate),
        }
        public.update(_document_classification(
            public["source"], public["kind"], public["title"]
        ))
        return public

    def _visible_documents_for_sources(self, sources: list[str]) -> dict[str, dict[str, Any]]:
        """检索命中的 source → 可见文档；与 ``list_documents(collection="all")`` 同口径。

        以前每次检索都把**全库**文档逐份加工一遍（300 份资料 ≈ 30ms，而检索本身约 5ms，
        2026-11-11 审查）。现在只取命中的那几份；命中里有 Wiki 页时，才补取 Wiki 全族，
        因为「同一概念多页只显示一页」的去重要看同族的所有页。
        """
        from rag.sqlite_store import KBSQLiteStore

        wanted = [source for source in dict.fromkeys(sources) if source]
        if not wanted:
            return {}
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            rows = store.get_documents_by_sources(wanted)
            hit_public = [self._public_document(item) for item in rows]
            if any(item["collection"] == "wiki" for item in hit_public):
                known = {item["source"] for item in hit_public}
                hit_public += [
                    self._public_document(item)
                    for item in store.list_wiki_documents()
                    if item.get("source") not in known
                ]
        finally:
            store.close()
        visible = self._visible_documents(hit_public)
        wanted_set = set(wanted)
        return {item["source"]: item for item in visible if item["source"] in wanted_set}

    @staticmethod
    def _visible_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        visible = [item for item in documents if item.get("content_role") != "metadata"]
        wiki_groups: dict[str, list[dict[str, Any]]] = {}
        output = []
        for item in visible:
            if item.get("collection") != "wiki":
                output.append(item)
                continue
            wiki_groups.setdefault(item.get("canonical_id") or item["document_id"], []).append(item)

        for items in wiki_groups.values():
            items.sort(key=lambda item: (
                item.get("wiki_type") != "concept",
                " " not in (item.get("title") or ""),
                item.get("source") or "",
            ))
            output.append(items[0])
        return output

    # --- RAG Search ---

    def search(
        self,
        query: str,
        course: str | None = None,
        top_k: int = 5,
        mode: str = "auto",
        document_ids: list[str] | None = None,
        preferred_document_ids: list[str] | None = None,
        collection: str = "all",
        config: dict | None = None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            return _err("query is required")

        from rag.retriever import search_index_with_status

        storage_dir = knowledge_dir(self.workspace)
        db_path = os.path.join(storage_dir, "knowledge.db")
        if not os.path.exists(db_path):
            # 契约：缺索引不是请求错误，而是 retrieval_mode="unavailable" + 原因与下一步。
            # 以前这里返回错误（HTTP 400 request_failed），空库的搜索框只能静默吞掉
            # （QA-LIVE-01 发现）。状态由检索层统一给出，不在这里另拼一份。
            _, retrieval_status = search_index_with_status(self.workspace, query=query.strip())
            return _ok(results=[], **retrieval_status)

        requested_top_k = max(1, min(top_k, 20))
        candidate_top_k = 20 if document_ids or preferred_document_ids else requested_top_k
        results, retrieval_status = search_index_with_status(
            self.workspace,
            query=query.strip(),
            course=course,
            top_k=candidate_top_k,
            config=config or {},
            mode=mode,
        )
        source_documents = self._visible_documents_for_sources(
            [str(item.get("source") or "") for item in results]
        )
        allowed_document_ids = set(document_ids or [])
        preferred_ids = set(preferred_document_ids or [])
        merged = []
        seen = set()
        for item in results:
            visible_document = source_documents.get(str(item.get("source") or ""))
            if not visible_document:
                continue
            if collection != "all" and visible_document.get("collection") != collection:
                continue
            if allowed_document_ids and visible_document["document_id"] not in allowed_document_ids:
                continue
            item["document_id"] = visible_document["document_id"]
            item["title"] = visible_document["title"]
            item["collection"] = visible_document["collection"]
            item["wiki_type"] = visible_document["wiki_type"]
            key = item.get("chunk_id") or (item.get("source"), item.get("text"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        if preferred_ids and not allowed_document_ids:
            merged.sort(key=lambda item: (
                0 if item.get("document_id") in preferred_ids else 1,
                -float(item.get("score") or item.get("similarity") or 0),
            ))
        if not allowed_document_ids:
            wiki_results = [item for item in merged if item.get("collection") == "wiki"]
            material_results = [item for item in merged if item.get("collection") == "material"]
            if wiki_results and material_results:
                merged = wiki_results[:2] + material_results + wiki_results[2:]
        return _ok(results=merged[:requested_top_k], **retrieval_status)

    # --- Reset ---

    def reset(self) -> dict[str, Any]:
        from rag.retriever import clear_retrieval_cache

        clear_retrieval_cache(self.workspace)
        storage_dir = knowledge_dir(self.workspace)
        if os.path.exists(storage_dir):
            # Preserve retired JSON indexes and graph_store.json. They are
            # read-only migration sources and may contain the user's only copy.
            # P1-28: manifest.json is part of the index too. Leaving it behind
            # made build_library_summary claim files that list_documents no
            # longer had. It is derived data, rebuilt by the next sync.
            for filename in (
                "knowledge.db", "knowledge.db-shm", "knowledge.db-wal", "bobodan.db",
                "bobodan.db-shm", "bobodan.db-wal", "sync_state.json", "import_report.json",
                "manifest.json",
            ):
                path = os.path.join(storage_dir, filename)
                if os.path.isfile(path):
                    os.remove(path)
            qdrant = os.path.join(storage_dir, "qdrant")
            if os.path.isdir(qdrant):
                shutil.rmtree(qdrant)
        return _ok(message="Knowledge base reset")
