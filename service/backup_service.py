"""Full-library backup, integrity verification, clean-directory restore, and rollback (W4-RESTORE-01).

Guarantees:
- SQLite databases are snapshotted via ``sqlite3.Connection.backup()`` (WAL-consistent,
  zero ``-wal``/``-shm`` sidecars) and verified with ``PRAGMA integrity_check``.
- Secrets (``provider.json``, ``.env*``) and machine-specific ``libraries.json`` are
  explicitly excluded from every archive and disclosed in ``backup_manifest.json``.
- ``knowledge.db`` document paths inside the workspace are normalized to portable
  relative POSIX paths on backup and rebased to the target directory on restore, so
  citations, reader raw views, and wrong-answer anchors survive cross-path restores.
- Every restore validates all SHA-256 checksums and SQLite integrity before mutating
  anything, and rolls back target files, global stores, and ``libraries.json`` if any
  step fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from core.db import (
    backup_sqlite,
    clear_schema_migrated_cache,
    integrity_check_sqlite,
    remove_sqlite_sidecars,
)
from knowledge.paths import knowledge_dir
from service._result import err as _err, ok as _ok
from service.library_service import LIBRARY_DESCRIPTOR, LibraryService

BACKUP_FORMAT = "bobodan-backup"
BACKUP_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "backup_manifest.json"

LIBRARY_SQLITE_STORES = (
    "knowledge.db",
    "bobodan.db",
    "concept_graph.db",
    "research.db",
)

LIBRARY_META_FILES = (
    "source_roots.json",
    "manifest.json",
    "archive_index.json",
    "organize_index.json",
    "page-archives.json",
    "checkpoint.json",
    "sync_state.json",
    "import_report.json",
    "embedding_signature.json",
)

LIBRARY_META_DIRS = (
    "archive",
    "checkpoints",
    "sources",
)

GLOBAL_SQLITE_STORES = (
    "personal-knowledge.db",
    "usage.db",
)

GLOBAL_JSON_STORES = (
    "preferences.json",
)

EXCLUDED_DISCLOSURE: list[dict[str, str]] = [
    {"name": "provider.json", "reason": "云端 API 密钥与供应商凭证默认不导出"},
    {"name": ".env", "reason": "本地环境变量密钥默认不导出"},
    {"name": "libraries.json", "reason": "包含本机绝对路径；恢复后由目标机器重新注册"},
    {"name": "qdrant/", "reason": "可重建向量索引，恢复后按需重新同步"},
    {"name": "events.db", "reason": "可重建流式断线重连日志"},
    {"name": "cache.db", "reason": "可重建 Wiki 编排缓存"},
]

_SKIP_TOP_DIRS = {".bobodan", ".knowledge", ".session", ".git", "__pycache__", "backups"}
_FORBIDDEN_BASENAMES = {"provider.json", ".env"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_slug(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", (name or "").strip()).strip("-")
    return cleaned[:48] or "library"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_forbidden_secret_name(name: str) -> bool:
    lower = name.lower()
    return lower in _FORBIDDEN_BASENAMES or lower.startswith(".env.")


def _resolve_home(home: str | None = None) -> Path:
    configured = home or os.getenv("BOBODAN_HOME")
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".bobodan").resolve()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _validate_zip_member_name(name: str) -> bool:
    if not name or name.startswith(("/", "\\")):
        return False
    if re.match(r"^[A-Za-z]:", name):
        return False
    parts = Path(name).parts
    if any(part in ("..", "") for part in parts):
        return False
    return True


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == 0o120000


def _normalize_knowledge_db_paths(db_path: Path, workspace_root: Path) -> None:
    """Rewrite absolute workspace paths in staged ``knowledge.db`` to portable relative POSIX paths."""
    if not db_path.is_file():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "documents" not in tables:
            return
        rows = conn.execute("SELECT id, path FROM documents WHERE path IS NOT NULL AND path != ''").fetchall()
        updates: list[tuple[str, str]] = []
        root_resolved = workspace_root.resolve()
        for doc_id, stored_path in rows:
            raw = str(stored_path or "")
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.is_absolute():
                try:
                    rel = candidate.resolve().relative_to(root_resolved).as_posix()
                    updates.append((rel, doc_id))
                except ValueError:
                    # External file outside library: strip machine path, keep filename only if not portable
                    continue
            else:
                updates.append((raw.replace("\\", "/"), doc_id))
        if updates:
            conn.executemany("UPDATE documents SET path = ? WHERE id = ?", updates)
            conn.commit()
    finally:
        conn.close()


def _rebase_knowledge_db_paths(db_path: Path, target_root: Path) -> None:
    """Rebase portable relative POSIX paths in restored ``knowledge.db`` to ``target_root``."""
    if not db_path.is_file():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "documents" not in tables:
            return
        rows = conn.execute("SELECT id, path FROM documents WHERE path IS NOT NULL AND path != ''").fetchall()
        updates: list[tuple[str, str]] = []
        target_resolved = target_root.resolve()
        for doc_id, stored_path in rows:
            raw = str(stored_path or "")
            if not raw:
                continue
            if os.path.isabs(raw) or re.match(r"^[A-Za-z]:", raw):
                continue
            candidate = (target_resolved / Path(raw)).resolve()
            if _is_within(candidate, target_resolved):
                updates.append((str(candidate), doc_id))
        if updates:
            conn.executemany("UPDATE documents SET path = ? WHERE id = ?", updates)
            conn.commit()
    finally:
        conn.close()


def _count_sqlite_rows(db_path: Path, table: str) -> int:
    if not db_path.is_file():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if table not in tables:
            return 0
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.DatabaseError:
        return 0
    finally:
        conn.close()


def _read_library_meta(workspace: Path) -> dict[str, Any]:
    descriptor_path = workspace / LIBRARY_DESCRIPTOR
    if descriptor_path.is_file():
        try:
            data = yaml.safe_load(descriptor_path.read_text(encoding="utf-8")) or {}
            return {
                "library_id": str(data.get("library_id") or ""),
                "name": str(data.get("name") or workspace.name),
                "is_portable": True,
            }
        except (OSError, yaml.YAMLError):
            pass
    return {
        "library_id": "",
        "name": workspace.name,
        "is_portable": False,
    }


def _copy_tree_filtered(source: Path, dest: Path) -> None:
    for root, dirs, files in os.walk(source):
        rel_root = Path(root).relative_to(source)
        dirs[:] = [
            name for name in dirs
            if name not in {".git", "__pycache__"} and not name.startswith(".tmp")
        ]
        for filename in files:
            if _is_forbidden_secret_name(filename):
                continue
            if filename.endswith(("-wal", "-shm", "-journal")):
                continue
            src_file = Path(root) / filename
            if src_file.is_symlink():
                continue
            dst_file = dest / rel_root / filename
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)


def _atomic_copy_file(src: Path, dst: Path, *, is_sqlite: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_sqlite:
        remove_sqlite_sidecars(str(dst))
    tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)
    if is_sqlite:
        remove_sqlite_sidecars(str(dst))


class BackupService:
    """Create, inspect, verify, and restore full Bobodan library backups."""

    def __init__(self, *, home: str | None = None) -> None:
        self.home = _resolve_home(home)
        self.backups_dir = self.home / "backups"

    def _safe_backup_path(self, backup_id: str) -> Path | None:
        if not backup_id or "/" in backup_id or "\\" in backup_id or ".." in backup_id:
            return None
        if not backup_id.endswith(".zip"):
            return None
        candidate = (self.backups_dir / backup_id).resolve()
        if not _is_within(candidate, self.backups_dir):
            return None
        return candidate

    def plan(self, workspace: str, *, include_global: bool = True) -> dict[str, Any]:
        """Preview backup scope and disclosures without writing anything."""
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            return _err("资料库目录不存在", code="library_unavailable")

        meta = _read_library_meta(root)
        store_dir = Path(knowledge_dir(str(root)))
        library_dbs = [name for name in LIBRARY_SQLITE_STORES if (store_dir / name).is_file()]
        session_dir = root / ".session"
        session_count = len([p for p in session_dir.glob("*.json") if p.is_file()]) if session_dir.is_dir() else 0

        global_items: list[str] = []
        if include_global:
            for name in (*GLOBAL_SQLITE_STORES, *GLOBAL_JSON_STORES):
                if (self.home / name).is_file():
                    global_items.append(name)

        counts = {
            "materials": _count_sqlite_rows(store_dir / "knowledge.db", "documents"),
            "questions": _count_sqlite_rows(store_dir / "bobodan.db", "questions"),
            "notes_and_knowledge": _count_sqlite_rows(store_dir / "bobodan.db", "personal_knowledge"),
            "concepts": _count_sqlite_rows(store_dir / "concept_graph.db", "concepts"),
            "sessions": session_count,
        }
        return _ok(
            library=meta,
            library_databases=library_dbs,
            includes_global=include_global,
            global_items=global_items,
            excluded_items=EXCLUDED_DISCLOSURE,
            counts=counts,
        )

    def create_backup(
        self,
        workspace: str,
        output_path: str | None = None,
        *,
        include_global: bool = True,
    ) -> dict[str, Any]:
        """Create a verified, WAL-consistent ZIP archive for a library (and optional global data)."""
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            return _err("资料库目录不存在", code="library_unavailable")

        meta = _read_library_meta(root)
        store_dir = Path(knowledge_dir(str(root)))
        store_rel_dir = store_dir.relative_to(root).as_posix()

        if output_path:
            dest = Path(output_path).expanduser().resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            filename = f"bobodan-backup-{_safe_slug(meta['name'])}-{_timestamp_slug()}-{uuid.uuid4().hex[:6]}.zip"
            dest = self.backups_dir / filename

        staging = Path(tempfile.mkdtemp(prefix="bobodan-backup-stage-"))
        try:
            lib_stage = staging / "library"
            lib_stage.mkdir(parents=True, exist_ok=True)

            # 1. Original materials, descriptor, wiki, user course folders
            for entry in sorted(root.iterdir(), key=lambda item: item.name):
                name = entry.name
                if name in _SKIP_TOP_DIRS or _is_forbidden_secret_name(name):
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_file():
                    shutil.copy2(entry, lib_stage / name)
                elif entry.is_dir():
                    _copy_tree_filtered(entry, lib_stage / name)

            # 2. Chat sessions (.session/)
            session_dir = root / ".session"
            if session_dir.is_dir():
                _copy_tree_filtered(session_dir, lib_stage / ".session")

            # 3. Library SQLite DBs via online backup API (WAL-consistent)
            sqlite_archived: list[str] = []
            meta_stage = lib_stage / store_rel_dir
            meta_stage.mkdir(parents=True, exist_ok=True)
            for db_name in LIBRARY_SQLITE_STORES:
                src_db = store_dir / db_name
                if src_db.is_file():
                    dst_db = meta_stage / db_name
                    backup_sqlite(str(src_db), str(dst_db))
                    if db_name == "knowledge.db":
                        _normalize_knowledge_db_paths(dst_db, root)
                        ok_db, detail = integrity_check_sqlite(str(dst_db))
                        if not ok_db:
                            raise sqlite3.DatabaseError(f"knowledge.db integrity check failed after path normalization: {detail}")
                    sqlite_archived.append(f"library/{store_rel_dir}/{db_name}")

            # 4. Library non-transient metadata files & subdirs
            for filename in LIBRARY_META_FILES:
                src_file = store_dir / filename
                if src_file.is_file():
                    shutil.copy2(src_file, meta_stage / filename)
            for dirname in LIBRARY_META_DIRS:
                src_dir = store_dir / dirname
                if src_dir.is_dir():
                    _copy_tree_filtered(src_dir, meta_stage / dirname)

            # 5. Optional global user data (NEVER provider.json / .env / libraries.json)
            global_items: list[str] = []
            if include_global:
                global_stage = staging / "global"
                global_stage.mkdir(parents=True, exist_ok=True)
                for db_name in GLOBAL_SQLITE_STORES:
                    src_db = self.home / db_name
                    if src_db.is_file():
                        dst_db = global_stage / db_name
                        backup_sqlite(str(src_db), str(dst_db))
                        sqlite_archived.append(f"global/{db_name}")
                        global_items.append(db_name)
                for json_name in GLOBAL_JSON_STORES:
                    src_json = self.home / json_name
                    if src_json.is_file():
                        shutil.copy2(src_json, global_stage / json_name)
                        global_items.append(json_name)

            # 6. Compute SHA-256 checksums for every file to archive
            file_entries: list[dict[str, Any]] = []
            for file_path in sorted(staging.rglob("*")):
                if not file_path.is_file():
                    continue
                arcname = file_path.relative_to(staging).as_posix()
                file_entries.append({
                    "path": arcname,
                    "size": file_path.stat().st_size,
                    "sha256": _sha256_file(file_path),
                })

            staged_session_dir = lib_stage / ".session"
            session_count = len(list(staged_session_dir.glob("*.json"))) if staged_session_dir.is_dir() else 0
            counts = {
                "files": len(file_entries),
                "materials": _count_sqlite_rows(meta_stage / "knowledge.db", "documents"),
                "questions": _count_sqlite_rows(meta_stage / "bobodan.db", "questions"),
                "notes_and_knowledge": _count_sqlite_rows(meta_stage / "bobodan.db", "personal_knowledge"),
                "concepts": _count_sqlite_rows(meta_stage / "concept_graph.db", "concepts"),
                "sessions": session_count,
            }

            manifest = {
                "format": BACKUP_FORMAT,
                "schema_version": BACKUP_SCHEMA_VERSION,
                "created_at": _now_iso(),
                "library": meta,
                "storage_dir": store_rel_dir,
                "includes_global": include_global,
                "global_items": global_items,
                "excluded_items": EXCLUDED_DISCLOSURE,
                "sqlite_databases": sqlite_archived,
                "counts": counts,
                "files": file_entries,
            }
            manifest_path = staging / MANIFEST_FILENAME
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            # 7. Write ZIP atomically
            tmp_zip = dest.with_name(f".{dest.name}.{uuid.uuid4().hex[:8]}.tmp")
            try:
                with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(manifest_path, MANIFEST_FILENAME)
                    for entry in file_entries:
                        zf.write(staging / entry["path"], entry["path"])
                os.replace(tmp_zip, dest)
            finally:
                if tmp_zip.exists():
                    try:
                        tmp_zip.unlink()
                    except OSError:
                        pass

            return _ok(
                backup_id=dest.name,
                filename=dest.name,
                archive_path=str(dest),
                size_bytes=dest.stat().st_size,
                created_at=manifest["created_at"],
                library=meta,
                includes_global=include_global,
                global_items=global_items,
                excluded_items=EXCLUDED_DISCLOSURE,
                counts=counts,
                sqlite_databases=sqlite_archived,
            )
        except Exception as exc:
            return _err(f"创建备份失败：{exc}", code="backup_create_failed")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def list_backups(self) -> dict[str, Any]:
        """List backups saved under ``<BOBODAN_HOME>/backups`` without exposing absolute paths."""
        if not self.backups_dir.is_dir():
            return _ok(backups=[])
        items: list[dict[str, Any]] = []
        for path in sorted(self.backups_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
            entry: dict[str, Any] = {
                "backup_id": path.name,
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "created_at": "",
                "library": None,
                "includes_global": False,
                "counts": {},
                "valid_manifest": False,
            }
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    if MANIFEST_FILENAME in zf.namelist():
                        manifest = json.loads(zf.read(MANIFEST_FILENAME).decode("utf-8"))
                        if isinstance(manifest, dict) and manifest.get("format") == BACKUP_FORMAT:
                            entry["created_at"] = str(manifest.get("created_at") or "")
                            entry["library"] = manifest.get("library")
                            entry["includes_global"] = bool(manifest.get("includes_global"))
                            entry["counts"] = manifest.get("counts") or {}
                            entry["valid_manifest"] = True
            except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
                pass
            items.append(entry)
        return _ok(backups=items)

    def resolve_backup_file(self, backup_id: str) -> Path | None:
        path = self._safe_backup_path(backup_id)
        return path if path is not None and path.is_file() else None

    def verify_backup(self, archive_path: str) -> dict[str, Any]:
        """Validate archive structure, every file SHA-256 checksum, secret exclusion, and SQLite integrity."""
        path = Path(archive_path).expanduser().resolve()
        if not path.is_file():
            return _err("找不到备份文件", code="backup_not_found")

        temp_dir = Path(tempfile.mkdtemp(prefix="bobodan-backup-verify-"))
        try:
            try:
                zf = zipfile.ZipFile(path, "r")
            except (OSError, zipfile.BadZipFile) as exc:
                return _err(f"备份压缩包损坏或格式无效：{exc}", code="backup_corrupt")

            with zf:
                infos = zf.infolist()
                names: list[str] = []
                for info in infos:
                    if info.is_dir():
                        continue
                    if not _validate_zip_member_name(info.filename):
                        return _err(f"备份包含不安全路径：{info.filename}", code="backup_invalid")
                    if _is_zip_symlink(info):
                        return _err(f"备份不允许包含符号链接：{info.filename}", code="backup_invalid")
                    basename = Path(info.filename).name
                    if _is_forbidden_secret_name(basename):
                        return _err(
                            f"备份包含禁止导出的敏感密钥文件：{basename}",
                            code="backup_invalid",
                        )
                    names.append(info.filename)

                if MANIFEST_FILENAME not in names:
                    return _err("备份缺少清单文件 backup_manifest.json", code="backup_invalid")

                try:
                    manifest = json.loads(zf.read(MANIFEST_FILENAME).decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    return _err(f"备份清单损坏：{exc}", code="backup_corrupt")

                if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
                    return _err("这不是有效的 Bobodan 备份包", code="backup_invalid")

                schema_version = manifest.get("schema_version")
                if schema_version != BACKUP_SCHEMA_VERSION:
                    return _err(
                        f"不支持的备份格式版本：{schema_version}",
                        code="backup_invalid",
                    )

                declared_files = manifest.get("files")
                if not isinstance(declared_files, list):
                    return _err("备份清单缺少文件校验列表", code="backup_invalid")

                declared_map: dict[str, dict[str, Any]] = {}
                for item in declared_files:
                    if not isinstance(item, dict) or not item.get("path"):
                        return _err("备份清单条目格式无效", code="backup_invalid")
                    rel = str(item["path"])
                    if not _validate_zip_member_name(rel) or rel == MANIFEST_FILENAME:
                        return _err(f"备份清单包含非法路径：{rel}", code="backup_invalid")
                    declared_map[rel] = item

                actual_payload_names = {n for n in names if n != MANIFEST_FILENAME}
                missing = sorted(set(declared_map) - actual_payload_names)
                unexpected = sorted(actual_payload_names - set(declared_map))
                if missing or unexpected:
                    return _err(
                        "备份文件与校验清单不一致，可能已被修改或截断",
                        code="backup_corrupt",
                        missing_files=missing[:10],
                        unexpected_files=unexpected[:10],
                    )

                mismatched: list[str] = []
                for rel, expected in declared_map.items():
                    data = zf.read(rel)
                    actual_sha = hashlib.sha256(data).hexdigest()
                    if len(data) != int(expected.get("size", -1)) or actual_sha != str(expected.get("sha256") or ""):
                        mismatched.append(rel)
                if mismatched:
                    return _err(
                        f"备份文件校验失败（SHA-256 不匹配）：{', '.join(mismatched[:5])}",
                        code="backup_corrupt",
                        mismatched_files=mismatched[:10],
                    )

                # Verify every declared SQLite DB passes PRAGMA integrity_check
                sqlite_dbs = [str(item) for item in (manifest.get("sqlite_databases") or [])]
                checked_dbs: list[str] = []
                for rel_db in sqlite_dbs:
                    if rel_db not in declared_map:
                        return _err(f"清单声明的数据库不存在于备份中：{rel_db}", code="backup_corrupt")
                    out_db = temp_dir / Path(rel_db).name
                    out_db.write_bytes(zf.read(rel_db))
                    ok_db, detail = integrity_check_sqlite(str(out_db))
                    if not ok_db:
                        return _err(
                            f"备份中的数据库损坏（{Path(rel_db).name}）：{detail}",
                            code="backup_corrupt",
                            corrupt_database=rel_db,
                        )
                    checked_dbs.append(rel_db)
                    out_db.unlink(missing_ok=True)

                return _ok(
                    valid=True,
                    created_at=str(manifest.get("created_at") or ""),
                    library=manifest.get("library") or {},
                    storage_dir=str(manifest.get("storage_dir") or ".bobodan"),
                    includes_global=bool(manifest.get("includes_global")),
                    global_items=list(manifest.get("global_items") or []),
                    excluded_items=list(manifest.get("excluded_items") or EXCLUDED_DISCLOSURE),
                    counts=dict(manifest.get("counts") or {}),
                    sqlite_databases=checked_dbs,
                    verified_files=len(declared_map),
                )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def restore_backup(
        self,
        archive_path: str,
        target_dir: str,
        *,
        restore_global: bool = False,
        activate: bool = True,
        new_library_id: bool = False,
        _fault_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Verify and atomically restore a backup into a clean target directory, with full rollback on error."""
        from rag.retriever import clear_retrieval_cache

        verified = self.verify_backup(archive_path)
        if not verified.get("ok"):
            return verified

        target = Path(target_dir).expanduser().resolve()
        if _is_within(target, self.home) or _is_within(self.home, target):
            return _err("恢复目标目录不能与应用数据目录重叠，请选择单独的资料库文件夹", code="restore_target_invalid")
        if target.exists():
            if not target.is_dir():
                return _err("恢复目标路径已存在且不是文件夹", code="restore_target_not_empty")
            if any(target.iterdir()):
                return _err("恢复目标文件夹不为空，请选择一个空白文件夹以避免覆盖已有资料", code="restore_target_not_empty")

        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".bobodan-restore-stage-", dir=str(target.parent)))
        rollback_dir = Path(tempfile.mkdtemp(prefix="bobodan-restore-rollback-"))

        library_service = LibraryService(home=str(self.home))
        registry_path = library_service.registry_path
        registry_existed = registry_path.is_file()
        registry_snapshot = rollback_dir / "libraries.bak"
        if registry_existed:
            shutil.copy2(registry_path, registry_snapshot)

        global_files = (*GLOBAL_SQLITE_STORES, *GLOBAL_JSON_STORES)
        global_snapshots: dict[str, Path | None] = {}
        apply_global = bool(restore_global and verified.get("includes_global"))
        if apply_global:
            for name in global_files:
                src = self.home / name
                if src.is_file():
                    snap = rollback_dir / f"global-{name}.bak"
                    if name in GLOBAL_SQLITE_STORES:
                        backup_sqlite(str(src), str(snap))
                    else:
                        shutil.copy2(src, snap)
                    global_snapshots[name] = snap
                else:
                    global_snapshots[name] = None

        target_existed_empty = target.exists()
        moved_to_target = False
        try:
            # Stage extract & prepare library directory before touching live locations
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir() or info.filename == MANIFEST_FILENAME:
                        continue
                    out = (staging / info.filename).resolve()
                    if not _is_within(out, staging):
                        raise ValueError(f"Unsafe archive path: {info.filename}")
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(zf.read(info.filename))

            staged_lib = staging / "library"
            if not staged_lib.is_dir():
                raise ValueError("备份中缺少 library 目录")

            storage_rel = str(verified.get("storage_dir") or ".bobodan")
            staged_kb_db = staged_lib / storage_rel / "knowledge.db"
            if staged_kb_db.is_file():
                _rebase_knowledge_db_paths(staged_kb_db, target)
                ok_db, detail = integrity_check_sqlite(str(staged_kb_db))
                if not ok_db:
                    raise sqlite3.DatabaseError(f"knowledge.db rebase verification failed: {detail}")

            descriptor_path = staged_lib / LIBRARY_DESCRIPTOR
            if descriptor_path.is_file() and new_library_id:
                descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8")) or {}
                descriptor["library_id"] = str(uuid.uuid4())
                descriptor_path.write_text(
                    yaml.safe_dump(descriptor, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )

            # Remove empty placeholder dir so os.replace/shutil.move moves cleanly into `target`
            if target_existed_empty:
                target.rmdir()
            shutil.move(str(staged_lib), str(target))
            moved_to_target = True

            if _fault_hook is not None:
                _fault_hook("after_library_move")

            # Restore optional global stores (NEVER touches provider.json)
            restored_global: list[str] = []
            if apply_global:
                self.home.mkdir(parents=True, exist_ok=True)
                staged_global = staging / "global"
                if staged_global.is_dir():
                    for name in global_files:
                        staged_item = staged_global / name
                        if staged_item.is_file():
                            _atomic_copy_file(
                                staged_item,
                                self.home / name,
                                is_sqlite=(name in GLOBAL_SQLITE_STORES),
                            )
                            restored_global.append(name)

            if _fault_hook is not None:
                _fault_hook("after_global_write")

            # Register restored library (portable libraries have BOBODAN_LIBRARY.yaml)
            if (target / LIBRARY_DESCRIPTOR).is_file():
                registered = library_service.register(str(target), activate=activate)
            else:
                registered = library_service.initialize(str(target), activate=activate)

            if _fault_hook is not None:
                _fault_hook("after_register")

            clear_retrieval_cache()
            clear_schema_migrated_cache()

            # Post-restore verification: confirm all restored SQLite DBs pass integrity_check
            restored_store_dir = Path(knowledge_dir(str(target)))
            for db_name in LIBRARY_SQLITE_STORES:
                db_file = restored_store_dir / db_name
                if db_file.is_file():
                    ok_db, detail = integrity_check_sqlite(str(db_file))
                    if not ok_db:
                        raise sqlite3.DatabaseError(f"Restored {db_name} failed integrity check: {detail}")
            if apply_global:
                for db_name in GLOBAL_SQLITE_STORES:
                    db_file = self.home / db_name
                    if db_file.is_file():
                        ok_db, detail = integrity_check_sqlite(str(db_file))
                        if not ok_db:
                            raise sqlite3.DatabaseError(f"Restored global {db_name} failed integrity check: {detail}")

            resolved = library_service.resolve(registered["library_id"])
            if resolved is None or Path(resolved["path"]).resolve() != target.resolve():
                raise ValueError("恢复后的资料库未成功注册")

            if _fault_hook is not None:
                _fault_hook("after_verify")

            return _ok(
                library=registered,
                restored_global=restored_global,
                excluded_items=list(verified.get("excluded_items") or EXCLUDED_DISCLOSURE),
                counts=verified.get("counts") or {},
                verified_files=verified.get("verified_files", 0),
            )
        except Exception as exc:
            # Full rollback: restore target, global stores, and libraries.json to exact pre-restore state
            clear_retrieval_cache()
            clear_schema_migrated_cache()

            if moved_to_target and target.exists():
                shutil.rmtree(target, ignore_errors=True)
                if target_existed_empty:
                    target.mkdir(parents=True, exist_ok=True)

            if apply_global:
                for name, snap in global_snapshots.items():
                    dst = self.home / name
                    if name in GLOBAL_SQLITE_STORES:
                        remove_sqlite_sidecars(str(dst))
                    if snap is not None and snap.is_file():
                        _atomic_copy_file(snap, dst, is_sqlite=(name in GLOBAL_SQLITE_STORES))
                    elif dst.exists():
                        try:
                            dst.unlink()
                        except OSError:
                            pass

            if registry_existed and registry_snapshot.is_file():
                _atomic_copy_file(registry_snapshot, registry_path)
            elif registry_path.exists():
                try:
                    registry_path.unlink()
                except OSError:
                    pass

            clear_retrieval_cache()
            clear_schema_migrated_cache()
            return _err(
                f"恢复失败，已回滚到恢复前状态：{exc}",
                code="restore_failed",
                rolled_back=True,
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(rollback_dir, ignore_errors=True)
