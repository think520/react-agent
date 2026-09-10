"""E13 regression: the two anti-bypass defenses around the practice card.

Defense 1 (server-side binding): the web agent cannot call quiz_start/quiz_submit,
so the only path to a practice is the persisted practice_ready artifact.
Defense 2 (plain-text redirect): a model that ends the turn with lettered options
is redirected to question_generate instead of showing unbound questions.
"""

from __future__ import annotations

from service.evidence_policy import InlineQuestionPolicy


def _history(*records: dict) -> list[dict]:
    return list(records)


def test_detects_lettered_options() -> None:
    policy = InlineQuestionPolicy()
    assert policy.looks_like_inline_question("A. 甲\nB. 乙\nC. 丙")
    assert policy.looks_like_inline_question("（1）题干\nA、甲\nB、乙")
    assert policy.looks_like_inline_question("A）甲\nB）乙")


def test_ignores_plain_prose_and_single_option() -> None:
    policy = InlineQuestionPolicy()
    assert not policy.looks_like_inline_question("这是一段解释，没有任何选项。")
    assert not policy.looks_like_inline_question("A. 只有唯一一个选项")


def test_allows_a_normal_answer() -> None:
    decision = InlineQuestionPolicy().validate(_history(), "普通回答，没有选项。", 0)
    assert decision.allow is True


def test_allows_when_question_generate_succeeded() -> None:
    decision = InlineQuestionPolicy().validate(
        _history({"name": "question_generate", "ok": True}),
        "A. 甲\nB. 乙",
        0,
    )
    assert decision.allow is True


def test_redirects_plain_text_question_to_the_card() -> None:
    decision = InlineQuestionPolicy().validate(_history(), "A. 甲\nB. 乙", 0)
    assert decision.allow is False
    assert "question_generate" in decision.correction_prompt


def test_falls_back_after_retries_are_exhausted() -> None:
    decision = InlineQuestionPolicy().validate(_history(), "A. 甲\nB. 乙", 5)
    assert decision.allow is False
    assert decision.fallback_content
    assert not decision.correction_prompt


def test_practice_request_heuristic() -> None:
    from web.backend.routers.chat import _requests_practice

    assert _requests_practice("根据资料出 5 道题")
    assert _requests_practice("帮我测验一下这章")
    assert _requests_practice("quiz me on chapter 3")
    assert not _requests_practice("帮我解释一下熵增定律")


def test_web_agent_cannot_start_a_practice_directly() -> None:
    from web.backend.routers.chat import _WEB_TOOL_NAMES

    assert "question_generate" in _WEB_TOOL_NAMES
    # Defense 1: the card path is the only server-bound way to start practice.
    assert "quiz_start" not in _WEB_TOOL_NAMES
    assert "quiz_submit" not in _WEB_TOOL_NAMES
