import logging

from core.llm_json import parse_llm_object

from .schema import Question

logger = logging.getLogger(__name__)

GRADING_PROMPT = """你是一个批改老师。学生回答了一道简答题。

题目：{question}
参考答案：{expected_answer}
学生答案：{student_answer}

请评判答案是否正确。考虑语义等价性，不要求完全一致。
严格按以下 JSON 格式输出，不要添加其他文字：
{{"is_correct": true, "feedback": "解释为什么正确或错误，并在错误时给出正确答案。"}}"""

GRADING_RETRY_SUFFIX = """

注意：你上一次的输出无法被解析为 JSON。请只输出一个 JSON 对象，
不要包含任何多余文字、代码块标记或注释。"""

_TRUE_WORDS = ("true", "t", "对", "正确", "yes", "是", "√")
_FALSE_WORDS = ("false", "f", "错", "错误", "no", "否", "×")


class GradingError(Exception):
    """Raised when grading cannot produce a verdict (LLM failure or unparseable
    output). Callers must NOT treat this as a wrong answer."""


def _normalize_bool_answer(raw: str) -> str:
    value = raw.strip().lower()
    if value in _TRUE_WORDS:
        return "true"
    if value in _FALSE_WORDS:
        return "false"
    return value


def _parse_grading_response(text: str) -> tuple[bool, str]:
    """Parse LLM grading response. Raises GradingError when no verdict exists."""
    data = parse_llm_object(text)
    if data is None:
        raise GradingError("no JSON object found in grading response")
    if "is_correct" not in data:
        raise GradingError("grading JSON missing is_correct")
    is_correct = bool(data.get("is_correct"))
    feedback = data.get("feedback", "")
    return is_correct, feedback


class QuizEvaluator:
    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def evaluate(self, question: Question, user_answer: str) -> tuple[bool, str]:
        """Grade an answer. Returns (is_correct, feedback).

        Raises GradingError when a short answer cannot be judged; callers
        should surface a retryable error instead of recording a wrong answer.
        """
        if question.type == "single_choice":
            return self._evaluate_choice(question, user_answer)
        elif question.type == "true_false":
            return self._evaluate_true_false(question, user_answer)
        elif question.type == "short_answer":
            return self._evaluate_short_answer(question, user_answer)
        else:
            return False, f"未知题型: {question.type}"

    def _evaluate_choice(self, question: Question, user_answer: str) -> tuple[bool, str]:
        """Auto-grade single_choice: normalize answer letter and compare."""
        normalized = user_answer.strip().upper()
        if len(normalized) > 1:
            # Try to extract letter from "A" or "A." or "选A"
            for ch in normalized:
                if ch in "ABCD":
                    normalized = ch
                    break
        correct = normalized == question.answer.strip().upper()
        if correct:
            feedback = f"正确！{question.explanation}" if question.explanation else "正确！"
        else:
            feedback = f"错误。正确答案是 {question.answer}。"
            if question.explanation:
                feedback += f" {question.explanation}"
        return correct, feedback

    def _evaluate_true_false(self, question: Question, user_answer: str) -> tuple[bool, str]:
        """Auto-grade true_false: normalize both sides to true/false and compare."""
        normalized = _normalize_bool_answer(user_answer)
        correct = normalized == _normalize_bool_answer(question.answer)
        if correct:
            feedback = f"正确！{question.explanation}" if question.explanation else "正确！"
        else:
            feedback = f"错误。正确答案是 {question.answer}。"
            if question.explanation:
                feedback += f" {question.explanation}"
        return correct, feedback

    def _evaluate_short_answer(self, question: Question, user_answer: str) -> tuple[bool, str]:
        """LLM-grade short_answer with one retry on unparseable output."""
        if not self.llm:
            # Fallback: simple string matching
            expected = question.answer.strip().lower()
            actual = user_answer.strip().lower()
            if expected == actual:
                return True, "正确！"
            if expected in actual or actual in expected:
                return True, "基本正确。"
            return False, f"参考答案：{question.answer}"

        prompt = GRADING_PROMPT.format(
            question=question.question,
            expected_answer=question.answer,
            student_answer=user_answer,
        )
        last_error: Exception | None = None
        for attempt, current_prompt in enumerate((prompt, prompt + GRADING_RETRY_SUFFIX)):
            try:
                response = self.llm.complete([{"role": "user", "content": current_prompt}])
                raw_text = response.content if hasattr(response, "content") else str(response)
                return _parse_grading_response(raw_text)
            except GradingError as exc:
                last_error = exc
                logger.warning("Grading parse failed (attempt %d): %s", attempt + 1, exc)
            except Exception as exc:
                last_error = exc
                logger.error("LLM grading failed (attempt %d): %s", attempt + 1, exc)
        raise GradingError(f"grading unavailable: {last_error}") from last_error
