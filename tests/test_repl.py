import re
import time

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _plain(text: str) -> str:
    """Strip ANSI SGR sequences for substring assertions."""
    return _ANSI_RE.sub("", text)


from cli.repl import REPL, SlashCommandCompleter
from core.session import Session
from providers.types import LLMResponse, LLMStreamChunk, ToolCallDelta
from tools.base import TOOL_REGISTRY, TOOL_SCHEMAS, ToolResult, register_tool


class DummyProvider:
    def complete(self, messages, tools=None):
        return LLMResponse(content="ok")

    def get_name(self):
        return "dummy"


class SlowProvider:
    """Provider that sleeps longer than any reasonable timeout."""

    def __init__(self, delay=10):
        self.delay = delay

    def complete(self, messages, tools=None):
        time.sleep(self.delay)
        return LLMResponse(content="done")

    def get_name(self):
        return "slow"


class StreamingProvider:
    def __init__(self, chunk_groups):
        self.chunk_groups = list(chunk_groups)
        self.call_count = 0

    def complete_stream(self, messages, tools=None):
        chunks = self.chunk_groups[min(self.call_count, len(self.chunk_groups) - 1)]
        self.call_count += 1
        yield from chunks

    def complete(self, messages, tools=None):
        raise AssertionError("streaming provider should use complete_stream")

    def get_name(self):
        return "streaming"


class DelayedStreamingProvider(StreamingProvider):
    def __init__(self, chunk_groups, delay=0.08):
        super().__init__(chunk_groups)
        self.delay = delay

    def complete_stream(self, messages, tools=None):
        chunks = self.chunk_groups[min(self.call_count, len(self.chunk_groups) - 1)]
        self.call_count += 1
        for chunk in chunks:
            time.sleep(self.delay)
            yield chunk


def test_repl_uses_terminal_cell_width_for_cjk_partial_clear():
    repl = REPL()

    assert repl._terminal_cell_width("知识🐱") == 6


def test_repl_initialize_renders_rich_startup(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test", "max_messages": 3},
    }

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: DummyProvider())
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()

    output = capsys.readouterr().out
    assert "bobodan" in output
    assert "session" in output
    assert "model" in output
    assert "save dir" in output
    assert ".session-test" in output
    assert "Type / for suggestions" in output
    assert "╔" not in output
    assert repl.tool_count == 1
    assert repl.session.max_messages == 3


def test_repl_load_session_updates_agent_session(tmp_path, monkeypatch):
    save_dir = tmp_path / "sessions"
    loaded_cwd = tmp_path / "workspace"
    loaded_cwd.mkdir()

    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": str(save_dir), "max_messages": 5},
    }

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: DummyProvider())
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()

    loaded_session = Session.new(str(loaded_cwd), max_messages=5)
    loaded_session.add_message("user", "hello")
    save_dir.mkdir(parents=True, exist_ok=True)
    loaded_session.save_to_file(str(save_dir / f"{loaded_session.session_id}.json"))

    repl.load_session(loaded_session.session_id, announce=False)

    assert repl.session.session_id == loaded_session.session_id
    assert repl.agent.session.session_id == loaded_session.session_id
    assert repl.session.cwd == str(loaded_cwd)
    assert repl.resumed_session is True


def test_repl_status_output(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test", "max_messages": 4},
    }

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: DummyProvider())
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.print_status()

    output = capsys.readouterr().out
    assert "运行状态:" in output or "Runtime Status:" in output
    assert "minimax" in output
    assert "MiniMax-Text-01" in output
    assert ".session-test" in output


def test_repl_timeout_does_not_modify_session(monkeypatch, capsys):
    """On timeout, the main session should not be modified."""
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 1},
    }

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: SlowProvider(delay=10))
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    messages_before = len(repl.session.messages)

    repl.run_agent("hello")

    # Session should NOT have the user message added
    assert len(repl.session.messages) == messages_before
    output = capsys.readouterr().out
    assert "timeout" in output.lower()
    assert "session not modified" in output.lower()


def test_repl_success_commits_session(monkeypatch, capsys):
    """On success, the main session should have the new messages."""
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: DummyProvider())
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()

    repl.run_agent("hello")

    # Session should end with user message + assistant response
    assert repl.session.messages[-2]["role"] == "user"
    assert repl.session.messages[-2]["content"] == "hello"
    assert repl.session.messages[-1]["role"] == "assistant"
    assert repl.session.messages[-1]["content"] == "ok"


def test_repl_streaming_strips_markdown_and_ends_with_newline(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = StreamingProvider([
        [
            LLMStreamChunk(content_delta="我目前有以下 **5 个技能**：\n"),
            LLMStreamChunk(content_delta="| 技能名称 | 功能描述 |\n|---|---|\n| **aihot** | AI 资讯查询 |\n"),
            LLMStreamChunk(content_delta="- “帮我查一下今天 AI 圈有什么新闻”"),
        ]
    ])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("你有哪些 skills")

    output = capsys.readouterr().out
    assert "**" not in output
    assert "|---|---|" not in output
    assert "技能名称" in output
    assert "功能描述" in output
    assert "aihot" in output
    assert "AI 资讯查询" in output
    assert output.endswith("\n")


def test_repl_streaming_shows_tool_calls_by_default(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = StreamingProvider([
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="call_1", name="list_dir", arguments='{"path":"."}'),
            ]),
        ],
        [
            LLMStreamChunk(content_delta="done"),
        ],
    ])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "list_dir"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("列出当前目录")

    output = capsys.readouterr().out
    assert "list_dir" in output
    assert "done" in output


def test_repl_streaming_renders_user_message_panel(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = StreamingProvider([
        [
            LLMStreamChunk(content_delta="hello"),
        ]
    ])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("hello")

    output = capsys.readouterr().out
    assert "hello" in output


def test_repl_streaming_does_not_leak_prompt_into_body(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = StreamingProvider([
        [
            LLMStreamChunk(content_delta="first line\n"),
            LLMStreamChunk(content_delta="- second line"),
        ]
    ])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("hello")

    output = capsys.readouterr().out
    assert "first line" in output
    assert "second line" in output
    assert "bobodan:" not in output
    assert "Thinking" in output


def test_repl_streaming_does_not_restart_thinking_after_text_starts(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = DelayedStreamingProvider([
        [
            LLMStreamChunk(content_delta="alpha\n"),
            LLMStreamChunk(content_delta="beta\n"),
            LLMStreamChunk(content_delta="gamma"),
        ]
    ], delay=1.3)

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("hello")

    output = _plain(capsys.readouterr().out)
    assert "alpha" in output
    assert "beta" in output
    assert "gamma" in output
    after_text = output[output.index("alpha"):]
    assert "Thinking" not in after_text
    assert "Checking" not in after_text
    assert "Working" not in after_text
    assert "Drafting" not in after_text
    assert "Polishing" not in after_text


def test_repl_streaming_preserves_lines_split_across_chunks(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "deepseek",
            "providers": {
                "deepseek": {
                    "model": "deepseek-v4-flash",
                    "api_key_env": "DEEPSEEK_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = DelayedStreamingProvider([
        [
            LLMStreamChunk(content_delta="我可以帮你"),
            LLMStreamChunk(content_delta="做这些：\n"),
            LLMStreamChunk(content_delta="- 学习"),
            LLMStreamChunk(content_delta="计划\n"),
        ]
    ])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("你可以帮我干什么")

    output = capsys.readouterr().out
    assert "我可以帮你做这些：" in output
    assert "学习计划" in output


def test_repl_streaming_hides_think_content_from_body(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = StreamingProvider([
        [
            LLMStreamChunk(content_delta="<think>planning tools</think>answer body"),
        ]
    ])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    capsys.readouterr()

    repl.run_agent("hello")

    output = capsys.readouterr().out
    assert "answer body" in output
    # Think tags are stripped from streaming output
    assert "planning tools" not in output


def test_repl_streaming_preserves_mcp_prompt(monkeypatch, capsys):
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    provider = StreamingProvider([[LLMStreamChunk(content_delta="ok")]])

    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])

    repl = REPL(config_path="config.yaml")
    repl.initialize()
    repl.mcp_prompt = "## MCP Servers\n- `amap`: 12 tools"
    capsys.readouterr()

    repl.run_agent("hello")

    system_text = "\n".join(
        message.get("content", "")
        for message in repl.session.messages
        if message.get("role") == "system"
    )
    assert "## MCP Servers" in system_text
    assert "`amap`: 12 tools" in system_text


def test_ui_command_toggles_tool_display(capsys):
    repl = REPL()

    repl.handle_ui_command("")
    output = capsys.readouterr().out
    assert "UI Settings" in output
    assert "on" in output

    repl.handle_ui_command("tools on")
    output = capsys.readouterr().out
    assert "enabled" in output
    assert repl.show_tool_calls is True

    repl.handle_ui_command("tools off")
    output = capsys.readouterr().out
    assert "disabled" in output
    assert repl.show_tool_calls is False


def test_kb_commands_sync_status_search_graph_and_reset(tmp_path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Dijkstra.md").write_text(
        """---
course: 数据结构
chapter: 图
tags: [algorithm]
---

# Dijkstra 算法

Dijkstra solves shortest path problems with [[图]] and [[优先队列]].
""",
        encoding="utf-8",
    )

    repl = REPL()
    repl.set_session(Session.new(str(tmp_path)))

    repl.handle_kb_command("sync vault")
    sync_output = capsys.readouterr().out
    assert "Knowledge base synced" in sync_output
    assert (tmp_path / ".knowledge" / "rag_index.json").exists()

    repl.handle_kb_command("status")
    status_output = capsys.readouterr().out
    assert "Knowledge Base Status" in status_output
    assert "chunks" in status_output

    repl.handle_kb_command("search shortest path")
    search_output = capsys.readouterr().out
    assert "RAG Search Results" in search_output
    assert "obsidian/Dijkstra.md" in search_output

    repl.handle_kb_command("graph Dijkstra 算法")
    graph_output = capsys.readouterr().out
    assert "Graph Query" in graph_output
    assert "优先队列" in graph_output

    repl.handle_kb_command("reset --yes")
    reset_output = capsys.readouterr().out
    assert "Knowledge base reset" in reset_output
    assert not (tmp_path / ".knowledge").exists()


def test_kb_reset_requires_yes(tmp_path, capsys):
    knowledge_dir = tmp_path / ".knowledge"
    knowledge_dir.mkdir()

    repl = REPL()
    repl.set_session(Session.new(str(tmp_path)))
    repl.handle_kb_command("reset")

    output = capsys.readouterr().out
    assert "reset --yes" in output
    assert knowledge_dir.exists()


def test_slash_command_palette_for_empty_command(capsys):
    repl = REPL()
    repl.handle_command("")

    output = capsys.readouterr().out
    assert "Slash commands" in output
    assert "/kb sync" in output
    assert "/help" in output


def test_slash_command_completer_suggests_kb_commands():
    pytest = __import__("pytest")
    prompt_document = pytest.importorskip("prompt_toolkit.document").Document

    completer = SlashCommandCompleter()
    completions = list(completer.get_completions(prompt_document("/kb s"), None))
    texts = [item.text for item in completions]

    assert "/kb sync " in texts
    assert "/kb search " in texts
    assert "/kb status" in texts


def test_repl_print_response_renders_markdown(capsys):
    repl = REPL()
    repl.print_response("### 标题\n\n- 使用 `rag_search`\n\n```text\nhello\n```")

    output = capsys.readouterr().out
    assert "###" not in output
    assert "```" not in output
    assert "标题" in output
    assert "rag_search" in output


# --- L3: B-lite active-line structure (Q8) ----------------------------------
#
# These tests assert structural properties of the B-lite state machine:
#   - the active line is sealed on interrupt events
#   - the spinner frame is rewritten in place on each tick
#   - the low-noise mode (`show_tool_calls=False`) hides success events but
#     still surfaces errors
# They do NOT call a real LLM, do NOT sleep, and do NOT assert on the full
# stdout string — only on substring presence and ordering.


def _make_repl_for_tool_event(monkeypatch, provider):
    """Create a REPL wired to a mock streaming provider for tool-event tests."""
    config = {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "model": "MiniMax-Text-01",
                    "api_key_env": "MINIMAX_API_KEY",
                }
            },
        },
        "session": {"save_dir": ".session-test"},
        "agent": {"timeout": 30},
    }
    monkeypatch.setattr("cli.repl.ProviderFactory.load_config", lambda path: config)
    monkeypatch.setattr("cli.repl.ProviderFactory.create", lambda provider_config, agent_config: provider)
    monkeypatch.setattr("cli.repl.get_tools_schema", lambda: [{"function": {"name": "read_file"}}])
    repl = REPL(config_path="config.yaml")
    repl.initialize()
    return repl


def test_b_lite_seal_on_assistant_delta(monkeypatch, capsys, tmp_path):
    """A tool call followed by a text delta must put the result and the text
    on separate lines (the active line is sealed when the text arrives)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hi.txt").write_text("hi", encoding="utf-8")
    provider = StreamingProvider([
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="c1", name="read_file", arguments='{"path":"hi.txt"}'),
            ]),
        ],
        [LLMStreamChunk(content_delta="after-text")],
    ])
    repl = _make_repl_for_tool_event(monkeypatch, provider)
    capsys.readouterr()

    repl.run_agent("read hi")

    output = _plain(capsys.readouterr().out)
    # Tool result line with the elapsed marker is present
    assert "✓ read_file" in output
    # The assistant text after the tool call is present (not concatenated to the
    # active line)
    assert "after-text" in output
    # The success line comes before the streamed text
    assert output.index("✓ read_file") < output.index("after-text")


def test_b_lite_seal_on_new_tool_start(monkeypatch, capsys, tmp_path):
    """Two consecutive tool calls in one turn each get their own result line."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    provider = StreamingProvider([
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="c1", name="read_file", arguments='{"path":"a.txt"}'),
                ToolCallDelta(index=1, id="c2", name="read_file", arguments='{"path":"b.txt"}'),
            ]),
        ],
        [LLMStreamChunk(content_delta="done")],
    ])
    repl = _make_repl_for_tool_event(monkeypatch, provider)
    capsys.readouterr()

    repl.run_agent("read both")

    output = _plain(capsys.readouterr().out)
    # Two distinct success lines (each on its own line)
    occurrences = output.count("✓ read_file")
    assert occurrences >= 2, f"expected ≥2 success lines, got {occurrences}"
    # The streamed text comes after both result lines
    first = output.index("✓ read_file")
    second = output.index("✓ read_file", first + 1)
    assert output.index("done") > second


def test_b_lite_active_line_in_place_update(capsys):
    """The active line is rewritten in place: each call uses the same
    carriage-return + clear-line escape sequence, so the spinner frame on
    the visible line changes while only one line of terminal real estate
    is used."""
    repl = REPL()
    # Manually drive the active line state machine without a real run.
    repl._active_line_kind = "tool"
    repl._active_tool_name = "read_file"
    repl._active_tool_summary = "/path/to/file.md"
    repl._active_tool_start_ts = 0.0
    repl._active_tool_indent = "  "

    from cli.tool_display import SPINNER_FRAMES

    seen_frames: list[str] = []
    for i, frame in enumerate(SPINNER_FRAMES[:4]):
        text = repl._b_render_tool_start(frame, "read_file", "/path/to/file.md", "  ")
        repl._b_write_active_line(text)
        seen_frames.append(frame)

    output = capsys.readouterr().out
    # The in-place rewrite sequence (\r\033[2K) appears for every update
    rewrite_count = output.count("\r\033[2K")
    assert rewrite_count >= len(seen_frames), (
        f"expected ≥{len(seen_frames)} rewrite sequences, got {rewrite_count}"
    )
    # All four frames appear in the (ANSI-stripped) output
    plain = _plain(output)
    for f in seen_frames:
        assert f in plain


def test_b_lite_thinking_line_spinner_advances():
    repl = REPL()

    first = _plain(repl._b_render_thinking(0.0))
    second = _plain(repl._b_render_thinking(0.1))

    assert first != second


def test_b_lite_coalesce_summary_uses_wall_clock_not_tool_duration(monkeypatch, capsys, tmp_path):
    """Four consecutive successful calls should flush a positive total, not a
    negative number caused by mixing monotonic timestamps with per-tool duration."""
    monkeypatch.chdir(tmp_path)
    for name in ["a.txt", "b.txt", "c.txt", "d.txt"]:
        (tmp_path / name).write_text(name, encoding="utf-8")
    provider = StreamingProvider([
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="c1", name="read_file", arguments='{"path":"a.txt"}'),
                ToolCallDelta(index=1, id="c2", name="read_file", arguments='{"path":"b.txt"}'),
                ToolCallDelta(index=2, id="c3", name="read_file", arguments='{"path":"c.txt"}'),
                ToolCallDelta(index=3, id="c4", name="read_file", arguments='{"path":"d.txt"}'),
            ]),
        ],
        [LLMStreamChunk(content_delta="done")],
    ])
    repl = _make_repl_for_tool_event(monkeypatch, provider)
    capsys.readouterr()

    repl.run_agent("read four")

    output = _plain(capsys.readouterr().out)
    assert "✓ read_file ×4 total" in output
    assert "total -" not in output


def test_b_lite_delegate_success_is_recorded_in_parent_scope(monkeypatch, capsys, tmp_path):
    """Outer delegate success must not increment the specialist's inner tool run."""
    monkeypatch.chdir(tmp_path)

    def delegate_fake():
        return ToolResult(
            ok=True,
            content="delegate summary",
            data={
                "display_events": [
                    {"type": "tool_start", "tool_name": "read_file", "args": {"path": "a.md"}},
                    {"type": "tool_end", "tool_name": "read_file", "ok": True, "content": "a", "elapsed": 0.1},
                    {"type": "tool_start", "tool_name": "read_file", "args": {"path": "b.md"}},
                    {"type": "tool_end", "tool_name": "read_file", "ok": True, "content": "b", "elapsed": 0.1},
                ]
            },
        )

    TOOL_REGISTRY.pop("delegate_fake", None)
    TOOL_SCHEMAS[:] = [
        schema for schema in TOOL_SCHEMAS
        if schema.get("function", {}).get("name") != "delegate_fake"
    ]
    register_tool(
        "delegate_fake",
        "fake delegate",
        {"type": "object", "properties": {}},
        delegate_fake,
    )
    try:
        provider = StreamingProvider([
            [
                LLMStreamChunk(tool_call_deltas=[
                    ToolCallDelta(index=0, id="c1", name="delegate_fake", arguments="{}"),
                ]),
            ],
            [LLMStreamChunk(content_delta="done")],
        ])
        repl = _make_repl_for_tool_event(monkeypatch, provider)
        capsys.readouterr()

        repl.run_agent("delegate")

        output = _plain(capsys.readouterr().out)
        assert "✓ delegate_fake ×3" not in output
        assert "✓ delegate_fake" in output
    finally:
        TOOL_REGISTRY.pop("delegate_fake", None)
        TOOL_SCHEMAS[:] = [
            schema for schema in TOOL_SCHEMAS
            if schema.get("function", {}).get("name") != "delegate_fake"
        ]


def test_b_lite_off_mode_hides_success_keeps_error(monkeypatch, capsys, tmp_path):
    """In low-noise mode (show_tool_calls=False), success tool events are
    hidden but the error line (✗) is still surfaced for the user's safety."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
    # Two turns: first a successful read_file, then a failing read_file.
    provider = StreamingProvider([
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="c1", name="read_file", arguments='{"path":"ok.txt"}'),
            ]),
        ],
        [LLMStreamChunk(content_delta="ok-done")],
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="c2", name="read_file", arguments='{"path":"missing.md"}'),
            ]),
        ],
        [LLMStreamChunk(content_delta="err-done")],
    ])
    repl = _make_repl_for_tool_event(monkeypatch, provider)
    repl.show_tool_calls = False
    capsys.readouterr()

    repl.run_agent("read ok")
    output_ok = _plain(capsys.readouterr().out)

    repl.run_agent("read missing")
    output_err = _plain(capsys.readouterr().out)

    # Successful turn: the tool's args summary and ✓ marker are NOT in the
    # output. The thinking line still shows but with no tool-specific text.
    assert "ok.txt" not in output_ok
    assert "✓" not in output_ok
    # Streamed text is still shown
    assert "ok-done" in output_ok
    # Thinking line is still rendered (it is the only visible feedback in
    # off mode between events).
    assert "Thinking" in output_ok

    # Error turn: ✗ marker and the file path are present even in off mode.
    assert "✗ read_file" in output_err
    assert "missing.md" in output_err
    # Streamed text after the error is still shown
    assert "err-done" in output_err
