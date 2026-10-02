"""W1 E5：出题三阶段管线 —— Explore → Plan → 逐题生成，每题就绪**立即入库**。

设计来自参考项目 DeepTutor «deeptutor/agents/question/pipeline.py»（见
docs/Bobodan参考项目调研报告.md 的 D8/D9）：
- Phase 1 Explore：先确认资料里有可出题的内容（拿不到证据就明确失败，不静默出空题）；
- Phase 2 Plan：一次 LLM 调用给出逐题模板；**模型不可用时用确定性兜底**，不空转；
- Phase 3 Quiz：逐题生成，**每生成一道就落库并回调一次**（"每题就绪即渲染"的数据前提）。

本轮只交付管线核心与事件；SSE 传输与界面是下一步（如实记账）。
"""

from __future__ import annotations

import json

from quiz.pipeline import (
    PlanItem,
    build_plan,
    default_plan,
    run_question_pipeline,
)
from quiz.store import QuizStore


class StubLLM:
    """按提示词分流：计划器提示词回计划，出题提示词回题目。"""

    def __init__(self, *, plan: str | None = None, question: str | None = None):
        self.plan = plan
        self.question = question
        self.calls: list[str] = []

    def complete(self, messages, **kwargs):
        prompt = messages[0]["content"]
        self.calls.append(prompt)
        from quiz.pipeline import PLAN_PROMPT_MARKER

        payload = self.plan if PLAN_PROMPT_MARKER in prompt else self.question
        if payload is None:
            payload = "not json"
        return type("Response", (), {"content": payload})()


PLAN_JSON = (
    '[{"topic": "极限的定义", "question_type": "single_choice", "difficulty": "easy"},'
    ' {"topic": "极限与连续", "question_type": "short_answer", "difficulty": "medium"}]'
)


def _question_json(topic: str) -> str:
    return (
        '[{"type": "single_choice", "question": "关于'
        + topic
        + '，下列哪项正确？", "options": ["A. 甲", "B. 乙"], "answer": "B",'
        ' "explanation": "因为乙。", "concepts": ["'
        + topic
        + '"], "difficulty": "medium"}]'
    )


def test_default_plan_is_deterministic_and_covers_the_requested_count():
    plan = default_plan("极限", 3)

    assert len(plan) == 3
    assert all(item.topic for item in plan)
    assert [item.question_type for item in plan] == [item.question_type for item in default_plan("极限", 3)]
    # 具体类型要有变化，不能全是单选。
    assert len({item.question_type for item in plan}) >= 2


def test_build_plan_uses_the_model_and_falls_back_when_it_cannot():
    good = build_plan("极限", 2, llm=StubLLM(plan=PLAN_JSON))
    broken = build_plan("极限", 2, llm=StubLLM(plan="这不是 JSON"))

    assert [item.topic for item in good[0]] == ["极限的定义", "极限与连续"], good
    assert good[1] == "llm", good
    # 模型不可用 → 确定性兜底（并如实标注来源）。
    assert len(broken[0]) == 2, broken
    assert broken[1] == "fallback", broken
    assert [item.topic for item in broken[0]] == [item.topic for item in default_plan("极限", 2)]


def test_pipeline_runs_three_phases_in_order_and_persists_each_question(monkeypatch, tmp_path):
    """每题就绪**立即入库**：事件发生的那一刻，题库里就应该已经有这道题。"""
    import quiz.pipeline as pipeline

    monkeypatch.setattr(
        pipeline, "_explore",
        lambda **kwargs: [{"chunk_id": "c1", "title": "高数", "text": "极限的定义……"}],
    )
    llm = StubLLM(plan=PLAN_JSON, question=None)

    def fake_generate(self, query, count=1, document_ids=None, **kwargs):
        from quiz.schema import Question

        item = Question(
            type="single_choice", question=f"{query} 的题", answer="B",
            options=["A. 甲", "B. 乙"], explanation=f"{query} 的解释", concepts=[query],
        )
        return [item]

    monkeypatch.setattr(
        "quiz.generator.QuestionGenerator.generate_from_query", fake_generate,
    )

    store = QuizStore(str(tmp_path))
    seen: list[tuple[str, int]] = []

    def total_in_bank() -> int:
        # count_questions() 是**按题型**返回的字典，没有 total 键。
        return sum(store.count_questions().values())

    def on_event(event):
        seen.append((event["event"], total_in_bank()))

    result = run_question_pipeline(
        workspace=str(tmp_path), topic="极限", count=2, llm=llm, on_event=on_event,
    )

    names = [name for name, _ in seen]
    assert names[0] == "pipeline_started", names
    assert "explore_done" in names and "quiz_plan" in names, names
    assert names[-1] == "pipeline_done", names
    emitted = [index for index, (name, _) in enumerate(seen) if name == "quiz_question_emitted"]
    assert len(emitted) == 2, names
    # 每道题在"发出事件"的那一刻就已经在库里（1 → 2）。
    assert seen[emitted[0]][1] == 1, seen
    assert seen[emitted[1]][1] == 2, seen
    assert len(result["question_ids"]) == 2, result
    # explanation 随题入库（D9）。
    saved = store.get_question(result["question_ids"][0])
    assert saved.explanation, saved


def test_pipeline_stops_when_cancelled_between_questions(monkeypatch, tmp_path):
    import quiz.pipeline as pipeline

    monkeypatch.setattr(
        pipeline, "_explore",
        lambda **kwargs: [{"chunk_id": "c1", "title": "高数", "text": "极限……"}],
    )

    def fake_generate(self, query, count=1, document_ids=None, **kwargs):
        from quiz.schema import Question

        return [Question(type="single_choice", question=f"{query}?", answer="B",
                         options=["A. 甲", "B. 乙"], explanation="因为。", concepts=[query])]

    monkeypatch.setattr("quiz.generator.QuestionGenerator.generate_from_query", fake_generate)

    from core.cancellation import CancelToken

    token = CancelToken()
    store = QuizStore(str(tmp_path))
    events: list[str] = []

    def on_event(event):
        events.append(event["event"])
        if event["event"] == "quiz_question_emitted":
            token.cancel()

    result = run_question_pipeline(
        workspace=str(tmp_path), topic="极限", count=3, llm=StubLLM(plan=PLAN_JSON),
        on_event=on_event, cancel_token=token,
    )

    assert events[-1] == "pipeline_cancelled", events
    # 已经就绪的那道题保留（取消不删东西），后面的不再生成。
    assert len(result["question_ids"]) == 1, result
    assert sum(store.count_questions().values()) == 1


def test_pipeline_fails_loudly_without_evidence(monkeypatch, tmp_path):
    """没有可出题的资料时要说清楚，而不是安静地出 0 道题。"""
    import quiz.pipeline as pipeline

    monkeypatch.setattr(pipeline, "_explore", lambda **kwargs: [])
    events: list[dict] = []

    result = run_question_pipeline(
        workspace=str(tmp_path), topic="不存在的主题", count=2,
        llm=StubLLM(plan=PLAN_JSON), on_event=events.append,
    )

    assert result["ok"] is False, result
    assert result["code"] == "no_evidence", result
    assert events[-1]["event"] == "pipeline_failed", events


def test_the_service_can_run_the_pipeline_without_double_persisting(monkeypatch, tmp_path):
    """W1 E5：服务层的 pipeline 开关。管线自己逐题入库，服务不能再入库一次。"""
    import quiz.pipeline as pipeline
    from service.quiz_service import QuizService

    monkeypatch.setattr(
        pipeline, "_explore",
        lambda **kwargs: [{"chunk_id": "c1", "title": "高数", "text": "极限……"}],
    )

    def fake_generate(self, query, count=1, document_ids=None, **kwargs):
        from quiz.schema import Question

        return [Question(type="single_choice", question=f"{query}?", answer="B",
                         options=["A. 甲", "B. 乙"], explanation="因为。", concepts=[query])]

    monkeypatch.setattr("quiz.generator.QuestionGenerator.generate_from_query", fake_generate)
    monkeypatch.setattr(
        "service.quiz_service._get_llm_provider",
        lambda config=None: StubLLM(plan=PLAN_JSON),
    )

    result = QuizService(str(tmp_path)).generate_questions(
        query="极限", count=2, pipeline=True,
    )

    assert result["ok"] is True, result
    assert result["count"] == 2, result
    # 每题只入库一次（不是生成一次 + 服务再存一次 = 4）。
    from quiz.store import QuizStore

    assert sum(QuizStore(str(tmp_path)).count_questions().values()) == 2


def test_the_tool_passes_the_pipeline_flag_through(monkeypatch, tmp_path):
    from service.quiz_service import QuizService
    from tools import quiz_tools

    seen: dict = {}

    def fake_generate(self, **kwargs):
        seen.update(kwargs)
        return {"ok": True, "status": "ready", "question_ids": [], "count": 0,
                "types": {}, "questions": [], "resolved_query": kwargs.get("query", "")}

    monkeypatch.setattr(QuizService, "generate_questions", fake_generate)

    quiz_tools.question_generate(query="极限", workspace=str(tmp_path), pipeline=True)

    assert seen.get("pipeline") is True, seen


def test_the_stream_endpoint_emits_each_event_in_order(monkeypatch):
    """W1 E5 第二批：SSE 端点把管线事件**逐帧**发出去（每题一帧）。"""
    import quiz.pipeline as pipeline
    from fastapi.testclient import TestClient

    from web.backend.app import create_app

    def fake_pipeline(*, on_event, **kwargs):
        on_event({"event": "pipeline_started", "topic": "极限", "count": 2})
        on_event({"event": "quiz_plan", "source": "fallback", "plan": []})
        on_event({"event": "quiz_question_emitted", "index": 0, "total": 2, "question_id": 11})
        on_event({"event": "quiz_question_emitted", "index": 1, "total": 2, "question_id": 12})
        on_event({"event": "pipeline_done", "question_ids": [11, 12], "total": 2})
        return {"ok": True, "question_ids": [11, 12], "plan_source": "fallback"}

    monkeypatch.setattr(pipeline, "run_question_pipeline", fake_pipeline)

    client = TestClient(create_app())
    with client.stream(
        "POST", "/api/quiz/pipeline/stream",
        json={"topic": "极限", "count": 2},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in response.iter_text())

    events = [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    names = [event["event"] for event in events]
    # 事件按顺序到达，并且每题一帧。
    assert names[:4] == [
        "pipeline_started", "quiz_plan", "quiz_question_emitted", "quiz_question_emitted",
    ], names
    assert names[-1] == "pipeline_result", names
    assert events[-1]["question_ids"] == [11, 12]


def test_explore_honours_the_selected_documents_and_course(monkeypatch):
    """W1 E5 细节：逐题管线以前**完全忽略 document_ids**（用户选的资料范围无效），
    也不吃 course —— 这里钉住：范围与课程都要传给检索。"""
    from quiz import pipeline as pipeline_module

    seen: dict[str, object] = {}

    class _KB:
        def __init__(self, workspace):
            seen["workspace"] = workspace

        def search(self, query, course=None, top_k=5, document_ids=None, **kwargs):
            seen.update({"query": query, "course": course, "document_ids": document_ids, "top_k": top_k})
            return {"ok": True, "results": [{"chunk_id": "c1", "text": "证据", "document_id": "doc-2"}]}

    monkeypatch.setattr("service.kb_service.KBService", _KB)

    chunks = pipeline_module._explore(
        workspace="/tmp/x", topic="最短路", document_ids=["doc-2"], course="算法课",
    )

    assert [chunk["chunk_id"] for chunk in chunks] == ["c1"], chunks
    assert seen["document_ids"] == ["doc-2"], seen
    assert seen["course"] == "算法课", seen


def test_explore_reports_no_evidence_when_the_search_fails(monkeypatch):
    from quiz import pipeline as pipeline_module

    class _Failing:
        def __init__(self, workspace):
            pass

        def search(self, *args, **kwargs):
            raise RuntimeError("index missing")

    monkeypatch.setattr("service.kb_service.KBService", _Failing)

    assert pipeline_module._explore(workspace="/tmp/x", topic="x", document_ids=None) == []


def test_the_pipeline_forwards_course_to_explore(monkeypatch):
    from quiz import pipeline as pipeline_module

    seen: dict[str, object] = {}

    def _fake_explore(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(pipeline_module, "_explore", _fake_explore)

    outcome = pipeline_module.run_question_pipeline(
        workspace="/tmp/x", topic="最短路", count=1, llm=None, course="算法课", document_ids=["doc-2"],
    )

    assert outcome["ok"] is False and outcome["code"] == "no_evidence", outcome
    assert seen["course"] == "算法课", seen
    assert seen["document_ids"] == ["doc-2"], seen


# --- W1 E5 细节：个性化上下文进管线（只影响讲法/难度偏好，**不能变成证据**） ---


def _stub_explore(monkeypatch, chunks):
    """只管 Phase 1 探路；Phase 3 里生成器**自己**还会检索一次，所以两处都要 stub，
    否则真实生成路径根本走不到提示词（那样测的就不是提示词了）。"""
    from quiz import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "_explore", lambda **kwargs: chunks)
    monkeypatch.setattr("quiz.generator.search_index", lambda *args, **kwargs: chunks)


def test_the_pipeline_feeds_personalization_into_the_question_prompt(monkeypatch, tmp_path):
    _stub_explore(monkeypatch, [{"chunk_id": "c1", "text": "极限的严格定义……", "document_id": "doc-1"}])
    llm = StubLLM(plan=PLAN_JSON, question=_question_json("极限的定义"))

    run_question_pipeline(
        workspace=str(tmp_path), topic="极限", count=1, llm=llm,
        personalization="这位学生是初学者，喜欢先看例子。",
    )

    question_prompts = [prompt for prompt in llm.calls if "初学者" in prompt]
    assert question_prompts, llm.calls
    assert len(question_prompts) == 1, llm.calls


def test_without_personalization_the_prompt_says_so(monkeypatch, tmp_path):
    _stub_explore(monkeypatch, [{"chunk_id": "c1", "text": "证据", "document_id": "doc-1"}])
    llm = StubLLM(plan=PLAN_JSON, question=_question_json("极限的定义"))

    run_question_pipeline(workspace=str(tmp_path), topic="极限", count=1, llm=llm)

    assert any("无。按资料本身生成题目。" in prompt for prompt in llm.calls), llm.calls


def test_personalization_never_becomes_a_source(monkeypatch, tmp_path):
    """个人上下文只能调讲法；题目来源必须仍然来自检索到的 chunk。"""
    _stub_explore(monkeypatch, [{"chunk_id": "c1", "text": "极限的严格定义……", "document_id": "doc-1"}])
    llm = StubLLM(plan=PLAN_JSON, question=_question_json("极限的定义"))

    outcome = run_question_pipeline(
        workspace=str(tmp_path), topic="极限", count=1, llm=llm,
        personalization="学生上次说自己在准备考研。",
    )

    store = QuizStore(str(tmp_path))
    question = store.get_question(outcome["question_ids"][0])
    sources = [str(item) for item in (question.sources or [])]
    assert sources, question
    assert all("考研" not in source for source in sources), sources


# --- W1 E5 细节：实时卡片需要更多字段（只发题干，界面只能列一行字） ---


def test_the_emitted_question_carries_what_a_card_needs(monkeypatch, tmp_path):
    from quiz import pipeline as pipeline_module

    chunks = [{"chunk_id": "c1", "title": "高数", "text": "极限……"}]
    monkeypatch.setattr(pipeline_module, "_explore", lambda **kwargs: chunks)
    monkeypatch.setattr("quiz.generator.search_index", lambda *args, **kwargs: chunks)

    from quiz.schema import Question

    def fake_generate(self, query, count=1, document_ids=None, **kwargs):
        return [Question(
            type="single_choice", question=f"{query}?", answer="B",
            options=["A. 甲", "B. 乙"], explanation="因为。", concepts=[query],
            difficulty="hard",
        )]

    monkeypatch.setattr("quiz.generator.QuestionGenerator.generate_from_query", fake_generate)

    seen: list[dict] = []
    run_question_pipeline(
        workspace=str(tmp_path), topic="极限", count=1, llm=StubLLM(plan=PLAN_JSON),
        on_event=lambda event: seen.append(event) if event["event"] == "quiz_question_emitted" else None,
    )

    payload = seen[0]["question"]
    assert payload["options"] == ["A. 甲", "B. 乙"], payload
    assert payload["type"] == "single_choice", payload
    assert payload["difficulty"] == "hard", payload
