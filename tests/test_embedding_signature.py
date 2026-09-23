"""G2: vectors must not outlive the model that produced them."""

from __future__ import annotations

import os

import yaml

from rag.embedding_signature import (
    SIGNATURE_FILENAME,
    mismatch_reason,
    read_signature,
    signature_path,
    write_signature,
)

INFO = {"name": "openai_compat", "model": "embedding-3", "dim": 2048}


def test_a_matching_signature_is_not_a_mismatch(tmp_path):
    workspace = str(tmp_path)
    write_signature(workspace, INFO)

    assert read_signature(workspace)["model"] == "embedding-3"
    assert mismatch_reason(workspace, INFO) is None


def test_a_model_change_is_reported_with_both_sides(tmp_path):
    workspace = str(tmp_path)
    write_signature(workspace, INFO)

    reason = mismatch_reason(workspace, {"name": "openai_compat", "model": "bge-m3", "dim": 1024})

    assert reason is not None
    assert "model" in reason and "dim" in reason
    assert "embedding-3" in reason and "bge-m3" in reason


def test_no_signature_means_nothing_to_contradict(tmp_path):
    assert mismatch_reason(str(tmp_path), INFO) is None


def test_a_corrupt_signature_is_ignored_not_fatal(tmp_path):
    workspace = str(tmp_path)
    os.makedirs(os.path.dirname(signature_path(workspace)), exist_ok=True)
    with open(signature_path(workspace), "w", encoding="utf-8") as handle:
        handle.write("{not json")

    assert read_signature(workspace) is None
    assert mismatch_reason(workspace, INFO) is None


def test_a_provider_that_cannot_report_a_dimension_cannot_contradict(tmp_path):
    workspace = str(tmp_path)
    write_signature(workspace, INFO)

    assert mismatch_reason(workspace, {"name": "ollama", "model": "x", "dim": None}) is None


class _FakeProvider:
    """Deterministic 4-dim vectors: no network, no vendor."""

    name = "openai_compat"
    model = "fake-model"

    def is_available(self, force_refresh: bool = False) -> bool:
        return True

    def embed(self, texts):
        return [[0.25, 0.5, 0.75, 1.0] for _ in texts]

    def get_model_info(self) -> dict:
        return {"name": self.name, "model": self.model, "dim": 4}


def test_sync_records_a_signature_and_a_stale_one_disables_semantic_search(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "rag.embedding_service.create_embedding_provider",
        lambda config=None: _FakeProvider(),
    )
    config = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    workspace = str(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "# 向量检索\n\n" + "向量检索把文本编码成向量，再按相似度取最近的片段。" * 20,
        encoding="utf-8",
    )

    from obsidian.sync import sync_sources

    summary = sync_sources(workspace, str(vault), config=config)
    assert summary.chunk_count >= 1

    stored = read_signature(workspace)
    assert stored is not None, "sync must record which model built the vectors"
    assert stored["model"] == "fake-model" and stored["dim"] == 4

    from rag.retriever import clear_retrieval_cache, search_index_with_status

    clear_retrieval_cache(workspace)
    _hits, status = search_index_with_status(workspace, "向量检索", top_k=3, config=config, mode="hybrid")
    assert status.get("semantic_available") is True, status

    # Someone switched models without rebuilding: the vectors are now foreign.
    write_signature(workspace, {"name": "openai_compat", "model": "another-model", "dim": 4})
    clear_retrieval_cache(workspace)
    _hits, stale = search_index_with_status(workspace, "向量检索", top_k=3, config=config, mode="hybrid")

    assert stale.get("semantic_available") is False, stale
