"""Tests for rag.sqlite_store — SQLite + FTS5 knowledge base storage."""

import json
import pytest
from pathlib import Path

from rag.sqlite_store import KBSQLiteStore, make_chunk_row, chunk_row_to_hit, _build_fts_query


@pytest.fixture
def store(tmp_path):
    """Create a temporary KBSQLiteStore for testing."""
    s = KBSQLiteStore(str(tmp_path))
    s.init_db()
    yield s
    s.close()


def _add_test_document(store: KBSQLiteStore, doc_id="doc1", source="course/ch01.md"):
    """Helper: insert a test document."""
    store.upsert_document(
        document_id=doc_id,
        source=source,
        content_hash="abc123",
        kind="course_document",
        title="Test Document",
        course="deep-learning",
        tags=["neural-network", "basics"],
        summary="A test document about neural networks.",
    )


def _add_test_chunks(store: KBSQLiteStore, document_id="doc1", source="course/ch01.md"):
    """Helper: insert test chunks for a document."""
    chunks = [
        make_chunk_row(
            chunk_id=f"chunk{i}",
            document_id=document_id,
            source=source,
            chunk_index=i,
            text=text,
            heading_path=["Chapter 1", section],
            heading_text=f"Chapter 1 > {section}",
            heading_level=2,
            section_id=f"ch01/{section.lower().replace(' ', '-')}",
        )
        for i, (text, section) in enumerate([
            ("Neural networks are computational models inspired by biological neurons.", "Introduction"),
            ("The activation function introduces non-linearity into the network.", "Activation Functions"),
            ("Backpropagation is the primary algorithm for training neural networks.", "Training"),
        ])
    ]
    store.insert_chunks(chunks)
    return chunks


# ── Schema init ─────────────────────────────────────────────────────────

class TestInit:
    def test_creates_tables(self, store):
        """init_db creates all required tables."""
        conn = store._get_conn()
        tables = {
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "documents" in tables
        assert "chunks" in tables
        assert "directory_entries" in tables
        assert "retrieval_runs" in tables

    def test_creates_fts5_virtual_tables(self, store):
        conn = store._get_conn()
        tables = {
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts%'").fetchall()
        }
        assert "chunks_fts" in tables
        assert "directory_entries_fts" in tables

    def test_idempotent_init(self, store):
        """Calling init_db twice doesn't error."""
        store.init_db()
        _add_test_document(store)
        assert store.get_document("doc1") is not None


# ── Document CRUD ───────────────────────────────────────────────────────

class TestDocumentCRUD:
    def test_upsert_and_get(self, store):
        _add_test_document(store)
        doc = store.get_document("doc1")
        assert doc is not None
        assert doc["source"] == "course/ch01.md"
        assert doc["title"] == "Test Document"
        assert doc["course"] == "deep-learning"
        assert json.loads(doc["tags_json"]) == ["neural-network", "basics"]
        assert doc["vector_status"] == "pending"

    def test_upsert_updates(self, store):
        _add_test_document(store)
        store.upsert_document(
            document_id="doc1",
            source="course/ch01.md",
            content_hash="def456",
            title="Updated Title",
            vector_status="indexed",
        )
        doc = store.get_document("doc1")
        assert doc["title"] == "Updated Title"
        assert doc["vector_status"] == "indexed"

    def test_delete_cascades(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        assert store.count_chunks() == 3
        store.delete_document("doc1")
        assert store.get_document("doc1") is None
        assert store.count_chunks() == 0

    def test_get_document_id_by_source(self, store):
        _add_test_document(store)
        assert store.get_document_id_by_source("course/ch01.md") == "doc1"
        assert store.get_document_id_by_source("nonexistent") is None

    def test_list_documents(self, store):
        _add_test_document(store, "doc1", "course/ch01.md")
        _add_test_document(store, "doc2", "course/ch02.md")
        docs = store.list_documents()
        assert len(docs) == 2

    def test_list_documents_by_course(self, store):
        _add_test_document(store, "doc1", "course/ch01.md")
        store.upsert_document(
            document_id="doc2", source="other/ch01.md",
            content_hash="x", course="other-course",
        )
        docs = store.list_documents(course="deep-learning")
        assert len(docs) == 1
        assert docs[0]["id"] == "doc1"


# ── Chunk CRUD ──────────────────────────────────────────────────────────

class TestChunkCRUD:
    def test_insert_and_get(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        assert store.count_chunks() == 3
        chunk = store.get_chunk_by_id("chunk0")
        assert chunk is not None
        assert "neural networks" in chunk["text"].lower()

    def test_get_chunks_by_document(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        chunks = store.get_chunks_by_document("doc1")
        assert len(chunks) == 3
        assert chunks[0]["chunk_index"] == 0

    def test_delete_chunks_by_document(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        store.delete_chunks_by_document("doc1")
        assert store.count_chunks() == 0

    def test_cascade_delete_on_document(self, store):
        """Deleting document cascades to chunks via FK."""
        _add_test_document(store)
        _add_test_chunks(store)
        store.delete_document("doc1")
        assert store.get_chunk_by_id("chunk0") is None


# ── FTS5 Search ─────────────────────────────────────────────────────────

class TestFTS5Search:
    def test_keyword_search(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        hits = store.search_fts5("activation function")
        assert len(hits) > 0
        assert any("activation" in h.text.lower() for h in hits)

    def test_exact_term_search(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        hits = store.search_fts5("backpropagation")
        assert len(hits) == 1
        assert "backpropagation" in hits[0].text.lower()

    def test_returns_retrieval_hits(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        hits = store.search_fts5("neural")
        assert len(hits) > 0
        h = hits[0]
        assert h.chunk_id  # has id
        assert h.document_id == "doc1"
        assert h.source == "course/ch01.md"
        assert h.heading_path  # has heading info
        assert "fts5" in h.retrievers

    def test_course_filter(self, store):
        _add_test_document(store, "doc1", "course/ch01.md")
        store.upsert_document(
            document_id="doc2", source="other/ch01.md",
            content_hash="x", course="other-course", title="Other",
        )
        store.insert_chunks([make_chunk_row(
            chunk_id="chunk_other", document_id="doc2", source="other/ch01.md",
            chunk_index=0, text="Activation in other course.",
        )])
        hits = store.search_fts5("activation", course="deep-learning")
        assert all(h.document_id == "doc1" for h in hits)

    def test_empty_query(self, store):
        assert store.search_fts5("") == []
        assert store.search_fts5("   ") == []

    def test_no_results(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        hits = store.search_fts5("quantum computing")
        assert len(hits) == 0


# ── Vector Status ───────────────────────────────────────────────────────

class TestVectorStatus:
    def test_default_pending(self, store):
        _add_test_document(store)
        doc = store.get_document("doc1")
        assert doc["vector_status"] == "pending"

    def test_mark_indexed(self, store):
        _add_test_document(store)
        store.mark_vector_indexed("doc1", "abc123")
        doc = store.get_document("doc1")
        assert doc["vector_status"] == "indexed"
        assert doc["vector_indexed_hash"] == "abc123"
        assert doc["vector_error"] is None

    def test_mark_error(self, store):
        _add_test_document(store)
        store.mark_vector_error("doc1", "connection refused")
        doc = store.get_document("doc1")
        assert doc["vector_status"] == "error"
        assert doc["vector_error"] == "connection refused"

    def test_get_pending(self, store):
        _add_test_document(store, "doc1", "a.md")
        _add_test_document(store, "doc2", "b.md")
        store.mark_vector_indexed("doc1", "hash")
        pending = store.get_pending_vector_documents()
        assert len(pending) == 1
        assert pending[0]["id"] == "doc2"


# ── Directory Entries ───────────────────────────────────────────────────

class TestDirectoryEntries:
    def test_upsert_and_search(self, store):
        _add_test_document(store)
        store.upsert_directory_entry(
            document_id="doc1",
            title="Neural Networks",
            summary="Introduction to neural networks and activation functions.",
            keywords=["neural", "activation", "backpropagation"],
            source="course/ch01.md",
            course="deep-learning",
            chunk_count=3,
        )
        results = store.search_directory("neural")
        assert len(results) > 0
        assert results[0]["title"] == "Neural Networks"

    def test_search_by_keyword(self, store):
        _add_test_document(store)
        store.upsert_directory_entry(
            document_id="doc1",
            title="Deep Learning Basics",
            summary="Covers fundamental concepts.",
            keywords=["ReLU", "sigmoid", "activation"],
            source="course/ch01.md",
            course="deep-learning",
        )
        results = store.search_directory("ReLU")
        assert len(results) > 0

    def test_course_filter(self, store):
        _add_test_document(store, "doc1", "a.md")
        store.upsert_directory_entry(
            document_id="doc1", title="A", source="a.md", course="ml",
        )
        store.upsert_document(
            document_id="doc2", source="b.md", content_hash="x", course="nlp",
        )
        store.upsert_directory_entry(
            document_id="doc2", title="B", source="b.md", course="nlp",
        )
        results = store.search_directory("A", course="ml")
        # Only course=ml results
        assert all(r.get("course") == "ml" for r in results)


# ── Bulk Operations ─────────────────────────────────────────────────────

class TestBulkOps:
    def test_clear_all(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        store.clear_all()
        assert store.count_chunks() == 0
        assert len(store.list_documents()) == 0

    def test_get_stats(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        stats = store.get_stats()
        assert stats["documents"] == 1
        assert stats["chunks"] == 3
        assert stats["vector_pending"] == 1

    def test_rebuild_fts(self, store):
        _add_test_document(store)
        _add_test_chunks(store)
        store.rebuild_fts()
        hits = store.search_fts5("neural")
        assert len(hits) > 0


# ── Helper Functions ────────────────────────────────────────────────────

class TestHelpers:
    def test_make_chunk_row(self):
        row = make_chunk_row(
            chunk_id="c1", document_id="d1", source="test.md",
            chunk_index=0, text="hello world",
            heading_path=["A", "B"], heading_text="A > B",
        )
        assert row["id"] == "c1"
        assert row["heading_path_json"] == '["A", "B"]'
        assert row["text"] == "hello world"

    def test_chunk_row_to_hit(self):
        row = {
            "id": "c1", "document_id": "d1", "source": "test.md",
            "text": "hello", "heading_path_json": '["A"]',
            "heading_text": "A", "heading_level": 1,
            "page_start": 1, "page_end": 2,
            "slide_start": None, "slide_end": None,
            "char_start": None, "char_end": None,
        }
        hit = chunk_row_to_hit(row)
        assert hit.chunk_id == "c1"
        assert hit.heading_path == ["A"]
        assert hit.page_start == 1

    def test_build_fts_query_single_word(self):
        assert _build_fts_query("neural") == '"neural"'

    def test_build_fts_query_multi_word(self):
        q = _build_fts_query("neural network")
        assert "OR" in q
        assert '"neural"' in q
        assert '"network"' in q

    def test_build_fts_query_empty(self):
        assert _build_fts_query("") == ""
        assert _build_fts_query("   ") == ""
