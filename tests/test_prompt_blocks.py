"""W1 E12：prompt 具名块**字节稳定** + KB seed 预检索进末尾 user 消息。

设计来自参考项目（见 docs/Bobodan参考项目调研报告.md 的 D5/D13）：
- system 拆具名块且全 turn 字节稳定（缓存友好、diff 有意义）；
- 进循环前先检索一次，把结果拼成 «[Knowledge Base Context]» 追加到**末尾 user 消息**，
  并明示「不完整，可以继续检索」—— 预检索**不替代**工具检索。
"""

from __future__ import annotations

from core.prompt_blocks import (
    KB_CONTEXT_HEADER,
    attach_kb_seed,
    build_kb_seed_block,
)

HITS = [
    {"chunk_id": "chunk-b", "title": "算法课", "document_id": "doc-1", "text": "Dijkstra 每次选距离最小的节点。"},
    {"chunk_id": "chunk-a", "title": "算法课", "document_id": "doc-1", "text": "贪心策略在非负权图上成立。"},
]


def test_seed_block_is_byte_stable_regardless_of_hit_order():
    """同一批命中，不管检索返回的顺序如何，拼出来的块必须**逐字节相同**。"""
    first = build_kb_seed_block(HITS)
    shuffled = build_kb_seed_block(list(reversed(HITS)))

    assert first == shuffled
    assert first.startswith(KB_CONTEXT_HEADER)
    assert "chunk-a" in first and "chunk-b" in first


def test_seed_block_says_it_does_not_replace_tools():
    block = build_kb_seed_block(HITS)

    assert "不完整" in block, block
    assert "检索" in block, block


def test_no_hits_means_no_block():
    assert build_kb_seed_block([]) == ""


def test_attach_is_idempotent():
    """重试或多轮再次注入时不能越拼越长。"""
    block = build_kb_seed_block(HITS)
    seeded = attach_kb_seed("什么是 Dijkstra？", block)

    assert seeded.startswith("什么是 Dijkstra？")
    assert seeded.count(KB_CONTEXT_HEADER) == 1
    assert attach_kb_seed(seeded, block) == seeded
    # 没有块时原样返回。
    assert attach_kb_seed("普通消息", "") == "普通消息"


def test_block_is_capped_and_says_so():
    big = [
        {"chunk_id": f"chunk-{index}", "title": "长文档", "text": "内容" * 400}
        for index in range(8)
    ]

    block = build_kb_seed_block(big, max_chars=600)

    assert len(block) <= 900, len(block)
    assert "截断" in block or "仅列" in block, block[-200:]



# --- W1 E12：AgentLoop 把块拼到末尾 user 消息（走真实路径） --------------------


def _run_loop(seed: str | None, message: str = "什么是 Dijkstra？"):
    from core.agent_loop import AgentLoop
    from core.session import Session
    from providers.types import LLMResponse

    class _LLM:
        def complete(self, messages, tools=None):
            return LLMResponse(content="ok")

        def get_name(self):
            return "mock"

    session = Session.new(".")
    AgentLoop(_LLM(), session, kb_seed=seed).run(message)
    return [m for m in session.messages if m["role"] == "user"]


def test_the_loop_appends_the_kb_seed_to_the_trailing_user_message():
    seed = build_kb_seed_block([{"chunk_id": "c1", "title": "算法课", "text": "贪心。"}])

    users = _run_loop(seed)

    assert len(users) == 1, users
    assert users[0]["content"].startswith("什么是 Dijkstra？")
    assert users[0]["content"].count(KB_CONTEXT_HEADER) == 1


def test_without_a_seed_the_user_message_is_untouched():
    users = _run_loop(None)

    assert users[0]["content"] == "什么是 Dijkstra？"


# --- W1 E12：预检索的触发面与「失败即没有」 -----------------------------------


def test_kb_seed_is_requested_for_knowledge_questions_not_practice():
    from web.backend.routers.chat import _wants_kb_seed

    assert _wants_kb_seed("什么是 Dijkstra？", has_document_scope=False) is True
    assert _wants_kb_seed("讲讲贪心和动态规划的区别", has_document_scope=False) is True
    assert _wants_kb_seed("解释一下", has_document_scope=False) is True
    # 选了资料就算知识型追问。
    assert _wants_kb_seed("这段怎么看", has_document_scope=True) is True
    # 出题轮不塞证据（练习走服务端绑定的卡片）。
    assert _wants_kb_seed("根据资料出 5 道题", has_document_scope=True) is False
    # 太短、或不像在问知识，就不预检索。
    assert _wants_kb_seed("嗯", has_document_scope=False) is False
    assert _wants_kb_seed("今天心情不错", has_document_scope=False) is False


def test_kb_seed_retrieval_failure_is_swallowed(monkeypatch):
    """预检索只是优化：失败就当没有，绝不能拖垮这一轮。"""
    import rag.retriever as retriever
    from web.backend.routers.chat import _kb_seed_for

    def boom(*args, **kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(retriever, "search_index", boom)

    assert _kb_seed_for("什么是 Dijkstra？", workspace=".", config={}, has_document_scope=False) == ""


def test_kb_seed_uses_retrieved_hits(monkeypatch):
    import rag.retriever as retriever
    from web.backend.routers.chat import _kb_seed_for

    calls: list[tuple] = []

    def fake_search(workspace, query, top_k=5, config=None, mode="auto"):
        calls.append((workspace, query, top_k))
        return [{"chunk_id": "c1", "title": "算法课", "text": "贪心策略。"}]

    monkeypatch.setattr(retriever, "search_index", fake_search)

    block = _kb_seed_for("什么是 Dijkstra？", workspace="/ws", config={}, has_document_scope=False)

    assert block.startswith(KB_CONTEXT_HEADER)
    assert "c1" in block
    assert calls and calls[0][0] == "/ws", calls


def test_kb_seed_is_not_retrieved_for_practice_turns(monkeypatch):
    import rag.retriever as retriever
    from web.backend.routers.chat import _kb_seed_for

    def boom(*args, **kwargs):
        raise AssertionError("practice turns must not pre-retrieve")

    monkeypatch.setattr(retriever, "search_index", boom)

    assert _kb_seed_for("根据资料出 5 道题", workspace=".", config={}, has_document_scope=True) == ""


def test_system_blocks_are_byte_stable_across_turns():
    """W1 E12：system 具名块在同一会话里**逐字节稳定**（缓存友好，diff 才有意义）。

    两次独立组装（同样的输入）必须产出完全相同的 system 消息序列。
    """
    from core.agent_loop import AgentLoop
    from core.session import Session
    from core.skills import SKILLS_PROMPT_MARKER
    from providers.types import LLMResponse

    class _LLM:
        def complete(self, messages, tools=None):
            return LLMResponse(content="ok")

        def get_name(self):
            return "mock"

    def _system_messages():
        session = Session.new(".")
        AgentLoop(
            _LLM(), session,
            skills_prompt=f"{SKILLS_PROMPT_MARKER}\n技能目录",
        ).run("你好")
        return [(m["role"], m["content"]) for m in session.messages if m["role"] == "system"]

    first = _system_messages()
    second = _system_messages()

    assert first == second
    assert len(first) >= 2, first  # 基础块 + 技能块

