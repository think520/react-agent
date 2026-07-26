import json
import os
from dataclasses import asdict

from knowledge.documents import DocumentRecord, build_document_records, document_records_to_dict
from knowledge.manifest import load_manifest, save_manifest
from knowledge.import_report import ImportReport, save_import_report, load_import_report
from knowledge.library import build_library_summary, format_library_summary


class FakeNote:
    """Minimal stand-in for a parsed Obsidian note."""
    def __init__(self, title="Test Note", body="body", course=None, chapter=None, tags=None):
        self.title = title
        self.body = body
        self.course = course
        self.chapter = chapter
        self.tags = tags or []


class FakeScannedNote:
    def __init__(self, rel_path="test.md", content_hash="abc123"):
        self.rel_path = rel_path
        self.content_hash = content_hash
        self.note = FakeNote(title="Test Note")


class FakeSourceDocument:
    def __init__(self, source="notes.txt", text="content", content_hash="def456"):
        self.source = source
        self.text = text
        self.content_hash = content_hash
        self.metadata = {"kind": "course_document", "title": "Test Doc"}


def test_build_document_records_from_notes():
    notes = [FakeScannedNote("a.md"), FakeScannedNote("b.md")]
    records = build_document_records(notes=notes)
    assert len(records) == 2
    assert records[0].source == "obsidian/a.md"
    assert records[0].kind == "obsidian_note"
    assert records[0].status == "ok"
    assert records[1].source == "obsidian/b.md"


def test_build_document_records_from_course_docs():
    docs = [FakeSourceDocument("ch1.txt")]
    records = build_document_records(course_docs=docs)
    assert len(records) == 1
    assert records[0].source == "course/ch1.txt"
    assert records[0].kind == "course_document"


def test_build_document_records_mixed():
    notes = [FakeScannedNote("a.md")]
    docs = [FakeSourceDocument("b.txt")]
    records = build_document_records(notes=notes, course_docs=docs)
    assert len(records) == 2


def test_document_records_to_dict():
    records = [DocumentRecord(source="test.md", kind="obsidian_note", title="Test")]
    result = document_records_to_dict(records)
    assert len(result) == 1
    assert result[0]["source"] == "test.md"
    assert result[0]["status"] == "ok"


def test_save_and_load_manifest(tmp_path):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, ".knowledge"))

    records = [
        DocumentRecord(source="obsidian/a.md", kind="obsidian_note", title="A", chunk_count=3),
        DocumentRecord(source="course/b.txt", kind="course_document", title="B", course="Math"),
    ]
    save_manifest(ws, records, {"scanned_files": 2})

    manifest = load_manifest(ws)
    assert manifest["version"] == 1
    assert len(manifest["documents"]) == 2
    assert manifest["documents"][0]["source"] == "obsidian/a.md"
    assert manifest["sync_summary"]["scanned_files"] == 2
    assert manifest["last_sync"] is not None


def test_load_manifest_missing(tmp_path):
    manifest = load_manifest(str(tmp_path))
    assert manifest["version"] == 1
    assert manifest["documents"] == []


def test_save_and_load_import_report(tmp_path):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, ".knowledge"))

    report = ImportReport(
        mode="full",
        scanned_files=10,
        updated_files=8,
        error_files=2,
        chunk_count=50,
        relationship_count=20,
        graph_backend="local",
        errors=[{"source": "bad.md", "error": "parse error"}],
    )
    save_import_report(ws, report)

    loaded = load_import_report(ws)
    assert loaded is not None
    assert loaded.mode == "full"
    assert loaded.scanned_files == 10
    assert loaded.error_files == 2
    assert len(loaded.errors) == 1
    assert loaded.errors[0]["source"] == "bad.md"


def test_load_import_report_missing(tmp_path):
    assert load_import_report(str(tmp_path)) is None


def test_build_library_summary(tmp_path):
    ws = str(tmp_path)
    knowledge_dir = os.path.join(ws, ".knowledge")
    os.makedirs(knowledge_dir)

    # Create manifest
    records = [
        DocumentRecord(source="obsidian/a.md", kind="obsidian_note", title="A",
                       course="OS", chunk_count=3),
        DocumentRecord(source="obsidian/b.md", kind="obsidian_note", title="B",
                       course="OS", chunk_count=2, status="error", error="bad file"),
    ]
    save_manifest(ws, records)

    # A retired graph file may still exist, but summary reads only the reviewed map.
    graph_data = {
        "version": 1,
        "backend": "local",
        "nodes": {
            "Concept:a": {"label": "Concept", "name": "A"},
            "Note:a.md": {"label": "Note", "name": "a.md"},
        },
        "relationships": [
            {"start": "Concept:a", "type": "MENTIONED_IN", "end": "Note:a.md"},
        ],
    }
    with open(os.path.join(knowledge_dir, "graph_store.json"), "w") as f:
        json.dump(graph_data, f)

    from graph.concept_store import ConceptStore

    concept_store = ConceptStore(os.path.join(knowledge_dir, "concept_graph.db"))
    first = concept_store.upsert_concept(name="A", level="core")
    second = concept_store.upsert_concept(name="B", level="detail")
    concept_store.upsert_relationship(
        from_id=first["concept_id"],
        to_id=second["concept_id"],
        rel_type="应用于",
    )

    summary = build_library_summary(ws)
    assert summary.total_files == 2
    assert summary.total_chunks == 5
    assert summary.total_errors == 1
    assert summary.graph_nodes == 2
    assert summary.graph_relationships == 1
    assert summary.graph_backend == "concept_sqlite"
    assert len(summary.courses) == 1
    assert summary.courses[0].name == "OS"
    assert summary.courses[0].error_count == 1


def test_build_library_summary_no_knowledge_dir(tmp_path):
    summary = build_library_summary(str(tmp_path))
    assert summary.total_files == 0
    assert summary.total_chunks == 0
    assert summary.graph_nodes == 0


def test_format_library_summary(tmp_path):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, ".knowledge"))
    records = [
        DocumentRecord(source="obsidian/a.md", kind="obsidian_note", title="A",
                       course="OS", chunk_count=3),
    ]
    save_manifest(ws, records)

    summary = build_library_summary(ws)
    text = format_library_summary(summary)
    assert "1 个文件" in text
    assert "3 个 chunk" in text
    assert "OS" in text


def test_knowledge_status_tool(tmp_path):
    from tools.knowledge_status import knowledge_status

    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, ".knowledge"))

    result = knowledge_status(workspace=ws)
    assert result.ok
    assert "No knowledge base" in result.content or "total_files" in result.data


def test_knowledge_status_tool_no_dir(tmp_path):
    from tools.knowledge_status import knowledge_status

    result = knowledge_status(workspace=str(tmp_path))
    assert not result.ok
    assert "No knowledge base" in result.content
