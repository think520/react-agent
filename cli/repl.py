import copy
import json
import os
import queue
import shlex
import shutil
import sys
import threading
import time
from dotenv import load_dotenv

load_dotenv()

from core.agent_loop import AgentLoop
from cli.markdown_render import (
    print_error,
    print_kv_panel,
    print_markdown,
    print_notice,
    print_search_table,
    print_startup_panel,
    print_success,
    console as rich_console,
)
from core.memory import MemoryManager
from core.session import Session
from core.skills import build_skills_system_prompt, list_skills, find_skill_by_name
from providers.factory import ProviderFactory
from tools import get_tools_schema
from tools.graph_query import graph_query
from tools.obsidian_tool import obsidian_sync
from tools.rag_search import rag_search

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import ANSI
except ImportError:
    PromptSession = None
    Completer = object
    Completion = None
    ANSI = None

THINK_START = "<think>"
THINK_END = "</think>"

from cli.tool_display import (
    SPINNER_FRAMES as THINK_FRAMES,
    THINK_VERBS,
    spinner_frame_at,
    think_verb_color_at,
    think_verb_at,
    summarize_tool_args,
    CoalescerStack,
)

# Module-level ANSI palette for B-lite (class-level constants can't be
# referenced inside instance method bodies in Python).
_B_CYAN = "\033[38;5;39m"
_B_ORANGE = "\033[38;5;209m"
_B_GREEN = "\033[32m"
_B_RED = "\033[31m"
_B_DIM = "\033[2m"
_B_RESET = "\033[0m"

ALL_COMMANDS = ["help", "status", "cwd", "tools", "skill", "kb", "quiz", "learning", "memory", "wiki", "mcp", "ui", "model", "specialists", "trace", "exit", "quit", "session"]

COMMAND_HINTS = [
    ("/help", "显示命令帮助"),
    ("/status", "运行状态"),
    ("/cwd", "当前工作目录"),
    ("/tools", "可用工具列表"),
    ("/kb status", "知识库状态"),
    ("/kb sync ", "同步 Obsidian vault"),
    ("/kb search ", "本地 RAG 检索"),
    ("/kb graph ", "知识图谱查询"),
    ("/kb reset --yes", "删除生成的知识库索引"),
    ("/mcp", "MCP server 状态"),
    ("/mcp status", "MCP 详细状态"),
    ("/mcp restart ", "重连 MCP server"),
    ("/mcp tools ", "列出 server 的 tools"),
    ("/mcp reload", "重读 config.yaml"),
    ("/skill list", "可用技能列表"),
    ("/skill run ", "执行技能"),
    ("/quiz generate <topic>", "生成练习题"),
    ("/quiz start [count]", "开始一轮练习"),
    ("/quiz wrong", "错题本"),
    ("/quiz weak", "薄弱点分析"),
    ("/quiz stats", "题库统计"),
    ("/learning plan <goal>", "生成学习计划"),
    ("/learning progress", "掌握度概览"),
    ("/learning review", "今日复习清单"),
    ("/learning mark <concept> <status>", "手动设置掌握度"),
    ("/learning plans", "已保存的学习计划"),
    ("/learning today", "今日任务 + 复习"),
    ("/memory list", "已保存的记忆"),
    ("/memory search ", "搜索记忆"),
    ("/memory show ", "查看记忆详情"),
    ("/memory forget ", "删除记忆"),
    ("/memory stats", "记忆统计"),
    ("/wiki init ", "初始化 wiki 目录"),
    ("/wiki ingest ", "编译源文件为 wiki 页面"),
    ("/wiki lint", "wiki 健康检查"),
    ("/wiki status", "wiki 统计"),
    ("/ui", "显示 UI 设置"),
    ("/ui tools on", "显示工具调用"),
    ("/ui tools off", "隐藏工具调用"),
    ("/model", "当前激活的 provider / 模型"),
    ("/model list", "列出所有可用的 provider"),
    ("/model use ", "切换到指定 provider"),
    ("/specialists", "列出所有 specialist"),
    ("/specialists status", "最近 specialist 调用"),
    ("/specialists tools ", "specialist 的工具集"),
    ("/session list", "已保存的会话"),
    ("/session save ", "保存会话（可选命名）"),
    ("/session resume", "选择会话恢复"),
    ("/session load ", "加载会话（ID/名称）"),
    ("/trace", "最近 agent run 记录"),
    ("/trace last", "最近一次 run 详情"),
    ("/exit", "退出"),
]


class SlashCommandCompleter(Completer):
    """Prompt-toolkit completer for slash commands."""

    def get_completions(self, document, complete_event):
        if Completion is None:
            return
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        matches = [(cmd, meta) for cmd, meta in COMMAND_HINTS if cmd.startswith(text)]
        if text == "/":
            matches = COMMAND_HINTS
        for command, meta in matches:
            yield Completion(command, start_position=-len(text), display=command, display_meta=meta)


class REPL:
    """bobodan REPL interface."""

    def __init__(self, config_path: str = "config.yaml", resume_session_id: str | None = None):
        self.config_path = config_path
        self.resume_session_id = resume_session_id
        self.session = None
        self.agent = None
        self.running = False
        self.config = {}
        self.session_save_dir = ".session"
        self.session_max_messages = None
        self.default_provider = "unknown"
        self.model_name = "unknown"
        self.active_provider = "unknown"
        self.active_model = "unknown"
        self.api_key_env = ""
        self.tool_count = 0
        self.resumed_session = False
        self.skills_prompt = None
        self.skills_dir = "skills"
        self.skill_count = 0
        self.memory_prompt = None
        self.memory_manager = None
        self.memory_count = 0
        self.agent_timeout = 300  # seconds, per-turn timeout
        self.prompt_session = None
        self.show_tool_calls = True
        self.rag_router = None
        self.rag_backend_info = {}
        self.mcp_prompt = None
        self.agent_registry = None
        # B-lite active-line state (reset per run_agent_streaming invocation)
        self._active_line_kind: str = "none"  # "none" | "thinking" | "tool"
        self._active_tool_name: str = ""
        self._active_tool_summary: str = ""
        self._active_tool_start_ts: float = 0.0
        self._active_tool_indent: str = "  "  # 2 for main, 4 for specialist
        self._coalescer_stack: CoalescerStack = CoalescerStack()

    def initialize(self):
        """Initialize the agent with config."""
        try:
            self.config = ProviderFactory.load_config(self.config_path)
            llm_config = self.config.get("llm", {})
            self.default_provider = llm_config.get("default_provider", "unknown")
            self.active_provider = self.default_provider
            provider_info = llm_config.get("providers", {}).get(self.default_provider, {})
            self.model_name = provider_info.get("model", "unknown")
            self.active_model = self.model_name
            self.api_key_env = provider_info.get("api_key_env", "")

            session_config = self.config.get("session", {})
            self.session_save_dir = session_config.get("save_dir", ".session")
            self.session_max_messages = session_config.get("max_messages")

            agent_config = self.config.get("agent", {})
            self.agent_timeout = agent_config.get("timeout", 300)

            # Skills configuration
            skills_config = self.config.get("skills", {})
            if skills_config.get("enabled", True):
                self.skills_dir = skills_config.get("dir", "skills")
                self.skills_prompt = build_skills_system_prompt(self.skills_dir)
                self.skill_count = len(list_skills(self.skills_dir))

            # Memory configuration
            memory_config = self.config.get("memory", {})
            if memory_config.get("enabled", True):
                memory_dir = memory_config.get("dir", ".bobodan")
                self.memory_manager = MemoryManager(os.getcwd(), base_dir=memory_dir)
                self.memory_prompt = self.memory_manager.build_memory_prompt()
                self.memory_count = len(self.memory_manager.list_entries())

            # RAG embedding backend probe
            rag_config = self.config.get("rag") or {}
            embedding_backend = rag_config.get("embedding_backend", "auto")
            if embedding_backend != "local":
                from rag.router import VectorStoreRouter
                try:
                    self.rag_router = VectorStoreRouter(os.getcwd(), self.config)
                    info = self.rag_router.get_backend_info()
                    self.rag_backend_info = info
                except Exception:
                    self.rag_router = None
                    self.rag_backend_info = {"active": "sparse", "fallback": None, "mode": "auto"}
            else:
                self.rag_router = None
                self.rag_backend_info = {"active": "sparse", "fallback": None, "mode": "local"}

            # MCP server registration (must run before AgentLoop so its
            # tools_schema snapshot includes the MCP tools).
            try:
                from tools.mcp import register_mcp_tools
                register_mcp_tools(self.config)
            except Exception as e:
                logger.warning("MCP registration failed: %s", e)

            # Specialist (multi-agent) registration — must run before AgentLoop
            # so delegate_* tools are in the snapshot.
            try:
                from agents.registry import register_builtin_specialists
                from tools.agents import register_delegate_tools
                yaml_section = self.config.get("specialists") or {}
                self.agent_registry = register_builtin_specialists(yaml_section)
                register_delegate_tools(
                    self.agent_registry,
                    get_session=lambda: self.session,
                    get_app_config=lambda: self.config,
                )
            except Exception as e:
                logger.warning("Specialist registration failed: %s", e)
                self.agent_registry = None

            # Build the MCP status prompt segment for the LLM system prompt.
            try:
                from mcp_client.prompt import build_mcp_status_prompt
                from tools.mcp import get_mcp_manager as _get_mcp_mgr
                self.mcp_prompt = build_mcp_status_prompt(_get_mcp_mgr())
            except Exception as e:
                logger.warning("MCP prompt build failed: %s", e)
                self.mcp_prompt = None

            if self.resume_session_id:
                self.load_session(self.resume_session_id, announce=False)
            elif self.session is None:
                self.set_session(Session.new(os.getcwd(), max_messages=self.session_max_messages))
            else:
                self.set_session(self.session)

            self.agent = AgentLoop(
                self._make_active_provider(),
                self.session,
                skills_prompt=self.skills_prompt,
                memory_prompt=self.memory_prompt,
                mcp_prompt=self.mcp_prompt,
            )
            self.tool_count = len(get_tools_schema())
            self.setup_prompt_session()
            self.render_startup()
        except Exception as e:
            self.print_initialization_error(e)
            sys.exit(1)

    def setup_prompt_session(self):
        """Enable live slash-command hints when prompt_toolkit is installed."""
        if PromptSession is None:
            self.prompt_session = None
            return
        try:
            self.prompt_session = PromptSession(
                completer=SlashCommandCompleter(),
                complete_while_typing=True,
            )
        except Exception:
            self.prompt_session = None

    def set_session(self, session: Session, resumed: bool = False) -> None:
        if self.session_max_messages is not None:
            session.max_messages = self.session_max_messages
            session._trim_messages()
        self.session = session
        self.resumed_session = resumed
        if self.agent is not None:
            self.agent.set_session(session)

    def render_startup(self) -> None:
        from tools.mcp import get_mcp_manager
        mgr = get_mcp_manager()
        mcp_line = "disabled"
        if mgr is not None:
            states = mgr.get_all_states()
            connected = sum(1 for s in states.values() if s.state == "connected")
            total = sum(1 for s in states.values() if s.config.enabled)
            n_tools = sum(len(s.tools) for s in states.values() if s.state == "connected")
            mcp_line = f"{connected}/{total} connected, {n_tools} tools"

        print_startup_panel(
            [
                ("session", self.session.session_id),
                ("state", "resumed" if self.resumed_session else "new"),
                ("cwd", self.session.cwd),
                ("workspace", self.session.workspace_root),
                ("model", f"{self.active_provider}/{self.active_model}"),
                ("tools", f"{self.tool_count} registered"),
                ("skills", self.skill_count),
                ("memories", self.memory_count),
                ("mcp", mcp_line),
                ("save dir", self.session_save_dir),
            ]
        )

    def print_initialization_error(self, error: Exception) -> None:
        print()
        print_error(str(error))
        if self.api_key_env and self.api_key_env in str(error):
            print(f"  \033[2;37mHint: set {self.api_key_env} in .env or update {self.config_path}\033[0m")

    def build_prompt(self) -> str:
        cwd_name = os.path.basename(os.path.normpath(self.session.cwd)) or self.session.cwd
        return f"\033[1;37mbobodan\033[0m:\033[38;5;117m{cwd_name}\033[0m> "

    def build_thinking_prompt(self) -> str:
        return "THINK"

    def read_input(self) -> str:
        prompt = self.build_prompt()
        if self.prompt_session is not None and ANSI is not None:
            return self.prompt_session.prompt(ANSI(prompt)).strip()
        return input(prompt).strip()

    def run(self):
        """Start the REPL."""
        self.running = True
        self.initialize()

        while self.running:
            try:
                user_input = self.read_input()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self.handle_command(user_input[1:])
                    continue

                self.run_agent(user_input)

            except KeyboardInterrupt:
                print("\n  \033[90mUse /exit to quit.\033[0m")
            except Exception as e:
                print()
                print_error(str(e))

    def handle_command(self, cmd_line: str):
        parts = cmd_line.strip().split()
        if not parts:
            self.print_command_palette()
            return

        cmd = parts[0]

        if cmd in ["exit", "quit"]:
            self.handle_exit()
            return

        if cmd == "help":
            self.print_help()
            return

        if cmd == "status":
            self.print_status()
            return

        if cmd.startswith("session"):
            self.handle_session_command(cmd_line[len("session"):].strip())
            return

        if cmd == "cwd":
            print(self.session.cwd)
            return

        if cmd == "tools":
            self.print_tools()
            return

        if cmd == "kb":
            self.handle_kb_command(cmd_line[len("kb"):].strip())
            return

        if cmd == "quiz":
            self.handle_quiz_command(cmd_line[len("quiz"):].strip())
            return

        if cmd == "learning":
            self.handle_learning_command(cmd_line[len("learning"):].strip())
            return

        if cmd == "skill":
            self.handle_skill_command(cmd_line[len("skill"):].strip())
            return

        if cmd == "memory":
            self.handle_memory_command(cmd_line[len("memory"):].strip())
            return

        if cmd == "wiki":
            self.handle_wiki_command(cmd_line[len("wiki"):].strip())
            return

        if cmd == "mcp":
            self.handle_mcp_command(cmd_line[len("mcp"):].strip())
            return

        if cmd == "ui":
            self.handle_ui_command(cmd_line[len("ui"):].strip())
            return

        if cmd == "model":
            self.handle_model_command(cmd_line[len("model"):].strip())
            return

        if cmd == "specialists":
            self.handle_specialists_command(cmd_line[len("specialists"):].strip())
            return

        if cmd == "trace":
            self.handle_trace_command(cmd_line[len("trace"):].strip())
            return

        print(f"  \033[1;38;5;208mUnknown command: {cmd}\033[0m")
        print("  Type \033[1;38;5;210m/help\033[0m for available commands")

    def complete(self, text: str, state: int):
        """Tab completion for command input."""
        options = [c for c in ALL_COMMANDS if c.startswith(text)]
        if state < len(options):
            return options[state]
        return None

    def print_command_palette(self):
        print()
        print("  \033[1;37mSlash commands:\033[0m")
        for command, meta in COMMAND_HINTS:
            print(f"  \033[1;38;5;210m  {command:<24}\033[0m {meta}")
        print()

    def _visible_stream_text(self, text: str) -> str:
        """Hide completed or partial <think> blocks while streaming."""
        visible = []
        index = 0
        while index < len(text):
            start = text.find(THINK_START, index)
            if start == -1:
                visible.append(text[index:])
                break
            visible.append(text[index:start])
            end = text.find(THINK_END, start + len(THINK_START))
            if end == -1:
                break
            index = end + len(THINK_END)
        return "".join(visible)

    @staticmethod
    def _terminal_cell_width(text: str) -> int:
        """Return terminal display columns, not Python character count."""
        try:
            from rich.cells import cell_len
            return cell_len(text)
        except Exception:
            import unicodedata

            total = 0
            for ch in text:
                if unicodedata.combining(ch):
                    continue
                if unicodedata.category(ch)[0] == "C":
                    continue
                total += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
            return total

    def _flush_stream_buffer(self, buffer: str, force: bool = False, clear_partial: int = 0) -> tuple[str, bool]:
        """Render complete lines with markdown.

        Args:
            buffer: accumulated text to render.
            force: if True, write remaining partial content without delay.
            clear_partial: number of terminal columns already written as partial preview
                           (will be cleared before re-rendering the full line).

        Returns:
            (remaining_buffer, wrote_something)
        """
        from cli.markdown_render import render_inline, strip_table_separator, is_table_row, DIM, BOLD, RESET, GRAY, CYAN
        import re

        out = rich_console().file
        wrote = False

        # Clear previously written partial preview
        if clear_partial > 0:
            out.write(f"\033[{clear_partial}D\033[K")
            out.flush()

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            stripped = line.strip()

            # Inside code block
            if self._stream_in_code_block:
                if stripped.startswith("```"):
                    self._stream_in_code_block = False
                    continue
                rendered = f"  {GRAY}|{RESET} {CYAN}{line}{RESET}\n"
                out.write(rendered)
                out.flush()
                wrote = True
                continue

            # Opening code fence
            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                rendered = f"  {DIM} code: {lang} {RESET}\n" if lang else f"  {DIM} code {RESET}\n"
                out.write(rendered)
                out.flush()
                self._stream_in_code_block = True
                wrote = True
                continue

            if not stripped:
                out.write("\n")
                out.flush()
                wrote = True
                continue

            # Table separator — skip
            if strip_table_separator(line):
                continue

            # Table data row
            if is_table_row(line):
                cells = [render_inline(c.strip()) for c in stripped.strip("|").split("|")]
                rendered = "  " + "  ".join(cells) + "\n"
            else:
                heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
                if heading:
                    rendered = f"  {BOLD}{render_inline(heading.group(2))}{RESET}\n"
                else:
                    list_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
                    if list_match:
                        indent = " " * (len(list_match.group(1)) + 2)
                        rendered = f"{indent}- {render_inline(list_match.group(2))}\n"
                    else:
                        quote_match = re.match(r"^>\s?(.*)$", line)
                        if quote_match:
                            rendered = f"  {DIM}| {render_inline(quote_match.group(1))}{RESET}\n"
                        else:
                            rendered = f"  {render_inline(line)}\n"

            out.write(rendered)
            out.flush()
            wrote = True

        # Partial line at end
        if force and buffer:
            out.write(buffer)
            out.flush()
            wrote = True
            buffer = ""

        return buffer, wrote

    def _render_thinking_line(self, frame: str, elapsed: float = 0.0) -> str:
        cyan = "\033[38;5;39m"
        dim = "\033[2m"
        reset = "\033[0m"
        verb = think_verb_at(elapsed)
        verb_color = think_verb_color_at(elapsed)
        if elapsed >= 1.0:
            timer = f" {dim}·{reset} {dim}{elapsed:.1f}s{reset}"
        else:
            timer = ""
        return f"  {cyan}{frame}{reset} {verb_color}{verb}{reset}{timer}"

    # --- B-lite active line helpers -----------------------------------------

    _B_TOOL_INDENT_MAIN = "  "
    _B_TOOL_INDENT_SPECIALIST = "    "
    _B_PARTIAL_PREVIEW_MIN_CHARS = 48

    def _b_write_active_line(self, text: str) -> None:
        """Rewrite the current active line in place (no trailing newline)."""
        out = rich_console().file
        out.write(f"\r\033[2K{text}")
        out.flush()

    def _b_seal_active_line(self) -> None:
        """Terminate the current active line with a newline (no-op if none)."""
        if self._active_line_kind == "none":
            return
        out = rich_console().file
        out.write("\n")
        out.flush()
        self._active_line_kind = "none"
        self._active_tool_name = ""
        self._active_tool_summary = ""
        self._active_tool_start_ts = 0.0

    def _b_clear_active_line(self) -> None:
        """Clear the current active line without leaving it in scrollback."""
        if self._active_line_kind == "none":
            return
        out = rich_console().file
        out.write("\r\033[2K")
        out.flush()
        self._active_line_kind = "none"
        self._active_tool_name = ""
        self._active_tool_summary = ""
        self._active_tool_start_ts = 0.0

    def _b_render_thinking(self, elapsed: float) -> str:
        verb = think_verb_at(elapsed)
        verb_color = think_verb_color_at(elapsed)
        if elapsed >= 1.0:
            timer = f" {_B_DIM}·{_B_RESET} {_B_DIM}{elapsed:.1f}s{_B_RESET}"
        else:
            timer = ""
        return f"  {_B_CYAN}{spinner_frame_at(elapsed)}{_B_RESET} {verb_color}{verb}{_B_RESET}{timer}"

    def _b_render_tool_start(self, frame: str, name: str, summary: str, indent: str = _B_TOOL_INDENT_MAIN) -> str:
        summary_part = f" {_B_DIM}{summary}{_B_RESET}" if summary else ""
        return f"{indent}{_B_ORANGE}{frame}{_B_RESET} {_B_ORANGE}{name}{_B_RESET}{summary_part}"

    def _b_render_tool_success(self, name: str, summary: str, elapsed: float, indent: str = _B_TOOL_INDENT_MAIN) -> str:
        summary_part = f" {_B_DIM}{summary}{_B_RESET}" if summary else ""
        return f"{indent}{_B_GREEN}✓{_B_RESET} {name}{summary_part} {_B_DIM}({elapsed:.1f}s){_B_RESET}"

    def _b_render_coalesce_marker(self, name: str, count: int, indent: str = _B_TOOL_INDENT_MAIN) -> str:
        return f"{indent}{_B_GREEN}✓{_B_RESET} {name} {_B_DIM}×{count}{_B_RESET}"

    def _b_render_tool_error(self, name: str, msg: str, indent: str = _B_TOOL_INDENT_MAIN) -> str:
        msg_part = f": {_B_DIM}{msg}{_B_RESET}" if msg else ""
        return f"{indent}{_B_RED}✗{_B_RESET} {name}{msg_part}"

    @staticmethod
    def _b_short_error(content: str, limit: int = 60) -> str:
        if not content:
            return ""
        first = content.replace("\n", " ").replace("\r", " ").strip()
        if len(first) > limit:
            return first[: max(0, limit - 1)] + "…"
        return first

    def _b_should_show(self, ok: bool) -> bool:
        """Q7: in low-noise mode, hide success events but always show errors."""
        return self.show_tool_calls or not ok

    def run_agent_streaming(self, user_input: str) -> None:
        """Run agent with B-lite single-active-line UI.

        B-lite invariants:
          - Only one active line at a time (thinking line OR tool spinner)
          - Each tick (100ms) advances the in-place frame/verb on the active line
          - Tool start: seal previous, write spinner (no newline)
          - Tool end success: replace spinner with result line + newline
          - Tool end error: replace spinner with error line + newline
          - Errors always shown (low-noise mode keeps them per Q7)
          - Coalesce tracks consecutive same-name success calls per visual scope
        """
        import time
        from core.agent_loop import AgentLoop
        from core.trace import TraceWriter

        session_copy = copy.deepcopy(self.session)

        # Per-run trace writer: each user input gets its own trace file
        run_trace = None
        try:
            run_trace = TraceWriter(session_copy.session_id, session_copy.workspace_root)
        except Exception:
            pass

        agent_copy = AgentLoop(
            self._make_active_provider(),
            session_copy,
            skills_prompt=self.skills_prompt,
            memory_prompt=self.memory_prompt,
            mcp_prompt=self.mcp_prompt,
            trace_writer=run_trace,
        )

        events: queue.Queue[dict] = queue.Queue()
        done_event = threading.Event()
        error_holder = [None]

        def run_in_thread():
            try:
                for event in agent_copy.run_stream(user_input):
                    events.put(event)
            except Exception as e:
                error_holder[0] = e
            finally:
                done_event.set()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

        out = rich_console().file
        # User input echo (separate from B-lite active line)
        out.write(f"\n  \033[1;37m>\033[0m {user_input}\n")
        out.flush()

        # Reset B-lite per-turn state
        self._active_line_kind = "thinking"
        self._active_tool_name = ""
        self._active_tool_summary = ""
        self._active_tool_start_ts = 0.0
        self._active_tool_indent = self._B_TOOL_INDENT_MAIN
        self._coalescer_stack = CoalescerStack()

        # Initial thinking line (B-lite: write without \n, cursor stays on line)
        self._b_write_active_line(self._b_render_thinking(0.0))

        accumulated = ""
        rendered_text = ""
        stream_buffer = ""
        stream_wrote = False
        response = ""
        start = time.monotonic()
        timed_out = False
        last_tick_frame_index = -1
        self._stream_in_code_block = False
        partial_written = 0
        partial_preview = ""
        delegate_summaries_by_call: dict[str, str] = {}
        assistant_stream_started = False

        def _flush_partial_stream() -> None:
            nonlocal stream_buffer, partial_written, partial_preview
            if partial_preview:
                stream_buffer = partial_preview + stream_buffer
                partial_preview = ""
            if partial_written:
                out.write(f"\033[{partial_written}D\033[K")
                out.flush()
                partial_written = 0
            if stream_buffer:
                stream_buffer, _ = self._flush_stream_buffer(stream_buffer, force=True)

        def _handle_tool_start(tool_name: str, args: dict, indent: str) -> str:
            nonlocal stream_buffer, partial_written, partial_preview, stream_wrote, assistant_stream_started
            nonlocal accumulated, rendered_text
            _flush_partial_stream()
            if stream_wrote and self._active_line_kind == "none":
                out.write("\n")
                out.flush()
            stream_wrote = False
            assistant_stream_started = False
            accumulated = ""
            rendered_text = ""
            self._stream_in_code_block = False
            self._b_seal_active_line()
            ts = time.monotonic()
            flush_payload = self._coalescer_stack.record_start(tool_name, ts)
            if tool_name.startswith("delegate_"):
                self._coalescer_stack.push_scope()
            summary = summarize_tool_args(tool_name, args)
            self._active_tool_name = tool_name
            self._active_tool_summary = summary
            self._active_tool_start_ts = ts
            self._active_tool_indent = indent
            if self._b_should_show(True):
                if flush_payload:
                    out.write(f"{flush_payload}\n")
                    out.flush()
                self._active_line_kind = "tool"
                self._b_write_active_line(
                    self._b_render_tool_start(THINK_FRAMES[0], tool_name, summary, indent)
                )
            return summary

        def _handle_tool_end(tool_name: str, ok: bool, elapsed_tool: float,
                             result_summary: str | None, content: str,
                             indent: str, summary_override: str | None = None) -> None:
            summary = result_summary or summary_override or self._active_tool_summary
            if ok:
                show_inline, _count = self._coalescer_stack.record_success(time.monotonic())
                if not self._b_should_show(True):
                    # Off mode: success hidden. If a spinner was on screen, seal it.
                    if self._active_line_kind == "tool":
                        out.write("\n")
                        out.flush()
                    self._active_line_kind = "none"
                    self._active_tool_name = ""
                    self._active_tool_summary = ""
                    self._active_tool_start_ts = 0.0
                elif show_inline:
                    if _count <= 2:
                        text = self._b_render_tool_success(tool_name, summary, elapsed_tool, indent)
                    else:
                        text = self._b_render_coalesce_marker(tool_name, _count, indent)
                    self._b_write_active_line(text)
                    out.write("\n")
                    out.flush()
                    self._active_line_kind = "none"
                    self._active_tool_name = ""
                    self._active_tool_summary = ""
                    self._active_tool_start_ts = 0.0
                # count >= 4 silent: spinner line stays for next event to seal
            else:
                flush_payload = self._coalescer_stack.record_error()
                if flush_payload and self._b_should_show(True):
                    out.write(f"{flush_payload}\n")
                    out.flush()
                if self._b_should_show(False):
                    if self._active_line_kind == "tool":
                        # Replace the in-place spinner with the error line
                        msg = self._b_short_error(content)
                        text = self._b_render_tool_error(tool_name, msg, indent)
                        self._b_write_active_line(text)
                        out.write("\n")
                        out.flush()
                        self._active_line_kind = "none"
                        self._active_tool_name = ""
                        self._active_tool_summary = ""
                        self._active_tool_start_ts = 0.0
                    else:
                        # Off mode: no spinner on screen; write error on the
                        # line the cursor is on (which may be the thinking
                        # line). Seal first.
                        self._b_seal_active_line()
                        msg = self._b_short_error(content)
                        text = self._b_render_tool_error(tool_name, msg, indent)
                        out.write(f"{text}\n")
                        out.flush()
                else:
                    self._b_seal_active_line()

        try:
            while not done_event.is_set() or not events.empty():
                now = time.monotonic()
                elapsed = now - start
                if elapsed >= self.agent_timeout:
                    timed_out = True
                    break

                # B-lite tick: rewrite the active line in place
                tick_frame_index = int(elapsed / 0.1)
                if tick_frame_index != last_tick_frame_index:
                    last_tick_frame_index = tick_frame_index
                    if self._active_line_kind == "tool":
                        frame = spinner_frame_at(elapsed - self._active_tool_start_ts)
                        self._b_write_active_line(
                            self._b_render_tool_start(
                                frame,
                                self._active_tool_name,
                                self._active_tool_summary,
                                self._active_tool_indent,
                            )
                        )
                    elif self._active_line_kind == "thinking":
                        self._b_write_active_line(self._b_render_thinking(elapsed))

                try:
                    event = events.get(timeout=0.03)
                except queue.Empty:
                    continue

                batch = [event]
                while True:
                    try:
                        batch.append(events.get_nowait())
                    except queue.Empty:
                        break

                for event in batch:
                    event_type = event.get("type")

                    if event_type == "assistant_delta":
                        # Assistant text owns the output once it starts. Clear
                        # a thinking line instead of sealing it into scrollback.
                        if self._active_line_kind == "thinking":
                            self._b_clear_active_line()
                        else:
                            self._b_seal_active_line()
                        assistant_stream_started = True
                        if partial_preview:
                            stream_buffer = partial_preview + stream_buffer
                            partial_preview = ""
                        accumulated += event.get("content", "")
                        visible_text = self._visible_stream_text(accumulated)
                        if visible_text.startswith(rendered_text):
                            delta = visible_text[len(rendered_text):]
                        else:
                            delta = visible_text
                        if delta:
                            stream_buffer += delta
                            rendered_text = visible_text
                        continue

                    if event_type == "assistant_done":
                        response = event.get("content", "")
                        continue

                    if event_type == "tool_start":
                        tool_name = event.get("tool_name", "?")
                        summary = _handle_tool_start(tool_name, event.get("args", {}), self._B_TOOL_INDENT_MAIN)
                        if tool_name.startswith("delegate_"):
                            delegate_summaries_by_call[str(event.get("tool_call_id", ""))] = summary
                        continue

                    if event_type == "tool_end":
                        tool_name = event.get("tool_name", "?")
                        ok = event.get("ok", False)
                        elapsed_tool = event.get("elapsed", 0.0)
                        result_summary = event.get("result_summary")
                        content = event.get("content", "")
                        summary_override = None
                        if tool_name.startswith("delegate_"):
                            pop_payload = self._coalescer_stack.pop_scope()
                            if pop_payload and self._b_should_show(True):
                                out.write(f"{pop_payload}\n")
                                out.flush()
                            summary_override = delegate_summaries_by_call.pop(str(event.get("tool_call_id", "")), None)
                        _handle_tool_end(
                            tool_name,
                            ok,
                            elapsed_tool,
                            result_summary,
                            content,
                            self._B_TOOL_INDENT_MAIN,
                            summary_override=summary_override,
                        )
                        continue

                    if event_type == "specialist_event":
                        sub = event.get("event_type")
                        tool_name = event.get("tool_name", "?")
                        if sub == "tool_start":
                            _handle_tool_start(tool_name, event.get("args", {}), self._B_TOOL_INDENT_SPECIALIST)
                        elif sub == "tool_end":
                            ok = event.get("ok", False)
                            elapsed_tool = event.get("elapsed", 0.0)
                            result_summary = event.get("result_summary")
                            content = event.get("content", "")
                            _handle_tool_end(tool_name, ok, elapsed_tool, result_summary, content, self._B_TOOL_INDENT_SPECIALIST)
                        continue

                # After processing all events in the batch
                if self._active_line_kind == "thinking" and stream_buffer:
                    self._b_clear_active_line()
                clear_partial = partial_written if stream_buffer else 0
                stream_buffer, wrote = self._flush_stream_buffer(
                    stream_buffer, clear_partial=clear_partial
                )
                if clear_partial:
                    partial_written = 0
                    partial_preview = ""
                if wrote:
                    stream_wrote = True

                if (
                    stream_buffer
                    and self._active_line_kind == "none"
                    and len(stream_buffer) >= self._B_PARTIAL_PREVIEW_MIN_CHARS
                ):
                    out.write(stream_buffer)
                    out.flush()
                    stream_wrote = True
                    stream_buffer = ""

                if (
                    not stream_buffer
                    and stream_wrote
                    and self._active_line_kind == "none"
                    and not assistant_stream_started
                ):
                    self._active_line_kind = "thinking"
                    self._b_write_active_line(self._b_render_thinking(elapsed))

                if len(stream_buffer) >= 120:
                    if self._active_line_kind == "thinking":
                        self._b_clear_active_line()
                    if partial_preview:
                        stream_buffer = partial_preview + stream_buffer
                        partial_preview = ""
                    stream_buffer, _ = self._flush_stream_buffer(stream_buffer, force=True)
                    stream_wrote = True

            if not timed_out:
                thread.join(timeout=1)
        finally:
            self._b_seal_active_line()

        # Final stream flush
        if partial_preview:
            stream_buffer = partial_preview + stream_buffer
            partial_preview = ""
        if partial_written:
            out.write(f"\033[{partial_written}D\033[K")
            out.flush()
            partial_written = 0
        stream_buffer, _ = self._flush_stream_buffer(stream_buffer, force=True)
        if stream_wrote:
            out.write("\n")
            out.flush()

        # Flush any pending coalesce at turn end
        final_flush = self._coalescer_stack.flush_current()
        if final_flush and self._b_should_show(True):
            out.write(f"{final_flush}\n")
            out.flush()

        if timed_out:
            print_error(
                f"[Timeout] Agent did not respond within {self.agent_timeout}s.\n"
                "Session not modified. The background request may still be running;\n"
                "consider restarting the REPL if you experience issues."
            )
            return

        if error_holder[0]:
            print_error(str(error_holder[0]))
            return

        self.set_session(session_copy)
        self.agent = agent_copy

    def run_agent(self, user_input: str) -> None:
        """Run agent with streaming-style feedback.

        Uses a deep copy of the session so that on timeout the main session
        is not polluted with partial state.
        """
        return self.run_agent_streaming(user_input)

    def strip_think_tags(self, text: str) -> tuple[str, str]:
        """Strip thinking tags from response. Returns (answer, thinking)."""
        thinking = ""
        if THINK_START in text and THINK_END in text:
            start = text.find(THINK_START)
            end = text.find(THINK_END) + len(THINK_END)
            thinking = text[start + len(THINK_START):end - len(THINK_END)].strip()
            text = text[:start] + text[end:]
        return text.strip(), thinking

    def print_response(self, response: str):
        """Print response with thinking content in distinct style."""
        answer, thinking = self.strip_think_tags(response)

        if thinking:
            print()
            print("  \033[2;37m" + "-" * 50 + "\033[0m")
            for line in thinking.split("\n"):
                if line.strip():
                    print(f"  \033[2;37m{line}\033[0m")
            print("  \033[2;37m" + "-" * 50 + "\033[0m")
            print()

        if answer:
            print_markdown(answer)

    def print_help(self):
        print()
        print("  \033[1;37m基本命令:\033[0m")
        print("  \033[1;38;5;210m  /help\033[0m             显示帮助")
        print("  \033[1;38;5;210m  /status\033[0m           运行状态")
        print("  \033[1;38;5;210m  /cwd\033[0m              当前工作目录")
        print("  \033[1;38;5;210m  /tools\033[0m           可用工具列表")
        print("  \033[1;38;5;210m  /kb\033[0m              知识库命令")
        print("  \033[1;38;5;210m  /skill\033[0m           技能管理")
        print("  \033[1;38;5;210m  /ui\033[0m              显示设置")
        print("  \033[1;38;5;210m  /exit, /quit\033[0m      退出")
        print()
        print("  \033[1;37m会话管理:\033[0m")
        print("  \033[1;38;5;210m  /session list\033[0m       已保存的会话")
        print("  \033[1;38;5;210m  /session save [name]\033[0m  保存会话（可选命名）")
        print("  \033[1;38;5;210m  /session resume\033[0m     选择会话恢复")
        print("  \033[1;38;5;210m  /session load <id>\033[0m   按 ID 或名称加载")
        print()
        print("  \033[1;37m技能:\033[0m")
        print("  \033[1;38;5;210m  /skill list\033[0m       可用技能列表")
        print("  \033[1;38;5;210m  /skill <name>\033[0m     查看技能内容")
        print("  \033[1;38;5;210m  /skill run <name>\033[0m  执行技能")
        print()
        print("  \033[1;37m知识库:\033[0m")
        print("  \033[1;38;5;210m  /kb sync <vault> [course_dir] [--full]\033[0m  同步资料")
        print("  \033[1;38;5;210m  /kb status\033[0m                                   知识库状态")
        print("  \033[1;38;5;210m  /kb search <query> [--course name] [--top-k n]\033[0m  检索")
        print("  \033[1;38;5;210m  /kb graph <concept> [--intent related] [--limit n]\033[0m  图谱查询")
        print("  \033[1;38;5;210m  /kb reset --yes\033[0m                               删除索引")
        print()
        print("  \033[1;37m题库:\033[0m")
        print("  \033[1;38;5;210m  /quiz generate <topic> [--count n]\033[0m  生成练习题")
        print("  \033[1;38;5;210m  /quiz start [count]\033[0m               开始练习")
        print("  \033[1;38;5;210m  /quiz wrong\033[0m                       错题本")
        print("  \033[1;38;5;210m  /quiz weak\033[0m                        薄弱点分析")
        print("  \033[1;38;5;210m  /quiz stats\033[0m                       题库统计")
        print()
        print("  \033[1;37m学习路线:\033[0m")
        print("  \033[1;38;5;210m  /learning plan <goal>\033[0m              生成学习计划")
        print("  \033[1;38;5;210m  /learning progress\033[0m                掌握度概览")
        print("  \033[1;38;5;210m  /learning review\033[0m                  今日复习清单")
        print("  \033[1;38;5;210m  /learning mark <概念> <状态>\033[0m       手动设置掌握度")
        print("  \033[1;38;5;210m  /learning plans\033[0m                   已保存的学习计划")
        print()
        print("  \033[1;37m记忆:\033[0m")
        print("  \033[1;38;5;210m  /memory list\033[0m         已保存的记忆")
        print("  \033[1;38;5;210m  /memory show <name>\033[0m  查看记忆详情")
        print("  \033[1;38;5;210m  /memory search <query>\033[0m  搜索记忆")
        print("  \033[1;38;5;210m  /memory forget <name>\033[0m  删除记忆")
        print("  \033[1;38;5;210m  /memory stats\033[0m       记忆统计")
        print()
        print("  \033[1;37m显示设置:\033[0m")
        print("  \033[1;38;5;210m  /ui\033[0m              当前设置")
        print("  \033[1;38;5;210m  /ui tools on\033[0m     显示工具调用")
        print("  \033[1;38;5;210m  /ui tools off\033[0m    隐藏工具调用")
        print()
        print("  \033[1;37m模型:\033[0m")
        print("  \033[1;38;5;210m  /model\033[0m              当前激活的 provider / 模型")
        print("  \033[1;38;5;210m  /model list\033[0m         列出所有可用的 provider")
        print("  \033[1;38;5;210m  /model use <name>\033[0m   切换到指定 provider（不写入 config.yaml）")
        print()
        print("  \033[1;37mTrace:\033[0m")
        print("  \033[1;38;5;210m  /trace\033[0m              最近 agent run 记录")
        print("  \033[1;38;5;210m  /trace last\033[0m         最近一次 run 详情")
        print("  \033[1;38;5;210m  /trace <n>\033[0m           第 n 次 run 详情")
        print()
        print("  \033[1;37mAgent 工具:\033[0m")
        schemas = get_tools_schema()
        for schema in schemas:
            func = schema.get("function", {})
            name = func.get("name", "?")
            desc = func.get("description", "")
            print(f"  \033[1;38;5;147m  {name}\033[0m          {desc}")
        print()

    def print_status(self):
        print()
        print("  \033[1;37m运行状态:\033[0m")
        print(f"  \033[1;38;5;210m  会话 ID\033[0m   {self.session.session_id}")
        print(f"  \033[1;38;5;210m  工作目录\033[0m  {self.session.cwd}")
        print(f"  \033[1;38;5;210m  工作区\033[0m    {self.session.workspace_root}")
        print(f"  \033[1;38;5;210m  Provider\033[0m  {self.active_provider} (default: {self.default_provider})")
        print(f"  \033[1;38;5;210m  模型\033[0m      {self.active_model}")
        print(f"  \033[1;38;5;210m  消息数\033[0m    {len(self.session.messages)}")
        print(f"  \033[1;38;5;210m  工具数\033[0m    {self.tool_count}")
        print(f"  \033[1;38;5;210m  保存目录\033[0m  {self.session_save_dir}")
        print(f"  \033[1;38;5;210m  恢复会话\033[0m  {'是' if self.resumed_session else '否'}")
        print()

    def print_tools(self):
        print()
        print("  \033[1;37mAgent tools:\033[0m")
        schemas = get_tools_schema()
        for schema in schemas:
            func = schema.get("function", {})
            name = func.get("name", "?")
            desc = func.get("description", "")
            print(f"  \033[1;38;5;147m  {name}\033[0m          {desc}")
        print()

    def handle_memory_command(self, cmd: str):
        if not self.memory_manager:
            print_error("Memory system is not enabled. Set memory.enabled in config.yaml")
            return

        parts = cmd.strip().split()
        if not parts:
            self.print_memory_help()
            return

        action = parts[0]

        if action == "list":
            from service.memory_service import MemoryService
            svc = MemoryService(self.session.workspace_root)
            result = svc.list_entries()
            entries = result["entries"]
            if not entries:
                print_notice("No memories saved yet.")
                return
            print()
            print("  \033[1;37mSaved memories:\033[0m")
            for e in entries:
                print(f"    \033[1;38;5;147m{e['name']}\033[0m [{e['type']}]  {e['description']}")
            print()

        elif action == "show" and len(parts) > 1:
            from service.memory_service import MemoryService
            svc = MemoryService(self.session.workspace_root)
            result = svc.get_entry(parts[1])
            if not result["ok"]:
                print_error(result["error"])
                return
            print_kv_panel(
                f"Memory: {result['name']}",
                [
                    ("type", result["type"]),
                    ("description", result["description"]),
                    ("created", result["created"]),
                    ("updated", result["updated"]),
                    ("file", result["file_path"]),
                ],
            )
            print()
            print_markdown(result["content"])
            print()

        elif action == "search" and len(parts) > 1:
            from service.memory_service import MemoryService
            svc = MemoryService(self.session.workspace_root)
            result = svc.recall(query=" ".join(parts[1:]), top_k=5)
            if not result["results"]:
                print_notice("No matching memories found.")
                return
            print_search_table(result["results"])

        elif action == "forget" and len(parts) > 1:
            from service.memory_service import MemoryService
            svc = MemoryService(self.session.workspace_root)
            result = svc.forget(parts[1])
            if result["ok"]:
                print_success(f"Memory forgotten: {parts[1]}")
                if self.memory_manager:
                    self.memory_manager.load_entries()
                    self.memory_count = len(self.memory_manager.list_entries())
                    self.memory_prompt = self.memory_manager.build_memory_prompt()
            else:
                print_error(result["error"])

        elif action == "daily":
            self.handle_memory_daily(parts[1:])

        elif action == "promote":
            self.handle_memory_promote(parts[1:])

        elif action == "review":
            self.handle_memory_review()

        elif action == "stats":
            from service.memory_service import MemoryService
            svc = MemoryService(self.session.workspace_root)
            result = svc.get_stats()
            fts_info = result.get("fts", {})
            print_kv_panel(
                "Memory Statistics",
                [
                    ("total memories", result["total"]),
                    ("by type", result.get("by_type", {})),
                    ("vector chunks", result.get("vector_chunks", 0)),
                    ("FTS5 chunks", fts_info.get("total_chunks", "N/A")),
                    ("daily chunks", fts_info.get("daily_chunks", "N/A")),
                    ("permanent chunks", fts_info.get("permanent_chunks", "N/A")),
                    ("recalls", fts_info.get("total_recalls", "N/A")),
                    ("promotions", fts_info.get("total_promotions", "N/A")),
                    ("base dir", result.get("base_dir", "")),
                ],
            )

        else:
            print(f"  \033[1;38;5;208mUnknown /memory command: {action}\033[0m")
            self.print_memory_help()

    def handle_memory_daily(self, args: list[str]):
        """Handle /memory daily [content | YYYY-MM-DD]"""
        from service.memory_service import MemoryService
        svc = MemoryService(self.session.workspace_root)

        if not args:
            result = svc.daily_read()
            if not result["content"].strip():
                print_notice("今日暂无每日记忆。使用 /memory daily <content> 写入。")
                return
            print()
            print("  \033[1;37m今日记忆:\033[0m")
            print_markdown(result["content"])
            print()
            return

        # Check if it's a date string
        if len(args) == 1 and len(args[0]) == 10 and args[0][4] == "-":
            result = svc.daily_read(date=args[0])
            if not result["content"].strip():
                print_notice(f"{args[0]} 没有记忆记录。")
                return
            print()
            print(f"  \033[1;37m{args[0]} 记忆:\033[0m")
            print_markdown(result["content"])
            print()
            return

        # Otherwise treat as content to save
        text = " ".join(args)
        result = svc.daily_save(content=text)
        if result["ok"]:
            print_success(f"每日记忆已保存: {result['path']}")
        else:
            print_error(result["error"])

    def handle_memory_promote(self, args: list[str]):
        """Handle /memory promote [--dry-run]"""
        from service.memory_service import MemoryService
        svc = MemoryService(self.session.workspace_root)
        dry_run = "--dry-run" in args

        result = svc.promote(dry_run=dry_run)
        candidates = result["candidates"]

        if not candidates:
            print_notice("没有待晋升的每日记忆。")
            return

        print()
        print(f"  \033[1;37m晋升候选 ({len(candidates)}):\033[0m")
        for c in candidates:
            status = "\033[1;32m✓ eligible\033[0m" if c["eligible"] else "\033[1;31m✗\033[0m"
            print(
                f"    {c['date']} — score: {c['score']:.2f} "
                f"(freq={c['frequency']:.1f}, quiz={c['quiz']:.1f}, recency={c['recency']:.1f}) "
                f"recalls={c['recall_count']} — {status}"
            )
            if c.get("promoted"):
                print(f"      → {c['details']}")

        if dry_run:
            print("\n  (Dry run — 未执行晋升)")
        print()

    def handle_memory_review(self):
        """Show today's review list from learning scheduler."""
        try:
            from service.learning_service import LearningService
            svc = LearningService(self.session.workspace_root)
            result = svc.get_due_reviews()

            if result["count"] == 0:
                print_notice("今日没有需要复习的知识点。")
                return

            print()
            print("  \033[1;37m今日复习清单:\033[0m")
            for item in result["concepts"]:
                print(f"    [{item['status']}] {item['concept']} (score: {item['score']:.1f})")
            print()
        except Exception as e:
            print_error(f"获取复习清单失败: {e}")

    def print_memory_help(self):
        print()
        print("  \033[1;37m记忆命令:\033[0m")
        print("  \033[1;38;5;210m  /memory list\033[0m              已保存的记忆")
        print("  \033[1;38;5;210m  /memory show <name>\033[0m       查看记忆详情")
        print("  \033[1;38;5;210m  /memory search <query>\033[0m    搜索记忆")
        print("  \033[1;38;5;210m  /memory forget <name>\033[0m     删除记忆")
        print("  \033[1;38;5;210m  /memory daily [content]\033[0m   写入/查看今日记忆")
        print("  \033[1;38;5;210m  /memory daily YYYY-MM-DD\033[0m  查看指定日期记忆")
        print("  \033[1;38;5;210m  /memory promote\033[0m           检查并执行记忆晋升")
        print("  \033[1;38;5;210m  /memory review\033[0m            今日复习清单")
        print("  \033[1;38;5;210m  /memory stats\033[0m             记忆统计")
        print()

    def handle_wiki_command(self, cmd: str):
        parts = cmd.strip().split()
        if not parts or parts[0] in {"help", "-h", "--help"}:
            self.print_wiki_help()
            return

        action = parts[0]
        if action == "init":
            self.handle_wiki_init(parts[1:])
        elif action == "ingest":
            self.handle_wiki_ingest(parts[1:])
        elif action == "lint":
            self.handle_wiki_lint(parts[1:])
        elif action == "status":
            self.handle_wiki_status(parts[1:])
        else:
            print(f"  \033[1;38;5;208mUnknown /wiki command: {action}\033[0m")
            self.print_wiki_help()

    def handle_wiki_init(self, args: list[str]):
        """Initialize wiki directory structure in vault."""
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /wiki init <vault_path>")
            return

        vault_path = args[0]
        if not os.path.isabs(vault_path):
            vault_path = os.path.join(self.session.workspace_root, vault_path)

        if not os.path.isdir(vault_path):
            print_error(f"Vault path not found: {vault_path}")
            return

        from wiki.schema import WikiConfig
        config = WikiConfig()
        for subdir in [config.entity_dir, config.concept_dir]:
            path = os.path.join(vault_path, config.wiki_dir, subdir)
            os.makedirs(path, exist_ok=True)

        print_success(f"Wiki 目录已初始化: {os.path.join(vault_path, config.wiki_dir)}")
        print()
        print("  \033[1;37m目录结构:\033[0m")
        print(f"    {config.wiki_dir}/")
        print(f"      {config.entity_dir}/         实体页面")
        print(f"      {config.concept_dir}/         概念页面")
        print(f"      source_registry.json  来源注册表")
        print(f"      index.md              内容索引")
        print(f"      log.md                操作日志")
        print()

    def handle_wiki_ingest(self, args: list[str]):
        """Compile source files into wiki pages."""
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /wiki ingest <source_path> [--vault path] [--force]")
            return

        source_path = args[0]
        force = "--force" in args

        # Find vault path from args or config
        vault_path = None
        for i, arg in enumerate(args):
            if arg == "--vault" and i + 1 < len(args):
                vault_path = args[i + 1]
        if not vault_path:
            # Try to use the last synced vault from knowledge base
            from knowledge.manifest import load_manifest
            manifest = load_manifest(self.session.workspace_root)
            vault_path = manifest.get("vault_path")
            if not vault_path:
                print_error("请指定 vault 路径：/wiki ingest <source> --vault <path>")
                return

        if not os.path.isabs(source_path):
            source_path = os.path.join(self.session.workspace_root, source_path)
        if not os.path.isabs(vault_path):
            vault_path = os.path.join(self.session.workspace_root, vault_path)

        if not os.path.exists(source_path):
            print_error(f"Source path not found: {source_path}")
            return

        from wiki.compiler import WikiCompiler
        compiler = WikiCompiler(self.session.workspace_root, vault_path)

        # Collect files
        source_files = []
        if os.path.isfile(source_path):
            source_files = [source_path]
        elif os.path.isdir(source_path):
            for root, dirs, files in os.walk(source_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'wiki']
                for f in files:
                    if f.endswith(".md"):
                        source_files.append(os.path.join(root, f))

        if not source_files:
            print_notice("未找到 .md 文件。")
            return

        print(f"\n  \033[1;37m编译 {len(source_files)} 个文件...\033[0m\n")

        result = compiler.compile_batch(source_files, force=force)

        print_kv_panel(
            "Wiki 编译结果",
            [
                ("处理文件", len(source_files)),
                ("生成实体", result.entities_count),
                ("生成概念", result.concepts_count),
                ("生成来源页", result.sources_count),
                ("跳过（未变更）", len(result.skipped)),
                ("错误", len(result.errors)),
            ],
        )

        if result.pages:
            print()
            print("  \033[1;37m生成的页面:\033[0m")
            for page in result.pages:
                icon = {"wiki_entity": "▸", "wiki_concept": "◆", "wiki_source": "●"}.get(page.page_type, "·")
                print(f"    {icon} {page.title} [{page.page_type}]")

        if result.errors:
            print()
            for err in result.errors:
                print_error(f"  {err.get('source', '?')}: {err.get('error', '?')}")
        print()

    def handle_wiki_lint(self, args: list[str]):
        """Check wiki health."""
        vault_path = args[0] if args else None
        if not vault_path:
            from knowledge.manifest import load_manifest
            manifest = load_manifest(self.session.workspace_root)
            vault_path = manifest.get("vault_path")
            if not vault_path:
                print_error("请指定 vault 路径：/wiki lint <vault_path>")
                return

        if not os.path.isabs(vault_path):
            vault_path = os.path.join(self.session.workspace_root, vault_path)

        from wiki.lint import WikiLinter
        linter = WikiLinter(vault_path)
        result = linter.lint()
        summary = linter.format_result(result)
        print()
        print(f"  {summary}")
        print()

    def handle_wiki_status(self, args: list[str]):
        """Show wiki statistics."""
        vault_path = args[0] if args else None
        if not vault_path:
            from knowledge.manifest import load_manifest
            manifest = load_manifest(self.session.workspace_root)
            vault_path = manifest.get("vault_path")
            if not vault_path:
                print_error("请指定 vault 路径：/wiki status <vault_path>")
                return

        if not os.path.isabs(vault_path):
            vault_path = os.path.join(self.session.workspace_root, vault_path)

        from wiki.schema import WikiConfig, load_wiki_state, load_source_registry
        config = WikiConfig()
        wiki_dir = os.path.join(vault_path, config.wiki_dir)

        if not os.path.isdir(wiki_dir):
            print_notice("Wiki 未初始化。使用 /wiki init <vault> 初始化。")
            return

        # Count pages
        counts = {}
        for dir_name in [config.entity_dir, config.concept_dir]:
            dir_path = os.path.join(wiki_dir, dir_name)
            if os.path.isdir(dir_path):
                counts[dir_name] = len([f for f in os.listdir(dir_path) if f.endswith(".md")])
            else:
                counts[dir_name] = 0

        state = load_wiki_state(vault_path, config)
        registry = load_source_registry(vault_path, config)

        print_kv_panel(
            "Wiki Status",
            [
                ("实体页面", counts.get(config.entity_dir, 0)),
                ("概念页面", counts.get(config.concept_dir, 0)),
                ("已编译源文件", len(registry)),
                ("最后编译", state.get("last_compile", "never")),
                ("目录", wiki_dir),
            ],
        )

    def print_wiki_help(self):
        print()
        print("  \033[1;37mWiki 命令:\033[0m")
        print("  \033[1;38;5;210m  /wiki init <vault>\033[0m              初始化 wiki 目录结构")
        print("  \033[1;38;5;210m  /wiki ingest <source> [--vault path]\033[0m  编译源文件为 wiki 页面")
        print("  \033[1;38;5;210m  /wiki lint [vault]\033[0m              wiki 健康检查")
        print("  \033[1;38;5;210m  /wiki status [vault]\033[0m            wiki 统计")
        print()

    # --- MCP commands ---

    def handle_mcp_command(self, cmd: str):
        """Dispatch /mcp <subcommand> [args].

        Subcommands:
          (none) / list   — overview of all configured servers
          status          — detailed per-server state
          restart [name]  — disconnect + reconnect (no name = all)
          tools <name>    — list tools exposed by a server
          reload          — reread config.yaml, diff + reconnect
        """
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            print_error(str(e))
            return

        if not parts or parts[0] in {"help", "-h", "--help", "list"}:
            self.handle_mcp_list()
            return

        action = parts[0]
        args = parts[1:]
        if action == "status":
            self.handle_mcp_status()
        elif action == "restart":
            self.handle_mcp_restart(args)
        elif action == "tools":
            self.handle_mcp_tools(args)
        elif action == "reload":
            self.handle_mcp_reload()
        else:
            print_error(f"Unknown /mcp subcommand: {action}")
            self.print_mcp_help()

    def print_mcp_help(self):
        print()
        print("  \033[1;37mMCP 命令:\033[0m")
        print("  \033[1;38;5;210m  /mcp\033[0m                     列出所有 server 状态")
        print("  \033[1;38;5;210m  /mcp status\033[0m              详细状态（错误/重试时间）")
        print("  \033[1;38;5;210m  /mcp restart [name]\033[0m      重连 server（无 name = 全部）")
        print("  \033[1;38;5;210m  /mcp tools <name>\033[0m        列出该 server 暴露的 tools")
        print("  \033[1;38;5;210m  /mcp reload\033[0m               重新读 config.yaml")
        print()

    def handle_mcp_list(self):
        """Default view: one line per server."""
        from tools.mcp import get_mcp_status_text
        text = get_mcp_status_text()
        for line in text.split("\n"):
            print(f"  {line}")
        self.print_mcp_help()

    def handle_mcp_status(self):
        """Detailed per-server state."""
        from tools.mcp import get_mcp_manager
        mgr = get_mcp_manager()
        if mgr is None:
            print_notice("MCP not initialized (disabled or no servers).")
            return
        states = mgr.get_all_states()
        if not states:
            print_notice("No MCP servers configured.")
            return
        print()
        print("  \033[1;37mMCP Status:\033[0m")
        for name, state in sorted(states.items()):
            if not state.config.enabled:
                print(f"  \033[90m- {name}: disabled\033[0m")
                continue
            icon = "✓" if state.state == "connected" else "✗"
            color = "32" if state.state == "connected" else "31"
            cfg = state.config
            transport_info = cfg.transport
            if cfg.transport == "stdio":
                transport_info = f"stdio ({cfg.command})"
            elif cfg.transport in ("sse", "streamable_http"):
                transport_info = f"{cfg.transport} ({cfg.url})"
            print(f"  \033[1;38;5;{color}m{icon} {name}\033[0m [{state.state}] {transport_info}")
            print(f"      tools: {len(state.tools)}")
            if state.state == "connected" and state.last_connected_at:
                print(f"      last_connected: {state.last_connected_at}")
            if state.last_error:
                err = state.last_error
                if len(err) > 70:
                    err = err[:67] + "..."
                print(f"      \033[31mlast_error: {err}\033[0m")
        print()

    def handle_mcp_restart(self, args: list[str]):
        """Disconnect and reconnect one or all servers."""
        from tools.mcp import get_mcp_manager
        mgr = get_mcp_manager()
        if mgr is None:
            print_notice("MCP not initialized.")
            return
        if args:
            name = args[0]
            state = mgr.get_state(name)
            if state is None:
                print_error(f"No MCP server named {name!r}")
                return
            print(f"  Restarting {name}...")
            ok = mgr.restart_server(name)
            if ok:
                print_success(f"  {name} reconnected ({len(state.tools)} tools)")
            else:
                err = state.last_error or "unknown error"
                print_error(f"  {name} failed: {err}")
        else:
            print("  Restarting all MCP servers...")
            for name in mgr.list_server_names():
                state = mgr.get_state(name)
                if state is None or not state.config.enabled:
                    continue
                print(f"  - {name}...", end=" ", flush=True)
                ok = mgr.restart_server(name)
                if ok:
                    print(f"\033[32mok\033[0m ({len(state.tools)} tools)")
                else:
                    err = (state.last_error or "unknown error")[:50]
                    print(f"\033[31mfailed: {err}\033[0m")

    def handle_mcp_tools(self, args: list[str]):
        """List tools exposed by a single MCP server."""
        from tools.mcp import get_mcp_manager
        mgr = get_mcp_manager()
        if mgr is None:
            print_notice("MCP not initialized.")
            return
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /mcp tools <server_name>")
            return
        name = args[0]
        state = mgr.get_state(name)
        if state is None:
            print_error(f"No MCP server named {name!r}")
            return
        if state.state != "connected" or not state.tools:
            print_notice(f"{name} is not connected; cannot list tools.")
            return
        print()
        print(f"  \033[1;37mTools exposed by {name}:\033[0m")
        for tool in state.tools:
            desc = tool.get("description", "").split("\n")[0]
            if len(desc) > 80:
                desc = desc[:77] + "..."
            tname = tool.get("name", "?")
            print(f"  \033[1;38;5;210m  {tname}\033[0m  {desc}")
        print()

    def handle_mcp_reload(self):
        """Reread config.yaml, diff against current, add/remove/reconnect."""
        from tools.mcp import get_mcp_manager
        from providers.factory import ProviderFactory
        mgr = get_mcp_manager()
        if mgr is None:
            print_notice("MCP not initialized; nothing to reload.")
            return
        try:
            new_config = ProviderFactory.load_config(self.config_path)
        except Exception as e:
            print_error(f"Failed to load {self.config_path}: {e}")
            return
        from mcp_client.config import load_config as load_mcp_config
        new_mcp_cfg = load_mcp_config(new_config)
        if not new_mcp_cfg.enabled:
            print_notice("MCP is disabled in the new config. Reload skipped.")
            return
        diff = mgr.reload(new_mcp_cfg)
        added = diff.get("added", [])
        removed = diff.get("removed", [])
        updated = diff.get("updated", [])
        unchanged = diff.get("unchanged", [])
        print()
        print("  \033[1;37mMCP config reloaded:\033[0m")
        if added:
            print(f"  \033[32m+ added:\033[0m {', '.join(added)}")
        if removed:
            print(f"  \033[31m- removed:\033[0m {', '.join(removed)}")
        if updated:
            print(f"  \033[33m~ updated:\033[0m {', '.join(updated)}")
        if unchanged:
            print(f"  \033[90m= unchanged: {len(unchanged)}\033[0m")
        # Note: added/updated/removed server tools will only take full
        # effect after an AgentLoop restart. The current tools_schema
        # snapshot is taken at AgentLoop construction time.
        print("  \033[90m(hint: /exit and re-launch REPL to pick up new tools)\033[0m")
        print()

    def handle_ui_command(self, cmd: str):
        parts = cmd.strip().split()
        if not parts:
            print()
            print("  \033[1;37mUI Settings:\033[0m")
            print(f"  \033[1;38;5;210m  tool calls\033[0m   {'on' if self.show_tool_calls else 'off'}")
            print()
            return

        if len(parts) == 2 and parts[0] == "tools" and parts[1] in {"on", "off"}:
            self.show_tool_calls = parts[1] == "on"
            state = "enabled" if self.show_tool_calls else "disabled"
            print_success(f"Tool call display {state}")
            return

        print("  \033[1;38;5;210mUsage:\033[0m /ui [tools on|tools off]")

    # --- Model / provider switching ---

    def _make_active_provider(self):
        """Create a provider instance for the currently active provider.

        Used by both initialize() and run_agent_streaming() so that
        /model use takes effect on the next turn.
        """
        provider_config = (
            self.config.get("llm", {}).get("providers", {}).get(self.active_provider)
        )
        if not provider_config:
            available = sorted((self.config.get("llm", {}).get("providers") or {}).keys())
            raise ValueError(
                f"Active provider '{self.active_provider}' not found in "
                f"{self.config_path}. Available: {', '.join(available) or '(none)'}"
            )
        agent_config = self.config.get("agent", {})
        return ProviderFactory.create(provider_config, agent_config)

    def set_provider(self, provider_name: str) -> tuple[bool, str]:
        """Switch the active LLM provider at runtime.

        Returns (success, message). On failure, the active provider is
        unchanged. Does not modify config.yaml — to persist, edit the file
        and restart the REPL.
        """
        providers = self.config.get("llm", {}).get("providers") or {}
        if provider_name not in providers:
            available = ", ".join(sorted(providers.keys())) or "(none)"
            return False, f"Unknown provider '{provider_name}'. Available: {available}"

        provider_config = providers[provider_name]
        agent_config = self.config.get("agent", {})
        try:
            new_provider = ProviderFactory.create(provider_config, agent_config)
        except Exception as e:
            return False, f"Failed to create provider: {e}"

        previous = f"{self.active_provider}/{self.active_model}"
        self.active_provider = provider_name
        self.active_model = provider_config.get("model", "?")
        if self.agent is not None:
            self.agent.set_provider(new_provider)
        new_label = f"{self.active_provider}/{self.active_model}"
        return True, f"Switched: {previous} → {new_label}"

    def handle_model_command(self, cmd: str):
        """Dispatch /model [list|use <name>|current]."""
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            print_error(str(e))
            return

        if not parts or parts[0] in {"current"}:
            self.print_model_status()
            return

        if parts[0] in {"help", "-h", "--help"}:
            self.print_model_help()
            return

        action = parts[0]
        if action == "list":
            self.print_model_list()
        elif action == "use":
            if len(parts) < 2:
                print("  \033[1;38;5;210mUsage:\033[0m /model use <provider_name>")
                return
            ok, message = self.set_provider(parts[1])
            if ok:
                print_success(message)
            else:
                print_error(message)
        else:
            print(f"  \033[1;38;5;208mUnknown /model subcommand: {action}\033[0m")
            self.print_model_help()

    def print_model_status(self):
        """Show the active provider and model (default view for /model)."""
        marker = "★ " if self.active_provider == self.default_provider else "  "
        is_default = self.active_provider == self.default_provider
        print()
        print("  \033[1;37mActive provider:\033[0m")
        if is_default:
            print(f"  \033[1;38;5;210m  {self.active_provider}\033[0m / {self.active_model}  (default)")
        else:
            print(f"  \033[1;38;5;210m  {self.active_provider}\033[0m / {self.active_model}  \033[2;37m(overridden from default: {self.default_provider})\033[0m")
        print()

    def print_model_list(self):
        """List all configured providers, marking the active one."""
        providers = self.config.get("llm", {}).get("providers") or {}
        if not providers:
            print_notice("No providers configured in config.yaml.")
            return
        print()
        print("  \033[1;37mConfigured providers:\033[0m")
        for name in sorted(providers.keys()):
            info = providers[name]
            model = info.get("model", "?")
            api_key_env = info.get("api_key_env", "?")
            ptype = info.get("type", "?")
            star = "★" if name == self.active_provider else " "
            color = "147" if name == self.active_provider else "245"
            print(f"  \033[1;38;5;{color}m  {star} {name:<14}\033[0m {model:<24} type={ptype:<14} key={api_key_env}")
        print()
        print("  \033[90m★ = active.  /model use <name> to switch.\033[0m")
        print()

    def print_model_help(self):
        print()
        print("  \033[1;37mModel 命令:\033[0m")
        print("  \033[1;38;5;210m  /model\033[0m              当前激活的 provider / 模型")
        print("  \033[1;38;5;210m  /model list\033[0m         列出所有可用的 provider")
        print("  \033[1;38;5;210m  /model use <name>\033[0m   切换到指定 provider（不写入 config.yaml）")
        print()

    # --- Specialists (multi-agent) ---

    def handle_specialists_command(self, cmd: str):
        """Dispatch /specialists [status|tools <name>]."""
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            print_error(str(e))
            return

        if not parts or parts[0] in {"help", "-h", "--help", "list"}:
            self.print_specialists_list()
            return

        action = parts[0]
        if action == "status":
            self.print_specialists_status()
        elif action == "tools":
            self.print_specialists_tools(parts[1:])
        else:
            print(f"  \033[1;38;5;208mUnknown /specialists subcommand: {action}\033[0m")
            self.print_specialists_help()

    def print_specialists_help(self):
        print()
        print("  \033[1;37mSpecialists 命令:\033[0m")
        print("  \033[1;38;5;210m  /specialists\033[0m              列出所有 specialist + 配置")
        print("  \033[1;38;5;210m  /specialists status\033[0m       最近 3 次调用")
        print("  \033[1;38;5;210m  /specialists tools <name>\033[0m  该 specialist 的 effective tool set")
        print()

    def print_specialists_list(self):
        if self.agent_registry is None:
            print_notice("Specialists not initialized (check logs).")
            return
        enabled = self.agent_registry.list_enabled()
        all_names = self.agent_registry.list_names()
        n_enabled = len(enabled)
        n_total = len(all_names)
        print()
        print(f"  \033[1;37mConfigured specialists ({n_enabled}/{n_total} enabled):\033[0m")
        for name, sp, cfg in enabled:
            print(
                f"  \033[1;38;5;210m  {name:<14}\033[0m enabled   "
                f"provider={cfg.provider or sp.default_provider:<10} "
                f"model={cfg.model or sp.default_model:<22} "
                f"timeout={cfg.timeout_seconds}s   iter={cfg.max_iterations}"
            )
        for name in all_names:
            if name in {n for n, _, _ in enabled}:
                continue
            cfg = self.agent_registry.get_config(name)
            if cfg is not None and not cfg.enabled:
                print(f"  \033[90m  {name:<14} disabled\033[0m")
        print()

    def print_specialists_status(self):
        if self.agent_registry is None:
            print_notice("Specialists not initialized.")
            return
        records = self.agent_registry.get_invocation(3)
        if not records:
            print_notice("No specialist invocations yet.")
            return
        print()
        print("  \033[1;37mLast specialist invocations (in-memory, REPL runtime):\033[0m")
        for r in records:
            ago = int(time.time() - r.ts) if r.ts else 0
            ago_str = f"{ago}s ago" if ago < 60 else f"{ago // 60}m ago"
            icon = "✓" if r.ok else "✗"
            color = "32" if r.ok else "31"
            err = f" error={r.error_type}" if not r.ok else ""
            print(
                f"  \033[1;38;5;{color}m{icon} {r.specialist:<14}\033[0m "
                f"{'ok=True' if r.ok else 'ok=False':<10}{err:<25} "
                f"{r.duration_ms}ms   {ago_str}"
            )
        print()

    def print_specialists_tools(self, args: list):
        if self.agent_registry is None:
            print_notice("Specialists not initialized.")
            return
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /specialists tools <name>")
            return
        name = args[0]
        cfg = self.agent_registry.get_config(name)
        if cfg is None:
            print_error(f"No specialist named {name!r}. Available: {', '.join(self.agent_registry.list_names())}")
            return
        # Show effective tool set by filtering the live TOOL_REGISTRY
        from tools.base import TOOL_REGISTRY, get_tools_schema
        from agents.runner import build_specialist_tools
        all_tools = get_tools_schema()
        effective = build_specialist_tools(cfg, all_tools)
        print()
        print(f"  \033[1;37mSpecialist {name!r} effective tool set:\033[0m")
        for t in effective:
            print(f"  \033[1;38;5;147m  {t['function']['name']}\033[0m  {t['function'].get('description', '')[:80]}")
        print()
        print("  \033[90mNote: delegate_* and memory_* are always excluded (v1 hard walls).\033[0m")
        if not cfg.allow_mcp:
            print("  \033[90mNote: MCP tools excluded (allow_mcp=false).\033[0m")
        print()

    # --- Trace commands ---

    def handle_trace_command(self, cmd: str):
        """Dispatch /trace [last|<n>]."""
        from core.trace import list_traces, read_trace, summarize_trace

        parts = cmd.strip().split()
        traces = list_traces(self.session.workspace_root, limit=10)

        if not traces:
            print_notice("No trace files found. Traces are written to .bobodan/traces/")
            return

        # /trace — list recent runs
        if not parts:
            print()
            print("  \033[1;37mRecent agent runs:\033[0m")
            for i, t in enumerate(traces):
                events = read_trace(t["path"])
                summary = summarize_trace(events)
                term = summary["termination_reason"] or "?"
                tools = summary["tool_count"]
                dur = summary["duration"]
                ok_icon = "\033[32m✓\033[0m" if term == "final_answer" else "\033[31m✗\033[0m"
                ts_short = t["started_at"][:16].replace("T", " ")
                print(
                    f"  {ok_icon} [{i + 1}] {ts_short}  "
                    f"{tools} tools  {dur:.1f}s  \033[2m{term}\033[0m  "
                    f"\033[2m({t['session_id']})\033[0m"
                )
            print()
            print("  \033[90m/trace last — show details of most recent run\033[0m")
            print("  \033[90m/trace <n>  — show details of run #n\033[0m")
            print()
            return

        # /trace last or /trace <n>
        target = parts[0]
        if target == "last":
            idx = 0
        elif target.isdigit():
            idx = int(target) - 1
        else:
            print_error(f"Usage: /trace [last|<n>]")
            return

        if idx < 0 or idx >= len(traces):
            print_error(f"Run #{idx + 1} not found. Have {len(traces)} traces.")
            return

        t = traces[idx]
        events = read_trace(t["path"])
        summary = summarize_trace(events)

        print()
        print(f"  \033[1;37mTrace: {os.path.basename(t['path'])}\033[0m")
        print(f"  session:  {t['session_id']}")
        print(f"  started:  {t['started_at'][:19].replace('T', ' ')}")
        print(f"  duration: {summary['duration']:.1f}s")
        print(f"  tools:    {summary['tool_count']} ({summary['tools_ok']} ok, {summary['tools_fail']} fail)")
        print(f"  ended:    {summary['termination_reason']}")
        print()

        if summary["tool_details"]:
            print("  \033[1;37mTool timeline:\033[0m")
            for td in summary["tool_details"]:
                icon = "\033[32m✓\033[0m" if td["ok"] else "\033[31m✗\033[0m"
                elapsed = f"{td['elapsed']:.2f}s"
                name = td["tool_name"]
                extra = ""
                if td.get("result_summary"):
                    extra = f" \033[2m{td['result_summary']}\033[0m"
                elif not td["ok"] and td.get("result_summary"):
                    extra = f" \033[31m{td['result_summary']}\033[0m"
                print(f"    {icon} {name:<28} {elapsed:>8}{extra}")
            print()

    def normalize_session_id(self, session_id: str) -> str:
        return session_id[:-5] if session_id.endswith(".json") else session_id

    def get_session_path(self, session_id: str) -> str:
        normalized = self.normalize_session_id(session_id)
        return os.path.join(self.session_save_dir, f"{normalized}.json")

    def save_session(self, name: str = "") -> str:
        os.makedirs(self.session_save_dir, exist_ok=True)
        if name:
            self.session.name = name
        save_path = self.get_session_path(self.session.session_id)
        self.session.save_to_file(save_path)
        return save_path

    def load_session(self, session_id: str, announce: bool = True) -> Session:
        normalized = self.resolve_session_id(session_id)
        load_path = self.get_session_path(normalized)
        session = Session.load_from_file(load_path)
        self.set_session(session, resumed=True)
        if announce:
            label = f"{session.name} ({normalized})" if session.name else normalized
            print(f"  \033[1;32m[OK]\033[0m Session loaded: {label}")
            print(f"  \033[1;32m[OK]\033[0m Working directory: {self.session.cwd}")
            self.print_session_history(session)
        return session

    def print_session_history(self, session: Session) -> None:
        """Display recent chat history from a loaded session."""
        # Filter to user and assistant messages only (skip system/tool)
        history = []
        for msg in session.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and content:
                history.append(("user", content))
            elif role == "assistant" and content and not msg.get("tool_calls"):
                history.append(("assistant", content))

        if not history:
            return

        # Show last N turns (each turn = user + assistant)
        max_display = 10
        recent = history[-max_display:]

        print(f"  \033[90m--- Recent history ({len(history)} messages) ---\033[0m")
        for role, content in recent:
            if role == "user":
                # Truncate long messages
                display = content if len(content) <= 200 else content[:200] + "..."
                print(f"  \033[1;37m> {display}\033[0m")
            else:
                display = content if len(content) <= 300 else content[:300] + "..."
                print(f"  \033[2;37m{display}\033[0m")
        print(f"  \033[90m---\033[0m")
        print()

    def resolve_session_id(self, query: str) -> str:
        """Resolve a session ID by exact match, prefix match, or name match."""
        query = query.strip()
        if query.endswith(".json"):
            query = query[:-5]

        summaries = Session.list_session_summaries(self.session_save_dir)
        if not summaries:
            raise FileNotFoundError(f"No saved sessions found")

        # Exact match
        for s in summaries:
            if s["session_id"] == query:
                return s["session_id"]

        # Prefix match
        matches = [s for s in summaries if s["session_id"].startswith(query)]
        if len(matches) == 1:
            return matches[0]["session_id"]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous session ID prefix '{query}', matches {len(matches)} sessions")

        # Name match (case-insensitive)
        name_matches = [s for s in summaries if query.lower() in s["name"].lower()]
        if len(name_matches) == 1:
            return name_matches[0]["session_id"]
        if len(name_matches) > 1:
            raise ValueError(f"Ambiguous name '{query}', matches {len(name_matches)} sessions")

        raise FileNotFoundError(f"Session not found: {query}")

    def handle_session_command(self, cmd: str):
        parts = cmd.strip().split()
        if not parts:
            print("  \033[1;38;5;210mUsage:\033[0m /session <list|save|resume|load>")
            return

        action = parts[0]
        if action == "list":
            self.print_session_list()
        elif action == "save":
            name = " ".join(parts[1:]) if len(parts) > 1 else ""
            save_path = self.save_session(name)
            label = f" as '{name}'" if name else ""
            print(f"  \033[1;32m[OK]\033[0m Session saved{label}: {save_path}")
        elif action == "resume":
            self.handle_session_resume()
        elif action == "load" and len(parts) > 1:
            try:
                self.load_session(parts[1])
            except Exception as e:
                print_error(f"Failed to load session: {e}")
        else:
            print("  \033[1;38;5;210mUsage:\033[0m /session <list|save [name]|resume|load <id>>")

    def print_session_list(self):
        summaries = Session.list_session_summaries(self.session_save_dir)
        if not summaries:
            print("  \033[1;38;5;210mNo saved sessions.\033[0m")
            return
        print(f"  \033[1;37mSaved sessions ({len(summaries)}):\033[0m")
        for i, s in enumerate(summaries, 1):
            name_part = f" \033[1;33m{s['name']}\033[0m" if s["name"] else ""
            short_id = s["session_id"][:8]
            msgs = s["message_count"]
            time_str = s["last_active"][:16].replace("T", " ") if s["last_active"] else "?"
            print(f"    \033[90m{i}.\033[0m{name_part} \033[1;38;5;147m{short_id}...\033[0m  \033[90m{msgs} msgs, {time_str}\033[0m")

    def handle_session_resume(self):
        summaries = Session.list_session_summaries(self.session_save_dir)
        if not summaries:
            print("  \033[1;38;5;210mNo saved sessions to resume.\033[0m")
            return
        self.print_session_list()
        print()
        choice = input("  Enter number or session name/id: ").strip()
        if not choice:
            print("  \033[90mCancelled.\033[0m")
            return
        # Try as index
        try:
            idx = int(choice)
            if 1 <= idx <= len(summaries):
                target_id = summaries[idx - 1]["session_id"]
                self.load_session(target_id)
                return
            else:
                print_error(f"Invalid number: {idx}")
                return
        except ValueError:
            pass
        # Try as name/id
        try:
            self.load_session(choice)
        except Exception as e:
            print_error(str(e))

    def handle_kb_command(self, cmd: str):
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            print_error(str(e))
            return

        if not parts or parts[0] in {"help", "-h", "--help"}:
            self.print_kb_help()
            return

        action = parts[0]
        args = parts[1:]
        if action == "sync":
            self.handle_kb_sync(args)
        elif action == "status":
            self.print_kb_status()
        elif action == "search":
            self.handle_kb_search(args)
        elif action == "graph":
            self.handle_kb_graph(args)
        elif action == "reset":
            self.handle_kb_reset(args)
        else:
            print(f"  \033[1;38;5;208mUnknown /kb command: {action}\033[0m")
            self.print_kb_help()

    def print_kb_help(self):
        print()
        print("  \033[1;37m知识库命令:\033[0m")
        print("  \033[1;38;5;210m  /kb sync <vault> [course_dir] [--full]\033[0m  同步资料到知识库")
        print("  \033[1;38;5;210m  /kb status\033[0m                                   查看知识库状态")
        print("  \033[1;38;5;210m  /kb search <query> [--course name] [--top-k n]\033[0m  本地检索")
        print("  \033[1;38;5;210m  /kb graph <concept> [--intent related] [--limit n]\033[0m  图谱查询")
        print("  \033[1;38;5;210m  /kb reset --yes\033[0m                               删除索引")
        print()

    def handle_kb_sync(self, args: list[str]):
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /kb sync <vault> [course_dir] [--full]")
            return

        from obsidian.sync import sync_sources
        from tools.base import _resolve_path

        mode = "full" if "--full" in args else "incremental"
        paths = [arg for arg in args if arg != "--full"]
        vault_path = paths[0]
        course_dir = paths[1] if len(paths) > 1 else None

        resolved_vault = _resolve_path(vault_path, self.session.cwd)
        resolved_course = _resolve_path(course_dir, self.session.cwd) if course_dir else None

        try:
            summary = sync_sources(
                workspace=os.path.abspath(self.session.workspace_root),
                vault_path=resolved_vault,
                course_dir=resolved_course,
                mode=mode,
                config=self.config,
            )
        except Exception as e:
            print_error(str(e))
            return

        print_success("Knowledge base synced")
        panel_items = [
            ("files", f"{summary.scanned_files} scanned, {summary.updated_files} updated"),
            ("chunks", summary.chunk_count),
            ("relations", summary.relationship_count),
            ("graph", summary.graph_backend),
        ]
        # Show embedding backend info
        info = self.rag_backend_info or {}
        active = info.get("active", "sparse")
        if active == "dense":
            panel_items.append(("embedding", f"ollama ({info.get('model')}, dim={info.get('dim')})"))
        else:
            panel_items.append(("embedding", "local (sparse)"))
        print_kv_panel("Sync Summary", panel_items)

    def print_kb_status(self):
        knowledge_dir = os.path.join(self.session.workspace_root, ".knowledge")

        if not os.path.exists(knowledge_dir):
            print_notice("No knowledge base found. Run /kb sync <vault> first.")
            return

        from knowledge.library import build_library_summary, format_library_summary
        from knowledge.import_report import load_import_report

        summary = build_library_summary(self.session.workspace_root)
        report = load_import_report(self.session.workspace_root)

        print_kv_panel(
            "Knowledge Base Status",
            [
                ("files", summary.total_files),
                ("chunks", summary.total_chunks),
                ("errors", summary.total_errors) if summary.total_errors else ("errors", "0"),
                ("graph nodes", summary.graph_nodes),
                ("graph relations", summary.graph_relationships),
                ("graph backend", summary.graph_backend),
                ("last sync", summary.last_sync or "never"),
            ],
        )

        # Show embedding backend info
        info = self.rag_backend_info or {}
        active = info.get("active", "sparse")
        mode = info.get("mode", "auto")
        embedding_items = [("backend", f"{active} (mode: {mode})")]
        if active == "dense" or info.get("model"):
            embedding_items.append(("model", info.get("model", "?")))
            embedding_items.append(("dim", info.get("dim", "?")))
        sparse_count = info.get("sparse_chunks")
        dense_count = info.get("dense_chunks")
        if sparse_count is not None:
            embedding_items.append(("sparse chunks", sparse_count))
        if dense_count is not None:
            embedding_items.append(("dense chunks", dense_count))
        if info.get("fallback"):
            embedding_items.append(("fallback", info["fallback"]))
        print()
        print_kv_panel("Embedding", embedding_items)

        # Show per-course breakdown
        if summary.courses and len(summary.courses) > 1:
            print()
            print("  \033[1;37mCourses:\033[0m")
            for cs in sorted(summary.courses, key=lambda c: c.name):
                err = f" \033[1;31m({cs.error_count} errors)\033[0m" if cs.error_count else ""
                print(f"    {cs.name}: {cs.file_count} files, {cs.chunk_count} chunks{err}")

        # Show graph node types
        if summary.graph_nodes_by_type:
            print()
            print("  \033[1;37mGraph node types:\033[0m")
            for label, count in sorted(summary.graph_nodes_by_type.items()):
                print(f"    {label}: {count}")

        # Show errors from last import
        if report and report.errors:
            print()
            print(f"  \033[1;31mImport errors ({len(report.errors)}):\033[0m")
            for err in report.errors[:5]:
                print(f"    {err.get('source', '?')}: {err.get('error', '?')}")
            if len(report.errors) > 5:
                print(f"    ... and {len(report.errors) - 5} more")

    def handle_kb_search(self, args: list[str]):
        query_tokens, options = self._parse_kb_options(args, {"--course", "--top-k"})
        query = " ".join(query_tokens).strip()
        if not query:
            print("  \033[1;38;5;210mUsage:\033[0m /kb search <query> [--course name] [--top-k n]")
            return

        top_k = self._parse_int_option(options.get("--top-k"), default=5, minimum=1, maximum=20)
        result = rag_search(
            query=query,
            course=options.get("--course"),
            top_k=top_k,
            workspace=self.session.workspace_root,
        )
        if not result.ok:
            print_error(result.content)
            return

        results = result.data.get("results", [])
        if not results:
            print_notice("No matching knowledge chunks found.")
            return

        print_search_table(results)

    def handle_kb_graph(self, args: list[str]):
        concept_tokens, options = self._parse_kb_options(args, {"--intent", "--limit"})
        concept = " ".join(concept_tokens).strip()
        if not concept:
            print("  \033[1;38;5;210mUsage:\033[0m /kb graph <concept> [--intent related] [--limit n]")
            return

        limit = self._parse_int_option(options.get("--limit"), default=20, minimum=1, maximum=50)
        intent = options.get("--intent", "related")
        result = graph_query(
            concept=concept,
            intent=intent,
            limit=limit,
            workspace=self.session.workspace_root,
        )
        if not result.ok:
            print_error(result.content)
            return

        data = result.data
        relationships = data.get("relationships", [])
        nodes_by_id = {node.get("id"): node for node in data.get("nodes", [])}
        if not relationships:
            print_notice("No graph relationships found.")
            return

        print()
        print(f"  \033[1;37mGraph Query:\033[0m {data.get('concept', concept)}  intent={data.get('intent', intent)}  source={data.get('source', 'unknown')}")
        for rel in relationships:
            start = nodes_by_id.get(rel.get("start"), {})
            end = nodes_by_id.get(rel.get("end"), {})
            start_name = start.get("name") or start.get("properties", {}).get("name") or rel.get("start")
            end_name = end.get("name") or end.get("properties", {}).get("name") or rel.get("end")
            print(f"  {start_name} -[{rel.get('type')}]-> {end_name}")
        print()

    def handle_kb_reset(self, args: list[str]):
        if "--yes" not in args:
            print("  \033[1;38;5;210mUsage:\033[0m /kb reset --yes")
            print("  This deletes generated .knowledge indexes only.")
            return

        knowledge_dir = os.path.join(self.session.workspace_root, ".knowledge")
        if os.path.exists(knowledge_dir):
            shutil.rmtree(knowledge_dir)
        print_success("Knowledge base reset")

    def _parse_kb_options(self, args: list[str], option_names: set[str]) -> tuple[list[str], dict[str, str]]:
        tokens = []
        options = {}
        index = 0
        while index < len(args):
            token = args[index]
            if token in option_names and index + 1 < len(args):
                options[token] = args[index + 1]
                index += 2
                continue
            tokens.append(token)
            index += 1
        return tokens, options

    def _parse_int_option(self, value: str | None, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value) if value is not None else default
        except ValueError:
            parsed = default
        return max(minimum, min(parsed, maximum))

    def _read_json_file(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    # --- Quiz commands ---

    def handle_quiz_command(self, cmd: str):
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            print_error(str(e))
            return

        if not parts or parts[0] in {"help", "-h", "--help"}:
            self.print_quiz_help()
            return

        action = parts[0]
        args = parts[1:]

        if action == "generate":
            self.handle_quiz_generate(args)
        elif action == "start":
            self.handle_quiz_start(args)
        elif action == "wrong":
            self.handle_quiz_wrong()
        elif action == "weak":
            self.handle_quiz_weak()
        elif action == "stats":
            self.handle_quiz_stats()
        else:
            print(f"  \033[1;38;5;208mUnknown /quiz command: {action}\033[0m")
            self.print_quiz_help()

    def print_quiz_help(self):
        print()
        print("  \033[1;37m题库命令:\033[0m")
        print("  \033[1;38;5;210m  /quiz generate <topic> [--count n] [--course name]\033[0m  生成练习题")
        print("  \033[1;38;5;210m  /quiz start [count] [--course name]\033[0m               开始练习")
        print("  \033[1;38;5;210m  /quiz wrong\033[0m                                       错题本")
        print("  \033[1;38;5;210m  /quiz weak\033[0m                                        薄弱点分析")
        print("  \033[1;38;5;210m  /quiz stats\033[0m                                       题库统计")
        print()

    def handle_quiz_generate(self, args: list[str]):
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /quiz generate <topic> [--count n] [--course name]")
            return

        query_tokens, options = self._parse_kb_options(args, {"--count", "--course"})
        query = " ".join(query_tokens).strip()
        count = self._parse_int_option(options.get("--count"), default=5, minimum=1, maximum=20)
        course = options.get("--course")

        from service.quiz_service import QuizService
        svc = QuizService(self.session.workspace_root)
        result = svc.generate_questions(query=query, course=course, count=count)
        if result["ok"]:
            print_success(f"Generated {result['count']} questions")
            print()
            lines = []
            for q in result["questions"]:
                lines.append(f"{q['id']}. [{q['type_label']}] {q['question']}")
                if q.get("options"):
                    for opt in q["options"]:
                        lines.append(f"   {opt}")
                lines.append(f"   知识点: {', '.join(q['concepts'])}")
                lines.append("")
            print_markdown("\n".join(lines))
        else:
            print_error(result["error"])

    def handle_quiz_start(self, args: list[str]):
        _, options = self._parse_kb_options(args, {"--course", "--type"})
        count = 5
        if args and not args[0].startswith("--"):
            count = self._parse_int_option(args[0], default=5, minimum=1, maximum=20)

        from service.quiz_service import QuizService
        svc = QuizService(self.session.workspace_root)
        result = svc.start_quiz(
            count=count,
            course=options.get("--course"),
            question_type=options.get("--type"),
        )
        if not result["ok"]:
            print_error(result["error"])
            return

        questions = result["questions"]
        print()
        print(f"  \033[1;37m练习开始！共 {len(questions)} 道题，session_id={result['session_id']}\033[0m\n")
        for i, q in enumerate(questions, 1):
            print(f"  第 {i} 题 (id={q['id']}) [{q['type_label']}] 难度: {q['difficulty']}")
            print(f"    {q['question']}")
            if q.get("options"):
                for opt in q["options"]:
                    print(f"    {opt}")
            if q["type"] == "true_false":
                print("    （请回答：true / false 或 对 / 错）")
            elif q["type"] == "single_choice":
                print("    （请回答选项字母，如 A）")
            print()

        print("  请使用 quiz_submit 提交答案，格式：quiz_submit(session_id, question_id, answer)")

    def handle_quiz_wrong(self):
        from service.quiz_service import QuizService
        from quiz.review import format_wrong_answer_book

        try:
            svc = QuizService(self.session.workspace_root)
            result = svc.get_wrong_answer_book()
            print()
            print_markdown(format_wrong_answer_book(result["entries"]))
        except Exception as e:
            print_error(f"Failed to load wrong answers: {e}")

    def handle_quiz_weak(self):
        from service.quiz_service import QuizService
        from quiz.review import format_weakness_analysis

        try:
            svc = QuizService(self.session.workspace_root)
            result = svc.get_weakness_analysis()
            print()
            print_markdown(format_weakness_analysis(result["analysis"]))
        except Exception as e:
            print_error(f"Failed to analyze weaknesses: {e}")

    def handle_quiz_stats(self):
        from service.quiz_service import QuizService

        try:
            svc = QuizService(self.session.workspace_root)
            result = svc.get_stats()
            if result["total"] == 0:
                print_notice("题库为空。使用 /quiz generate <topic> 生成题目。")
                return

            counts = result["counts"]
            print_kv_panel(
                "Quiz Statistics",
                [
                    ("total questions", result["total"]),
                    ("single_choice", counts.get("single_choice", 0)),
                    ("true_false", counts.get("true_false", 0)),
                    ("short_answer", counts.get("short_answer", 0)),
                ],
            )
        except Exception as e:
            print_error(f"Failed to load quiz stats: {e}")

    # --- Learning commands ---

    def handle_learning_command(self, cmd: str):
        parts = cmd.strip().split()
        if not parts:
            self.print_learning_help()
            return

        action = parts[0]
        args = parts[1:]

        if action == "plan":
            self.handle_learning_plan(args)
        elif action == "progress":
            self.handle_learning_progress(args)
        elif action == "review":
            self.handle_learning_review()
        elif action == "mark":
            self.handle_learning_mark(args)
        elif action == "plans":
            self.handle_learning_plans()
        elif action == "today":
            self.handle_learning_today()
        else:
            print(f"  \033[1;38;5;208mUnknown /learning command: {action}\033[0m")
            self.print_learning_help()

    def print_learning_help(self):
        print()
        print("  \033[1;37m学习路线命令:\033[0m")
        print("  \033[1;38;5;210m  /learning plan <goal> [--course name] [--deadline date]\033[0m  生成学习计划")
        print("  \033[1;38;5;210m  /learning progress [concept name]\033[0m                     掌握度概览")
        print("  \033[1;38;5;210m  /learning review\033[0m                                       今日复习清单")
        print("  \033[1;38;5;210m  /learning mark <concept> mastered|learning|needs_review\033[0m  手动设置")
        print("  \033[1;38;5;210m  /learning plans\033[0m                                         已保存计划")
        print("  \033[1;38;5;210m  /learning today\033[0m                                        今日任务 + 复习")
        print()

    def handle_learning_plan(self, args: list[str]):
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /learning plan <goal> [--course name] [--deadline date]")
            return

        query_tokens, options = self._parse_kb_options(args, {"--course", "--deadline"})
        goal = " ".join(query_tokens).strip()
        course = options.get("--course")
        deadline = options.get("--deadline")

        from service.learning_service import LearningService
        svc = LearningService(self.session.workspace_root)
        result = svc.generate_path(goal=goal, course=course, deadline=deadline)
        if result["ok"]:
            print_success(f"Plan generated: {result.get('title', '')}")
            print()
            # Format steps for display
            lines = []
            for step in result["steps"]:
                day = step["day"]
                topics = ", ".join(step["topics"])
                lines.append(f"第 {day} 天: {topics}")
                for t in step["tasks"]:
                    lines.append(f"  - {t}")
                if step.get("review"):
                    lines.append(f"  复习: {', '.join(step['review'])}")
                lines.append("")
            print_markdown("\n".join(lines))
        else:
            print_error(result["error"])

    def handle_learning_progress(self, args: list[str]):
        concept = " ".join(args).strip() if args else None

        from service.learning_service import LearningService
        svc = LearningService(self.session.workspace_root)
        result = svc.get_progress(concept=concept)
        if not result["ok"]:
            print_error(result["error"])
            return

        if concept:
            lines = [
                f"知识点: {result['concept']}",
                f"状态: {result['status']}",
                f"掌握度: {result['score']:.0%}",
                f"复习次数: {result['review_count']}",
                f"连续正确: {result['consecutive_correct']}",
                f"来源: {result['source']}",
            ]
            if result.get("next_review"):
                lines.append(f"下次复习: {result['next_review'][:16]}")
        else:
            if result["total_concepts"] == 0:
                print_notice("暂无学习进度记录。开始做题后会自动追踪掌握度。")
                return
            lines = [
                f"学习进度概览",
                f"已跟踪知识点: {result['total_concepts']}",
                f"平均掌握度: {result['average_score']:.0%}",
                f"状态分布: {json.dumps(result['by_status'], ensure_ascii=False)}",
            ]
            if result.get("weakest"):
                lines.append("\n最薄弱知识点:")
                for w in result["weakest"]:
                    lines.append(f"  - {w['concept']}: {w['score']:.0%} ({w['status']})")
            if result.get("strongest"):
                lines.append("\n掌握最好:")
                for s in result["strongest"]:
                    lines.append(f"  - {s['concept']}: {s['score']:.0%} ({s['status']})")

        print()
        print_markdown("\n".join(lines))

    def handle_learning_review(self):
        from service.learning_service import LearningService
        svc = LearningService(self.session.workspace_root)
        result = svc.get_due_reviews()
        if result["count"] == 0:
            print_notice("今天没有需要复习的知识点！")
            return

        print()
        print(f"  \033[1;37m今日复习清单 ({result['count']} 个知识点):\033[0m\n")
        for i, r in enumerate(result["concepts"], 1):
            print(f"  {i}. {r['concept']} — 掌握度 {r['score']:.0%}, 连续正确 {r['consecutive_correct']}")
        print("\n  使用 quiz_start 开始针对性练习。")

    def handle_learning_today(self):
        from service.learning_service import LearningService
        svc = LearningService(self.session.workspace_root)
        result = svc.get_today_tasks()
        today = {k: v for k, v in result.items() if k != "ok"}

        if not today["plans"] and not today["reviews"]:
            print_notice("没有待完成的学习任务或复习。")
            return

        print()
        for p in today["plans"]:
            print(f"  \033[1;37m学习计划: {p['title']}\033[0m")
            if p.get("deadline"):
                print(f"  \033[2m截止: {p['deadline']}\033[0m")
            for step in p["steps"]:
                topics = ", ".join(step["topics"])
                print(f"    第 {step['day']} 天: {topics}")
                for task in step["tasks"]:
                    print(f"      [ ] {task}")
            print()

        if today["reviews"]:
            print(f"  \033[1;37m复习清单 ({len(today['reviews'])} 个知识点):\033[0m")
            for i, r in enumerate(today["reviews"], 1):
                print(f"    {i}. {r['concept']} — 掌握度 {r['score']:.0%} ({r['status']})")
            print()

    def handle_learning_mark(self, args: list[str]):
        if len(args) < 2:
            print("  \033[1;38;5;210mUsage:\033[0m /learning mark <concept> mastered|learning|needs_review")
            return

        valid_statuses = {"mastered", "learning", "needs_review"}
        status = args[-1]
        concept = " ".join(args[:-1]).strip()

        if status not in valid_statuses:
            print_error(f"Invalid status: {status}. Use: mastered, learning, needs_review")
            return

        from service.learning_service import LearningService
        try:
            svc = LearningService(self.session.workspace_root)
            result = svc.mark_mastery(concept, status)
            print_success(f"Marked '{result['concept']}' as {result['status']} (score: {result['score']:.0%})")
        except Exception as e:
            print_error(f"Failed to mark concept: {e}")

    def handle_learning_plans(self):
        from service.learning_service import LearningService
        try:
            svc = LearningService(self.session.workspace_root)
            result = svc.list_plans()
            plans = result["plans"]
            if not plans:
                print_notice("No learning plans yet. Use /learning plan <goal> to create one.")
                return

            print(f"  \033[1;37mLearning plans ({len(plans)}):\033[0m")
            for p in plans:
                days = p["days"]
                deadline = f", deadline: {p['deadline']}" if p["deadline"] else ""
                course = f", course: {p['course']}" if p["course"] else ""
                status = f" [{p['status']}]" if p["status"] != "active" else ""
                print(f"    \033[1;38;5;147m#{p['id']}\033[0m {p['title']} ({days} days{course}{deadline}){status}")
        except Exception as e:
            print_error(f"Failed to list plans: {e}")

    def handle_skill_command(self, cmd: str):
        parts = cmd.strip().split()
        action = parts[0] if parts else "list"

        if action == "list":
            skills = list_skills(self.skills_dir)
            if skills:
                print("  \033[1;37mAvailable skills:\033[0m")
                for skill in skills:
                    print(f"    \033[1;38;5;147m{skill.name}\033[0m  {skill.description}")
            else:
                print("  \033[1;38;5;210mNo skills found.\033[0m")
            return

        if action == "run" and len(parts) > 1:
            skill_name = parts[1]
            skill = find_skill_by_name(self.skills_dir, skill_name)
            if not skill:
                print(f"  \033[1;31m[Error]\033[0m Skill not found: {skill_name}")
                return
            try:
                with open(skill.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Strip frontmatter, pass body as user context
                if content.startswith("---"):
                    idx = content.find("---", 3)
                    if idx != -1:
                        content = content[idx + 3:].strip()
                self.run_agent(f"[Skill: {skill_name}]\n{content}")
            except Exception as e:
                print_error(str(e))
            return

        # Default: show skill info
        skill_name = action
        skill = find_skill_by_name(self.skills_dir, skill_name)
        if not skill:
            print_error(f"Skill not found: {skill_name}")
            return
        try:
            with open(skill.file_path, "r", encoding="utf-8") as f:
                print(f.read())
        except Exception as e:
            print_error(str(e))

    def handle_exit(self):
        print()
        save = input("  Save session? (y/n): ").strip().lower()
        if save == "y":
            save_path = self.save_session()
            print(f"  \033[1;32m[OK]\033[0m Session saved to {save_path}")
        print("  \033[1;38;5;208mGoodbye!\033[0m")
        self.running = False
