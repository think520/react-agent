"""W1 E5：出题三阶段管线 —— Explore → Plan → 逐题生成，每题就绪**立即入库**。

设计来自参考项目 DeepTutor «deeptutor/agents/question/pipeline.py»（见
docs/Bobodan参考项目调研报告.md 的 D8/D9）：
- Phase 1 Explore：先确认资料里有可出题的内容（拿不到证据就明确失败，不静默出空题）；
- Phase 2 Plan：一次 LLM 调用给出逐题模板；**模型不可用时用确定性兜底**，不空转；
- Phase 3 Quiz：逐题生成，**每生成一道就落库并回调一次**（"每题就绪即渲染"的数据前提）。

本轮只交付管线核心与事件；SSE 传输与界面是下一步（如实记账）。
"""

from __future__ import annotations

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
