from collections import deque
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Session:
    session_id: str
    cwd: str
    workspace_root: str = ""
    messages: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())
    max_messages: Optional[int] = None
    name: str = ""
    name_source: str = "fallback"

    @staticmethod
    def new(cwd: str, max_messages: Optional[int] = None) -> "Session":
        return Session(
            session_id=str(uuid.uuid4()),
            cwd=cwd,
            workspace_root=cwd,
            max_messages=max_messages,
        )

    def _trim_messages(self) -> None:
        if not self.max_messages or self.max_messages <= 0 or len(self.messages) <= self.max_messages:
            return

        # Preserve leading system message(s)
        system_msgs = []
        rest = self.messages
        while rest and rest[0].get("role") == "system":
            system_msgs.append(rest[0])
            rest = rest[1:]

        budget = self.max_messages - len(system_msgs)
        if budget <= 0:
            self.messages = system_msgs
            return

        # Group messages into "turns" to avoid splitting tool call groups.
        # A tool call group = assistant(tool_calls) + its matching tool messages.
        # We keep groups atomic: either the whole group stays or it's removed.
        groups = self._group_messages(rest)

        # Trim from the oldest groups first
        trimmed = []
        used = 0
        for group in reversed(groups):
            group_size = len(group)
            if used + group_size <= budget:
                trimmed = group + trimmed
                used += group_size
            else:
                break  # can't fit this group, stop

        self.messages = system_msgs + trimmed

    def _group_messages(self, messages: list[dict]) -> list[list[dict]]:
        """Split messages into atomic groups.

        Each group is either:
        - A single non-tool message (user, assistant without tool_calls)
        - An assistant(tool_calls) message followed by its matching tool messages
        """
        groups: list[list[dict]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Start of a tool call group: assistant + all matching tool messages
                group = [msg]
                i += 1
                while i < len(messages) and messages[i].get("role") == "tool":
                    group.append(messages[i])
                    i += 1
                groups.append(group)
            else:
                groups.append([msg])
                i += 1
        return groups

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.last_active = datetime.now().isoformat()
        self._trim_messages()

    def add_message_with_tool_calls(self, role: str, content: str, tool_calls: list) -> None:
        msg = {"role": role, "content": content, "tool_calls": tool_calls}
        self.messages.append(msg)
        self.last_active = datetime.now().isoformat()
        self._trim_messages()

    def add_tool_message(self, tool_call_id: str, content: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })
        self.last_active = datetime.now().isoformat()
        self._trim_messages()

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_from_file(path: str) -> "Session":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "max_messages" not in data:
            data["max_messages"] = None
        if "workspace_root" not in data:
            data["workspace_root"] = data.get("cwd", "")
        if "name" not in data:
            data["name"] = ""
        if "name_source" not in data:
            data["name_source"] = "manual" if data.get("name") else "fallback"
        return Session(**data)

    @staticmethod
    def list_sessions(save_dir: str) -> list[str]:
        import os
        if not os.path.exists(save_dir):
            return []
        sessions = []
        for file_name in os.listdir(save_dir):
            if file_name.endswith(".json"):
                sessions.append(file_name[:-5])
        return sorted(sessions)

    @staticmethod
    def list_session_summaries(save_dir: str) -> list[dict]:
        """Return session metadata sorted by last_active descending."""
        import os
        if not os.path.exists(save_dir):
            return []
        summaries = []
        for file_name in os.listdir(save_dir):
            if not file_name.endswith(".json"):
                continue
            path = os.path.join(save_dir, file_name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                summaries.append({
                    "session_id": data.get("session_id", file_name[:-5]),
                    "name": data.get("name", ""),
                    "name_source": data.get(
                        "name_source", "manual" if data.get("name") else "fallback"
                    ),
                    "created_at": data.get("created_at", ""),
                    "last_active": data.get("last_active", ""),
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, OSError):
                continue
        summaries.sort(key=lambda s: s["last_active"], reverse=True)
        return summaries
