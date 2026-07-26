from rag.chunker import TextChunk, chunk_text
from rag.vector_store import LocalVectorStore


def test_chunk_markdown_text():
    text = "# Dijkstra\n\nShortest path algorithm."
    chunks = chunk_text(text, source="note.md", metadata={"course": "数据结构"}, max_chars=80)

    assert chunks
    assert chunks[0].source == "note.md"
    assert "Shortest path" in chunks[0].text
    assert chunks[0].metadata["course"] == "数据结构"


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
