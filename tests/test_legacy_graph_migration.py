import json

from service.legacy_graph_migration import LegacyGraphMigrationService


def _write_graph(tmp_path):
    directory = tmp_path / ".knowledge"
    directory.mkdir()
    path = directory / "graph_store.json"
    path.write_text(json.dumps({
        "nodes": {
            "Concept:transformer": {"id": "Concept:transformer", "label": "Concept", "name": "Transformer", "properties": {}},
            "Concept:attention": {"id": "Concept:attention", "label": "Concept", "name": "注意力机制", "properties": {"description": "加权聚合信息"}},
            "Memory:style": {"id": "Memory:style", "label": "Memory", "name": "喜欢图示", "properties": {}},
            "Note:lesson": {"id": "Note:lesson", "label": "Note", "name": "lesson.md", "properties": {}},
        },
        "relationships": [{
            "start": "Concept:transformer", "type": "USES", "end": "Concept:attention", "properties": {},
        }],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_preview_classifies_legacy_nodes_without_mutation(tmp_path):
    path = _write_graph(tmp_path)
    service = LegacyGraphMigrationService(str(tmp_path), home=str(tmp_path / "home"))

    preview = service.preview()

    assert preview["detected"] is True
    assert len(preview["concepts"]) == 2
    assert preview["memories"][0]["quality"] == "name_only"
    assert preview["excluded"] == {"Note": 1}
    assert preview["relationships"] == 1
    assert path.exists()


def test_migration_creates_review_candidates_then_archives(tmp_path):
    path = _write_graph(tmp_path)
    service = LegacyGraphMigrationService(str(tmp_path), home=str(tmp_path / "home"))

    result = service.migrate(
        concept_ids=["Concept:transformer", "Concept:attention"],
        memory_ids=["Memory:style"],
        archive=True,
    )

    assert result["ok"] is True
    assert len(result["concept_candidates"]) == 2
    assert result["concept_candidates"][0]["status"] == "pending"
    assert len(result["memory_candidates"]) == 1
    assert not path.exists()
    assert result["archive_path"].endswith(".archived")


def test_graph_memory_covered_by_markdown_is_not_duplicated(tmp_path):
    _write_graph(tmp_path)
    memory_dir = tmp_path / ".bobodan" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "style.md").write_text(
        "---\nname: 喜欢图示\ntype: user\n---\n\n请多画图",
        encoding="utf-8",
    )
    service = LegacyGraphMigrationService(str(tmp_path), home=str(tmp_path / "home"))

    result = service.migrate(concept_ids=[], memory_ids=["Memory:style"], archive=False)

    assert result["memory_candidates"] == []
    assert result["memory_skipped"][0]["reason"] == "covered_by_legacy_memory"


def test_invalid_selection_does_not_archive_or_create_candidates(tmp_path):
    path = _write_graph(tmp_path)
    service = LegacyGraphMigrationService(str(tmp_path), home=str(tmp_path / "home"))

    result = service.migrate(
        concept_ids=["Memory:style", "Concept:missing"],
        memory_ids=[],
        archive=True,
    )

    assert result["ok"] is False
    assert result["invalid_ids"] == ["Memory:style", "Concept:missing"]
    assert path.exists()
    assert not (tmp_path / ".knowledge" / "concept_graph.db").exists()


def test_archive_metadata_failure_restores_source_file(tmp_path, monkeypatch):
    path = _write_graph(tmp_path)
    service = LegacyGraphMigrationService(str(tmp_path), home=str(tmp_path / "home"))
    original_write_text = type(path).write_text

    def fail_metadata_write(self, data, *args, **kwargs):
        if self.name.endswith(".migration.json"):
            raise OSError("disk full")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(type(path), "write_text", fail_metadata_write)
    result = service.migrate(
        concept_ids=["Concept:transformer"],
        memory_ids=[],
        archive=True,
    )

    assert result["ok"] is False
    assert result["code"] == "legacy_archive_failed"
    assert path.exists()
    assert not list(path.parent.glob("graph_store.json*.archived"))
