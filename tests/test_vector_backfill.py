"""P1-18: a document imported while embeddings were down must get vectors later."""

from rag.qdrant_store import QdrantStore
from rag.sqlite_store import KBSQLiteStore


class _FakeEmbedding:
    """Stands in for the Ollama client; the stores under test are real."""

    def __init__(self, dim=4, available=True):
        self.dim = dim
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def get_model_info(self):
        return {"dim": self.dim}

    def embed_texts(self, texts):
        self.calls += 1
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


def _seed(workspace: str) -> KBSQLiteStore:
    store = KBSQLiteStore(workspace)
    store.init_db()
    store.upsert_document("doc-1", "course/a.md", "hash-1", title="A", vector_status="pending")
    store.insert_chunks([{
        "id": "chunk-1",
        "document_id": "doc-1",
        "source": "course/a.md",
        "chunk_index": 0,
        "text": "正文",
        "heading_path_json": "[]",
        "heading_text": "",
        "heading_level": 1,
        "section_id": "s1",
        "chunk_index_in_section": 0,
        "page_start": None,
        "page_end": None,
        "slide_start": None,
        "slide_end": None,
        "char_start": 0,
        "char_end": 2,
        "metadata_json": "{}",
    }])
    return store


def test_backfill_indexes_pending_documents(tmp_path):
    from obsidian.sync import backfill_vectors

    workspace = str(tmp_path)
    store = _seed(workspace)
    qdrant = QdrantStore(workspace)
    qdrant.init_collection(4)
    embedding = _FakeEmbedding()

    assert len(store.get_pending_vector_documents()) == 1

    count = backfill_vectors(store, qdrant, embedding, 4)

    assert count == 1
    assert store.get_pending_vector_documents() == []
    assert embedding.calls == 1


def test_backfill_is_a_no_op_without_embeddings(tmp_path):
    from obsidian.sync import backfill_vectors

    workspace = str(tmp_path)
    store = _seed(workspace)
    qdrant = QdrantStore(workspace)

    assert backfill_vectors(store, qdrant, _FakeEmbedding(available=False), None) == 0
    assert len(store.get_pending_vector_documents()) == 1


def test_backfill_records_an_embedding_failure(tmp_path):
    """A failure must be recorded on the document, not left pending silently."""
    from obsidian.sync import backfill_vectors

    workspace = str(tmp_path)
    store = _seed(workspace)
    qdrant = QdrantStore(workspace)
    qdrant.init_collection(4)

    class _Boom(_FakeEmbedding):
        def embed_texts(self, texts):
            raise RuntimeError("ollama down")

    backfill_vectors(store, qdrant, _Boom(), 4)

    assert store.get_document("doc-1")["vector_status"] == "error"
