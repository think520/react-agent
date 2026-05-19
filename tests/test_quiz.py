import json
import os
from dataclasses import asdict

from quiz.schema import Question, QuizSession, QuizAttempt, QUESTION_TYPES, DIFFICULTY_LEVELS
from quiz.store import QuizStore
from quiz.evaluator import QuizEvaluator
from quiz.review import QuizReviewer


# --- Schema tests ---

def test_question_defaults():
    q = Question()
    assert q.type == "single_choice"
    assert q.options == []
    assert q.concepts == []
    assert q.difficulty == "medium"
    assert q.id is None


def test_quiz_session_defaults():
    s = QuizSession()
    assert s.question_ids == []
    assert s.completed_at is None


def test_quiz_attempt_defaults():
    a = QuizAttempt()
    assert a.is_correct is False
    assert a.feedback == ""


def test_question_types_constant():
    assert QUESTION_TYPES == {"single_choice", "true_false", "short_answer"}


def test_difficulty_levels_constant():
    assert DIFFICULTY_LEVELS == {"easy", "medium", "hard"}


# --- Store tests ---

def test_store_creates_tables(tmp_path):
    ws = str(tmp_path)
    store = QuizStore(ws)
    assert os.path.exists(store.db_path)


def test_add_and_get_question(tmp_path):
    store = QuizStore(str(tmp_path))
    q = Question(
        type="single_choice",
        question="What is 1+1?",
        options=["A. 1", "B. 2", "C. 3", "D. 4"],
        answer="B",
        explanation="Basic math",
        concepts=["arithmetic"],
        difficulty="easy",
    )
    qid = store.add_question(q)
    assert qid > 0

    loaded = store.get_question(qid)
    assert loaded is not None
    assert loaded.question == "What is 1+1?"
    assert loaded.answer == "B"
    assert loaded.options == ["A. 1", "B. 2", "C. 3", "D. 4"]
    assert loaded.concepts == ["arithmetic"]


def test_list_questions(tmp_path):
    store = QuizStore(str(tmp_path))
    store.add_question(Question(type="single_choice", question="Q1", answer="A"))
    store.add_question(Question(type="true_false", question="Q2", answer="true"))
    store.add_question(Question(type="single_choice", question="Q3", answer="B"))

    all_q = store.list_questions()
    assert len(all_q) == 3

    sc_only = store.list_questions(qtype="single_choice")
    assert len(sc_only) == 2

    limited = store.list_questions(limit=2)
    assert len(limited) == 2


def test_get_questions_by_ids(tmp_path):
    store = QuizStore(str(tmp_path))
    id1 = store.add_question(Question(question="Q1", answer="A"))
    id2 = store.add_question(Question(question="Q2", answer="B"))
    id3 = store.add_question(Question(question="Q3", answer="C"))

    questions = store.get_questions_by_ids([id2, id1])
    assert len(questions) == 2
    assert questions[0].question == "Q2"
    assert questions[1].question == "Q1"


def test_count_questions(tmp_path):
    store = QuizStore(str(tmp_path))
    store.add_question(Question(type="single_choice", question="Q1", answer="A"))
    store.add_question(Question(type="true_false", question="Q2", answer="true"))

    counts = store.count_questions()
    assert counts["single_choice"] == 1
    assert counts["true_false"] == 1


def test_create_and_get_session(tmp_path):
    store = QuizStore(str(tmp_path))
    qid = store.add_question(Question(question="Q1", answer="A"))

    session = store.create_session([qid])
    assert session.id is not None
    assert session.question_ids == [qid]
    assert session.completed_at is None

    loaded = store.get_session(session.id)
    assert loaded is not None
    assert loaded.question_ids == [qid]


def test_complete_session(tmp_path):
    store = QuizStore(str(tmp_path))
    session = store.create_session([1, 2])
    store.complete_session(session.id)

    loaded = store.get_session(session.id)
    assert loaded.completed_at is not None


def test_record_and_get_attempts(tmp_path):
    store = QuizStore(str(tmp_path))
    qid = store.add_question(Question(question="Q1", answer="A"))
    session = store.create_session([qid])

    attempt = QuizAttempt(
        session_id=session.id,
        question_id=qid,
        user_answer="B",
        is_correct=False,
        feedback="Wrong",
    )
    aid = store.record_attempt(attempt)
    assert aid > 0

    attempts = store.get_attempts_for_session(session.id)
    assert len(attempts) == 1
    assert attempts[0].user_answer == "B"
    assert attempts[0].is_correct is False


def test_get_wrong_answers(tmp_path):
    store = QuizStore(str(tmp_path))
    qid = store.add_question(Question(
        type="single_choice", question="Q1", answer="A",
        options=["A. ok", "B. no"], concepts=["math"],
    ))
    session = store.create_session([qid])
    store.record_attempt(QuizAttempt(
        session_id=session.id, question_id=qid,
        user_answer="B", is_correct=False, feedback="Wrong",
    ))

    wrong = store.get_wrong_answers()
    assert len(wrong) == 1
    assert wrong[0]["question"] == "Q1"
    assert wrong[0]["user_answer"] == "B"


def test_get_weakness_analysis(tmp_path):
    store = QuizStore(str(tmp_path))
    q1 = store.add_question(Question(
        question="Q1", answer="A", concepts=["algebra", "basics"],
    ))
    q2 = store.add_question(Question(
        question="Q2", answer="B", concepts=["algebra"],
    ))
    session = store.create_session([q1, q2])
    store.record_attempt(QuizAttempt(
        session_id=session.id, question_id=q1,
        user_answer="B", is_correct=False,
    ))
    store.record_attempt(QuizAttempt(
        session_id=session.id, question_id=q2,
        user_answer="B", is_correct=True,
    ))

    analysis = store.get_weakness_analysis()
    concepts = {a["concept"]: a for a in analysis}
    assert "algebra" in concepts
    assert concepts["algebra"]["total_attempts"] == 2
    assert concepts["algebra"]["wrong_count"] == 1


# --- Evaluator tests ---

def test_evaluator_choice_correct():
    q = Question(type="single_choice", question="Q", answer="B")
    ev = QuizEvaluator()
    correct, feedback = ev.evaluate(q, "B")
    assert correct is True
    assert "正确" in feedback


def test_evaluator_choice_wrong():
    q = Question(type="single_choice", question="Q", answer="B", explanation="Because")
    ev = QuizEvaluator()
    correct, feedback = ev.evaluate(q, "A")
    assert correct is False
    assert "B" in feedback
    assert "Because" in feedback


def test_evaluator_choice_normalization():
    q = Question(type="single_choice", question="Q", answer="B")
    ev = QuizEvaluator()
    # Lowercase should be normalized
    correct, _ = ev.evaluate(q, "b")
    assert correct is True


def test_evaluator_true_false_true():
    q = Question(type="true_false", question="Q", answer="true")
    ev = QuizEvaluator()
    correct, _ = ev.evaluate(q, "true")
    assert correct is True


def test_evaluator_true_false_chinese():
    q = Question(type="true_false", question="Q", answer="true")
    ev = QuizEvaluator()
    correct, _ = ev.evaluate(q, "对")
    assert correct is True

    correct, _ = ev.evaluate(q, "错")
    assert correct is False


def test_evaluator_true_false_false():
    q = Question(type="true_false", question="Q", answer="false")
    ev = QuizEvaluator()
    correct, _ = ev.evaluate(q, "false")
    assert correct is True


def test_evaluator_short_answer_no_llm():
    q = Question(type="short_answer", question="Q", answer="Dijkstra")
    ev = QuizEvaluator(llm_provider=None)
    correct, feedback = ev.evaluate(q, "Dijkstra")
    assert correct is True

    correct, feedback = ev.evaluate(q, "BFS")
    assert correct is False


def test_evaluator_short_answer_with_mock_llm():
    """Test short answer grading with a mock LLM provider."""
    class MockProvider:
        class Response:
            content = '{"is_correct": true, "feedback": "Correct!"}'
        def complete(self, messages):
            return self.Response()

    q = Question(type="short_answer", question="What algo?", answer="Dijkstra")
    ev = QuizEvaluator(llm_provider=MockProvider())
    correct, feedback = ev.evaluate(q, "Dijkstra algorithm")
    assert correct is True
    assert "Correct" in feedback


# --- Review tests ---

def test_wrong_answer_book_empty(tmp_path):
    store = QuizStore(str(tmp_path))
    reviewer = QuizReviewer(store)
    entries = reviewer.get_wrong_answer_book()
    assert entries == []


def test_wrong_answer_book_formatting(tmp_path):
    store = QuizStore(str(tmp_path))
    reviewer = QuizReviewer(store)
    text = reviewer.format_wrong_answer_book([])
    assert "暂无错题" in text


def test_weakness_analysis_empty(tmp_path):
    store = QuizStore(str(tmp_path))
    reviewer = QuizReviewer(store)
    analysis = reviewer.get_weakness_analysis()
    assert analysis == []


def test_weakness_analysis_formatting(tmp_path):
    store = QuizStore(str(tmp_path))
    reviewer = QuizReviewer(store)
    text = reviewer.format_weakness_analysis([])
    assert "暂无" in text


# --- Generator tests ---

def test_generator_parses_json():
    from quiz.generator import _parse_json_from_llm

    raw = '[{"type": "single_choice", "question": "Q", "answer": "A"}]'
    result = _parse_json_from_llm(raw)
    assert len(result) == 1
    assert result[0]["type"] == "single_choice"


def test_generator_parses_markdown_fenced():
    from quiz.generator import _parse_json_from_llm

    raw = '```json\n[{"type": "true_false", "question": "Q", "answer": "true"}]\n```'
    result = _parse_json_from_llm(raw)
    assert len(result) == 1


def test_generator_handles_no_json():
    from quiz.generator import _parse_json_from_llm
    assert _parse_json_from_llm("no json here") == []


def test_generator_handles_invalid_json():
    from quiz.generator import _parse_json_from_llm
    assert _parse_json_from_llm("[invalid json") == []


def test_generator_handles_multiple_arrays():
    from quiz.generator import _parse_json_from_llm

    # LLM returns two separate arrays
    raw = '[]\n[]'
    assert _parse_json_from_llm(raw) == []

    # LLM returns valid array followed by extra text
    raw = '[{"type": "single_choice", "question": "Q", "answer": "A"}]\nextra'
    result = _parse_json_from_llm(raw)
    assert len(result) == 1


def test_generator_handles_trailing_commas():
    from quiz.generator import _parse_json_from_llm

    raw = '[{"type": "single_choice", "question": "Q", "answer": "A",},]'
    result = _parse_json_from_llm(raw)
    assert len(result) == 1


def test_generator_handles_nested_brackets():
    from quiz.generator import _parse_json_from_llm

    raw = '[{"type": "single_choice", "options": ["A", "B"], "question": "Q", "answer": "A"}]'
    result = _parse_json_from_llm(raw)
    assert len(result) == 1
    assert result[0]["options"] == ["A", "B"]


def test_generator_validate_question():
    from quiz.generator import _validate_question

    assert _validate_question({"type": "single_choice", "question": "Q", "answer": "A"})
    assert not _validate_question({"type": "single_choice", "question": "Q"})  # missing answer
    assert not _validate_question({"type": "bad", "question": "Q", "answer": "A"})
    assert not _validate_question({})


def test_generator_from_chunks_mock():
    """Test question generation with mock LLM."""
    class MockProvider:
        class Response:
            content = json.dumps([{
                "type": "single_choice",
                "question": "Test Q?",
                "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
                "answer": "B",
                "explanation": "Because",
                "concepts": ["test"],
                "difficulty": "easy",
            }])
        def complete(self, messages):
            return self.Response()

    from quiz.generator import QuestionGenerator
    gen = QuestionGenerator(str("/tmp"), MockProvider())
    chunks = [{"text": "some content", "source": "test.md"}]
    questions = gen.generate_from_chunks(chunks, count=1)
    assert len(questions) == 1
    assert questions[0].question == "Test Q?"
    assert questions[0].answer == "B"


# --- Tool integration tests ---

def test_question_generate_tool_no_llm(tmp_path, monkeypatch):
    from tools.quiz_tools import question_generate

    # Without config or knowledge base, should fail gracefully
    result = question_generate(query="test", workspace=str(tmp_path))
    assert not result.ok


def test_quiz_start_empty(tmp_path):
    from tools.quiz_tools import quiz_start

    result = quiz_start(workspace=str(tmp_path))
    assert not result.ok
    assert "为空" in result.content or "empty" in result.content.lower()


def test_quiz_submit_invalid_session(tmp_path):
    from tools.quiz_tools import quiz_submit

    result = quiz_submit(session_id=999, question_id=1, answer="A", workspace=str(tmp_path))
    assert not result.ok
    assert "不存在" in result.content
