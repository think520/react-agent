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


# --- W1 E13：触发面（不再只看用户措辞） ---------------------------------------


def test_strict_mode_only_fires_on_a_real_inline_quiz() -> None:
    """严格判定：给"无条件挂载"用，必须**成组的短选项出现在结尾**且上下文在提问。

    宽松判定（措辞命中时用）只要求 ≥2 个字母选项 —— 它会误伤讲解里的
    「A. 从能量角度…… B. 从熵角度……」这种列举。
    """
    policy = InlineQuestionPolicy()
    real_quiz = "下面哪一项属于贪心策略？\nA. 分治\nB. 每次选局部最优\nC. 动态规划\nD. 回溯"
    explanation = (
        "可以从两个角度理解：\n"
        "A. 从能量角度，系统倾向于更低的状态，这里还能继续展开很长的解释，"
        "把两种视角的区别讲清楚，而不是让学生选一个。\n"
        "B. 从熵角度，混乱度上升。"
    )

    assert policy.looks_like_inline_question(real_quiz, strict=True) is True
    assert policy.looks_like_inline_question(explanation, strict=True) is False
    # 宽松判定仍然认这两段（它只在用户明确要题时使用）。
    assert policy.looks_like_inline_question(real_quiz) is True


def test_strict_mode_ignores_options_that_are_not_at_the_end() -> None:
    policy = InlineQuestionPolicy()
    text = (
        "A. 甲\nB. 乙\n"
        "然后我们继续讲后面的内容，这段解释很长，把前面两个选项包围起来，"
        "让它们显然不是一道题的选项，而只是并列的两种说法。"
    )
    assert policy.looks_like_inline_question(text, strict=True) is False


def test_the_guard_is_mounted_even_when_the_phrasing_does_not_match() -> None:
    """W1 E13：措辞表漏了就绕过 —— 所以防线②**无条件挂载**，措辞只决定灵敏度。"""
    from web.backend.routers.chat import _build_response_policies

    def inline_policy(policies):
        return next(p for p in policies if isinstance(p, InlineQuestionPolicy))

    off_phrase = _build_response_policies("给我讲讲这个", has_document_scope=False)
    assert inline_policy(off_phrase)._strict is True
    assert not any(type(p).__name__ == "LocalEvidencePolicy" for p in off_phrase)

    on_phrase = _build_response_policies("根据资料出 5 道题", has_document_scope=True)
    assert inline_policy(on_phrase)._strict is False
    assert any(type(p).__name__ == "LocalEvidencePolicy" for p in on_phrase)


def test_practice_phrases_cover_more_than_the_original_list() -> None:
    """表外语义不该绕过：这些说法过去一个都不命中。"""
    from web.backend.routers.chat import _requests_practice

    for phrase in ("刷几道题", "给我来点题", "练一练这章", "考考我", "检验一下我学会了没", "drill me"):
        assert _requests_practice(phrase), phrase
