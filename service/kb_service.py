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


class KBService(WikiMaintenanceMixin):
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

# --- 只读文件夹树（E17 ②）---------------------------------------------

    #: 每个文件夹最多列出多少条"已忽略"明细（计数不受此限制）。
    #: 真实库实测：50 条时树接口 141 KB；20 条足够核对，别把导航层做胖。
    TREE_IGNORED_SAMPLE = 20

    def tree(self) -> dict[str, Any]:
        """只读文件夹树：真实文件夹 + 资料文件 + 已忽略计数 + 索引徽章。

        设计见 `docs/LIBRARY_TREE_DESIGN.md` §3.1 / §3.3：
        - 树建在真实文件系统上，文件夹就是用户在资源管理器里看到的文件夹；
        - 隐藏 Bobodan 内部结构（`.bobodan/`、`wiki/`、点目录）与标记文件；
        - 非资料文件不出现，但按文件夹给出「另有 N 个文件已忽略」与原因；
        - 每份资料带索引徽章；**未索引的资料也要看得见**（否则用户以为没进去）；
        - 绝不下发绝对路径。
        """
        from datetime import datetime, timezone

        from obsidian.scan_policy import is_repo_metadata
        from obsidian.sync import _LIBRARY_INTERNAL_DIRS
        from rag.parsers import SUPPORTED_EXTENSIONS

        indexed: dict[str, dict[str, Any]] = {}
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore

            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                for document in store.list_documents():
                    stored = document.get("path") or ""
                    if not stored:
                        continue
                    candidate = stored if os.path.isabs(stored) else os.path.join(self.workspace, stored)
                    candidate = os.path.abspath(candidate)
                    if not self._is_within_workspace(candidate, self.workspace):
                        continue
                    relative = os.path.relpath(candidate, self.workspace).replace(os.sep, "/")
                    indexed[relative] = {
                        "document_id": document.get("id"),
                        "title": document.get("title") or "",
                        "extraction_status": document.get("extraction_status") or "complete",
                        "chunk_count": int(document.get("chunk_count") or 0),
                    }
            finally:
                store.close()

        hidden_names = set(_LIBRARY_INTERNAL_DIRS) | {"BOBODAN_LIBRARY.yaml", "WIKI_SCHEMA.md"}

        def build(absolute: str, relative: str) -> dict[str, Any]:
            node: dict[str, Any] = {
                "type": "folder",
                "name": os.path.basename(absolute) or relative,
                "path": relative,
                "children": [],
                "files": [],
                # material_count / indexed_count / ignored_count 是**含子目录**的
                # 合计（文件夹行上的徽章就用它们）；ignored_here 只列本层明细。
                "material_count": 0,
                "indexed_count": 0,
                "ignored_count": 0,
                "ignored_here": [],
            }
            try:
                entries = sorted(os.scandir(absolute), key=lambda item: item.name.casefold())
            except OSError:
                return node
            for entry in entries:
                name = entry.name
                if name.startswith(".") or name in hidden_names:
                    continue
                child_relative = f"{relative}/{name}" if relative else name
                if entry.is_dir(follow_symlinks=False):
                    child = build(entry.path, child_relative)
                    node["children"].append(child)
                    node["material_count"] += child["material_count"]
                    node["indexed_count"] += child["indexed_count"]
                    node["ignored_count"] += child["ignored_count"]
                    continue
                extension = os.path.splitext(name)[1].lower()
                metadata = is_repo_metadata(name)
                if extension not in SUPPORTED_EXTENSIONS or metadata:
                    node["ignored_count"] += 1
                    if len(node["ignored_here"]) < self.TREE_IGNORED_SAMPLE:
                        node["ignored_here"].append({
                            "name": name,
                            "path": child_relative,
                            "reason": "repo_metadata" if metadata else "unsupported_type",
                        })
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                badge = indexed.get(child_relative) or {}
                node["files"].append({
                    "type": "file",
                    "name": name,
                    "path": child_relative,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "indexed": bool(badge),
                    "document_id": badge.get("document_id"),
                    "title": badge.get("title", ""),
                    "extraction_status": badge.get("extraction_status"),
                    "chunk_count": badge.get("chunk_count", 0),
                })
                node["material_count"] += 1
                if badge:
                    node["indexed_count"] += 1
            node["files"].sort(key=lambda item: item["name"].casefold())
            return node

        tree = build(self.workspace, "")
        tree["name"] = os.path.basename(os.path.normpath(self.workspace)) or "资料库"
        return _ok(tree=tree)

    def _scan_prefix_for(self, absolute: str) -> str:
        """给一个绝对路径算出它在扫描口径下的 source（与 obsidian/sync.py 完全一致）。"""
        from obsidian.sync import _course_prefix

        _vault_path, course_dirs = self._registered_roots()
        candidates: list[tuple[str, str]] = []
        if course_dirs:
            candidates.append((course_dirs[0], _course_prefix(course_dirs[0], "course")))
            for index, extra in enumerate(course_dirs[1:]):
                candidates.append((extra, _course_prefix(extra, f"course-{index + 2}")))
        best: tuple[str, str] | None = None
        for root, prefix in candidates:
            if not self._is_within_workspace(absolute, root):
                continue
            if best is None or len(os.path.abspath(root)) > len(os.path.abspath(best[0])):
                best = (root, prefix)
        if best is None:
            return ""
        root, prefix = best
        relative = os.path.relpath(absolute, root).replace(os.sep, "/")
        if os.path.abspath(root) == os.path.abspath(self.workspace) and relative.startswith("raw/"):
            relative = relative[len("raw/"):]
        return f"{prefix}/{relative}"

    def move_document(
        self,
        document_id: str,
        new_relative_path: str,
        config: dict | None = None,
        *,
        sync: bool = True,
    ) -> dict[str, Any]:
        """重命名或移动一份资料：文件搬走，**身份保留**，引用与证据跟着迁移（E17 ③）。

        ``sync=False`` 给批量调用方用（整理 / 撤销）：索引位置与 chunk 身份已在本方法里就地改好，
        末尾那次增量同步只负责重新嵌入向量，批量时由调用方最后统一做一次 ——
        否则搬 k 份资料要把整个资料库读 k 遍（2026-11-11 审查）。
        """
        from rag.chunker_v2 import _make_chunk_id
        from rag.sqlite_store import KBSQLiteStore

        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return _err(f"Document not found: {document_id}", code="document_not_found")
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document = store.get_document(document_id)
        finally:
            store.close()
        if document is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")

        path = document.get("path")
        if not path or not self._is_within_workspace(path, self.workspace) or self._is_internal_path(path):
            return _err("只能移动资料库里的资料", code="document_read_only")

        cleaned = str(new_relative_path or "").strip().replace("\\", "/").lstrip("/")
        if not cleaned or ".." in cleaned.split("/") or ":" in cleaned:
            return _err("目标路径不合法", code="invalid_target")
        from rag.parsers import SUPPORTED_EXTENSIONS

        if os.path.splitext(cleaned)[1].lower() not in SUPPORTED_EXTENSIONS:
            return _err("目标扩展名不是资料类型", code="unsupported_file_type")
        target = os.path.abspath(os.path.join(self.workspace, cleaned))
        if not self._is_within_workspace(target, self.workspace) or self._is_internal_path(target):
            return _err("目标路径不合法", code="invalid_target")
        if os.path.abspath(target) == os.path.abspath(path):
            return _err("新位置和原位置一样", code="target_unchanged")
        if os.path.exists(target):
            return _err("目标位置已经有同名文件", code="target_exists")

        new_source = self._scan_prefix_for(target)
        if not new_source:
            return _err("目标不在资料库的扫描范围内", code="invalid_target")

        # 1) 先算 chunk 身份映射：chunk_id 由 (source, index, text) 派生，改名就换身份。
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            mapping = {
                chunk["id"]: _make_chunk_id(
                    new_source,
                    int(chunk.get("chunk_index_in_section") or 0),
                    chunk.get("text") or "",
                )
                for chunk in store.get_chunks_by_document(document_id)
            }
        finally:
            store.close()

        # 2) 搬文件
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(path, target)

        # 3) 就地改写位置（id 不变）+ 迁移 chunk 身份
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            chunks_remapped = store.remap_chunk_ids(document_id, mapping, new_source)
            store.update_document_location(document_id, new_source, target, vector_status="pending")
        finally:
            store.close()

        # 4) 迁移挂在 chunk_id 上的引用：概念证据与笔记关联
        from knowledge.paths import knowledge_dir
        from graph.concept_store import ConceptStore
        from memory.personal_store import PersonalKnowledgeStore

        # ConceptStore 要的是**数据库路径**（不是工作区），且图谱是可选能力。
        concept_db_path = os.path.join(knowledge_dir(self.workspace), "concept_graph.db")
        evidence_remapped = (
            ConceptStore(concept_db_path).remap_evidence_chunk_ids(mapping)
            if os.path.exists(concept_db_path)
            else 0
        )
        references_remapped = PersonalKnowledgeStore(self.workspace).remap_reference_chunk_ids(mapping)

        # 5) chunk 身份变了 → 旧向量作废；标 pending 让下一次同步重新嵌入
        try:
            from rag.qdrant_store import shared_qdrant_store

            shared_qdrant_store(self.workspace).delete_by_filter(document_id)
        except Exception as exc:  # noqa: BLE001 - 向量是可选能力，删不掉不影响迁移
            logger.warning("移动资料时清理旧向量失败（不影响引用迁移）：%s", exc)

        summary = self._sync_registered_sources(mode="incremental", config=config or {}) if sync else None
        return _ok(
            migration={
                "document_id": document_id,
                "old_source": document.get("source") or "",
                "new_source": new_source,
                "relative_path": cleaned,
                "chunks_remapped": chunks_remapped,
                "evidence_remapped": evidence_remapped,
                "references_remapped": references_remapped,
            },
            sync=summary.to_dict() if summary is not None else None,
        )

    # --- 文件夹写操作：新建 / 删除（只删容器）（E17 ③）-------------------

    def _clean_relative(self, relative_path: str) -> str:
        cleaned = str(relative_path or "").strip().replace("\\", "/").strip("/")
        if not cleaned or ".." in cleaned.split("/") or ":" in cleaned:
            return ""
        return cleaned

    def _migrate_relocated_document(self, document: dict[str, Any], destination: str) -> dict[str, int]:
        """文件已经在磁盘上搬好之后：保留身份，并迁移挂在 chunk 上的引用。

        2026-09-24（E17 ③，审查发现）：delete_folder（ungroup）与 move_document 是
        同一个「移动」，两条路径必须行为一致 —— 否则被移出的资料会以新 source
        重新索引，document_id 变化，概念证据与笔记引用一起断。
        """
        from rag.chunker_v2 import _make_chunk_id
        from rag.sqlite_store import KBSQLiteStore

        document_id = str(document.get("id") or "")
        new_source = self._scan_prefix_for(destination)
        if not document_id or not new_source:
            return {"chunks_remapped": 0, "evidence_remapped": 0, "references_remapped": 0}

        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            mapping = {
                chunk["id"]: _make_chunk_id(
                    new_source,
                    int(chunk.get("chunk_index_in_section") or 0),
                    chunk.get("text") or "",
                )
                for chunk in store.get_chunks_by_document(document_id)
            }
            chunks_remapped = store.remap_chunk_ids(document_id, mapping, new_source)
            store.update_document_location(document_id, new_source, destination, vector_status="pending")
        finally:
            store.close()

        from knowledge.paths import knowledge_dir
        from graph.concept_store import ConceptStore
        from memory.personal_store import PersonalKnowledgeStore

        concept_db_path = os.path.join(knowledge_dir(self.workspace), "concept_graph.db")
        evidence_remapped = (
            ConceptStore(concept_db_path).remap_evidence_chunk_ids(mapping)
            if os.path.exists(concept_db_path)
            else 0
        )
        references_remapped = PersonalKnowledgeStore(self.workspace).remap_reference_chunk_ids(mapping)
        return {
            "chunks_remapped": chunks_remapped,
            "evidence_remapped": evidence_remapped,
            "references_remapped": references_remapped,
        }

    # --- 整理建议（E17 ⑤ 前半：只提议，不动文件）-------------------------

    #: 交给模型归类的文件数上限（提示词要短；整理不是批量搬迁）
    ORGANIZE_MODEL_LIMIT = 60

    def _loose_root_materials(self) -> tuple[list[str], list[str]]:
        """库根那一层的资料文件，以及现有顶层文件夹名（给模型当参考）。"""
        from obsidian.scan_policy import is_repo_metadata
        from rag.parsers import SUPPORTED_EXTENSIONS

        loose: list[str] = []
        folders: list[str] = []
        try:
            entries = sorted(os.scandir(self.workspace), key=lambda item: item.name.casefold())
        except OSError:
            entries = []
        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                folders.append(name)
                continue
            if name in {"BOBODAN_LIBRARY.yaml", "WIKI_SCHEMA.md"}:
                continue
            extension = os.path.splitext(name)[1].lower()
            if extension not in SUPPORTED_EXTENSIONS or is_repo_metadata(name):
                continue
            loose.append(name)
        return loose, folders

    def _rule_organization_proposals(self, loose: list[str]) -> list[dict[str, Any]]:
        """确定性规则：先把最明显的一类说出来（散落在库根的资料）。"""
        if not loose:
            return []
        return [{
            "kind": "loose_materials",
            "title": "库根散落的资料",
            "reason": "这些资料直接躺在资料库根目录，没有归到任何文件夹里；放进一个按课程或主题命名的文件夹会更好找。",
            "items": loose,
            "suggested_folder": "未归类",
            "requires_confirmation": True,
        }]

    def _model_organization_proposals(
        self, llm_provider: Any, loose: list[str], folders: list[str]
    ) -> tuple[list[dict[str, Any]], str]:
        """让模型把库根散落的资料分到几个文件夹里 —— 只提议，且逐条验证。

        模型在这里**没有任何动手能力**：它只能从给定的真实文件名里挑，服务端再
        把不存在的文件、越界或内部目录全部丢掉。剩下的才进"预览 → 用户确认"。
        """
        from core.llm_json import parse_llm_object

        system = (
            "你是个人知识库的整理助手，只输出 JSON。"
            "把资料库根目录里散落的文件分组到少量有意义的文件夹里。"
            "硬性要求：只能使用给定的文件名，不得新增、改写或猜测文件名；"
            "文件夹名用简短中文，不得以点开头，不得包含路径符号；"
            "宁少勿多——无法归类的文件不要放进任何组。"
        )
        user = json.dumps({
            "files": loose[: self.ORGANIZE_MODEL_LIMIT],
            "existing_folders": folders,
            "output_format": {"groups": [{"folder": "文件夹名", "items": ["文件名"], "reason": "一句话理由"}]},
        }, ensure_ascii=False)
        try:
            response = llm_provider.complete([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except Exception as exc:  # provider 的失败方式很多，一律如实降级（不假装是模型给的）
            logger.warning("organize: 模型归类不可用：%s", exc)
            return [], "model_unavailable"

        content = getattr(response, "content", "") or ""
        data = parse_llm_object(content if isinstance(content, str) else str(content)) or {}
        groups = data.get("groups") if isinstance(data, dict) else None
        if not isinstance(groups, list):
            return [], "model_returned_nothing"

        allowed = set(loose)
        used: set[str] = set()
        proposals: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            folder = self._clean_relative(str(group.get("folder") or ""))
            if not folder or folder.startswith("."):
                continue
            target = os.path.abspath(os.path.join(self.workspace, folder))
            if not self._is_within_workspace(target, self.workspace) or self._is_internal_path(target):
                continue
            items = [
                str(item) for item in (group.get("items") or [])
                if str(item) in allowed and str(item) not in used
            ]
            if not items:
                continue
            used.update(items)
            proposals.append({
                "kind": "ai_group",
                "title": f"归到「{folder}」",
                "reason": str(group.get("reason") or "模型建议的归类。"),
                "items": items,
                "suggested_folder": folder,
                "requires_confirmation": True,
                "source": "model",
            })
        return proposals, ("" if proposals else "model_returned_nothing")

    def propose_organization(self, llm_provider: Any = None) -> dict[str, Any]:
        """给出可复核的整理建议，**一份文件都不动**（E17 ⑤）。

        形状与设计一致：提议 → 预览 → 用户确认 → 执行 → 一键撤销。
        传了 `llm_provider` 就走**模型归类**；模型不可用或没说人话时，如实降级回
        确定性规则，并在 `degraded` 里说明原因（不假装那是模型给的）。
        """
        loose, folders = self._loose_root_materials()
        degraded = ""
        if llm_provider is not None and loose:
            proposals, degraded = self._model_organization_proposals(llm_provider, loose, folders)
            if proposals:
                return _ok(proposals=proposals, source="model", degraded=degraded)
        return _ok(proposals=self._rule_organization_proposals(loose), source="rules", degraded=degraded)

    def _documents_by_path(self) -> dict[str, dict[str, Any]]:
        """绝对路径 → 文档行。**一次扫描**建索引，别每个文件都 list_documents 一遍。"""
        from rag.sqlite_store import KBSQLiteStore

        index: dict[str, dict[str, Any]] = {}
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            for document in store.list_documents():
                stored = document.get("path") or ""
                if not stored:
                    continue
                candidate = stored if os.path.isabs(stored) else os.path.join(self.workspace, stored)
                index.setdefault(os.path.abspath(candidate), document)
        finally:
            store.close()
        return index

    def _document_by_path(self, absolute: str) -> dict[str, Any] | None:
        return self._documents_by_path().get(os.path.abspath(absolute))

    def _indexed_content_hashes(self, candidate_hashes: set[str] | None = None) -> dict[str, dict[str, Any]]:
        """内容哈希 → {path, indexed}（F08：去重以**索引**为准，资料被移动/改名也认得出来）。

        `documents.content_hash` 存的就是文件字节的 sha256（`obsidian/sync.py:220/294`），
        与上传时算的 `sha256(content)` 同一算法 —— 所以不必每次上传把全库文件读一遍。
        老数据可能没有 content_hash：那种行会被跳过（见 CHANGELOG 的已知边界）。
        `candidate_hashes` 让磁盘校验只发生在本次上传实际可能命中的候选上。
        """
        from rag.sqlite_store import KBSQLiteStore

        index: dict[str, dict[str, Any]] = {}
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return index
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            for document in store.list_documents():
                digest = str(document.get("content_hash") or "")
                stored = str(document.get("path") or "")
                if not digest or not stored:
                    continue
                if candidate_hashes is not None and digest not in candidate_hashes:
                    continue
                candidate = stored if os.path.isabs(stored) else os.path.join(self.workspace, stored)
                if not self._is_within_workspace(candidate, self.workspace) or self._is_internal_path(candidate):
                    continue
                try:
                    with open(candidate, "rb") as handle:
                        if hashlib.sha256(handle.read()).hexdigest() != digest:
                            # The database row is stale: the file was edited or
                            # removed after it was indexed. Do not discard a
                            # new upload merely because its old hash remains.
                            continue
                except OSError:
                    continue
                index.setdefault(digest, {
                    "path": self._relative_to_workspace(candidate),
                    # 只有真的切出片段才算"建好了索引"：光有行不算完成（审查 F04）。
                    "indexed": bool(document.get("chunk_count") or 0) > 0,
                })
        finally:
            store.close()
        return index

    def apply_organization(self, items: list[str], target_folder: str, config: dict | None = None) -> dict[str, Any]:
        result = self._apply_organization(items, target_folder, config=config)
        return self._with_batch_sync(result, config)

    def _with_batch_sync(self, result: dict[str, Any], config: dict | None) -> dict[str, Any]:
        """批量搬运结束后统一同步一次（逐份搬运时已跳过，见 ``move_document(sync=False)``）。

        只要有东西真的动过（moved / restored 非空）就同步 —— 部分失败也一样，
        否则已经搬过去的资料会一直停在「待重新嵌入」。
        """
        if result.get("moved") or result.get("restored"):
            summary = self._sync_registered_sources(mode="incremental", config=config or {})
            result = {**result, "sync": summary.to_dict()}
        return result

    def _apply_organization(self, items: list[str], target_folder: str, config: dict | None = None) -> dict[str, Any]:
        """把散落的资料收进一个文件夹，并返回**可撤销的动作清单**（E17 ⑤）。

        只处理资料库根目录那一层的文件；有索引的走 ③b 的 move_document（身份与
        引用一起迁移），没索引的直接搬。永远返回 moved 清单，供一键撤销。
        """
        cleaned = self._clean_relative(target_folder)
        if not cleaned:
            return _err("目标文件夹不合法", code="invalid_target")
        target_dir = os.path.abspath(os.path.join(self.workspace, cleaned))
        if not self._is_within_workspace(target_dir, self.workspace) or self._is_internal_path(target_dir):
            return _err("目标文件夹不合法", code="invalid_target")

        plans: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in items or []:
            relative = self._clean_relative(name)
            if not relative or "/" in relative or relative in seen:
                continue
            seen.add(relative)
            source = os.path.abspath(os.path.join(self.workspace, relative))
            if not os.path.isfile(source):
                continue
            destination_relative = f"{cleaned}/{os.path.basename(relative)}"
            destination = os.path.abspath(os.path.join(self.workspace, destination_relative))
            if os.path.exists(destination):
                return _err(
                    "目标位置已经有同名文件，未移动任何资料",
                    code="target_exists",
                    item=relative,
                    destination=destination_relative,
                )
            plans.append({
                "relative": relative,
                "source": source,
                "destination_relative": destination_relative,
                "destination": destination,
                "document": self._document_by_path(source),
            })

        if not plans:
            return _ok(moved=[], batch_id="")

        created_folders: list[str] = []
        if not os.path.isdir(target_dir):
            created = self.create_folder(cleaned)
            if not created.get("ok"):
                return created
            created_folders.append(cleaned)

        # **先写计划再动手**（write-ahead，审查 F02）：进程在任何一步被强杀，重启后
        # 都能从台账看出"打算搬什么、已经搬到哪一项"，而不是留下一地搬了一半的文件。
        entries: list[dict[str, Any]] = [{
            "document_id": str((plan["document"] or {}).get("id") or ""),
            "from": str(plan["relative"]),
            "to": str(plan["destination_relative"]),
            "state": "planned",
            "error": "",
        } for plan in plans]
        batch = self._write_organization_batch(
            self._new_organization_batch(cleaned, entries, created_folders, status="applying")
        )

        def finish(status: str) -> None:
            batch["status"] = status
            self._write_organization_batch(batch)

        def failure_payload(result: dict[str, Any], moved: list[dict[str, Any]], failed: list[dict[str, Any]]) -> dict[str, Any]:
            """部分失败也要把"搬走了哪些、哪些没成、台账 id"如实交出去（审查 F07）。

            判定只看 `moved`：一份都没搬成时没有任何东西可撤销，这一步自己建的文件夹要收回去、
            台账也不该留着。原来的 `not moved and not failed` 永远为假（调用点传入的 failed
            至少已含当前这一项），所以"零成功就回收"从来没生效过 —— 独立审查实测：
            零成功之后目标文件夹照样留在磁盘上、台账里还挂着一条空批次。
            """
            if not moved:
                for folder in reversed(created_folders):
                    try:
                        os.rmdir(os.path.join(self.workspace, folder))
                    except OSError:
                        pass
                self._forget_organization(batch["batch_id"])
                return {**result, "moved": [], "failed": [], "batch_id": "", "partial": False}
            return {
                **result,
                "moved": list(moved),
                "failed": list(failed),
                "batch_id": batch["batch_id"],
                "partial": bool(moved),
            }

        moved: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for index, plan in enumerate(plans):
            entry = entries[index]
            relative = str(plan["relative"])
            destination_relative = str(plan["destination_relative"])
            document = plan["document"]
            result: dict[str, Any]
            try:
                if document is not None:
                    result = self.move_document(str(document.get("id")), destination_relative, config=config, sync=False)
                    if not result.get("ok") and str(result.get("code") or "") == "document_not_found":
                        # 真机（2026-09-28）撞到过：计划到执行之间索引重建了身份，计划里记的 id
                        # 已经查不到 —— 按**现在的路径**重新解析一次，别让资料因为过期 id 搬不动。
                        fresh = self._document_by_path(str(plan["source"]))
                        if fresh is not None:
                            result = self.move_document(str(fresh.get("id")), destination_relative, config=config, sync=False)
                        if not result.get("ok") and str(result.get("code") or "") == "document_not_found":
                            # 索引里彻底没有这条记录了：按未索引文件直接搬（身份已无从谈起）。
                            shutil.move(str(plan["source"]), str(plan["destination"]))
                            result = {"ok": True}
                else:
                    shutil.move(str(plan["source"]), str(plan["destination"]))
                    result = {"ok": True}
            except Exception as exc:  # 审查 F02：异常同样要落账，不只是"返回 ok=False"
                result = _err(str(exc) or exc.__class__.__name__, code="organization_move_failed")

            if result.get("ok"):
                entry.update(state="moved", error="")
                moved.append({key: entry[key] for key in ("document_id", "from", "to")})
                finish("applying")
                continue

            # 失败也可能是"文件已经搬过去了、只是索引/引用迁移没成"——按磁盘事实判断，
            # 搬过去的照样进 moved 并保持可撤销（审查 F02 的第二条探针）。
            physical_moved = os.path.isfile(str(plan["destination"])) and not os.path.isfile(str(plan["source"]))
            reason = str(result.get("error") or "移动失败")
            entry.update(state="moved" if physical_moved else "failed", error=reason)
            if physical_moved:
                moved.append({key: entry[key] for key in ("document_id", "from", "to")})
            failures.append({**entry})
            finish("partial" if moved else "failed")
            error_code = "organization_index_failed" if physical_moved else str(result.get("code") or "organization_move_failed")
            return failure_payload(_err(reason, code=error_code), moved, failures)

        finish("applied")
        return _ok(moved=moved, failed=[], batch_id=batch["batch_id"], partial=False)

    # --- 整理台账：撤销必须活过刷新与重启（E17 ⑤）------------------------

    def _organize_root(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "organize")

    def _organize_index_path(self) -> str:
        # 名字要具体，且必须在 core/persistence_registry.py 里登记（R0.6 tripwire）。
        return os.path.join(self._organize_root(), "organize_index.json")

    def _load_organize_batches(self) -> list[dict[str, Any]]:
        path = self._organize_index_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _save_organize_batches(self, batches: list[dict[str, Any]]) -> None:
        from core.atomic_io import atomic_write_json

        os.makedirs(self._organize_root(), exist_ok=True)
        atomic_write_json(self._organize_index_path(), batches)

    def _new_organization_batch(
        self,
        target_folder: str,
        moves: list[dict[str, Any]],
        created_folders: list[str] | None = None,
        status: str = "planned",
    ) -> dict[str, Any]:
        """造一条台账（**先写计划再动手**，2026-09-28 审查 F02）。

        `status`：planned（计划已落盘，还没动文件）→ applying → applied
        ｜ partial（部分成功）｜ failed（一份都没成）。每一项还带自己的 `state`。
        """
        from datetime import datetime, timezone
        import uuid as _uuid

        return {
            "batch_id": _uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_folder": target_folder,
            "moves": moves,
            # 这一步自己建了哪些文件夹：撤销时要把它们收回去（用户自己的文件夹不在此列）。
            "created_folders": list(created_folders or []),
            "status": status,
        }

    def _write_organization_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        """把台账写进磁盘（同 id 覆盖，新 id 追加）。每次文件系统动作前后都要调它。"""
        batches = self._load_organize_batches()
        for index, existing in enumerate(batches):
            if existing.get("batch_id") == batch.get("batch_id"):
                batches[index] = batch
                break
        else:
            batches.append(batch)
            del batches[:-20]  # 只留最近 20 步，台账不是无限日志
        self._save_organize_batches(batches)
        return batch

    def _forget_organization(self, batch_id: str) -> None:
        if not batch_id:
            return
        self._save_organize_batches(
            [batch for batch in self._load_organize_batches() if batch.get("batch_id") != batch_id]
        )

    @staticmethod
    def _batch_has_actionable_moves(batch: dict[str, Any]) -> bool:
        """这一批还有没有"搬走了、没还回来"的项。

        真机（2026-09-28）：一批里第一项撤销成功、第二项其实没搬成，台账却还挂着"可撤销"，
        界面就会一直显示撤销入口 —— 没有任何东西可以撤销时不该提示撤销（状态字段见 apply_organization）。
        """
        moves = [item for item in batch.get("moves") or [] if isinstance(item, dict)]
        if not moves:
            return False
        states = {str(item.get("state") or "moved") for item in moves}
        if "moved" in states:
            return True
        # 计划已落盘、可能已经动过文件（进程被杀在这一刻）：仍然算待处理。
        return str(batch.get("status") or "") in {"planned", "applying"}

    def organization_state(self) -> dict[str, Any]:
        """界面刷新后要知道"还有没有一步可以撤销"（E17 ⑤）。"""
        batches = self._load_organize_batches()
        pending = next((batch for batch in reversed(batches) if self._batch_has_actionable_moves(batch)), None)
        return _ok(pending_undo=pending)

    def undo_organization(
        self,
        moves: list[dict[str, Any]] | None = None,
        batch_id: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        result = self._undo_organization(moves, batch_id=batch_id, config=config)
        return self._with_batch_sync(result, config)

    def _undo_organization(
        self,
        moves: list[dict[str, Any]] | None = None,
        batch_id: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        """一键撤销上一步整理：按 moved 清单把每份资料放回原位（身份同样保留）。

        不传清单时，用**服务端台账里最近仍有可执行动作的一步**——零成功的失败批次
        不会遮蔽旧批次；这样刷新页面、甚至重启应用之后，用户仍然点得到「撤销」。
        """
        batches = self._load_organize_batches()
        recorded: dict[str, Any] | None = None
        if not moves:
            if batch_id:
                recorded = next((item for item in batches if item.get("batch_id") == batch_id), None)
            else:
                # Keep selection consistent with organization_state(). A newer
                # zero-success failure batch must not hide an older actionable batch.
                recorded = next(
                    (batch for batch in reversed(batches) if self._batch_has_actionable_moves(batch)),
                    None,
                )
            moves = [item for item in (recorded or {}).get("moves") or [] if isinstance(item, dict)]
        restored: list[str] = []
        skipped: list[dict[str, str]] = []
        for move in moves or []:
            destination = self._clean_relative(str(move.get("to") or ""))
            original = self._clean_relative(str(move.get("from") or ""))
            if not destination or not original:
                continue
            if str(move.get("state") or "moved") in {"planned", "undone", "failed"}:
                # planned：计划里还没动过；undone：上次撤销已经还回去了；failed：它压根没搬成。
                # 这三种都没有东西要还，也不该被误报成"原位被占用"。
                continue
            source = os.path.abspath(os.path.join(self.workspace, destination))
            target = os.path.abspath(os.path.join(self.workspace, original))
            # **绝不覆盖**（审查 F03）：原位又出现了文件（用户后来新建的同名资料）就跳过
            # 这一项、保留台账并如实报告 —— 撤销不允许把用户的新内容变成旧内容。
            if os.path.exists(target):
                skipped.append({"from": original, "to": destination, "reason": "target_exists"})
                continue
            if not os.path.isfile(source):
                skipped.append({"from": original, "to": destination, "reason": "source_missing"})
                continue
            # 撤销**以"文件现在在哪"为准**：移动之后索引可能给这份资料重新分配身份，
            # 台账里记下的 document_id 不一定还查得到 —— 2026-09-24 在真实资料库上
            # 就是这样 404 的（文件躺在「未归类」里撤不回来）。台账仍保留该 id 供审计。
            current = self._document_by_path(source)
            try:
                if current is not None:
                    result = self.move_document(str(current.get("id") or ""), original, config=config, sync=False)
                    if not result.get("ok"):
                        skipped.append({"from": original, "to": destination,
                                        "reason": str(result.get("code") or "move_failed")})
                        continue
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.move(source, target)
            except Exception as exc:  # 单项失败不该让整次撤销无声中断
                skipped.append({"from": original, "to": destination,
                                "reason": str(exc) or exc.__class__.__name__})
                continue
            restored.append(original)
        cleanup: list[str] = []
        if recorded is not None:
            cleanup = [str(item) for item in recorded.get("created_folders") or []]
            if skipped:
                # 有跳过的项：台账必须留着（用户处理完冲突还能再撤），并把已还原的标出来，
                # 免得下次重试又把它们当成"还躺在目标目录里"。
                done = set(restored)
                for entry in recorded.get("moves") or []:
                    if str(entry.get("from") or "") in done:
                        entry["state"] = "undone"
                recorded["status"] = "partial_undo"
                self._write_organization_batch(recorded)
            else:
                self._forget_organization(str(recorded.get("batch_id") or ""))
        else:
            # 调用方自带清单（旧调用方式）：把与之相符的那一步台账也清掉，
            # 否则界面会继续提示"可撤销"，而实际上已经撤销过了。
            undone = {(str(item.get("from") or ""), str(item.get("to") or "")) for item in moves or []}
            for candidate in self._load_organize_batches():
                pairs = {(str(item.get("from") or ""), str(item.get("to") or "")) for item in candidate.get("moves") or []}
                if pairs and pairs <= undone and not skipped:
                    cleanup.extend(str(item) for item in candidate.get("created_folders") or [])
                    self._forget_organization(str(candidate.get("batch_id") or ""))
        # 撤销要把这一步**自己建的空文件夹**一起收回去 —— 但用户原本就有的文件夹一根汗毛都不动。
        for folder in cleanup:
            target = os.path.abspath(os.path.join(self.workspace, folder))
            if not self._is_within_workspace(target, self.workspace) or self._is_internal_path(target):
                continue
            try:
                if os.path.isdir(target) and not os.listdir(target):
                    os.rmdir(target)
            except OSError as exc:
                logger.warning("organize: 撤销后清不掉空文件夹 %s：%s", folder, exc)
        return _ok(restored=restored, skipped=skipped)
    def create_folder(self, relative_path: str) -> dict[str, Any]:
        """在资料库里新建一个真实文件夹（E17 ③）。"""
        cleaned = self._clean_relative(relative_path)
        if not cleaned:
            return _err("文件夹路径不合法", code="invalid_target")
        target = os.path.abspath(os.path.join(self.workspace, cleaned))
        if not self._is_within_workspace(target, self.workspace) or self._is_internal_path(target):
            return _err("文件夹路径不合法", code="invalid_target")
        if os.path.exists(target):
            return _err("这里已经有同名文件夹或文件", code="target_exists")
        os.makedirs(target, exist_ok=False)
        return _ok(folder={"name": os.path.basename(target), "path": cleaned})

    def delete_folder(self, relative_path: str, mode: str = "ungroup", config: dict | None = None) -> dict[str, Any]:
        """删掉一个文件夹这个**容器**：里面的资料移回库根，一份都不删。

        mode="ungroup"（默认也是唯一实现的语义）：参考项目 OpenMAIC 的注释说得最准
        —— a container's ⋯ must not be able to destroy work。非资料文件留在原地，
        于是目录会保留（并如实告诉用户），绝不静默丢东西。
        """
        cleaned = self._clean_relative(relative_path)
        if not cleaned:
            return _err("文件夹路径不合法", code="invalid_target")
        target = os.path.abspath(os.path.join(self.workspace, cleaned))
        if not self._is_within_workspace(target, self.workspace) or self._is_internal_path(target):
            return _err("文件夹路径不合法", code="invalid_target")
        if not os.path.isdir(target) or os.path.abspath(target) == os.path.abspath(self.workspace):
            return _err("文件夹不存在", code="folder_not_found")

        from obsidian.scan_policy import is_repo_metadata
        from rag.parsers import SUPPORTED_EXTENSIONS

        moved: list[str] = []
        # 先取索引里已知的 (真实路径 → 文档)，搬完要按同一个身份迁移引用。
        from rag.sqlite_store import KBSQLiteStore

        probe = KBSQLiteStore(self.workspace)
        probe.init_db()
        try:
            indexed_by_path = {
                os.path.abspath(str(item.get("path") or "")): item
                for item in probe.list_documents()
                if item.get("path")
            }
        finally:
            probe.close()

        for root, _dirs, files in os.walk(target):
            for filename in files:
                extension = os.path.splitext(filename)[1].lower()
                if extension not in SUPPORTED_EXTENSIONS or is_repo_metadata(filename):
                    continue
                source_path = os.path.join(root, filename)
                destination = os.path.join(self.workspace, filename)
                stem, suffix = os.path.splitext(filename)
                counter = 2
                while os.path.exists(destination):
                    destination = os.path.join(self.workspace, f"{stem} ({counter}){suffix}")
                    counter += 1
                document = indexed_by_path.get(os.path.abspath(source_path))
                shutil.move(source_path, destination)
                if document is not None:
                    # 与 move_document 完全相同的身份迁移（别再走一遍"当成新资料"）
                    self._migrate_relocated_document(document, destination)
                moved.append(self._relative_to_workspace(source_path))

        # 自底向上收掉空目录；还有东西就留着（不静默丢东西）。
        for root, dirs, _files in os.walk(target, topdown=False):
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(target)
            kept = False
        except OSError:
            kept = True

        # 必须带真实配置：空配置会让移回根目录的资料用默认 embedding 重新索引（2026-11-11 审查）。
        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(folder=cleaned, moved=sorted(moved), kept_directory=kept, sync=summary.to_dict())

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

    # --- 归档：所有资料都能归档，且永远可恢复（E17 ③）--------------------

    def _archive_root(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "archive")

    def _archive_index_path(self) -> str:
        # 名字要具体：`index.json` 太泛，且 tripwire 要求每个持久化文件都能在
        # core/persistence_registry.py 里被认出（R0.6）。
        return os.path.join(self._archive_root(), "archive_index.json")

    def _load_archive_index(self) -> list[dict[str, Any]]:
        path = self._archive_index_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _save_archive_index(self, entries: list[dict[str, Any]]) -> None:
        from core.atomic_io import atomic_write_json

        os.makedirs(self._archive_root(), exist_ok=True)
        atomic_write_json(self._archive_index_path(), entries)

    def _relative_to_workspace(self, path: str) -> str:
        return os.path.relpath(os.path.abspath(path), self.workspace).replace(os.sep, "/")

    def _is_internal_path(self, path: str) -> bool:
        """Bobodan 自己的结构（索引与生成页）不是用户的资料，不许归档。

        例外：上传收件区（旧工作区是 `.bobodan/sources`）装的是用户上传的资料，
        它虽然物理上在 `.bobodan/` 里，但属于用户。
        """
        absolute = os.path.abspath(path)
        if self._is_within_workspace(absolute, self.managed_sources_dir):
            return False
        return any(
            self._is_within_workspace(absolute, os.path.join(self.workspace, name))
            for name in (".bobodan", "wiki")
        )

    def list_archive(self) -> dict[str, Any]:
        """已归档的资料（E17 ③）：归档只是移走，永远可以恢复。"""
        entries = sorted(
            self._load_archive_index(),
            key=lambda item: str(item.get("archived_at") or ""),
            reverse=True,
        )
        return _ok(entries=entries)

    def archive_path(
        self,
        path: str,
        *,
        reason: str = "user",
        document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """把一份资料移进归档区，**保留它在资料库里的原目录层级**并记一条可恢复条目。

        2026-09-24（E17 ③）：旧实现只允许归档 `raw/` 下的文件（Bobodan 自己收进来
        的那些），用户剪进资料库的文件在 App 里删不掉。现在所有资料都能归档；
        文件名冲突不再是问题，因为归档路径带着原目录结构。
        """
        import uuid
        from datetime import datetime, timezone

        absolute = os.path.abspath(path) if path else ""
        if (
            not absolute
            or not self._is_within_workspace(absolute, self.workspace)
            or self._is_internal_path(absolute)
        ):
            return _err("只能归档资料库里的资料", code="document_read_only")
        if not os.path.isfile(absolute):
            return _err("文件已经不在磁盘上", code="document_file_missing")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        original_relative = self._relative_to_workspace(absolute)
        destination = os.path.join(self._archive_root(), stamp, original_relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(absolute, destination)

        entry = {
            "entry_id": uuid.uuid4().hex[:12],
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "document_id": (document or {}).get("id") or "",
            "source": (document or {}).get("source") or "",
            "title": (document or {}).get("title") or os.path.basename(absolute),
            "original_path": original_relative,
            "archived_path": self._relative_to_workspace(destination),
            "size": os.path.getsize(destination),
        }
        entries = self._load_archive_index()
        entries.append(entry)
        self._save_archive_index(entries)
        return _ok(entry=entry)

    def restore_archived(self, entry_id: str, config: dict | None = None) -> dict[str, Any]:
        """把一份已归档的资料放回**原来的位置**并重新索引。"""
        entries = self._load_archive_index()
        entry = next((item for item in entries if item.get("entry_id") == entry_id), None)
        if entry is None:
            return _err("找不到这条归档记录", code="archive_entry_not_found")

        archived = os.path.join(self.workspace, str(entry.get("archived_path") or ""))
        if not os.path.isfile(archived):
            return _err("归档文件已经不在磁盘上", code="archive_file_missing")

        target = os.path.join(self.workspace, str(entry.get("original_path") or ""))
        if os.path.exists(target):
            return _err("原位置已经有同名文件了，请先处理它", code="restore_target_exists")

        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(archived, target)
        self._save_archive_index(
            [item for item in entries if item.get("entry_id") != entry_id]
        )
        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(restored=entry, sync=summary.to_dict())

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
