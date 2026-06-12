import json
import logging
import os
import time
from collections.abc import Iterator
from core.memory import MEMORY_MARKER
from core.skills import SKILLS_PROMPT_MARKER
from tools import get_tools_schema, execute_tool
from tools.base import ToolResult
from providers.types import LLMResponse, ToolCall

logger = logging.getLogger(__name__)


def _compute_result_summary(tool_name: str, result: ToolResult) -> str | None:
    """Return a short display string for a tool's success result, or None.

    The whitelist intentionally lives here (not in cli/) so the AgentLoop can
    attach a stable, display-friendly hint to the tool_end event without
    inverting the core→cli dependency graph. Add new entries sparingly:
    the summary must be derivable from the tool's own ToolResult.data and
    must be safe to surface in scrollback and future trace events.
    """
    if tool_name == "change_dir":
        cwd = result.data.get("cwd") if isinstance(result.data, dict) else None
        if cwd:
            return f"→ {cwd}"
    if tool_name == "http_request":
        status = result.data.get("status") if isinstance(result.data, dict) else None
        if status:
            return f"status {status}"
    return None

LEGACY_BASE_SYSTEM_PROMPT = (
    "You are bobodan, an AI assistant running inside the bobodan CLI.\n"
    "Refer to yourself as 'bobodan' when needed.\n"
    "Do not call yourself Claude or any other assistant name.\n"
    "Keep replies concise, practical, and grounded in the current repository and tools."
)

BASE_SYSTEM_PROMPT_MARKER = "<!-- bobodan:base-prompt -->"

BASE_SYSTEM_PROMPT = """You are Bobodan, a local-first personal assistant with strong learning capabilities.

Your core strength is helping the user learn from their own materials:
- explain concepts with retrieved sources when available;
- turn notes and course materials into quizzes, review plans, and learning paths;
- track mastery and guide study progress;
- help organize and export learning work to Obsidian/wiki.

You can also help with general conversation, companionship, brainstorming, light entertainment, and everyday questions when the user is not asking for study-related work.

Follow the user's saved persona and tone preferences when available, but keep Bobodan's primary role as a learning-capable assistant.
Do not invent facts about the user's local knowledge base. Use tools when current local data is needed.
Prefer one clear next step over a long menu.
Do not call yourself Claude or any other assistant name."""

MCP_PROMPT_MARKER = "<!-- bobodan:mcp-prompt -->"


class AgentLoop:
    """ReAct agent loop implementation."""

    def __init__(self, llm_provider, session, skills_prompt: str | None = None,
                 memory_prompt: str | None = None, mcp_prompt: str | None = None,
                 tools_schema: list[dict] | None = None,
                 max_iterations: int | None = None,
                 trace_writer=None):
        self.llm = llm_provider
        self.session = session
        self.tools_schema = tools_schema if tools_schema is not None else get_tools_schema()
        self.max_iterations = max_iterations if max_iterations is not None else 8
        self.skills_prompt = skills_prompt
        self.memory_prompt = memory_prompt
        self.mcp_prompt = mcp_prompt
        self.trace_writer = trace_writer

    def set_session(self, session) -> None:
        self.session = session

    def set_provider(self, llm_provider) -> None:
        """Swap the active LLM provider at runtime.

        The new provider is used for subsequent turns. Session message
        history is preserved (the previous turns remain in the session);
        the new model will see them as context.
        """
        self.llm = llm_provider

    def _remove_legacy_base_prompt(self) -> None:
        self.session.messages = [
            msg for msg in self.session.messages
            if not (
                msg.get("role") == "system"
                and (msg.get("content") or "").strip() == LEGACY_BASE_SYSTEM_PROMPT
            )
        ]

    def _inject_base_prompt(self) -> None:
        """Inject the stable Bobodan product identity prompt once per session."""
        for m in self.session.messages:
            if m.get("role") == "system" and BASE_SYSTEM_PROMPT_MARKER in (m.get("content") or ""):
                return
        tagged = f"{BASE_SYSTEM_PROMPT_MARKER}\n{BASE_SYSTEM_PROMPT}"
        self.session.add_message("system", tagged)

    def _inject_skills_prompt(self) -> None:
        """Inject skills system prompt if not already present.

        Uses a stable marker to detect whether the skills prompt has already
        been injected — regardless of other system messages (base prompt,
        restored session, etc.). This replaces the old "any system message
        exists" check which blocked injection after session restore.
        """
        if not self.skills_prompt:
            return
        # Check if skills prompt was already injected (by marker)
        for m in self.session.messages:
            if m.get("role") == "system" and SKILLS_PROMPT_MARKER in (m.get("content") or ""):
                return
        self.session.add_message("system", self.skills_prompt)

    def _inject_memory_prompt(self) -> None:
        """Inject memory system prompt if not already present.

        Same idempotent marker pattern as skills prompt.
        """
        if not self.memory_prompt:
            return
        for m in self.session.messages:
            if m.get("role") == "system" and MEMORY_MARKER in (m.get("content") or ""):
                return
        self.session.add_message("system", self.memory_prompt)

    def _inject_mcp_prompt(self) -> None:
        """Inject MCP system prompt (active server list) if not present."""
        if not self.mcp_prompt:
            return
        for m in self.session.messages:
            if m.get("role") == "system" and MCP_PROMPT_MARKER in (m.get("content") or ""):
                return
        # The marker is an HTML comment so it doesn't affect the
        # visible prompt but is stable for idempotency detection.
        tagged = f"{MCP_PROMPT_MARKER}\n{self.mcp_prompt}"
        self.session.add_message("system", tagged)

    def run(self, user_input: str) -> str:
        """Run one turn of the agent loop."""
        final_response = ""
        for event in self.run_stream(user_input):
            if event.get("type") == "assistant_done":
                final_response = event.get("content", "")
        return final_response

    def run_stream(self, user_input: str) -> Iterator[dict]:
        """Run one turn and yield UI-friendly progress events."""
        try:
            self._remove_legacy_base_prompt()
            self._inject_base_prompt()
            self._inject_skills_prompt()
            self._inject_memory_prompt()
            self._inject_mcp_prompt()
            self.session.add_message("user", user_input)

            for iteration in range(self.max_iterations):
                response = yield from self._complete_with_events()

                if response.tool_calls:
                    # Add assistant(tool_calls) FIRST — providers require this
                    # before the corresponding tool result messages.
                    tool_calls_data = [tc.to_dict() for tc in response.tool_calls]
                    self.session.add_message_with_tool_calls("assistant", response.content, tool_calls_data)

                    # Now execute tools and add tool messages
                    for tc in response.tool_calls:
                        logger.info(f"[AgentLoop] calling tool — id={tc.id!r} name={tc.name!r}")

                        try:
                            args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                        except json.JSONDecodeError:
                            args = {}

                        tool_start_event = {
                            "type": "tool_start",
                            "tool_call_id": tc.id,
                            "tool_name": tc.name,
                            "args": args,
                        }
                        yield tool_start_event
                        if self.trace_writer:
                            self.trace_writer.write(tool_start_event)

                        start_ts = time.monotonic()
                        result = execute_tool(tc.name, args, session=self.session)
                        elapsed = time.monotonic() - start_ts
                        if isinstance(result, ToolResult):
                            self._sync_session_state(tc.name, result)
                            self.session.add_tool_message(tc.id, result.content)
                            logger.info(f"[AgentLoop] tool result for id={tc.id!r}: {result.content[:200]!r}")
                            for display_event in result.data.get("display_events", []):
                                yield {
                                    **display_event,
                                    "type": "specialist_event",
                                    "event_type": display_event.get("type"),
                                    "parent_tool_call_id": tc.id,
                                    "parent_tool_name": tc.name,
                                }
                            tool_end_event = {
                                "type": "tool_end",
                                "tool_call_id": tc.id,
                                "tool_name": tc.name,
                                "ok": result.ok,
                                "content": result.content,
                                "elapsed": elapsed,
                                "result_summary": _compute_result_summary(tc.name, result),
                            }
                            yield tool_end_event
                            if self.trace_writer:
                                self.trace_writer.write(tool_end_event)
                        else:
                            # Fallback for unknown tools returning plain string
                            self.session.add_tool_message(tc.id, str(result))
                            logger.info(f"[AgentLoop] tool result for id={tc.id!r}: {str(result)[:200]!r}")
                            fallback_end_event = {
                                "type": "tool_end",
                                "tool_call_id": tc.id,
                                "tool_name": tc.name,
                                "ok": True,
                                "content": str(result),
                                "elapsed": elapsed,
                                "result_summary": None,
                            }
                            yield fallback_end_event
                            if self.trace_writer:
                                self.trace_writer.write(fallback_end_event)

                    continue

                if response.content:
                    self.session.add_message("assistant", response.content)

                done_event = {
                    "type": "assistant_done",
                    "content": response.content,
                    "termination_reason": "final_answer",
                }
                yield done_event
                if self.trace_writer:
                    self.trace_writer.write(done_event)
                return response.content

            fallback = "Agent stopped after too many tool iterations."
            self.session.add_message("assistant", fallback)
            yield {"type": "assistant_delta", "content": fallback}
            max_iter_event = {
                "type": "assistant_done",
                "content": fallback,
                "termination_reason": "max_iter",
            }
            yield max_iter_event
            if self.trace_writer:
                self.trace_writer.write(max_iter_event)
        except Exception as exc:
            error_done = {
                "type": "assistant_done",
                "content": "",
                "termination_reason": "error",
            }
            yield error_done
            if self.trace_writer:
                self.trace_writer.write(error_done)
                self.trace_writer.write({"type": "error", "error": str(exc)})
            raise

    def _complete_with_events(self) -> Iterator[dict]:
        complete_stream = getattr(self.llm, "complete_stream", None)
        if not callable(complete_stream):
            response = self.llm.complete(self.session.messages, tools=self.tools_schema)
            if response.content:
                yield {"type": "assistant_delta", "content": response.content}
            return response

        content_parts: list[str] = []
        tool_buffers: dict[int, dict[str, object]] = {}

        for chunk in complete_stream(self.session.messages, tools=self.tools_schema):
            if chunk.content_delta:
                content_parts.append(chunk.content_delta)
                yield {"type": "assistant_delta", "content": chunk.content_delta}

            for delta in chunk.tool_call_deltas:
                buffer = tool_buffers.setdefault(delta.index, {
                    "id": "",
                    "name": "",
                    "arguments": [],
                })
                if delta.id:
                    buffer["id"] = delta.id
                if delta.name:
                    buffer["name"] = delta.name
                if delta.arguments:
                    buffer["arguments"].append(delta.arguments)

        tool_calls = []
        for index in sorted(tool_buffers):
            buffer = tool_buffers[index]
            name = str(buffer["name"])
            tool_calls.append(ToolCall(
                id=str(buffer["id"]) or f"call_{index}_{name}",
                name=name,
                arguments="".join(buffer["arguments"]),
            ))

        return LLMResponse(content="".join(content_parts), tool_calls=tool_calls)

    def _sync_session_state(self, tool_name: str, result: ToolResult) -> None:
        if tool_name != "change_dir":
            return
        new_cwd = result.data.get("cwd")
        if new_cwd:
            self.session.cwd = os.path.abspath(new_cwd)
