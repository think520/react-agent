import pytest

from rag.chunker import TextChunk, chunk_text
from rag.ingest import load_document
from rag.vector_store import LocalVectorStore


def test_chunk_markdown_document(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("---\ncourse: 数据结构\n---\n\n# Dijkstra\n\nShortest path algorithm.", encoding="utf-8")

    document = load_document(str(path), str(tmp_path))
    chunks = chunk_text(document.text, source=document.source, metadata=document.metadata, max_chars=80)

    assert document.metadata["course"] == "数据结构"
    assert chunks
    assert chunks[0].source == "note.md"
    assert "Shortest path" in chunks[0].text


def test_local_vector_search_is_stable(tmp_path):
    store = LocalVectorStore(str(tmp_path / "rag_index.json"))
    store.replace(
        [
            TextChunk(id="1", source="a.md", text="Dijkstra computes shortest paths in graphs."),
            TextChunk(id="2", source="b.md", text="Binary trees store ordered data."),
        ]
    )

    results = store.search("shortest path graph", top_k=2)

    assert results[0]["source"] == "a.md"
    assert results[0]["score"] > 0


def test_pdf_load_when_pypdf_available(tmp_path):
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        writer.write(f)

    document = load_document(str(path), str(tmp_path))

    assert document.source == "sample.pdf"
    assert document.metadata["source_type"] == "pdf"
