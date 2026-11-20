"""W4-RESTORE-01: full-library backup, WAL consistency, verification, restore & migration rollback tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from core.db import create_connection, integrity_check_sqlite
from graph.concept_store import ConceptStore
from memory.personal_store import PersonalKnowledgeStore
from rag.sqlite_store import KBSQLiteStore
from service.backup_service import BACKUP_FORMAT, MANIFEST_FILENAME, BackupService
from service.legacy_graph_migration import LegacyGraphMigrationService
from service.library_service import LIBRARY_DESCRIPTOR, LibraryService
from service.preference_service import PreferenceService


def _seed_library(tmp_path: Path, name: str = "Algorithms") -> tuple[Path, Path, dict]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    parent = tmp_path / "libraries"
    parent.mkdir(parents=True, exist_ok=True)
    lib_service = LibraryService(home=str(home))
    library = lib_service.create(name, str(parent))
    root = Path(lib_service.resolve(library["library_id"])["path"])

    material = root / "raw" / "inbox" / "dijkstra.md"
    material.write_text("# Dijkstra\n\n非负权图单源最短路径。\n", encoding="utf-8")

    # Populate knowledge.db in WAL mode with absolute path
    kb = KBSQLiteStore(str(root))
    kb.init_db()
    kb.upsert_document(
        document_id="doc-dijkstra",
        source="inbox/dijkstra.md",
        content_hash="abc123",
        path=str(material.resolve()),
        kind="markdown",
        title="Dijkstra",
    )
    kb.close()

    # Populate library bobodan.db & global personal-knowledge.db
    pk = PersonalKnowledgeStore(str(root), home=str(home))
    pk.create_item(
        scope="library",
        kind="course_insight",
        title="贪心正确性",
        content="Dijkstra 依赖非负边权。",
        references=[{"document_id": "doc-dijkstra", "chunk_id": "chunk-1"}],
    )
    pk.create_item(
        scope="global",
        kind="goal",
        title="考研算法冲刺",
        content="每周掌握两章图论。",
    )

    # Global preferences
    prefs = PreferenceService("deepseek", [], home=str(home))
    prefs.patch(0, {"user": {"display_name": "小张", "long_term_goal": "图论满分"}}, ["deepseek"], [])

    # Chat session
    session_dir = root / ".session"
    session_dir.mkdir(exist_ok=True)
    (session_dir / "11111111-1111-4111-8111-111111111111.json").write_text(
        json.dumps({"id": "11111111-1111-4111-8111-111111111111", "title": "图论问答", "messages": []}),
        encoding="utf-8",
    )

    # Secrets that MUST NEVER be exported
    (home / "provider.json").write_text(
        json.dumps({"providers": {"deepseek": {"api_key": "sk-secret-do-not-export-99999"}}}),
        encoding="utf-8",
    )
    (root / ".env").write_text("OPENAI_API_KEY=sk-env-secret-88888\n", encoding="utf-8")

    return home, root, library


def test_backup_uses_sqlite_online_backup_for_wal_consistency(tmp_path):
    home, root, _ = _seed_library(tmp_path)
    db_path = root / ".bobodan" / "bobodan.db"

    # Keep an active WAL connection with uncheckpointed writes while taking the backup
    conn = create_connection(str(db_path), wal=True)
    try:
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute(
            """INSERT INTO personal_knowledge
               (id, scope, kind, title, content, search_text, pinned, confidence,
                evidence, "references", source_candidate_id, created_at, updated_at, revision)
               VALUES ('wal-row-1', 'library', 'course_insight', 'WAL测试', '未检查点事务必须进备份',
                       'wal', 0, 1.0, '[]', '[]', NULL, '2026-11-20', '2026-11-20', 1)"""
        )
        conn.commit()
        assert Path(f"{db_path}-wal").exists(), "WAL file should exist before backup"

        archive = tmp_path / "wal-backup.zip"
        result = BackupService(home=str(home)).create_backup(str(root), str(archive), include_global=True)
        assert result["ok"] is True, result
    finally:
        conn.close()

    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        assert not any(name.endswith(("-wal", "-shm", "-journal")) for name in names), names
        extracted_db = tmp_path / "extracted-bobodan.db"
        extracted_db.write_bytes(zf.read("library/.bobodan/bobodan.db"))

    ok, detail = integrity_check_sqlite(str(extracted_db))
    assert ok, detail
    check = sqlite3.connect(str(extracted_db))
    try:
        row = check.execute("SELECT title, content FROM personal_knowledge WHERE id='wal-row-1'").fetchone()
    finally:
        check.close()
    assert row == ("WAL测试", "未检查点事务必须进备份")


def test_backup_excludes_secrets_and_normalizes_local_paths(tmp_path):
    home, root, _ = _seed_library(tmp_path)
    archive = tmp_path / "clean-backup.zip"
    service = BackupService(home=str(home))

    plan = service.plan(str(root), include_global=True)
    assert plan["ok"] is True
    assert any(item["name"] == "provider.json" for item in plan["excluded_items"])
    assert "preferences.json" in plan["global_items"]
    assert "personal-knowledge.db" in plan["global_items"]

    created = service.create_backup(str(root), str(archive), include_global=True)
    assert created["ok"] is True, created

    with zipfile.ZipFile(archive, "r") as zf:
        names = zf.namelist()
        assert not any("provider.json" in name for name in names)
        assert not any(Path(name).name.startswith(".env") for name in names)
        assert not any("libraries.json" in name for name in names)
        for name in names:
            raw = zf.read(name)
            assert b"sk-secret-do-not-export-99999" not in raw, f"secret leaked in {name}"
            assert b"sk-env-secret-88888" not in raw, f"env secret leaked in {name}"

        # Staged knowledge.db must hold portable relative path, not machine absolute path
        kb_copy = tmp_path / "staged-kb.db"
        kb_copy.write_bytes(zf.read("library/.bobodan/knowledge.db"))
        conn = sqlite3.connect(str(kb_copy))
        try:
            stored_path = conn.execute("SELECT path FROM documents WHERE id='doc-dijkstra'").fetchone()[0]
        finally:
            conn.close()
        assert stored_path == "raw/inbox/dijkstra.md"


def test_verify_detects_checksum_tamper_corrupt_sqlite_zip_slip_and_secrets(tmp_path):
    home, root, _ = _seed_library(tmp_path)
    service = BackupService(home=str(home))
    archive = tmp_path / "valid.zip"
    assert service.create_backup(str(root), str(archive), include_global=True)["ok"] is True
    assert service.verify_backup(str(archive))["ok"] is True

    # 1. Tamper with a single byte of a material file -> backup_corrupt
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive, "r") as src, zipfile.ZipFile(tampered, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith("dijkstra.md"):
                data = data + b" tampered"
            dst.writestr(info, data)
    res_tampered = service.verify_backup(str(tampered))
    assert res_tampered["ok"] is False
    assert res_tampered["code"] == "backup_corrupt"

    # 2. Corrupt SQLite DB even when manifest SHA-256 matches -> backup_corrupt
    corrupt_db_zip = tmp_path / "corrupt-db.zip"
    with zipfile.ZipFile(archive, "r") as src:
        manifest = json.loads(src.read(MANIFEST_FILENAME).decode("utf-8"))
        bad_bytes = b"not a valid sqlite database"
        for entry in manifest["files"]:
            if entry["path"] == "library/.bobodan/knowledge.db":
                entry["size"] = len(bad_bytes)
                entry["sha256"] = hashlib.sha256(bad_bytes).hexdigest()
        with zipfile.ZipFile(corrupt_db_zip, "w") as dst:
            dst.writestr(MANIFEST_FILENAME, json.dumps(manifest))
            for info in src.infolist():
                if info.filename == MANIFEST_FILENAME:
                    continue
                data = bad_bytes if info.filename == "library/.bobodan/knowledge.db" else src.read(info.filename)
                dst.writestr(info.filename, data)
    res_db = service.verify_backup(str(corrupt_db_zip))
    assert res_db["ok"] is False
    assert res_db["code"] == "backup_corrupt"

    # 3. Zip Slip attack -> backup_invalid
    slip_zip = tmp_path / "slip.zip"
    with zipfile.ZipFile(slip_zip, "w") as zf:
        zf.writestr("../../evil.txt", "boom")
        zf.writestr(MANIFEST_FILENAME, json.dumps({"format": BACKUP_FORMAT, "schema_version": 1, "files": []}))
    res_slip = service.verify_backup(str(slip_zip))
    assert res_slip["ok"] is False
    assert res_slip["code"] == "backup_invalid"

    # 4. Archive smuggling provider.json -> backup_invalid
    secret_zip = tmp_path / "secret.zip"
    with zipfile.ZipFile(secret_zip, "w") as zf:
        zf.writestr("global/provider.json", '{"api_key":"x"}')
        zf.writestr(MANIFEST_FILENAME, json.dumps({"format": BACKUP_FORMAT, "schema_version": 1, "files": []}))
    res_secret = service.verify_backup(str(secret_zip))
    assert res_secret["ok"] is False
    assert res_secret["code"] == "backup_invalid"


def test_restore_rejects_non_empty_target_without_modifying_files(tmp_path):
    home, root, _ = _seed_library(tmp_path)
    service = BackupService(home=str(home))
    archive = tmp_path / "backup.zip"
    assert service.create_backup(str(root), str(archive), include_global=True)["ok"] is True

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    keep = occupied / "existing-note.md"
    keep.write_text("不要覆盖我", encoding="utf-8")

    result = service.restore_backup(str(archive), str(occupied))
    assert result["ok"] is False
    assert result["code"] == "restore_target_not_empty"
    assert keep.read_text(encoding="utf-8") == "不要覆盖我"


@pytest.mark.parametrize("fault_stage", ["after_library_move", "after_global_write", "after_register"])
def test_restore_failure_rolls_back_target_global_stores_and_registry(tmp_path, fault_stage):
    src_home, src_root, _ = _seed_library(tmp_path / "source")
    archive = tmp_path / "backup.zip"
    assert BackupService(home=str(src_home)).create_backup(str(src_root), str(archive), include_global=True)["ok"] is True

    # Prepare destination machine with existing preferences, global personal knowledge, and another library
    dst_home = tmp_path / "dest-home"
    dst_parent = tmp_path / "dest-libs"
    dst_parent.mkdir(parents=True)
    existing_lib = LibraryService(home=str(dst_home)).create("Existing", str(dst_parent))
    existing_root = Path(LibraryService(home=str(dst_home)).resolve(existing_lib["library_id"])["path"])

    dst_prefs = PreferenceService("deepseek", [], home=str(dst_home))
    dst_prefs.patch(0, {"user": {"display_name": "原用户"}}, ["deepseek"], [])
    dst_pk = PersonalKnowledgeStore(str(existing_root), home=str(dst_home))
    dst_pk.create_item(scope="global", kind="goal", title="原有全局目标", content="恢复失败后必须还在")

    target_dir = tmp_path / "clean-restore-target"

    def fail_at(stage: str) -> None:
        if stage == fault_stage:
            raise RuntimeError(f"injected failure at {stage}")

    res = BackupService(home=str(dst_home)).restore_backup(
        str(archive),
        str(target_dir),
        restore_global=True,
        _fault_hook=fail_at,
    )
    assert res["ok"] is False
    assert res["code"] == "restore_failed"
    assert res["rolled_back"] is True

    # Target directory must be cleaned up
    assert not target_dir.exists()

    # Registry must still contain only the pre-existing library
    libs = LibraryService(home=str(dst_home)).list_libraries()
    assert [item["library_id"] for item in libs["libraries"]] == [existing_lib["library_id"]]
    assert libs["active_library_id"] == existing_lib["library_id"]

    # Global preferences and global personal knowledge must be intact
    assert PreferenceService("deepseek", [], home=str(dst_home)).get()["user"]["display_name"] == "原用户"
    global_items = PersonalKnowledgeStore(str(existing_root), home=str(dst_home)).list_items(scope="global")
    assert [item["title"] for item in global_items] == ["原有全局目标"]


def test_library_migration_failure_rolls_back_scaffolding_and_preserves_user_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    folder = tmp_path / "my-course-notes"
    folder.mkdir()
    user_note = folder / "lecture1.md"
    user_note.write_text("# 第一讲\n\n用户原始笔记。", encoding="utf-8")

    service = LibraryService(home=str(home))

    def broken_sync(self, library_id, config=None):
        raise RuntimeError("simulated sync crash")

    monkeypatch.setattr(LibraryService, "sync", broken_sync)

    with pytest.raises(RuntimeError, match="simulated sync crash"):
        service.migrate(str(folder), name="我的课程")

    # Registry remains empty
    assert service.list_libraries()["libraries"] == []
    # Newly created Bobodan scaffolding is cleaned up
    assert not (folder / LIBRARY_DESCRIPTOR).exists()
    assert not (folder / ".bobodan").exists()
    assert not (folder / "raw").exists()
    assert not (folder / "wiki").exists()
    assert not (folder / "WIKI_SCHEMA.md").exists()
    # Original user file is completely untouched
    assert user_note.read_text(encoding="utf-8") == "# 第一讲\n\n用户原始笔记。"


def test_legacy_graph_migration_failure_rolls_back_databases_and_keeps_source(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    workspace = tmp_path / "lib"
    (workspace / ".bobodan").mkdir(parents=True)
    (workspace / LIBRARY_DESCRIPTOR).write_text(
        "schema_version: 1\nlibrary_id: 11111111-1111-4111-8111-111111111111\nname: Legacy\n",
        encoding="utf-8",
    )

    # Seed pre-existing concept candidate to verify rollback restores exact state
    concept_db = workspace / ".bobodan" / "concept_graph.db"
    pre_store = ConceptStore(str(concept_db))
    pre_store.add_candidate(
        name="已有概念",
        level="core",
        definition="迁移前就存在",
        confidence="high",
        source_doc_id="doc-0",
        source_doc_title="原讲义",
        excerpt="原文",
    )

    graph_json = workspace / ".bobodan" / "graph_store.json"
    graph_json.write_text(
        json.dumps({
            "nodes": {
                "c1": {"label": "Concept", "name": "贝尔曼福特"},
                "m1": {"label": "Memory", "name": "学习习惯", "properties": {"content": "喜欢画图"}},
            },
            "relationships": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    from service.memory_service import MemoryService

    def explode(*args, **kwargs):
        raise RuntimeError("disk full during memory candidate write")

    monkeypatch.setattr(MemoryService, "add_candidate", explode)

    result = LegacyGraphMigrationService(str(workspace), home=str(home)).migrate(
        concept_ids=["c1"],
        memory_ids=["m1"],
        archive=True,
    )
    assert result["ok"] is False
    assert result["code"] == "legacy_migration_failed"
    assert result["rolled_back"] is True

    # Source file was NOT archived or deleted
    assert graph_json.is_file()
    # ConceptStore was rolled back: "贝尔曼福特" is gone, "已有概念" remains
    after_candidates = [c["name"] for c in ConceptStore(str(concept_db)).list_candidates()]
    assert after_candidates == ["已有概念"]
