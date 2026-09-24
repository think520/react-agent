"""① 扫描规则的两条复现测试（2026-09-24）。

bug 1：库根扫描没有跳过"已登记的来源根"，而来源根本身就在库根下面，
       于是同一份文件被两个扫描根各收一次（两个 document_id）。
       实测证据：真实库里 7 组重复（course/ai-agents-from-zero/... 与 course-2/...）。
       vault 扫描早就有这个跳过（obsidian/vault.py 的 registered_source_names），
       库根扫描没有。

bug 2：仓库元文件（README / CONTRIBUTING / requirements.txt / _sidebar.md …）
       被当成资料索引。旧实现只跳过**库根那一层**的 README.md，
       子目录里的照收（真实库里 course-2/README.md、course-2/requirements.txt 都在列表里）。
"""

import json

import pytest

from obsidian.sync import sync_sources
from rag.sqlite_store import KBSQLiteStore


@pytest.fixture
def portable_library(tmp_path):
    from service.library_service import LibraryService

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def _hermetic(monkeypatch):
    """Embedding/Qdrant are optional for sync; keep the test hermetic."""
    from unittest.mock import MagicMock

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr(
        "rag.embedding_service.EmbeddingService",
        lambda *a, **k: type("Embedding", (), {"is_available": lambda self: False})(),
    )


def _register_roots(portable_library, paths):
    roots_path = portable_library / ".bobodan" / "source_roots.json"
    roots = json.loads(roots_path.read_text(encoding="utf-8"))
    roots["course_dirs"] = [str(path) for path in paths]
    roots_path.write_text(json.dumps(roots, ensure_ascii=False, indent=2), encoding="utf-8")


def _sources(portable_library):
    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        return [d["source"] for d in store.list_documents()]
    finally:
        store.close()


def _sync(portable_library, extra_roots):
    return sync_sources(
        workspace=str(portable_library),
        vault_path=str(portable_library),
        course_dir=str(portable_library),
        extra_course_dirs=[str(path) for path in extra_roots],
        mode="full",
    )


def test_a_subdirectory_registered_as_a_source_root_is_not_indexed_twice(
    portable_library, monkeypatch
):
    """库根下的 course-pack/ 被登记为来源根时，pack 里的文件只能有一条记录。"""
    _hermetic(monkeypatch)
    pack = portable_library / "course-pack"
    pack.mkdir()
    (pack / "lesson.docx").write_bytes(b"PK fake docx")
    _register_roots(portable_library, [pack])

    _sync(portable_library, [pack])

    sources = _sources(portable_library)
    hits = [s for s in sources if s.endswith("lesson.docx")]
    assert hits == ["course-2/lesson.docx"], (
        "同一份文件被索引了多次：" + repr(sources)
    )
    assert not any(s.startswith("course/course-pack/") for s in sources), (
        "库根扫描必须跳过已登记的来源根：" + repr(sources)
    )


def test_a_nested_registered_source_root_is_not_indexed_twice(portable_library, monkeypatch):
    """raw/notes 这种**嵌套**来源根同样不能被库根扫描再收一次。"""
    _hermetic(monkeypatch)
    notes = portable_library / "raw" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "daily.md").write_text("# daily\n\n内容", encoding="utf-8")
    _register_roots(portable_library, [notes])

    _sync(portable_library, [notes])

    sources = _sources(portable_library)
    hits = [s for s in sources if s.endswith("daily.md")]
    assert hits == ["course-2/daily.md"], "嵌套来源根被重复索引：" + repr(sources)


def test_repo_metadata_files_are_skipped_and_reported(portable_library, monkeypatch):
    """仓库元文件任意层级都不索引，并在 summary 里如实列出。"""
    _hermetic(monkeypatch)
    pack = portable_library / "course-pack"
    (pack / "章节").mkdir(parents=True)
    (pack / "README.md").write_text("# 仓库说明", encoding="utf-8")
    (pack / "CONTRIBUTING.md").write_text("贡献指南", encoding="utf-8")
    (pack / "requirements.txt").write_text("langchain", encoding="utf-8")
    (pack / "_sidebar.md").write_text("- 目录", encoding="utf-8")
    (pack / "章节" / "README.md").write_text("# 子目录说明", encoding="utf-8")
    (pack / "教程目录大纲.md").write_text("# 大纲\n\n这是内容", encoding="utf-8")
    (portable_library / "README.md").write_text("# 库根说明", encoding="utf-8")
    _register_roots(portable_library, [pack])

    summary = _sync(portable_library, [pack])

    sources = _sources(portable_library)
    assert not any(s.casefold().endswith("readme.md") for s in sources), sources
    assert not any(s.endswith("CONTRIBUTING.md") for s in sources), sources
    assert not any(s.endswith("requirements.txt") for s in sources), sources
    assert not any(s.endswith("_sidebar.md") for s in sources), sources
    assert "course-2/教程目录大纲.md" in sources, "可能真有用的内容文件必须保留：" + repr(sources)

    reported = set(summary.skipped_files)
    assert any(s.endswith("README.md") for s in reported), reported
    assert any(s.endswith("requirements.txt") for s in reported), reported

def test_a_deleted_file_is_really_removed_after_two_scans(portable_library, monkeypatch):
    """P0-12 的"连续两次缺失才删除"实测永远到不了第 2 次。

    原因：状态文件里的 `files` 每次同步都被 new_state 覆盖，所以一个 source
    第一次缺失后就从 `old_state` 里消失了；而 _resolve_deletions 只遍历
    old_state —— 它的计数既到不了 DELETION_CONFIRMATIONS，下一次同步还会把
    `missing` 里的记录一起丢掉（实测：真实库 29 条该移除的记录既没删、也
    不在待确认列表里）。这条测试钉住"第二次缺失必须真的删除"。
    """
    _hermetic(monkeypatch)
    pack = portable_library / "course-pack"
    pack.mkdir()
    target = pack / "lesson.txt"
    target.write_text("内容", encoding="utf-8")
    _register_roots(portable_library, [pack])

    _sync(portable_library, [pack])
    assert any(s.endswith("lesson.txt") for s in _sources(portable_library))

    target.unlink()  # 用户在资源管理器里删掉它

    summary_one = _sync(portable_library, [pack])
    assert any(s.endswith("lesson.txt") for s in _sources(portable_library)), (
        "第一次缺失不能删除（防抖动）"
    )
    assert summary_one.pending_removal, "第一次缺失必须出现在待确认列表里"

    _sync(portable_library, [pack])
    assert not any(s.endswith("lesson.txt") for s in _sources(portable_library)), (
        "连续两次缺失后必须真的移除"
    )

def test_a_document_whose_source_left_the_scan_scope_is_cleaned_up(portable_library, monkeypatch):
    """状态漂移的自愈：索引里有、但已不属于任何扫描范围的 source 必须能被收回来。

    这正是真实库的情形 —— wiki 生成页（不再被扫描）与因扫描规则收紧而失去
    来源的 7 组重复，共 29 条记录留在索引里；而 sync_state.json 里既没有它们
    （state["files"] 每次都被覆盖）也没有 missing 计数，于是**谁也不会再看到它们**。
    这条测试直接种一条这样的历史记录。
    """
    from rag.sqlite_store import KBSQLiteStore

    _hermetic(monkeypatch)
    pack = portable_library / "course-pack"
    pack.mkdir()
    (pack / "lesson.txt").write_text("内容", encoding="utf-8")
    _register_roots(portable_library, [pack])
    _sync(portable_library, [pack])

    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        store.upsert_document(
            "legacy0000000000",
            "obsidian/wiki/concepts/RAG.md",
            "deadbeef",
            path=str(portable_library / "wiki" / "concepts" / "RAG.md"),
            kind="obsidian_note",
            title="RAG",
        )
    finally:
        store.close()
    assert "obsidian/wiki/concepts/RAG.md" in _sources(portable_library)

    # 再种一条"旧规则索引过、新规则跳过"的仓库元文件：它同样必须掉出索引，
    # 否则 README / requirements.txt 会永远留在资料列表里。
    (portable_library / "README.md").write_text("# 库根说明", encoding="utf-8")
    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        store.upsert_document(
            "legacyreadme0000",
            "course/README.md",
            "deadbeef01",
            path=str(portable_library / "README.md"),
            kind="course_document",
            title="README",
        )
    finally:
        store.close()

    _sync(portable_library, [pack])  # 第一次：进入待确认
    sources = _sources(portable_library)
    assert "obsidian/wiki/concepts/RAG.md" in sources, "第一次只应待确认"
    assert "course/README.md" in sources, "第一次只应待确认"

    _sync(portable_library, [pack])  # 第二次：真正移除
    sources = _sources(portable_library)
    assert "obsidian/wiki/concepts/RAG.md" not in sources, (
        "失去扫描范围的记录必须能被收回来，否则它永远留在索引里"
    )
    assert "course/README.md" not in sources, "被跳过的元文件同样必须掉出索引"
