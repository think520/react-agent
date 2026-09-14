"""Unit tests for core.memory_injector (AG-3.1)."""

import pytest

from core.memory_injector import (
    DEFAULT_TOKEN_BUDGET,
    MemoryInjector,
    estimate_tokens,
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    # Each test gets a fresh BOBODAN_HOME so global personal knowledge does not
    # leak between tests.
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "bobodan-home"))


def test_estimate_tokens_counts_cjk_conservatively():
    """P0-7: `len // 4` under-counted Chinese by roughly 4x.

    Measured on this project own corpus with cl100k_base: 25 Chinese
    characters are 29 tokens, 54 ASCII characters are 9. The old formula
    returned 6 for the Chinese sample, so `should_compact` fired late and a
    1500-token memory budget admitted several thousand tokens.
    """
    chinese = "大模型训练依赖的算力、GPU 集群与并行计算示意图"
    estimate = estimate_tokens(chinese)
    assert estimate >= len(chinese), (estimate, len(chinese))
    assert estimate <= len(chinese) * 2, (estimate, len(chinese))

    ascii_text = "the model training depends on compute and gpu clusters"
    ascii_estimate = estimate_tokens(ascii_text)
    assert ascii_estimate <= len(ascii_text) // 3, (ascii_estimate, len(ascii_text))

def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("x" * 8) == 2


def test_retrieve_empty_store(tmp_path):
    injector = MemoryInjector(str(tmp_path / "lib"))
    content, refs = injector.retrieve("anything")
    assert content == ""
    assert refs == []


def test_retrieve_returns_seeded_knowledge(tmp_path):
    from memory.personal_store import PersonalKnowledgeStore

    workspace = str(tmp_path / "lib")
    store = PersonalKnowledgeStore(workspace)
    store.create_item(
        scope="global", kind="preference", title="称呼", content="请叫我小明",
        pinned=True,
    )
    store.create_item(
        scope="library", kind="course_insight", title="Transformer", content="注意力机制",
    )

    injector = MemoryInjector(workspace)
    content, refs = injector.retrieve("Transformer")

    assert "称呼" in content
    assert any(item["title"] == "称呼" for item in refs)


def test_retrieve_stays_within_token_budget(tmp_path):
    from memory.personal_store import PersonalKnowledgeStore

    workspace = str(tmp_path / "lib")
    store = PersonalKnowledgeStore(workspace)
    store.create_item(
        scope="global", kind="preference", title="偏好", content="很长的内容" * 500,
        pinned=True,
    )

    injector = MemoryInjector(workspace, token_budget=50)
    content, _refs = injector.retrieve("偏好")

    assert estimate_tokens(content) <= 50


def test_build_injection_none_when_empty(tmp_path):
    injector = MemoryInjector(str(tmp_path / "lib"))
    assert injector.build_injection("query") is None


def test_build_injection_includes_marker(tmp_path):
    from memory.personal_store import PersonalKnowledgeStore

    workspace = str(tmp_path / "lib")
    PersonalKnowledgeStore(workspace).create_item(
        scope="global", kind="goal", title="目标", content="通过考试", pinned=True,
    )
    injector = MemoryInjector(workspace)
    injection = injector.build_injection("目标")

    assert injection is not None
    assert "<!-- bobodan:confirmed-personal-knowledge -->" in injection
    assert "通过考试" in injection


def test_before_turn_uses_session_workspace(tmp_path):
    from memory.personal_store import PersonalKnowledgeStore

    workspace = str(tmp_path / "lib")
    PersonalKnowledgeStore(workspace).create_item(
        scope="global", kind="goal", title="目标", content="背单词", pinned=True,
    )
    injector = MemoryInjector("/wrong/path")
    session = type("S", (), {"workspace_root": workspace})()

    injection = injector.before_turn(session, "目标")
    assert injection is not None
    assert "背单词" in injection


def test_default_budget_is_1500():
    assert DEFAULT_TOKEN_BUDGET == 1500
