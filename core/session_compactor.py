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

DEFAULT_OUTPUT_RESERVE = 16384
DEFAULT_TAIL_MESSAGES = 12
CHARS_PER_TOKEN = 4

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


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


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

    projected = list(system_msgs)
    if checkpoint is not None and not checkpoint.is_empty():
        projected.append(checkpoint.to_message())
    if tail > 0:
        projected.extend(rest[-tail:])
    return projected
