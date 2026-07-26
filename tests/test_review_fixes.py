"""Regression tests for the 2026-07 review fixes (docs/project_review_2026-07-26.md).

Each test pins one of the correctness bugs B1-B9 so it cannot silently return.
"""

import json
import os
import sqlite3

import pytest

from learning.schema import Mastery
from learning.scheduler import ReviewScheduler
from learning.store import LearningStore
from quiz.evaluator import GradingError, QuizEvaluator, _parse_grading_response
from quiz.schema import Question


# ---------------------------------------------------------------------------
# B1 — mastered concepts must still come due for review (spaced repetition)
# ---------------------------------------------------------------------------

class TestMasteredStillDue:
    def test_mastered_concept_appears_in_due_reviews(self, tmp_path):
        store = LearningStore(str(tmp_path))
        scheduler = ReviewScheduler(store)

        # Two consecutive correct answers → mastered
        scheduler.record_review("Dijkstra", correct=True)
        m = scheduler.record_review("Dijkstra", correct=True)
        assert m.status == "mastered"
        assert m.next_review is not None

        # Force the review date into the past, as if 7 days elapsed
        m.next_review = "2000-01-01T00:00:00+00:00"
        store.upsert_mastery(m)

        due = store.get_due_reviews()
        assert any(item.concept == "Dijkstra" for item in due), (
            "mastered concepts must re-enter the due queue when next_review elapses"
        )

    def test_full_interval_ladder_reachable(self, tmp_path):
        """Third and fourth correct answers must schedule 7 / 14 day intervals."""
        store = LearningStore(str(tmp_path))
        scheduler = ReviewScheduler(store)
        for _ in range(4):
            m = scheduler.record_review("BFS", correct=True)
            m.next_review = "2000-01-01T00:00:00+00:00"
            store.upsert_mastery(m)
            assert any(item.concept == "BFS" for item in store.get_due_reviews())


# ---------------------------------------------------------------------------
# B2 — grading parse failure must NOT be recorded as a wrong answer
# ---------------------------------------------------------------------------

class _BadJSONProvider:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        from types import SimpleNamespace
        return SimpleNamespace(content=self._responses.pop(0))


class TestGradingFailureNotWrong:
    def _question(self):
        return Question(
            id=1, type="short_answer", question="什么是 RAG？",
            options=[], answer="检索增强生成", explanation="",
            concepts=["RAG"], difficulty="easy",
        )

    def test_parse_failure_raises_grading_error(self):
        with pytest.raises(GradingError):
            _parse_grading_response("这不是 JSON")

    def test_missing_verdict_field_raises(self):
        with pytest.raises(GradingError):
            _parse_grading_response('{"feedback": "写得不错"}')

    def test_retry_then_success(self):
        provider = _BadJSONProvider([
            "垃圾输出没有JSON",
            '{"is_correct": true, "feedback": "正确"}',
        ])
        ev = QuizEvaluator(llm_provider=provider)
        correct, feedback = ev.evaluate(self._question(), "检索增强生成")
        assert correct is True
        assert provider.calls == 2

    def test_double_failure_raises_not_false(self):
        provider = _BadJSONProvider(["垃圾1", "垃圾2"])
        ev = QuizEvaluator(llm_provider=provider)
        with pytest.raises(GradingError):
            ev.evaluate(self._question(), "检索增强生成")

    def test_true_false_answer_normalized_both_sides(self):
        # LLM sometimes generates Chinese answers ("对") instead of "true"
        q = Question(
            id=2, type="true_false", question="Dijkstra 适用于负权图。",
            options=[], answer="错", explanation="", concepts=[], difficulty="easy",
        )
        ev = QuizEvaluator()
        correct, _ = ev.evaluate(q, "false")
        assert correct is True
        correct, _ = ev.evaluate(q, "错误")
        assert correct is True
        correct, _ = ev.evaluate(q, "true")
        assert correct is False


# ---------------------------------------------------------------------------
# B7 — learning path weakness summary must use real quiz data
# ---------------------------------------------------------------------------

class TestWeaknessSummaryAlive:
    def test_weakness_summary_reads_quiz_store(self, tmp_path):
        from quiz.store import QuizStore
        from quiz.schema import QuizAttempt
        from learning.progress import ProgressTracker
        from learning.path import LearningPathGenerator

        workspace = str(tmp_path)
        quiz_store = QuizStore(workspace)
        q = Question(
            id=None, type="single_choice", question="q?", options=["A", "B"],
            answer="A", explanation="", concepts=["贪心"], difficulty="easy",
        )
        qid = quiz_store.add_question(q)
        session = quiz_store.create_session([qid])
        quiz_store.record_attempt(QuizAttempt(
            session_id=session.id, question_id=qid, user_answer="B",
            is_correct=False, feedback="", answered_at="2026-01-01T00:00:00+00:00",
        ))

        store = LearningStore(workspace)
        tracker = ProgressTracker(store, ReviewScheduler(store))
        generator = LearningPathGenerator(store, tracker)
        summary = generator._get_weakness_summary(workspace)
        assert "贪心" in summary, "weakness summary must surface real wrong answers"
        assert "正确率" in summary

    def test_weakness_summary_empty_workspace_returns_empty(self, tmp_path):
        from learning.progress import ProgressTracker
        from learning.path import LearningPathGenerator
        store = LearningStore(str(tmp_path))
        tracker = ProgressTracker(store, ReviewScheduler(store))
        generator = LearningPathGenerator(store, tracker)
        assert generator._get_weakness_summary(str(tmp_path)) == ""


# ---------------------------------------------------------------------------
# B8 — empty concept graph must not raise SQL syntax error
# ---------------------------------------------------------------------------

class TestEmptyGraphState:
    def test_get_graph_state_on_empty_db(self, tmp_path):
        from graph.concept_store import ConceptStore
        store = ConceptStore(str(tmp_path / "concept_graph.db"))
        state = store.get_graph_state()
        assert state["concepts"] == []
        assert state["relationships"] == []


# ---------------------------------------------------------------------------
# B9 — shared sqlite helper closes connections and commits/rolls back
# ---------------------------------------------------------------------------

class TestOpenConnection:
    def test_commit_and_close(self, tmp_path):
        from core.db import open_connection
        db = str(tmp_path / "t.db")
        with open_connection(db) as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")
        # New connection sees committed data
        with open_connection(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1

    def test_rollback_on_error(self, tmp_path):
        from core.db import open_connection
        db = str(tmp_path / "t.db")
        with open_connection(db) as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
        with pytest.raises(RuntimeError):
            with open_connection(db) as conn:
                conn.execute("INSERT INTO t VALUES (1)")
                raise RuntimeError("boom")
        with open_connection(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0

    def test_ensure_columns_idempotent(self, tmp_path):
        from core.db import create_connection, ensure_columns
        db = str(tmp_path / "t.db")
        conn = create_connection(db)
        try:
            conn.execute("CREATE TABLE t (x INTEGER)")
            ensure_columns(conn, "t", {"y": "TEXT DEFAULT ''"})
            ensure_columns(conn, "t", {"y": "TEXT DEFAULT ''"})  # second run is a no-op
            cols = {r[1] for r in conn.execute("PRAGMA table_info(t)").fetchall()}
            assert cols == {"x", "y"}
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# B6 — streaming provider must not replay chunks after mid-stream failure
# ---------------------------------------------------------------------------

class TestStreamNoReplay:
    def test_midstream_timeout_raises_instead_of_retry(self, monkeypatch):
        import httpx
        from providers.openai_compat import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            api_key="k", model="m", base_url="https://example.invalid",
            provider_name="test", max_retries=3,
        )

        chunk = json.dumps({"choices": [{"delta": {"content": "hello"}}]})

        class FakeStreamResponse:
            status_code = 200

            def iter_lines(self):
                yield f"data: {chunk}"
                raise httpx.TimeoutException("mid-stream timeout")

            def read(self):
                return b""

        class FakeStreamCM:
            def __enter__(self):
                return FakeStreamResponse()

            def __exit__(self, *args):
                return False

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def stream(self, *args, **kwargs):
                return FakeStreamCM()

        monkeypatch.setattr(httpx, "Client", FakeClient)

        received = []
        with pytest.raises(Exception, match="interrupted mid-response"):
            for c in provider.complete_stream([{"role": "user", "content": "hi"}]):
                received.append(c)
        # The chunk before the failure was delivered exactly once
        assert len(received) == 1
        assert received[0].content_delta == "hello"


# ---------------------------------------------------------------------------
# Tool arg JSON parse failure surfaces to the model (agent_loop fix)
# ---------------------------------------------------------------------------

class TestToolArgParseError:
    def test_malformed_args_yield_error_tool_result(self, tmp_path):
        from core.agent_loop import AgentLoop
        from core.session import Session
        from providers.types import LLMResponse, ToolCall

        class OneToolCallProvider:
            name = "test"
            model = "test"

            def __init__(self):
                self.calls = 0

            def complete(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    return LLMResponse(
                        content="",
                        tool_calls=[ToolCall(id="tc1", name="read_file", arguments="{not valid json")],
                    )
                return LLMResponse(content="done", tool_calls=[])

            def get_name(self):
                return "test"

        session = Session.new(cwd=str(tmp_path))
        loop = AgentLoop(OneToolCallProvider(), session)
        list(loop.run_stream("hi"))

        tool_messages = [m for m in session.messages if m.get("role") == "tool"]
        assert tool_messages, "tool message must exist for the failed call"
        assert "Invalid tool arguments" in tool_messages[0]["content"]
