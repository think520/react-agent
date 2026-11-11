"""QA-LIVE-01：真实后端核心闭环门禁。

只替换模型（``ScriptedProvider``），其余全部是真的：FastAPI 路由与中间件、资料库注册表、
异步导入线程、SQLite / FTS5、出题与批改服务、掌握度契约、复习队列。

为什么要有这一层：E6.2 合入时 1877 条单元测试全绿，复查真实数据才发现旧库迁移会崩、
多概念题证据互相覆盖 —— 单元测试各自用空库、各自 mock 邻居，恰好绕开了「上一步的真实
产出就是下一步的输入」这个前提。这里把导入 → 检索 → 出题 → 作答 → 复习 → 重启串成一条线，
每一步只吃上一步通过 HTTP 真实返回的数据。
"""

from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from providers.factory import ProviderFactory
from rag.retriever import clear_retrieval_cache
from web.backend.app import create_app
from web.backend.deps import reset_dependency_caches
from web.backend.routers.kb import _import_registry_for_tests

MATERIAL = """# 最短路径

## Dijkstra 算法

Dijkstra 算法用于求解非负权图的单源最短路径。它采用贪心策略：每一轮从尚未确定的顶点中
选出距离源点最近的一个，把它标记为已确定，再用它松弛相邻顶点的距离。

## 负权边

Dijkstra 算法不能处理负权边，因为一旦顶点被确定就不会再更新；存在负权边时，
需要改用 Bellman-Ford 算法。
"""

CONCEPT = "Dijkstra 算法"

GENERATED = [
    {
        "type": "single_choice",
        "question": "Dijkstra 算法每一轮选择顶点时采用什么策略？",
        "options": ["A. 分治", "B. 贪心", "C. 动态规划", "D. 回溯"],
        "answer": "B",
        "explanation": "每一轮选出距离源点最近的未确定顶点。",
        "concepts": [CONCEPT],
        "difficulty": "easy",
        "source_ids": ["S1"],
    },
    {
        "type": "short_answer",
        "question": "为什么 Dijkstra 算法不能处理负权边？",
        "options": [],
        "answer": "顶点一旦确定就不再更新，负权边会让已确定的距离失效。",
        "explanation": "负权边场景应改用 Bellman-Ford。",
        "concepts": [CONCEPT],
        "difficulty": "medium",
        "source_ids": ["S1"],
    },
]

CONFIG = """
llm:
  default_provider: scripted
  providers:
    scripted:
      type: deepseek
      api_key_env: SCRIPTED_API_KEY
      model: scripted-model
agent:
  timeout: 30
  max_retries: 0
session:
  save_dir: .session
  max_messages: 20
mcp:
  enabled: false
rag:
  embedding_backend: local
""".strip()


@pytest.fixture
def live(tmp_path, monkeypatch, scripted_provider):
    """真实 app + 临时资料库；模型是唯一的替身。"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setenv("BOBODAN_CONFIG", str(config_path))
    monkeypatch.setenv("BOBODAN_WORKSPACE", str(tmp_path / "default-workspace"))
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SCRIPTED_API_KEY", "unused")
    # 所有服务（出题、批改、对话、概念提取）最终都走这一个工厂。
    monkeypatch.setattr(ProviderFactory, "create", staticmethod(lambda *a, **k: scripted_provider))
    reset_dependency_caches()

    parent = tmp_path / "libraries"
    parent.mkdir()
    state = {"tmp": tmp_path, "parent": parent, "provider": scripted_provider}
    try:
        yield state
    finally:
        _import_registry_for_tests().clear()
        clear_retrieval_cache()
        reset_dependency_caches()


def _client() -> TestClient:
    """每次都新建 app —— 第二次调用就是一次「重启」。"""
    reset_dependency_caches()
    clear_retrieval_cache()
    return TestClient(create_app())


def _ok(response, status: int = 200) -> dict:
    assert response.status_code == status, f"{response.request.method} {response.request.url}: {response.status_code} {response.text}"
    return response.json()


def _wait_import(client, headers, import_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = _ok(client.get(f"/api/kb/imports/{import_id}", headers=headers))
        if snapshot["status"] != "running":
            return snapshot
        time.sleep(0.1)
    raise AssertionError(f"import {import_id} still running after {timeout}s")


def _create_library_and_import(client, live) -> dict:
    library = _ok(client.post("/api/libraries", json={"name": "Live", "parent_path": str(live["parent"])}))
    headers = {"X-Bobodan-Library-ID": library["library_id"]}
    started = _ok(
        client.post(
            "/api/kb/imports",
            headers=headers,
            files=[("files", ("shortest-path.md", MATERIAL.encode("utf-8"), "text/markdown"))],
        ),
        202,
    )
    snapshot = _wait_import(client, headers, started["import_id"])
    assert snapshot["status"] == "completed", snapshot
    assert snapshot["error"] in (None, ""), snapshot
    return headers


def test_core_loop_survives_import_practice_review_and_restart(live):
    provider = live["provider"]
    client = _client()

    # 1. 建库 + 异步导入（后台线程、真实同步与分块）。
    headers = _create_library_and_import(client, live)
    documents = _ok(client.get("/api/kb/documents?collection=material", headers=headers))["documents"]
    assert len(documents) == 1, documents
    document_id = documents[0]["document_id"]

    # 2. 检索：没有向量能力时必须如实报 fts_only，且能命中刚导入的原文。
    search = _ok(client.post("/api/kb/search", headers=headers, json={"query": "负权边", "top_k": 5}))
    assert search["retrieval_mode"] == "fts_only", search
    assert search["results"], search
    assert any("负权边" in (item.get("text") or "") for item in search["results"]), search["results"]

    # 3. 出题：模型只给 source_ids，来源必须由检索结果确定性落到这份资料上。
    provider.queue(json.dumps(GENERATED, ensure_ascii=False))
    generated = _ok(client.post("/api/quiz/questions", headers=headers, json={"query": "Dijkstra 算法", "count": 2}))
    assert generated["status"] == "ready", generated
    assert generated["count"] == 2, generated
    question_ids = generated["question_ids"]
    for question in generated["questions"]:
        sources = json.dumps(question, ensure_ascii=False)
        assert document_id in sources, f"question lost its source: {question}"

    by_type = {q["type"]: q for q in generated["questions"]}
    choice_id = by_type["single_choice"]["id"]
    short_id = by_type["short_answer"]["id"]

    # 4. 练习：选择题确定性批改，简答题走模型批改。
    session = _ok(client.post("/api/quiz/sessions", headers=headers, json={"count": 2, "question_ids": question_ids}))
    session_id = session["practice_session_id"]
    calls_before = provider.call_count

    first = _ok(client.post("/api/quiz/answers", headers=headers, json={
        "practice_session_id": session_id, "question_id": choice_id, "answer": "B",
    }))
    assert first["is_correct"] is True, first
    assert provider.call_count == calls_before, "single choice must not call the model"

    # 同一题再交一次：只算一条证据，不推进调度。
    again = _ok(client.post("/api/quiz/answers", headers=headers, json={
        "practice_session_id": session_id, "question_id": choice_id, "answer": "B",
    }))
    assert again["is_correct"] is True, again

    provider.queue(json.dumps({"verdict": "incorrect", "feedback": "没有说明已确定顶点不再更新。"}, ensure_ascii=False))
    second = _ok(client.post("/api/quiz/answers", headers=headers, json={
        "practice_session_id": session_id, "question_id": short_id, "answer": "因为它太慢了",
    }))
    assert second["is_correct"] is False, second
    assert second["verdict"] == "incorrect", second

    progress = _ok(client.get("/api/learning/progress", headers=headers, params={"concept": CONCEPT}))
    assert progress["status_source"] == "history", progress
    assert progress["status"] == "needs_review", progress
    assert progress["attempts_total"] == 2, f"duplicate submit must not add evidence: {progress}"
    assert progress["review_count"] == 2, f"duplicate submit must not advance SM-2: {progress}"

    queue = _ok(client.get("/api/learning/review-queue", headers=headers))
    wrong_ids = {item.get("question_id") for item in queue["wrong_answers"]}
    assert short_id in wrong_ids, queue["wrong_answers"]
    assert choice_id not in wrong_ids, queue["wrong_answers"]

    state = _ok(client.get(f"/api/quiz/sessions/{session_id}", headers=headers))
    assert state["progress"]["answered"] == 2, state["progress"]
    assert state["progress"]["correct"] == 1, state["progress"]
    assert state["progress"]["wrong"] == 1, state["progress"]

    # 5. 重启：新 app、清掉所有缓存，数据必须从磁盘原样读回来。
    client.close()
    restarted = _client()
    after = _ok(restarted.get("/api/learning/progress", headers=headers, params={"concept": CONCEPT}))
    for key in ("status", "status_source", "attempts_total", "review_count", "next_review", "mastery"):
        assert after[key] == progress[key], f"{key} changed across restart: {progress[key]!r} -> {after[key]!r}"

    restored = _ok(restarted.get(f"/api/quiz/sessions/{session_id}", headers=headers))
    assert restored["progress"] == state["progress"], (state["progress"], restored["progress"])
    queue_after = _ok(restarted.get("/api/learning/review-queue", headers=headers))
    assert short_id in {item.get("question_id") for item in queue_after["wrong_answers"]}, queue_after

    search_after = _ok(restarted.post("/api/kb/search", headers=headers, json={"query": "负权边", "top_k": 5}))
    assert search_after["retrieval_mode"] == "fts_only", search_after
    assert search_after["results"], search_after
    restarted.close()


def test_grading_failure_is_unavailable_not_wrong(live):
    """批改两次都解析失败 → grading_unavailable，不得记为答错、不得写掌握度证据。"""
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)

    provider.queue(json.dumps(GENERATED, ensure_ascii=False))
    generated = _ok(client.post("/api/quiz/questions", headers=headers, json={"query": "Dijkstra 算法", "count": 2}))
    short_id = next(q["id"] for q in generated["questions"] if q["type"] == "short_answer")
    session = _ok(client.post("/api/quiz/sessions", headers=headers, json={"count": 1, "question_ids": [short_id]}))

    provider.queue("这不是 JSON", "还是不是 JSON")
    response = client.post("/api/quiz/answers", headers=headers, json={
        "practice_session_id": session["practice_session_id"], "question_id": short_id, "answer": "任意答案",
    })
    assert response.status_code == 503, response.text
    assert "grading_unavailable" in response.text, response.text

    progress = client.get("/api/learning/progress", headers=headers, params={"concept": CONCEPT})
    if progress.status_code == 200:
        assert progress.json().get("attempts_total", 0) == 0, progress.json()

    queue = _ok(client.get("/api/learning/review-queue", headers=headers))
    assert short_id not in {item.get("question_id") for item in queue["wrong_answers"]}, queue
    client.close()


def test_library_context_does_not_leak_across_libraries(live):
    """资料库请求只读自己的资料、练习与学习事件。"""
    provider = live["provider"]
    client = _client()
    headers_a = _create_library_and_import(client, live)

    provider.queue(json.dumps(GENERATED[:1], ensure_ascii=False))
    generated = _ok(client.post("/api/quiz/questions", headers=headers_a, json={"query": "Dijkstra 算法", "count": 1}))
    question_id = generated["question_ids"][0]
    session = _ok(client.post("/api/quiz/sessions", headers=headers_a, json={"count": 1, "question_ids": [question_id]}))
    _ok(client.post("/api/quiz/answers", headers=headers_a, json={
        "practice_session_id": session["practice_session_id"], "question_id": question_id, "answer": "A",
    }))

    library_b = _ok(client.post("/api/libraries", json={"name": "Other", "parent_path": str(live["parent"])}))
    headers_b = {"X-Bobodan-Library-ID": library_b["library_id"]}

    assert _ok(client.get("/api/kb/documents?collection=material", headers=headers_b))["documents"] == []
    # 空库没有索引：契约是 unavailable + 原因，而不是请求错误。
    search_b = _ok(client.post("/api/kb/search", headers=headers_b, json={"query": "负权边", "top_k": 5}))
    assert search_b["results"] == [], search_b
    assert search_b["retrieval_mode"] == "unavailable", search_b
    assert search_b["semantic_reason"]["action"], search_b
    queue_b = _ok(client.get("/api/learning/review-queue", headers=headers_b))
    assert not queue_b["wrong_answers"], queue_b
    assert not queue_b["due_concepts"], queue_b

    # A 的数据仍然在：切库不是清库。
    queue_a = _ok(client.get("/api/learning/review-queue", headers=headers_a))
    assert question_id in {item.get("question_id") for item in queue_a["wrong_answers"]}, queue_a
    client.close()


# --- W2-EVID-01：引用门禁在真实聊天链路上的反例验收 ---------------------------------


def _sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.split("\n\n"):
        name, data = "", None
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                except ValueError:
                    data = None  # 坏帧容忍
        if name and isinstance(data, dict):
            events.append((name, data))
    return events


def _chat(client, headers, message: str) -> tuple[str, list[tuple[str, dict]]]:
    response = client.post("/api/chat/runs", headers=headers, json={
        "message": message, "save": False, "memory_enabled": False,
    })
    assert response.status_code == 200, response.text
    events = _sse(response.text)
    answer = "".join(data.get("content", "") for name, data in events if name == "message_delta" and data.get("call_role") != "narration")
    return answer, events


def _chunk_label(client, headers, query: str) -> str:
    from rag.citations import cite_label

    hits = _ok(client.post("/api/kb/search", headers=headers, json={"query": query, "top_k": 5}))["results"]
    assert hits, query
    return cite_label(hits[0]["chunk_id"])


def test_a_real_citation_reaches_the_user_with_its_source(live):
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)
    label = _chunk_label(client, headers, "负权边")

    provider.queue(
        {"tool": "rag_search", "args": {"query": "负权边"}},
        f"Dijkstra 不能处理负权边 [{label}]。",
    )
    answer, events = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？")

    assert f"[{label}]" in answer, answer
    citations = [data["attribution"] for name, data in events if name == "citation"]
    assert citations, events
    labels = {source.get("cite_label") for source in citations[-1]["sources"]}
    assert label in labels, "the cited label must resolve to a visible source chip"
    # 模型拿到的工具结果里就是这个标签 —— 不是让它从位置编号去猜。
    tool_messages = [m for m in provider.requests[-1]["messages"] if m.get("role") == "tool"]
    assert any(f"[{label}]" in str(m.get("content")) for m in tool_messages)
    client.close()


def test_a_fabricated_citation_is_rewritten_and_never_shown(live):
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)
    label = _chunk_label(client, headers, "负权边")

    provider.queue(
        {"tool": "rag_search", "args": {"query": "负权边"}},
        "Dijkstra 支持所有负权图 [S1]。",           # 伪造引用 + 与资料矛盾
        f"Dijkstra 不能处理负权边 [{label}]。",     # 被门禁要求重写后
    )
    answer, _ = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？")

    assert "[S1]" not in answer, answer
    assert f"[{label}]" in answer, answer
    correction = [m for m in provider.requests[-1]["messages"] if m.get("role") == "system" and "[S1]" in str(m.get("content"))]
    assert correction, "the rewrite must be driven by the runtime gate, not by luck"
    client.close()


def test_a_citation_that_stays_fabricated_is_stripped_with_a_notice(live):
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)

    # 重试预算由 CombinedResponsePolicy 按挂载的策略数共享（既有语义），这里多备几轮，
    # 断言的是「最终一定被剥掉」以及「重写次数有上限」。
    provider.queue(
        {"tool": "rag_search", "args": {"query": "负权边"}},
        *(["Dijkstra 支持所有负权图 [S1]。"] * 6),
    )
    answer, _ = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？")

    assert "[S1]" not in answer, answer
    assert "无法对应本轮资料的引用" in answer, answer
    assert provider.call_count <= 1 + 4, f"rewrites must be bounded, got {provider.call_count} model calls"
    client.close()


def test_a_citation_to_rewritten_material_is_rejected(live):
    """资料更新后，旧片段的标签不再对应任何当前证据（chunk_id 由内容派生）。"""
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)
    stale = _chunk_label(client, headers, "负权边")

    library_root = next(p for p in live["parent"].iterdir() if p.is_dir())
    target = next(library_root.rglob("shortest-path.md"))
    target.write_text(MATERIAL.replace("需要改用 Bellman-Ford 算法", "应当改用 Bellman-Ford 或 SPFA 算法"), encoding="utf-8")
    _ok(client.post(f"/api/libraries/{headers['X-Bobodan-Library-ID']}/sync", headers=headers))
    fresh = _chunk_label(client, headers, "负权边")
    assert fresh != stale, "rewriting the chunk must change its identity"

    provider.queue(
        {"tool": "rag_search", "args": {"query": "负权边"}},
        f"需要改用 Bellman-Ford [{stale}]。",
        f"需要改用 Bellman-Ford 或 SPFA [{fresh}]。",
    )
    answer, _ = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？")
    assert f"[{stale}]" not in answer, answer
    assert f"[{fresh}]" in answer, answer
    client.close()


def test_kb_seed_respects_the_selected_document_scope(live):
    """预检索块会被引用门禁当成本轮证据，所以它必须遵守用户选定的资料范围。"""
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)
    other = MATERIAL.replace("最短路径", "图论杂记").replace("Dijkstra 算法", "Dijkstra 笔记")
    started = _ok(client.post("/api/kb/imports", headers=headers, files=[
        ("files", ("graph-notes.md", other.encode("utf-8"), "text/markdown")),
    ]), 202)
    assert _wait_import(client, headers, started["import_id"])["status"] == "completed"
    documents = _ok(client.get("/api/kb/documents?collection=material", headers=headers))["documents"]
    in_scope = next(item for item in documents if item["source"].endswith("shortest-path.md"))
    out_of_scope = next(item for item in documents if item["source"].endswith("graph-notes.md"))

    provider.queue("好的。")
    response = client.post("/api/chat/runs", headers=headers, json={
        "message": "为什么 Dijkstra 不能处理负权边？", "save": False, "memory_enabled": False,
        "document_ids": [in_scope["document_id"]],
    })
    assert response.status_code == 200, response.text
    sent = json.dumps(provider.requests[0]["messages"], ensure_ascii=False)
    assert "[Knowledge Base Context]" in sent, "seed should be present for a knowledge question"
    assert "图论杂记" not in sent and out_of_scope["document_id"] not in sent, "out-of-scope material leaked into the seed"
    client.close()


def test_an_unpracticed_concept_is_a_404_not_a_generic_failure(live):
    """界面要能区分「还没练过」与「读取失败」：前者是 404 mastery_not_found，不是 400 request_failed。"""
    client = _client()
    headers = _create_library_and_import(client, live)
    response = client.get("/api/learning/progress", headers=headers, params={"concept": "从未练过的概念"})
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "mastery_not_found", response.text
    client.close()
