"""Tests for RAG embedding settings, diagnostics, backfill, and hit-testing API."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from providers.catalog import catalog_path
from service.library_service import LibraryService
from web.backend.app import create_app
from web.backend.deps import reset_dependency_caches


@pytest.fixture
def rag_client(tmp_path, monkeypatch):
    home = tmp_path / "home"
    lib_root = tmp_path / "vault"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
llm:
  default_provider: deepseek
rag:
  embedding_backend: auto
  embedding_preset: zhipu
  embedding_dim: 0
session:
  save_dir: .session
mcp:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOBODAN_HOME", str(home))
    monkeypatch.setenv("BOBODAN_CONFIG", str(config_path))
    monkeypatch.setenv("BOBODAN_WORKSPACE", str(lib_root))
    for env_var in ("SILICONFLOW_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "ZHIPU_API_KEY", "ZHIPUAI_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)

    LibraryService(str(home)).initialize(str(lib_root), name="Study")
    inbox = lib_root / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "greedy.md").write_text("# 贪心算法\n\n每一步都选择当前局部最优解，并用交换论证证明全局最优。", encoding="utf-8")
    (inbox / "dp.md").write_text("# 动态规划\n\n通过重叠子问题与最优子结构把问题拆解后记忆化求解。", encoding="utf-8")

    from obsidian.sync import sync_sources

    sync_sources(workspace=str(lib_root), vault_path=str(lib_root), course_dir=str(lib_root / "raw"), mode="full")
    reset_dependency_caches()
    try:
        with TestClient(create_app()) as client:
            client.workspace = lib_root
            client.home = home
            client.config_path = config_path
            yield client
    finally:
        reset_dependency_caches()


def test_rag_settings_initial_status_and_provider_capabilities(rag_client):
    rag = rag_client.get("/api/settings/rag").json()
    assert rag["ok"] is True
    assert rag["status"]["knowledge_ready"] is True
    assert rag["status"]["effective_mode"] == "fts_only"
    assert rag["status"]["vector_stats"]["documents"] == 2
    assert rag["status"]["vector_stats"]["vector_indexed"] == 0
    assert rag["config"]["preset"] == "siliconflow"

    by_name = {item["name"]: item for item in rag["reusable_providers"]}
    assert by_name["deepseek"]["supports_embedding"] is False
    assert by_name["siliconflow"]["supports_embedding"] is True
    assert any(m["id"] == "BAAI/bge-m3" for m in by_name["siliconflow"]["embedding_models"])

    status = rag_client.get("/api/settings/status").json()
    assert status["retrieval"]["effective_mode"] == "fts_only"
    assert status["retrieval"]["documents"] == 2


def test_save_rag_settings_persists_to_provider_json_never_leaks_key(rag_client):
    res = rag_client.put("/api/settings/rag", json={
        "mode": "custom",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "api_key": "sk-secret-embedding-key-123456",
        "dim": 1024,
    })
    assert res.status_code == 200
    payload = res.json()
    assert "sk-secret-embedding-key-123456" not in json.dumps(payload, ensure_ascii=False)
    assert "sk-secret-embedding-key-123456" not in rag_client.config_path.read_text(encoding="utf-8")
    assert payload["config"]["has_api_key"] is True
    assert payload["config"]["api_key_source"] == "saved"
    assert payload["status"]["embedding_available"] is True
    assert payload["status"]["needs_backfill"] is True

    # Blank key to a DIFFERENT host must NOT reuse saved key
    other = rag_client.put("/api/settings/rag", json={
        "mode": "custom",
        "preset": "",
        "base_url": "https://other.invalid/v1",
        "model": "custom-embed",
        "api_key": "",
    }).json()
    assert other["config"]["has_api_key"] is False
    stored = json.loads(Path(catalog_path()).read_text(encoding="utf-8"))
    assert stored["embedding"]["api_key"] == ""


def test_rag_embedding_test_endpoint_success_and_redacts_errors(rag_client, monkeypatch):
    orig_post = httpx.Client.post

    def fake_ok(self, url, **kwargs):
        if not str(url).endswith("/embeddings"):
            return orig_post(self, url, **kwargs)
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={"data": [{"index": i, "embedding": [0.1] * 4} for i in range(len(inputs))]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_ok)
    ok_res = rag_client.post("/api/settings/rag/test", json={
        "mode": "custom",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "api_key": "sk-live-secret-999999",
    })
    assert ok_res.status_code == 200
    body = ok_res.json()
    assert body["ok"] is True
    assert body["dim"] == 4
    assert body["model"] == "BAAI/bge-m3"

    # Simulate an upstream echoing the secret back on 401
    def fake_401(self, url, **kwargs):
        if not str(url).endswith("/embeddings"):
            return orig_post(self, url, **kwargs)
        auth = kwargs.get("headers", {}).get("Authorization", "")
        req = httpx.Request("POST", url)
        return httpx.Response(401, json={"error": f"bad token {auth}"}, request=req)

    monkeypatch.setattr(httpx.Client, "post", fake_401)
    fail_res = rag_client.post("/api/settings/rag/test", json={
        "mode": "custom",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "api_key": "sk-live-secret-999999",
    })
    assert fail_res.status_code == 409
    assert "sk-live-secret-999999" not in fail_res.text


def test_rag_backfill_rebuild_and_search_test_end_to_end(rag_client, monkeypatch):
    orig_post = httpx.Client.post

    def fake_embed_post(self, url, **kwargs):
        if not str(url).endswith("/embeddings"):
            return orig_post(self, url, **kwargs)
        inputs = kwargs["json"]["input"]
        model = kwargs["json"]["model"]
        dim = 6 if model == "Qwen/Qwen3-Embedding-8B" else 4
        vectors = []
        for idx, text in enumerate(inputs):
            base = 0.9 if ("贪心" in text or "最优" in text) else 0.1
            vectors.append({"index": idx, "embedding": [base] * dim})
        return httpx.Response(200, json={"data": vectors}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", fake_embed_post)
    rag_client.put("/api/settings/rag", json={
        "mode": "custom",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "api_key": "sk-backfill-key",
        "dim": 4,
    })

    bf = rag_client.post("/api/settings/rag/backfill", json={"rebuild": False})
    assert bf.status_code == 200
    bf_data = bf.json()
    assert bf_data["result"]["backfilled"] == 2
    assert bf_data["result"]["dim"] == 4
    assert bf_data["rag"]["status"]["effective_mode"] == "hybrid"
    assert bf_data["rag"]["status"]["needs_backfill"] is False

    hit_res = rag_client.post("/api/settings/rag/search-test", json={"query": "局部最优", "top_k": 5})
    assert hit_res.status_code == 200
    hit_data = hit_res.json()
    assert hit_data["retrieval_mode"] == "hybrid"
    assert hit_data["semantic_available"] is True
    assert hit_data["results"]
    assert any("vector" in item["retrievers"] for item in hit_data["results"])

    # Switching model marks signature mismatch until rebuilt
    switched = rag_client.put("/api/settings/rag", json={
        "mode": "custom",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-Embedding-8B",
        "api_key": "",
        "dim": 6,
    }).json()
    assert switched["status"]["needs_rebuild"] is True
    assert switched["status"]["effective_mode"] == "fts_only"

    rebuilt = rag_client.post("/api/settings/rag/backfill", json={"rebuild": True}).json()
    assert rebuilt["result"]["rebuilt"] is True
    assert rebuilt["result"]["dim"] == 6
    assert rebuilt["rag"]["status"]["effective_mode"] == "hybrid"
    assert rebuilt["rag"]["status"]["needs_rebuild"] is False


def test_rag_settings_and_search_test_respect_library_header(rag_client):
    from obsidian.sync import sync_sources

    lib2_root = rag_client.workspace.parent / "other-vault"
    second = LibraryService(str(rag_client.home)).initialize(str(lib2_root), name="Physics", activate=False)
    inbox2 = lib2_root / "raw" / "inbox"
    inbox2.mkdir(parents=True, exist_ok=True)
    (inbox2 / "quantum.md").write_text("# 量子力学\n\n波函数坍缩与薛定谔方程描述微观粒子的演化。", encoding="utf-8")
    sync_sources(workspace=str(lib2_root), vault_path=str(lib2_root), course_dir=str(lib2_root / "raw"), mode="full")

    headers = {"X-Bobodan-Library-ID": second["library_id"]}
    rag2 = rag_client.get("/api/settings/rag", headers=headers).json()
    assert rag2["status"]["vector_stats"]["documents"] == 1

    # Active library Study has 2 docs (not 1) and does NOT contain 薛定谔方程
    rag1 = rag_client.get("/api/settings/rag").json()
    assert rag1["status"]["vector_stats"]["documents"] == 2

    search2 = rag_client.post("/api/settings/rag/search-test", headers=headers, json={"query": "薛定谔方程"}).json()
    assert search2["results"]
    assert all("quantum" in item["source"] for item in search2["results"])

    search1 = rag_client.post("/api/settings/rag/search-test", json={"query": "薛定谔方程"}).json()
    assert not any("quantum" in item["source"] for item in search1["results"])
