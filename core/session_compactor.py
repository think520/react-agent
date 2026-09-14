"""Checkpoint compaction for long sessions (AG-3.3).

Compaction is a pure context projection: history is never deleted. When a
session's estimated token count exceeds (context_window - output reserve), the
context is projected to [stable prefix + checkpoint + recent tail]. The
checkpoint is a structured summary (goal / progress / blockers / next steps)
that can be incrementally merged across compactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.token_budget import estimate_tokens  # P0-7: one shared estimator

DEFAULT_OUTPUT_RESERVE = 16384
#: Conservative window used when a run does not configure one. P0-8 was that
#: nothing configured one at all, so compaction never ran and long Chinese
#: sessions hit the provider limit instead.
DEFAULT_CONTEXT_WINDOW = 32000
DEFAULT_TAIL_MESSAGES = 12

CHECKPOINT_MARKER = "<!-- bobodan:checkpoint -->"

# Skeleton the summarizer is asked to fill (deterministic structure).
SUMMARIZER_PROMPT = "\n".join([
    "Summarize the conversation so far into a compact checkpoint with exactly four fields:",
    "目标: <the user's current goal>",
    "进展: <what has been established so far>",
    "阻塞: <any open blockers, or 无>",
    "下一步: <the concrete next step>",
    "Keep it under 400 tokens and do not invent facts.",
])


def resolve_context_window(config: dict | None) -> int:
    """Compaction window for a run: explicit config, else the safe default."""
    agent_config = (config or {}).get("agent") or {}
    raw = agent_config.get("context_window")
    try:
        window = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_WINDOW
    return window if window > 0 else DEFAULT_CONTEXT_WINDOW

def estimate_messages_tokens(messages: Sequence[dict]) -> int:
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
    return total


def should_compact(
    messages: Sequence[dict],
    context_window: int,
    output_reserve: int = DEFAULT_OUTPUT_RESERVE,
) -> bool:
    """True when the context should be compacted to leave room for output."""
    return estimate_messages_tokens(messages) > context_window - output_reserve


@dataclass
class Checkpoint:
    goal: str = ""
    progress: str = ""
    blockers: str = ""
    next_steps: str = ""
    summary: str = ""

    @staticmethod
    def from_summary(text: str) -> "Checkpoint":
        fields = {"目标": "", "进展": "", "阻塞": "", "下一步": ""}
        for line in (text or "").splitlines():
            line = line.strip()
            for key in fields:
                if line.startswith(key + ":") or line.startswith(key + "："):
                    fields[key] = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        checkpoint = Checkpoint(
            goal=fields["目标"],
            progress=fields["进展"],
            blockers=fields["阻塞"],
            next_steps=fields["下一步"],
        )
        if not any((checkpoint.goal, checkpoint.progress, checkpoint.blockers, checkpoint.next_steps)):
            checkpoint.summary = (text or "").strip()
        return checkpoint

    def merge(self, newer: "Checkpoint") -> "Checkpoint":
        """Incrementally merge a newer summary into this checkpoint."""
        progress_parts = [part for part in (self.progress, newer.progress) if part]
        return Checkpoint(
            goal=self.goal or newer.goal,
            progress="；".join(progress_parts),
            blockers=newer.blockers or self.blockers,
            next_steps=newer.next_steps or self.next_steps,
            summary=newer.summary or self.summary,
        )

    def to_message(self) -> dict:
        parts = []
        if self.goal:
            parts.append(f"目标: {self.goal}")
        if self.progress:
            parts.append(f"进展: {self.progress}")
        if self.blockers:
            parts.append(f"阻塞: {self.blockers}")
        if self.next_steps:
            parts.append(f"下一步: {self.next_steps}")
        if not parts and self.summary:
            parts.append(self.summary)
        return {"role": "system", "content": CHECKPOINT_MARKER + "\n" + "\n".join(parts)}

    def is_empty(self) -> bool:
        return not any((self.goal, self.progress, self.blockers, self.next_steps, self.summary))


#: Inserted for a tool call whose response never arrived (pause without resume,
#: or an exception mid-tool). A strict provider rejects the transcript without
#: it, so the loop backfills this instead of dropping the pair (P1-11).
INTERRUPTED_TOOL_RESULT = "[工具结果缺失：本轮被打断]"


def repair_tool_pairing(messages: Sequence[dict]) -> list[dict]:
    """Return a transcript a strict provider will accept (P0-8, P1-11).

    Two shapes are illegal and both used to reach the provider: a role=tool
    message whose parent assistant(tool_calls) is gone, and an
    assistant(tool_calls) whose responses never arrived. Orphans are dropped,
    missing responses are backfilled. Applied to the final payload, so it also
    protects against any future projection change.
    """
    repaired: list[dict] = []
    pending: list[str] = []

    def _flush() -> None:
        for call_id in pending:
            repaired.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": INTERRUPTED_TOOL_RESULT,
            })
        pending.clear()

    for message in messages:
        role = message.get("role")
        if role == "assistant":
            _flush()
            for call in message.get("tool_calls") or []:
                call_id = call.get("id")
                if call_id:
                    pending.append(call_id)
            repaired.append(message)
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if call_id in pending:
                pending.remove(call_id)
                repaired.append(message)
            # else: an orphan response - dropped
        else:
            _flush()
            repaired.append(message)
    _flush()
    return repaired


def _tail_start(messages: Sequence[dict], tail: int) -> int:
    """Index where the kept tail starts, pulled back off a tool response.

    Slicing with rest[-tail:] could land on a tool response, keeping the
    response while dropping its parent assistant(tool_calls). The boundary
    therefore moves *earlier* until it is no longer a tool response.
    """
    if tail <= 0:
        return len(messages)
    start = max(0, len(messages) - tail)
    while start > 0 and messages[start].get("role") == "tool":
        start -= 1
    return start


def structural_checkpoint(dropped: Sequence[dict]) -> Checkpoint:
    """Extract a checkpoint from the dropped messages by rule, not by model.

    Asking the model to summarize a context that just exceeded its window needs
    the very budget that ran out, so the middle is replaced by facts we can
    read off the transcript: the last stated goal, the tools that were used and
    how many tool results failed.
    """
    goal = ""
    next_steps = ""
    tools: list[str] = []
    failures = 0
    for message in dropped:
        role = message.get("role")
        content = message.get("content")
        if role == "user" and isinstance(content, str) and content.strip():
            goal = content.strip().splitlines()[0][:160]
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                name = (call.get("function") or {}).get("name") or call.get("name")
                if name and name not in tools:
                    tools.append(str(name))
        if role == "tool" and isinstance(content, str):
            head = content[:200].casefold()
            if head.startswith("[") or "error" in head or "失败" in head:
                failures += 1
    separator = "、"
    progress = "已使用工具：" + separator.join(tools) if tools else ""
    blockers = f"{failures} 条工具结果异常" if failures else ""
    if goal:
        next_steps = "继续当前目标；被省略的中段对话已不可见"
    return Checkpoint(goal=goal, progress=progress, blockers=blockers, next_steps=next_steps)


def project_context(
    messages: Sequence[dict],
    checkpoint: Checkpoint | None = None,
    tail: int = DEFAULT_TAIL_MESSAGES,
) -> list[dict]:
    """Project a message list to [stable prefix + checkpoint + recent tail].

    Does not mutate the input. Leading system messages are preserved (stable
    prefix), the checkpoint follows (dynamic), then the most recent tail.
    """
    rest = list(messages)
    system_msgs: list[dict] = []
    while rest and rest[0].get("role") == "system":
        system_msgs.append(rest.pop(0))

    # P0-8: the tail starts on a boundary a provider accepts, and the dropped
    # middle is replaced by a deterministic checkpoint instead of vanishing.
    start = _tail_start(rest, tail)
    if checkpoint is None or checkpoint.is_empty():
        checkpoint = structural_checkpoint(rest[:start])

    projected = list(system_msgs)
    if checkpoint is not None and not checkpoint.is_empty():
        projected.append(checkpoint.to_message())
    projected.extend(rest[start:])
    return projected
