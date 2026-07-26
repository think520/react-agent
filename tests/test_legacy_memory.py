"""Regression tests for the read-only legacy-memory migration boundary."""

from memory.legacy import LegacyMemoryReader
from service.memory_service import MemoryService


def _write_legacy_memory(tmp_path, name: str = "learning-style") -> None:
    directory = tmp_path / ".bobodan" / "memory"
    directory.mkdir(parents=True)
    (directory / f"{name}.md").write_text(
        "---\n"
        f"name: {name}\n"
        "type: feedback\n"
        "description: 旧版偏好\n"
        "created: 2026-01-01\n"
        "---\n\n"
        "喜欢先看具体例子。",
        encoding="utf-8",
    )


def test_legacy_reader_parses_without_writing(tmp_path):
    _write_legacy_memory(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    entries = LegacyMemoryReader(str(tmp_path)).list_entries()

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert len(entries) == 1
    assert entries[0].content == "喜欢先看具体例子。"
    assert before == after


def test_legacy_preview_and_import_create_review_candidate(tmp_path):
    _write_legacy_memory(tmp_path)
    service = MemoryService(
        str(tmp_path),
        home=str(tmp_path / "home"),
        legacy_workspace=str(tmp_path),
    )

    preview = service.legacy_preview()
    imported = service.import_legacy([{
        "name": "learning-style",
        "scope": "global",
        "kind": "learning_strategy",
    }])

    assert preview["entries"][0]["name"] == "learning-style"
    assert len(imported["created"]) == 1
    assert service.overview()["knowledge_count"] == 0
    assert service.overview()["pending_candidate_count"] == 1


def test_legacy_daily_files_are_previewed_only(tmp_path):
    daily = tmp_path / ".bobodan" / "daily"
    daily.mkdir(parents=True)
    (daily / "2026-07-27.md").write_text("旧记录", encoding="utf-8")

    preview = MemoryService(str(tmp_path)).legacy_preview()

    assert preview["daily_files"] == ["2026-07-27.md"]
