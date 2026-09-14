"""P1-22: grep cannot read PDF/Office bytes, and used to fail silently."""

from rag.grep_retriever import GrepRetriever
from rag.schema import DocumentHit


def _pdf_bytes() -> bytes:
    """Real PDFs carry NUL bytes early; that is what the sniffing rule looks for."""
    return b"%PDF-1.7\n" + b"\x00\x00" + b"\x00" * 512


def test_binary_documents_are_skipped_and_reported(tmp_path):
    """“原文定位” was a no-op on PDF/Word and said nothing about it, so the
    model could conclude the material does not contain the answer."""
    (tmp_path / "notes.md").write_text("Dijkstra 不能处理负权边", encoding="utf-8")
    (tmp_path / "slides.pdf").write_bytes(_pdf_bytes())

    retriever = GrepRetriever(str(tmp_path))
    documents = [
        DocumentHit(document_id="d1", source="notes.md", title="notes"),
        DocumentHit(document_id="d2", source="slides.pdf", title="slides"),
    ]
    stats: dict = {}

    hits = retriever.search("Dijkstra 不能处理负权边", documents=documents, stats=stats)

    assert hits, "the text document must still match"
    assert stats["binary_skipped"] == 1
    assert stats["binary_sources"] == ["slides.pdf"]


def test_rag_search_warns_the_model_about_unreadable_material(tmp_path, monkeypatch):
    """The audit point: an empty result must not read as “the material does not
    say it” when the material was a PDF nobody could open."""
    import importlib

    from service import kb_service

    # `from tools import rag_search` resolves to the re-exported function, so the
    # module has to be loaded by name.
    tool_module = importlib.import_module("tools.rag_search")

    class _FakeService:
        def __init__(self, _workspace):
            pass

        def search(self, **_kwargs):
            return {
                "ok": True,
                "results": [],
                "retrieval_mode": "directory_grep",
                "grep_unreadable": 2,
                "grep_unreadable_sources": ["slides.pdf", "deck.pptx"],
            }

    monkeypatch.setattr(kb_service, "KBService", _FakeService)

    result = tool_module.rag_search("负权边", workspace=str(tmp_path))

    assert result.ok
    assert "无法做原文定位" in result.content
    assert "slides.pdf" in result.content
    assert result.data["grep_unreadable"] == 2

def test_text_documents_are_not_flagged(tmp_path):
    (tmp_path / "notes.md").write_text("Dijkstra 不能处理负权边", encoding="utf-8")
    retriever = GrepRetriever(str(tmp_path))
    stats: dict = {}

    retriever.search(
        "Dijkstra",
        documents=[DocumentHit(document_id="d1", source="notes.md", title="notes")],
        stats=stats,
    )

    assert stats.get("binary_skipped", 0) == 0
