"""P5G.0: sync registers zero-chunk documents with extraction status.

A scanned PDF has no text layer: it must still appear in the Library
(registered as a document) with extraction_status "empty" and zero chunks,
instead of being silently skipped.
"""

import os

import pytest

from obsidian.sync import sync_sources
from rag.sqlite_store import KBSQLiteStore
from service.library_service import LibraryService


def _write_blank_pdf(path) -> None:
    """A structurally valid PDF with no text layer (image-only / scanned)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as handle:
        writer.write(handle)


@pytest.fixture
def portable_library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def test_scanned_pdf_is_registered_as_empty(portable_library, monkeypatch):
    # Embedding/Qdrant are optional for sync; keep the test hermetic.
    monkeypatch.setattr("rag.qdrant_store.QdrantStore", pytest.importorskip("unittest.mock").MagicMock())
    monkeypatch.setattr("rag.embedding_service.EmbeddingService", lambda *a, **k: type(
        "Embedding", (), {"is_available": lambda self: False}
    )())

    scanned = portable_library / "raw" / "inbox" / "scanned.pdf"
    _write_blank_pdf(scanned)

    summary = sync_sources(
        workspace=str(portable_library),
        vault_path=str(portable_library),
        course_dir=str(portable_library / "raw"),
        mode="full",
    )

    # The scanned PDF is counted as empty in the sync summary.
    assert summary.extraction_counts.get("empty", 0) == 1
    assert summary.extraction_counts.get("error", 0) == 0

    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        documents = store.list_documents()
    finally:
        store.close()

    pdf_docs = [d for d in documents if d["source"].endswith("scanned.pdf")]
    assert len(pdf_docs) == 1, f"scanned.pdf should be registered, got {documents}"
    doc = pdf_docs[0]
    assert doc["title"] == "scanned"
    assert doc["extraction_status"] == "empty"
    assert doc["extraction_total_units"] == 1
    assert doc["extraction_extracted_units"] == 0
    assert doc["extraction_empty_units"] == 1

    # The scanned PDF must not produce any searchable chunks.
    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        chunks = store.get_chunks_by_document(doc["id"])
        report = store.get_extraction_report(doc["id"])
    finally:
        store.close()
    assert len(chunks) == 0
    assert report is not None
    assert report["status"] == "empty"
    assert "scanned_or_empty_pages" in report["warnings"]


def test_text_pdf_is_registered_as_complete(portable_library, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr("rag.embedding_service.EmbeddingService", lambda *a, **k: type(
        "Embedding", (), {"is_available": lambda self: False}
    )())

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject({NameObject("/F1"): DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Real text page) Tj ET")
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Contents")] = writer._add_object(stream)
    page[NameObject("/Resources")] = writer._add_object(
        DictionaryObject({NameObject("/Font"): font})
    )
    writer.add_page(page)
    with open(portable_library / "raw" / "inbox" / "text.pdf", "wb") as handle:
        writer.write(handle)

    sync_sources(
        workspace=str(portable_library),
        vault_path=str(portable_library),
        course_dir=str(portable_library / "raw"),
        mode="full",
    )

    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        documents = store.list_documents()
        pdf_docs = [d for d in documents if d["source"].endswith("text.pdf")]
        assert len(pdf_docs) == 1
        assert pdf_docs[0]["extraction_status"] == "complete"
        assert pdf_docs[0]["extraction_extracted_units"] == 1
        chunks = store.get_chunks_by_document(pdf_docs[0]["id"])
    finally:
        store.close()

    assert len(chunks) > 0
