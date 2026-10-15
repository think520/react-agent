"""R05 / R12（F04·F08·F09）：导入链路的三条边界。

来源：`docs/reviews/2026-09-28-remediation-code-review.md` §2 与
`docs/reviews/evidence/2026-09-28/backend-probe-source.py.txt:85-121`。

**两处有意的偏离**（探针写法被报告自己的修复建议取代，理由留在这里，免得后人以为漏了）：

- **F04** 探针要求第一次 `import_files` **抛 RuntimeError**。现在第一次失败返回**结构化错误**
  （带 `imported` / `pending` 和错误码），HTTP 层不再 500；"重试必须真的补做索引"这条断言
  一字不差地保留。
- **F09** 探针直接断言 `sync.extraction_counts <= len(imported)`，而报告的建议是"逐文件结果
  给本次批次；**全库增量同步结果作为单独字段**展示"。所以这里断言：批次结果 `results` 只含
  本次上传的文件且计数不超过本次数量，全库同步落在 `library_sync`。**用户看到的那句谎话**
  由前端 `web/frontend/src/lib/importSummary.test.ts` 钉住。
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService
from rag.sqlite_store import KBSQLiteStore
from tests.test_organization_apply import _sync


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    (root / "first.md").write_text("# first\n\n" + "A lesson with enough text for indexing. " * 20, encoding="utf-8")
    return root


def test_retry_after_a_failed_sync_indexes_the_existing_file(library, monkeypatch):
    """F04：同步失败后重试，不能因为"盘上已经有同字节的文件"就跳过建索引。"""
    service = KBService(str(library))
    calls = 0

    def flaky_sync(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("review transient sync failure")
        return SimpleNamespace(to_dict=lambda: {"extraction_counts": {"complete": 1}})

    monkeypatch.setattr(service, "_sync_registered_sources", flaky_sync)
    files = [("retry.md", b"A new learning document")]

    first = service.import_files(files)

    assert first["ok"] is False, first
    assert first["code"] == "import_sync_failed", first
    assert (Path(service.managed_sources_dir) / "retry.md").is_file(), "文件应当已经落在 inbox（失败要如实说明）"

    second = service.import_files(files)

    assert second["ok"], second
    assert calls == 2, "文件已经在盘上，重试却按重复文件跳过，没有补做索引"
    assert [p.name for p in Path(service.managed_sources_dir).iterdir()] == ["retry.md"], \
        "重试不该再写一份副本"
    assert [item["status"] for item in second["results"]] == ["pending"], second


def test_reimport_after_organizing_is_recognised_as_duplicate(library, monkeypatch):
    """F08：资料被整理到别的目录后，再传同样的字节必须认出来 —— 不能又建一份副本。"""
    _sync(library, monkeypatch)
    service = KBService(str(library))
    content = b"A newly uploaded learning document. " * 20

    first = service.import_files([("upload.md", content)])
    assert first["ok"], first
    document = next(
        item for item in service.list_documents(collection="all")["documents"]
        if item["relative_path"] == "raw/inbox/upload.md"
    )
    moved = service.move_document(document["document_id"], "Lessons/upload.md")
    assert moved["ok"], moved

    again = service.import_files([("upload.md", content)])

    assert again["imported"] == [], "去重只扫 inbox，整理过的资料又被当成新文件"
    assert again["duplicates"], again
    assert again["duplicates"][0]["existing"] == "Lessons/upload.md", again["duplicates"]


def test_import_results_belong_to_this_batch_only(library, monkeypatch):
    """F09：批次计数只能算这次上传的文件；全库增量同步单独一个字段。"""
    _sync(library, monkeypatch)
    existing = library / "first.md"
    existing.write_text(existing.read_text(encoding="utf-8") + "\nChanged unrelated material", encoding="utf-8")

    result = KBService(str(library)).import_files([("new.md", b"A newly uploaded learning document. " * 20)])

    assert result["imported"] == ["new.md"], result
    batch = result["results"]
    assert [item["filename"] for item in batch] == ["new.md"], batch
    assert sum(1 for item in batch if item["searchable"]) <= len(result["imported"]), batch
    # 全库增量同步是另一个字段：它可以比这批大（资料库里别的文件也变了），但绝不能冒充批次计数。
    assert "library_sync" in result, result.keys()
    assert result["library_sync"]["extraction_counts"].get("complete", 0) >= 1, result["library_sync"]


def test_retry_reparses_a_file_that_failed_inside_the_real_sync(library, monkeypatch):
    _sync(library, monkeypatch)
    import obsidian.sync as sync

    service = KBService(str(library))
    parse_document = sync.parse_document
    parsed = []

    def fail_once(path, workspace):
        if Path(path).name == "retry.md":
            parsed.append(path)
            if len(parsed) == 1:
                raise RuntimeError("transient parser failure")
        return parse_document(path, workspace)

    monkeypatch.setattr(sync, "parse_document", fail_once)
    files = [("retry.md", b"A lesson with enough text for indexing. " * 20)]
    first = service.import_files(files)
    second = service.import_files(files)

    assert len(parsed) == 2, "Calling incremental sync again must actually retry parsing"
    assert first["results"][0]["extraction"] == "error", first
    assert second["results"][0]["searchable"] is True, second
    assert second["results"][0]["status"] == "indexed", second
    assert [path.name for path in Path(service.managed_sources_dir).iterdir()] == ["retry.md"]


@pytest.mark.parametrize("change", ["deleted", "edited"])
def test_stale_index_hash_cannot_discard_an_uploaded_file(library, monkeypatch, change):
    _sync(library, monkeypatch)
    service = KBService(str(library))
    content = (library / "first.md").read_bytes()
    if change == "deleted":
        (library / "first.md").unlink()
    else:
        (library / "first.md").write_text("A different version kept by the user", encoding="utf-8")

    result = service.import_files([("restored.md", content)])

    assert result["duplicates"] == [], "The indexed bytes are no longer on disk"
    assert result["imported"] == ["restored.md"], result
    assert (Path(service.managed_sources_dir) / "restored.md").read_bytes() == content
    assert result["results"][0]["searchable"] is True, result


def test_retry_of_an_unindexed_document_outside_inbox_uses_its_real_path(library, monkeypatch):
    _sync(library, monkeypatch)
    service = KBService(str(library))
    store = KBSQLiteStore(str(library))
    store.init_db()
    try:
        document = next(row for row in store.list_documents() if Path(row["path"]).name == "first.md")
        store.delete_chunks_by_document(document["id"])
    finally:
        store.close()

    result = service.import_files([("copy.md", (library / "first.md").read_bytes())])

    assert result["imported"] == []
    assert result["results"][0]["path"] == "first.md", result
    assert result["results"][0]["searchable"] is True, result
    assert result["results"][0]["status"] == "indexed", result
    assert not (Path(service.managed_sources_dir) / "copy.md").exists()
