import json
import logging
import re

from .schema import Question

logger = logging.getLogger(__name__)

GRADING_PROMPT = """你是一个批改老师。学生回答了一道简答题。

题目：{question}
参考答案：{expected_answer}
学生答案：{student_answer}

请评判答案是否正确。考虑语义等价性，不要求完全一致。
严格按以下 JSON 格式输出，不要添加其他文字：
{{"is_correct": true, "feedback": "解释为什么正确或错误，并在错误时给出正确答案。"}}"""


def _parse_grading_response(text: str) -> tuple[bool, str]:
    """Parse LLM grading response."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("No JSON object found in grading response")
        return False, "批改解析失败，请重试。"

    try:
        data = json.loads(text[start : end + 1])
        is_correct = bool(data.get("is_correct", False))
        feedback = data.get("feedback", "")
        return is_correct, feedback
    except json.JSONDecodeError:
        logger.warning("Failed to parse grading JSON")
        return False, "批改解析失败，请重试。"


class QuizEvaluator:
    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def evaluate(self, question: Question, user_answer: str) -> tuple[bool, str]:
        """Grade an answer. Returns (is_correct, feedback)."""
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
        """Auto-grade true_false: normalize to true/false and compare."""
        raw = user_answer.strip().lower()
        # Accept various formats
        if raw in ("true", "t", "对", "正确", "yes", "是", "√"):
            normalized = "true"
        elif raw in ("false", "f", "错", "错误", "no", "否", "×"):
            normalized = "false"
        else:
            normalized = raw

        correct = normalized == question.answer.strip().lower()
        if correct:
            feedback = f"正确！{question.explanation}" if question.explanation else "正确！"
        else:
            feedback = f"错误。正确答案是 {question.answer}。"
            if question.explanation:
                feedback += f" {question.explanation}"
        return correct, feedback

    def _evaluate_short_answer(self, question: Question, user_answer: str) -> tuple[bool, str]:
        """LLM-grade short_answer."""
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
        try:
            response = self.llm.complete([{"role": "user", "content": prompt}])
            raw_text = response.content if hasattr(response, "content") else str(response)
            return _parse_grading_response(raw_text)
        except Exception as e:
            logger.error("LLM grading failed: %s", e)
            return False, f"批改失败：{e}。参考答案：{question.answer}"
