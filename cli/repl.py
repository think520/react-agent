import copy
import json
import os
import queue
import shlex
import shutil
import sys
import threading
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
THINK_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

ALL_COMMANDS = ["help", "status", "cwd", "tools", "skill", "kb", "quiz", "learning", "memory", "ui", "exit", "quit", "session"]

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
    ("/memory list", "已保存的记忆"),
    ("/memory search ", "搜索记忆"),
    ("/memory show ", "查看记忆详情"),
    ("/memory forget ", "删除记忆"),
    ("/memory stats", "记忆统计"),
    ("/ui", "显示 UI 设置"),
    ("/ui tools on", "显示工具调用"),
    ("/ui tools off", "隐藏工具调用"),
    ("/session list", "已保存的会话"),
    ("/session save ", "保存会话（可选命名）"),
    ("/session resume", "选择会话恢复"),
    ("/session load ", "加载会话（ID/名称）"),
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

    def initialize(self):
        """Initialize the agent with config."""
        try:
            self.config = ProviderFactory.load_config(self.config_path)
            llm_config = self.config.get("llm", {})
            self.default_provider = llm_config.get("default_provider", "unknown")
            provider_info = llm_config.get("providers", {}).get(self.default_provider, {})
            self.model_name = provider_info.get("model", "unknown")
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

            if self.resume_session_id:
                self.load_session(self.resume_session_id, announce=False)
            elif self.session is None:
                self.set_session(Session.new(os.getcwd(), max_messages=self.session_max_messages))
            else:
                self.set_session(self.session)

            self.agent = AgentLoop(
                ProviderFactory.create_from_config(self.config_path),
                self.session,
                skills_prompt=self.skills_prompt,
                memory_prompt=self.memory_prompt,
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
        print_startup_panel(
            [
                ("session", self.session.session_id),
                ("state", "resumed" if self.resumed_session else "new"),
                ("cwd", self.session.cwd),
                ("workspace", self.session.workspace_root),
                ("model", f"{self.default_provider}/{self.model_name}"),
                ("tools", f"{self.tool_count} registered"),
                ("skills", self.skill_count),
                ("memories", self.memory_count),
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

        if cmd == "ui":
            self.handle_ui_command(cmd_line[len("ui"):].strip())
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

    def _format_tool_args(self, args: dict, limit: int = 80) -> str:
        try:
            text = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            text = str(args)
        if len(text) <= limit:
            return text
        return text[:limit - 3] + "..."

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

    def _flush_stream_buffer(self, buffer: str, force: bool = False, clear_partial: int = 0) -> tuple[str, bool]:
        """Render complete lines with markdown + typewriter effect.

        Args:
            buffer: accumulated text to render.
            force: if True, write remaining partial content without delay.
            clear_partial: number of chars already written as partial preview
                           (will be cleared before re-rendering the full line).

        Returns:
            (remaining_buffer, wrote_something)
        """
        import time
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
                for ch in rendered:
                    out.write(ch)
                    if ch not in ("\r", "\n"):
                        time.sleep(0.008)
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

            # Typewriter: character by character
            for ch in rendered:
                out.write(ch)
                if ch not in ("\r", "\n"):
                    time.sleep(0.012)
            out.flush()
            wrote = True

        # Partial line at end
        if force and buffer:
            out.write(buffer)
            out.flush()
            wrote = True
            buffer = ""

        return buffer, wrote

    def _render_thinking_line(self, frame: str) -> str:
        cyan = "\033[38;5;39m"
        dim = "\033[2m"
        reset = "\033[0m"
        return f"{cyan}{frame}{reset} {dim}thinking{reset}"

    def _show_thinking_line(self, frame: str) -> None:
        out = rich_console().file
        out.write(f"\r\033[2K{self._render_thinking_line(frame)}")
        out.flush()

    def _clear_thinking_line(self) -> None:
        out = rich_console().file
        out.write("\r\033[2K")
        out.flush()

    def run_agent_streaming(self, user_input: str) -> None:
        """Run agent with typewriter streaming, thinking animation, and compact tool display."""
        import time
        from core.agent_loop import AgentLoop

        session_copy = copy.deepcopy(self.session)
        agent_copy = AgentLoop(
            ProviderFactory.create_from_config(self.config_path),
            session_copy,
            skills_prompt=self.skills_prompt,
            memory_prompt=self.memory_prompt,
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

        # Simple user prefix, no panel
        print(f"\n  \033[1;37m>\033[0m {user_input}\n")

        out = rich_console().file
        accumulated = ""
        rendered_text = ""
        stream_buffer = ""
        stream_wrote = False
        thinking_visible = True
        response = ""
        start = time.monotonic()
        timed_out = False
        last_thinking_frame = ""
        self._stream_in_code_block = False
        partial_written = 0  # chars written as partial preview (for clearing)

        try:
            while not done_event.is_set() or not events.empty():
                elapsed = int(time.monotonic() - start)
                if elapsed >= self.agent_timeout:
                    timed_out = True
                    break

                # Thinking animation
                if thinking_visible:
                    frame_index = int((time.monotonic() - start) * 10) % len(THINK_FRAMES)
                    frame = THINK_FRAMES[frame_index]
                    if frame != last_thinking_frame:
                        self._show_thinking_line(frame)
                        last_thinking_frame = frame

                try:
                    event = events.get(timeout=0.03)
                except queue.Empty:
                    continue

                # Drain all pending events
                batch = [event]
                while True:
                    try:
                        batch.append(events.get_nowait())
                    except queue.Empty:
                        break

                for event in batch:
                    event_type = event.get("type")

                    if event_type == "assistant_delta":
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
                        if thinking_visible:
                            self._clear_thinking_line()
                            thinking_visible = False
                        if partial_written:
                            out.write(f"\033[{partial_written}D\033[K")
                            out.flush()
                            partial_written = 0
                        stream_buffer, _ = self._flush_stream_buffer(stream_buffer, force=True)
                        if stream_wrote:
                            out.write("\n")
                            out.flush()
                        accumulated = ""
                        rendered_text = ""
                        self._stream_in_code_block = False
                        if self.show_tool_calls:
                            tool_name = event.get("tool_name", "?")
                            args = self._format_tool_args(event.get("args", {}))
                            out.write(f"  \033[38;5;39m⏺\033[0m {tool_name} \033[2m{args}\033[0m\n")
                            out.flush()
                        stream_wrote = False
                        continue

                    if event_type == "tool_end":
                        if self.show_tool_calls:
                            ok = event.get("ok", False)
                            icon = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
                            result_preview = event.get("content", "")
                            if result_preview:
                                preview = result_preview[:80].replace("\n", " ")
                                if len(result_preview) > 80:
                                    preview += "..."
                                out.write(f"    {icon} \033[2m{preview}\033[0m\n")
                            else:
                                out.write(f"    {icon}\n")
                            out.flush()

                # Flush complete lines with typewriter effect
                if thinking_visible and stream_buffer:
                    self._clear_thinking_line()
                stream_buffer, wrote = self._flush_stream_buffer(
                    stream_buffer, clear_partial=partial_written
                )
                partial_written = 0
                if wrote:
                    stream_wrote = True

                # Write partial line as preview (no typewriter, cleared later)
                if stream_buffer and not thinking_visible:
                    out.write(stream_buffer)
                    out.flush()
                    partial_written = len(stream_buffer)
                    stream_buffer = ""

                # Re-show thinking if buffer is empty (waiting for more)
                if not stream_buffer and stream_wrote and not thinking_visible:
                    thinking_visible = True

                # Force flush large partial buffer
                if len(stream_buffer) >= 120:
                    if thinking_visible:
                        self._clear_thinking_line()
                    stream_buffer, _ = self._flush_stream_buffer(stream_buffer, force=True)
                    stream_wrote = True

            if not timed_out:
                thread.join(timeout=1)
        finally:
            self._clear_thinking_line()

        # Final flush
        if partial_written:
            out.write(f"\033[{partial_written}D\033[K")
            out.flush()
        stream_buffer, _ = self._flush_stream_buffer(stream_buffer, force=True)
        if stream_wrote:
            out.write("\n")
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
        print(f"  \033[1;38;5;210m  Provider\033[0m  {self.default_provider}")
        print(f"  \033[1;38;5;210m  模型\033[0m      {self.model_name}")
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
            entries = self.memory_manager.list_entries()
            if not entries:
                print_notice("No memories saved yet.")
                return
            print()
            print("  \033[1;37mSaved memories:\033[0m")
            for entry in entries:
                print(f"    \033[1;38;5;147m{entry.name}\033[0m [{entry.type}]  {entry.description}")
            print()

        elif action == "show" and len(parts) > 1:
            name = parts[1]
            entry = self.memory_manager.get_entry(name)
            if not entry:
                print_error(f"Memory not found: {name}")
                return
            print_kv_panel(
                f"Memory: {name}",
                [
                    ("type", entry.type),
                    ("description", entry.description),
                    ("created", entry.created),
                    ("updated", entry.updated),
                    ("file", entry.file_path),
                ],
            )
            print()
            print_markdown(entry.content)
            print()

        elif action == "search" and len(parts) > 1:
            query = " ".join(parts[1:])
            results = self.memory_manager.search(query, top_k=5)
            if not results:
                print_notice("No matching memories found.")
                return
            print_search_table(results)

        elif action == "forget" and len(parts) > 1:
            name = parts[1]
            if self.memory_manager.forget(name):
                print_success(f"Memory forgotten: {name}")
                self.memory_count = len(self.memory_manager.list_entries())
                self.memory_prompt = self.memory_manager.build_memory_prompt()
            else:
                print_error(f"Memory not found: {name}")

        elif action == "stats":
            stats = self.memory_manager.get_stats()
            print_kv_panel(
                "Memory Statistics",
                [
                    ("total memories", stats["total"]),
                    ("by type", stats.get("by_type", {})),
                    ("vector chunks", stats.get("vector_chunks", 0)),
                    ("base dir", stats.get("base_dir", "")),
                ],
            )

        else:
            print(f"  \033[1;38;5;208mUnknown /memory command: {action}\033[0m")
            self.print_memory_help()

    def print_memory_help(self):
        print()
        print("  \033[1;37m记忆命令:\033[0m")
        print("  \033[1;38;5;210m  /memory list\033[0m         已保存的记忆")
        print("  \033[1;38;5;210m  /memory show <name>\033[0m  查看记忆详情")
        print("  \033[1;38;5;210m  /memory search <query>\033[0m  搜索记忆")
        print("  \033[1;38;5;210m  /memory forget <name>\033[0m  删除记忆")
        print("  \033[1;38;5;210m  /memory stats\033[0m       记忆统计")
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

        mode = "full" if "--full" in args else "incremental"
        paths = [arg for arg in args if arg != "--full"]
        vault_path = paths[0]
        course_dir = paths[1] if len(paths) > 1 else None

        result = obsidian_sync(
            vault_path=vault_path,
            course_dir=course_dir,
            mode=mode,
            cwd=self.session.cwd,
            workspace=self.session.workspace_root,
        )
        if not result.ok:
            print_error(result.content)
            return

        data = result.data
        print_success("Knowledge base synced")
        print_kv_panel(
            "Sync Summary",
            [
                ("files", f"{data.get('scanned_files', 0)} scanned, {data.get('updated_files', 0)} updated"),
                ("chunks", data.get("chunk_count", 0)),
                ("relations", data.get("relationship_count", 0)),
                ("graph", data.get("graph_backend", "unknown")),
            ],
        )

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

        from tools.quiz_tools import question_generate
        result = question_generate(
            query=query, course=course, count=count,
            workspace=self.session.workspace_root,
        )
        if result.ok:
            print_success(f"Generated {result.data.get('count', 0)} questions")
            print()
            print_markdown(result.content)
        else:
            print_error(result.content)

    def handle_quiz_start(self, args: list[str]):
        _, options = self._parse_kb_options(args, {"--course", "--type"})
        count = 5
        if args and not args[0].startswith("--"):
            count = self._parse_int_option(args[0], default=5, minimum=1, maximum=20)

        from tools.quiz_tools import quiz_start
        result = quiz_start(
            count=count,
            course=options.get("--course"),
            question_type=options.get("--type"),
            workspace=self.session.workspace_root,
        )
        if result.ok:
            print()
            print_markdown(result.content)
        else:
            print_error(result.content)

    def handle_quiz_wrong(self):
        from quiz.store import QuizStore
        from quiz.review import QuizReviewer

        try:
            store = QuizStore(self.session.workspace_root)
            reviewer = QuizReviewer(store)
            entries = reviewer.get_wrong_answer_book()
            print()
            print_markdown(reviewer.format_wrong_answer_book(entries))
        except Exception as e:
            print_error(f"Failed to load wrong answers: {e}")

    def handle_quiz_weak(self):
        from quiz.store import QuizStore
        from quiz.review import QuizReviewer

        try:
            store = QuizStore(self.session.workspace_root)
            reviewer = QuizReviewer(store)
            analysis = reviewer.get_weakness_analysis()
            print()
            print_markdown(reviewer.format_weakness_analysis(analysis))
        except Exception as e:
            print_error(f"Failed to analyze weaknesses: {e}")

    def handle_quiz_stats(self):
        from quiz.store import QuizStore

        try:
            store = QuizStore(self.session.workspace_root)
            counts = store.count_questions()
            if not counts:
                print_notice("题库为空。使用 /quiz generate <topic> 生成题目。")
                return

            total = sum(counts.values())
            print_kv_panel(
                "Quiz Statistics",
                [
                    ("total questions", total),
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
        print()

    def handle_learning_plan(self, args: list[str]):
        if not args:
            print("  \033[1;38;5;210mUsage:\033[0m /learning plan <goal> [--course name] [--deadline date]")
            return

        query_tokens, options = self._parse_kb_options(args, {"--course", "--deadline"})
        goal = " ".join(query_tokens).strip()
        course = options.get("--course")
        deadline = options.get("--deadline")

        from tools.learning_tools import learning_path
        result = learning_path(
            goal=goal, course=course, deadline=deadline,
            workspace=self.session.workspace_root,
        )
        if result.ok:
            print_success(f"Plan generated: {result.data.get('title', '')}")
            print()
            print_markdown(result.content)
        else:
            print_error(result.content)

    def handle_learning_progress(self, args: list[str]):
        concept = " ".join(args).strip() if args else None

        from tools.learning_tools import learning_progress
        result = learning_progress(
            concept=concept,
            workspace=self.session.workspace_root,
        )
        if result.ok:
            print()
            print_markdown(result.content)
        else:
            print_error(result.content)

    def handle_learning_review(self):
        from tools.learning_tools import learning_review
        result = learning_review(workspace=self.session.workspace_root)
        if result.ok:
            print()
            print_markdown(result.content)
        else:
            print_error(result.content)

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

        from learning.store import LearningStore
        from learning.scheduler import ReviewScheduler
        try:
            store = LearningStore(self.session.workspace_root)
            scheduler = ReviewScheduler(store)
            m = scheduler.mark_manual(concept, status)
            print_success(f"Marked '{concept}' as {m.status} (score: {m.score:.0%})")
        except Exception as e:
            print_error(f"Failed to mark concept: {e}")

    def handle_learning_plans(self):
        from learning.store import LearningStore
        try:
            store = LearningStore(self.session.workspace_root)
            plans = store.list_plans(limit=10)
            if not plans:
                print_notice("No learning plans yet. Use /learning plan <goal> to create one.")
                return

            print(f"  \033[1;37mLearning plans ({len(plans)}):\033[0m")
            for p in plans:
                days = len(p.steps)
                deadline = f", deadline: {p.deadline}" if p.deadline else ""
                course = f", course: {p.course}" if p.course else ""
                print(f"    \033[1;38;5;147m#{p.id}\033[0m {p.title} ({days} days{course}{deadline})")
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
