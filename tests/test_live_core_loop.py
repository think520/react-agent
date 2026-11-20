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


def _chat(client, headers, message: str, *, save: bool = False) -> tuple[str, list[tuple[str, dict]]]:
    response = client.post("/api/chat/runs", headers=headers, json={
        "message": message, "save": save, "memory_enabled": False,
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
        "Dijkstra 支持所有负权图 [Sdeadbe]。",           # 伪造引用 + 与资料矛盾
        f"Dijkstra 不能处理负权边 [{label}]。",     # 被门禁要求重写后
    )
    answer, _ = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？")

    assert "[Sdeadbe]" not in answer, answer
    assert f"[{label}]" in answer, answer
    correction = [m for m in provider.requests[-1]["messages"] if m.get("role") == "system" and "[Sdeadbe]" in str(m.get("content"))]
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
        *(["Dijkstra 支持所有负权图 [Sdeadbe]。"] * 6),
    )
    answer, _ = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？")

    assert "[Sdeadbe]" not in answer, answer
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


def test_a_citation_survives_an_ask_user_pause_and_resume(live):
    """检索 → ask_user 暂停 → 用户作答 → 续跑：续跑后的回答引用暂停前检索到的片段，不能被当成伪造。

    续跑在 AgentLoop 里是一次新 run（tool_history 为空）；2026-11-11 合并前审查发现
    门禁因此会剥掉这些真实标签。现在暂停前那半轮的工具结果也算本轮证据。
    """
    provider = live["provider"]
    client = _client()
    headers = _create_library_and_import(client, live)
    label = _chunk_label(client, headers, "负权边")

    provider.queue(
        {"tool": "rag_search", "args": {"query": "负权边"}},
        {"tool": "ask_user", "args": {"questions": [{"id": "q1", "prompt": "想看证明还是例子？", "options": ["证明", "例子"]}]}},
    )
    response = client.post("/api/chat/runs", headers=headers, json={"message": "为什么 Dijkstra 不能处理负权边？", "memory_enabled": False})
    assert response.status_code == 200, response.text
    events = _sse(response.text)
    chat_session_id = next(data["chat_session_id"] for name, data in events if data.get("chat_session_id"))
    card = next(data["artifact"] for name, data in events if name == "chat_artifact" and data.get("artifact", {}).get("type") == "ask_user")

    answered = client.post(f"/api/chat/interactions/{card['artifact_id']}/answer", headers=headers, json={
        "chat_session_id": chat_session_id, "answers": [{"id": "q1", "answer": "例子"}],
    })
    assert answered.status_code == 200, answered.text

    provider.queue(f"举个例子：负权边会让已确定的顶点失效 [{label}]。")
    resumed = client.post("/api/chat/runs", headers=headers, json={
        "chat_session_id": chat_session_id, "resume_interaction_id": card["artifact_id"], "memory_enabled": False,
    })
    assert resumed.status_code == 200, resumed.text
    answer = "".join(data.get("content", "") for name, data in _sse(resumed.text)
                     if name == "message_delta" and data.get("call_role") != "narration")
    assert f"[{label}]" in answer, answer
    assert "无法对应本轮资料的引用" not in answer, answer
    client.close()


def test_organize_undo_conflict_preserves_new_file_and_keeps_ledger(live):
    """QA-LIVE-01 余项：资料移动后原位出现新文件，撤销必须跳过冲突项、绝不覆盖新文件。"""
    client = _client()
    headers = _create_library_and_import(client, live)
    library_root = next(p for p in live["parent"].iterdir() if p.is_dir())
    loose_name = "loose-dijkstra.md"
    original_disk = library_root / loose_name
    original_disk.write_text(MATERIAL, encoding="utf-8")
    _ok(client.post(f"/api/libraries/{headers['X-Bobodan-Library-ID']}/sync", headers=headers))

    # 通过整理批量接口把根目录散落资料收进新文件夹
    applied = _ok(client.post("/api/kb/organize/apply", headers=headers, json={
        "items": [loose_name],
        "target_folder": "图论讲义",
    }))
    assert len(applied["moved"]) == 1, applied
    batch_id = applied["batch_id"]

    # 用户在原位新建了一份同名新资料
    original_disk.write_text("# 新建同名讲义\n\n绝对不能被撤销覆盖。", encoding="utf-8")

    # 触发一键撤销
    undone = _ok(client.post("/api/kb/organize/undo", headers=headers, json={"batch_id": batch_id}))
    assert undone["restored"] == [], undone
    assert any(item.get("reason") == "target_exists" for item in undone["skipped"]), undone

    # 原位的新文件完好无损，已搬走的旧资料也仍在目标位置，撤销台账保持待处理
    assert "绝对不能被撤销覆盖" in original_disk.read_text(encoding="utf-8")
    assert (library_root / "图论讲义" / loose_name).is_file()
    state = _ok(client.get("/api/kb/organize/state", headers=headers))
    assert state["pending_undo"] is not None
    client.close()


def test_full_backup_and_clean_directory_restore_preserves_records_and_citations(live, monkeypatch):
    """W4-RESTORE-01 + QA-LIVE-01：小库放入资料+引用对话+错题+笔记 → 整库备份（不含密钥）→ 干净目录异地恢复 → 全部可核对。"""
    import shutil
    import zipfile
    from pathlib import Path

    provider = live["provider"]
    client = _client()

    # 1. 建库 + 导入资料
    headers = _create_library_and_import(client, live)
    library_id = headers["X-Bobodan-Library-ID"]
    documents = _ok(client.get("/api/kb/documents?collection=material", headers=headers))["documents"]
    document_id = documents[0]["document_id"]
    detail = _ok(client.get(f"/api/kb/documents/{document_id}", headers=headers))
    chunk_id = detail["sections"][0]["chunk_id"]
    label = _chunk_label(client, headers, "负权边")

    # 2. 带真实引用的对话并落盘
    provider.queue(
        {"tool": "rag_search", "args": {"query": "负权边"}},
        f"Dijkstra 不能处理负权边 [{label}]。",
    )
    answer, events = _chat(client, headers, "为什么 Dijkstra 不能处理负权边？", save=True)
    assert f"[{label}]" in answer
    chat_session_id = next(data["chat_session_id"] for _, data in events if data.get("chat_session_id"))

    # 3. 带原文锚点的笔记 + 全局个人知识 + 偏好 + 本地 API 密钥（密钥绝不能被备份）
    note = _ok(client.post("/api/memory/knowledge", headers=headers, json={
        "scope": "library",
        "kind": "course_insight",
        "title": "Dijkstra 限制笔记",
        "content": "遇到负权边要换 Bellman-Ford。",
        "references": [{"document_id": document_id, "chunk_id": chunk_id, "quote": "Dijkstra 算法不能处理负权边"}],
    }))
    assert note["item"]["id"]
    _ok(client.post("/api/memory/knowledge", headers=headers, json={
        "scope": "global",
        "kind": "goal",
        "title": "算法长期目标",
        "content": "完成图论全部练习。",
    }))
    settings_before = _ok(client.get("/api/settings"))
    _ok(client.patch("/api/settings/preferences", json={
        "revision": settings_before["preferences"]["revision"],
        "patch": {"user": {"display_name": "恢复验收测试者"}},
    }))
    old_home = Path(live["tmp"]) / "home"
    (old_home / "provider.json").write_text(
        json.dumps({"providers": {"deepseek": {"api_key": "sk-live-secret-never-backup"}}}),
        encoding="utf-8",
    )

    # 4. 出题并答错简答题，产生错题、掌握度历史和复习队列
    provider.queue(json.dumps(GENERATED, ensure_ascii=False))
    generated = _ok(client.post("/api/quiz/questions", headers=headers, json={"query": "Dijkstra 算法", "count": 2}))
    short_q = next(q for q in generated["questions"] if q["type"] == "short_answer")
    quiz_session = _ok(client.post("/api/quiz/sessions", headers=headers, json={
        "count": 2, "question_ids": generated["question_ids"],
    }))
    provider.queue(json.dumps({"verdict": "incorrect", "feedback": "缺少贪心失效说明"}, ensure_ascii=False))
    _ok(client.post("/api/quiz/answers", headers=headers, json={
        "practice_session_id": quiz_session["practice_session_id"],
        "question_id": short_q["id"],
        "answer": "不清楚",
    }))

    # 5. 查看备份计划并创建整库备份 + 下载 ZIP
    plan = _ok(client.get("/api/backup/plan?include_global=true", headers=headers))
    assert any(item["name"] == "provider.json" for item in plan["excluded_items"])
    created = _ok(client.post("/api/backup/create", headers=headers, json={"include_global": True}))
    assert created["includes_global"] is True
    assert created["counts"]["materials"] == 1
    assert created["counts"]["questions"] == 2
    downloaded = client.get(f"/api/backup/download/{created['backup_id']}")
    assert downloaded.status_code == 200
    archive_bytes = downloaded.content
    assert b"sk-live-secret-never-backup" not in archive_bytes
    client.close()

    # 6. 关闭缓存句柄、彻底删除旧库原件并切换到全新干净的 BOBODAN_HOME，模拟异地/换机恢复
    import gc

    clear_retrieval_cache()
    reset_dependency_caches()
    gc.collect()
    shutil.rmtree(live["parent"])
    clean_home = Path(live["tmp"]) / "clean-machine-home"
    clean_target = Path(live["tmp"]) / "clean-machine-restored-library"
    monkeypatch.setenv("BOBODAN_HOME", str(clean_home))
    monkeypatch.setenv("BOBODAN_WORKSPACE", str(Path(live["tmp"]) / "clean-default-workspace"))

    fresh = _client()
    assert _ok(fresh.get("/api/libraries"))["libraries"] == []

    # 7. 校验并恢复到干净目录
    verified = _ok(fresh.post(
        "/api/backup/verify",
        files={"file": (created["filename"], archive_bytes, "application/zip")},
    ))
    assert verified["valid"] is True
    assert verified["includes_global"] is True

    restored = _ok(fresh.post(
        "/api/backup/restore",
        data={"target_dir": str(clean_target), "restore_global": "true", "activate": "true"},
        files={"file": (created["filename"], archive_bytes, "application/zip")},
    ))
    restored_lib_id = restored["library"]["library_id"]
    assert restored_lib_id == library_id
    assert not (clean_home / "provider.json").exists(), "API keys must never be restored from backup"
    fresh.close()

    # 8. 再次“重启”后端，逐项核对关键记录、原文锚点、错题回原文、笔记、会话与全局数据
    after_restart = _client()
    restored_headers = {"X-Bobodan-Library-ID": restored_lib_id}

    # 原件与路径重定位
    docs_after = _ok(after_restart.get("/api/kb/documents?collection=material", headers=restored_headers))["documents"]
    assert len(docs_after) == 1
    assert docs_after[0]["document_id"] == document_id
    assert docs_after[0]["has_original"] is True, docs_after[0]
    assert docs_after[0]["relative_path"], docs_after[0]
    raw_resp = after_restart.get(f"/api/kb/documents/{document_id}/raw", headers=restored_headers)
    assert raw_resp.status_code == 200 and "Bellman-Ford" in raw_resp.text

    # 检索正常
    search_after = _ok(after_restart.post("/api/kb/search", headers=restored_headers, json={"query": "负权边", "top_k": 5}))
    assert search_after["results"]

    # 错题仍能点回原文 document_id 与 chunk
    review_after = _ok(after_restart.get("/api/learning/review-queue", headers=restored_headers))
    wrong_questions = review_after.get("wrong_answers") or []
    assert any(q.get("question_id") == short_q["id"] for q in wrong_questions), review_after
    bank_after = _ok(after_restart.get("/api/quiz/bank?state=incorrect", headers=restored_headers))
    bank_wrong = next(q for q in (bank_after.get("items") or bank_after.get("questions") or []) if q["id"] == short_q["id"])
    source_doc_ids = [s.get("document_id") for s in (bank_wrong.get("attribution") or {}).get("sources") or []]
    assert document_id in source_doc_ids, bank_wrong
    doc_back = _ok(after_restart.get(f"/api/kb/documents/{document_id}", headers=restored_headers))
    assert any(sec["chunk_id"] == chunk_id for sec in doc_back["sections"])

    # 掌握度与复习历史保留
    progress_after = _ok(after_restart.get("/api/learning/progress", headers=restored_headers, params={"concept": CONCEPT}))
    assert progress_after["status_source"] == "history"
    assert progress_after["attempts_total"] == 1

    # 笔记锚点、会话与全局偏好/个人知识保留
    notes_after = _ok(after_restart.get(f"/api/memory/knowledge/by-document/{document_id}", headers=restored_headers))["items"]
    assert any(item["title"] == "Dijkstra 限制笔记" for item in notes_after)
    global_after = _ok(after_restart.get("/api/memory/knowledge?scope=global", headers=restored_headers))["items"]
    assert any(item["title"] == "算法长期目标" for item in global_after)
    session_after = _ok(after_restart.get(f"/api/chat/sessions/{chat_session_id}", headers=restored_headers))
    assert any(f"[{label}]" in (m.get("content") or "") for m in session_after.get("messages") or [])
    prefs_after = _ok(after_restart.get("/api/settings"))["preferences"]
    assert prefs_after["user"]["display_name"] == "恢复验收测试者"
    after_restart.close()
