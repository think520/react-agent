import logging
from datetime import datetime, timezone

from quiz.store import QuizStore
from quiz.generator import QuestionGenerator
from quiz.evaluator import QuizEvaluator
from quiz.schema import Question

from .base import register_tool, ToolResult

logger = logging.getLogger(__name__)


def _get_llm_provider():
    """Create LLM provider from config."""
    from providers.factory import ProviderFactory
    return ProviderFactory.create_from_config()


def question_generate(
    query: str,
    course: str | None = None,
    count: int = 5,
    workspace: str = ".",
) -> ToolResult:
    """Generate quiz questions from knowledge base content based on a topic or query."""
    try:
        llm = _get_llm_provider()
    except Exception as e:
        return ToolResult(ok=False, content=f"LLM provider not available: {e}")

    try:
        store = QuizStore(workspace)
        generator = QuestionGenerator(workspace, llm)
        questions = generator.generate_from_query(query, course=course, count=count)

        if not questions:
            return ToolResult(
                ok=False,
                content=(
                    "未能生成题目。可能原因：\n"
                    "1. 知识库中没有与该主题相关的资料（先用 /kb search 验证）\n"
                    "2. 相关材料内容太少，不足以出题\n"
                    "3. LLM 返回格式异常（已记录日志）\n"
                    f"搜索主题: {query}"
                ),
            )

        # Save to store
        saved_ids = []
        for q in questions:
            qid = store.add_question(q)
            saved_ids.append(qid)

        summary = {
            "question_ids": saved_ids,
            "count": len(saved_ids),
            "types": {q.type: sum(1 for x in questions if x.type == q.type) for q in questions},
        }

        # Format for display
        lines = [f"已生成 {len(questions)} 道题目：\n"]
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. [{_type_label(q.type)}] {q.question}")
            if q.options:
                for opt in q.options:
                    lines.append(f"   {opt}")
            lines.append(f"   知识点: {', '.join(q.concepts)}")
            lines.append("")

        return ToolResult(ok=True, content="\n".join(lines), data=summary)
    except Exception as e:
        logger.error("Question generation failed: %s", e)
        return ToolResult(ok=False, content=f"题目生成失败: {e}")


def quiz_start(
    count: int = 5,
    course: str | None = None,
    question_type: str | None = None,
    workspace: str = ".",
) -> ToolResult:
    """Start a quiz session. Returns questions without answers for the user to answer."""
    try:
        store = QuizStore(workspace)
    except Exception as e:
        return ToolResult(ok=False, content=f"Failed to open quiz store: {e}")

    try:
        # Try to find existing questions
        questions = store.list_questions(course=course, qtype=question_type, limit=count)

        if len(questions) < count:
            # Generate more
            try:
                llm = _get_llm_provider()
                generator = QuestionGenerator(workspace, llm)
                query = course or "课程重点知识"
                new_questions = generator.generate_from_query(
                    query, course=course, count=count - len(questions)
                )
                for q in new_questions:
                    qid = store.add_question(q)
                    q.id = qid
                questions.extend(new_questions)
            except Exception as e:
                logger.warning("Could not generate more questions: %s", e)

        if not questions:
            return ToolResult(
                ok=False,
                content="题库为空。请先使用 question_generate 生成题目，或确保知识库中有资料。",
            )

        # Create session
        question_ids = [q.id for q in questions if q.id is not None]
        session = store.create_session(question_ids)

        # Format questions (without answers)
        lines = [f"练习开始！共 {len(questions)} 道题，session_id={session.id}\n"]
        for i, q in enumerate(questions, 1):
            lines.append(f"第 {i} 题 (id={q.id}) [{_type_label(q.type)}] 难度: {q.difficulty}")
            lines.append(f"  {q.question}")
            if q.options:
                for opt in q.options:
                    lines.append(f"  {opt}")
            if q.type == "true_false":
                lines.append("  （请回答：true / false 或 对 / 错）")
            elif q.type == "single_choice":
                lines.append("  （请回答选项字母，如 A）")
            lines.append("")

        lines.append("请使用 quiz_submit 提交答案，格式：quiz_submit(session_id, question_id, answer)")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={"session_id": session.id, "question_ids": question_ids},
        )
    except Exception as e:
        logger.error("Quiz start failed: %s", e)
        return ToolResult(ok=False, content=f"启动练习失败: {e}")


def quiz_submit(
    session_id: int,
    question_id: int,
    answer: str,
    workspace: str = ".",
) -> ToolResult:
    """Submit an answer for a quiz question. Returns grading and feedback."""
    try:
        store = QuizStore(workspace)
    except Exception as e:
        return ToolResult(ok=False, content=f"Failed to open quiz store: {e}")

    try:
        # Validate session
        session = store.get_session(session_id)
        if not session:
            return ToolResult(ok=False, content=f"练习 session {session_id} 不存在。")

        # Get question
        question = store.get_question(question_id)
        if not question:
            return ToolResult(ok=False, content=f"题目 {question_id} 不存在。")

        # Evaluate
        try:
            llm = _get_llm_provider()
            evaluator = QuizEvaluator(llm)
        except Exception:
            evaluator = QuizEvaluator()

        is_correct, feedback = evaluator.evaluate(question, answer)

        # Record attempt
        from quiz.schema import QuizAttempt
        attempt_record = QuizAttempt(
            session_id=session_id,
            question_id=question_id,
            user_answer=answer,
            is_correct=is_correct,
            feedback=feedback,
            answered_at=datetime.now(timezone.utc).isoformat(),
        )
        store.record_attempt(attempt_record)

        # Record learning effect (daily memory + mastery update)
        try:
            from learning.quiz_integration import record_quiz_learning_effect, record_quiz_session_summary
            record_quiz_learning_effect(
                workspace=workspace,
                question_concepts=question.concepts,
                is_correct=is_correct,
                feedback=feedback,
            )
        except Exception as e:
            logger.warning("Failed to record quiz learning effect: %s", e)

        # Check session completion
        session_completed = False
        try:
            attempts = store.get_attempts_for_session(session_id)
            session_completed = record_quiz_session_summary(
                workspace=workspace,
                session_id=session_id,
                question_ids=session.question_ids,
                attempts=attempts,
            )
        except Exception as e:
            logger.warning("Failed to check session completion: %s", e)

        # Format result
        status = "✓ 正确" if is_correct else "✗ 错误"
        lines = [
            f"{status}\n",
            f"反馈: {feedback}",
        ]
        if not is_correct and question.explanation:
            lines.append(f"解析: {question.explanation}")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={
                "is_correct": is_correct,
                "feedback": feedback,
                "correct_answer": question.answer,
                "session_completed": session_completed,
            },
        )
    except Exception as e:
        logger.error("Quiz submit failed: %s", e)
        return ToolResult(ok=False, content=f"提交答案失败: {e}")


def _type_label(qtype: str) -> str:
    return {
        "single_choice": "单选",
        "true_false": "判断",
        "short_answer": "简答",
    }.get(qtype, qtype)


# Register tools
register_tool(
    name="question_generate",
    description="Generate quiz questions from the knowledge base on a specific topic. Use when the user wants to create practice questions or a question bank.",
    params_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Topic or search query to find relevant content for question generation",
            },
            "course": {
                "type": "string",
                "description": "Optional course name to filter content",
            },
            "count": {
                "type": "integer",
                "description": "Number of questions to generate (default 5)",
            },
        },
        "required": ["query"],
    },
    func=question_generate,
)

register_tool(
    name="quiz_start",
    description="Start a quiz practice session. Returns questions without answers for the user to answer one by one.",
    params_schema={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of questions in the quiz (default 5)",
            },
            "course": {
                "type": "string",
                "description": "Optional course name to filter questions",
            },
            "question_type": {
                "type": "string",
                "description": "Optional question type filter: single_choice, true_false, short_answer",
            },
        },
        "required": [],
    },
    func=quiz_start,
)

register_tool(
    name="quiz_submit",
    description="Submit an answer for a quiz question. Returns whether the answer is correct, feedback, and explanation.",
    params_schema={
        "type": "object",
        "properties": {
            "session_id": {
                "type": "integer",
                "description": "Quiz session ID from quiz_start",
            },
            "question_id": {
                "type": "integer",
                "description": "Question ID to answer",
            },
            "answer": {
                "type": "string",
                "description": "User's answer (letter for choice, true/false for T/F, text for short answer)",
            },
        },
        "required": ["session_id", "question_id", "answer"],
    },
    func=quiz_submit,
)
