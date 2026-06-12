import logging

from .base import register_tool, ToolResult

logger = logging.getLogger(__name__)


def question_generate(
    query: str,
    course: str | None = None,
    count: int = 5,
    workspace: str = ".",
) -> ToolResult:
    """Generate quiz questions from knowledge base content based on a topic or query."""
    try:
        from service.quiz_service import QuizService
        svc = QuizService(workspace)
        result = svc.generate_questions(query=query, course=course, count=count)

        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        lines = [f"已生成 {result['count']} 道题目：\n"]
        for q in result["questions"]:
            lines.append(f"{q['id']}. [{q['type_label']}] {q['question']}")
            if q.get("options"):
                for opt in q["options"]:
                    lines.append(f"   {opt}")
            lines.append(f"   知识点: {', '.join(q['concepts'])}")
            lines.append("")

        return ToolResult(ok=True, content="\n".join(lines), data={
            "question_ids": result["question_ids"],
            "count": result["count"],
            "types": result["types"],
        })
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
        from service.quiz_service import QuizService
        svc = QuizService(workspace)
        result = svc.start_quiz(count=count, course=course, question_type=question_type)

        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        questions = result["questions"]
        lines = [f"练习开始！共 {len(questions)} 道题，session_id={result['session_id']}\n"]
        for i, q in enumerate(questions, 1):
            lines.append(f"第 {i} 题 (id={q['id']}) [{q['type_label']}] 难度: {q['difficulty']}")
            lines.append(f"  {q['question']}")
            if q.get("options"):
                for opt in q["options"]:
                    lines.append(f"  {opt}")
            if q["type"] == "true_false":
                lines.append("  （请回答：true / false 或 对 / 错）")
            elif q["type"] == "single_choice":
                lines.append("  （请回答选项字母，如 A）")
            lines.append("")

        lines.append("请使用 quiz_submit 提交答案，格式：quiz_submit(session_id, question_id, answer)")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={"session_id": result["session_id"], "question_ids": result["question_ids"]},
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
        from service.quiz_service import QuizService
        svc = QuizService(workspace)
        result = svc.submit_answer(session_id=session_id, question_id=question_id, answer=answer)

        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        status = "✓ 正确" if result["is_correct"] else "✗ 错误"
        lines = [
            f"{status}\n",
            f"反馈: {result['feedback']}",
        ]
        if not result["is_correct"] and result.get("explanation"):
            lines.append(f"解析: {result['explanation']}")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={
                "is_correct": result["is_correct"],
                "feedback": result["feedback"],
                "correct_answer": result["correct_answer"],
                "session_completed": result["session_completed"],
            },
        )
    except Exception as e:
        logger.error("Quiz submit failed: %s", e)
        return ToolResult(ok=False, content=f"提交答案失败: {e}")


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
