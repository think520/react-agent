"""User-level Bobodan preferences and confirmed settings proposals."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 4


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _home() -> Path:
    configured = os.getenv("BOBODAN_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".bobodan"


def default_preferences(default_provider: str = "", skill_names: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "assistant": {
            "display_name": "Bobodan",
            "teaching_style": "guided",
            "answer_depth": "standard",
            "feedback_strength": "gentle",
        },
        "user": {
            "display_name": "",
            "profile": "",
            "long_term_goal": "",
        },
        "appearance": {
            "reading_font": "jin-kai",
            "body_font_size": 16,
            "content_width": 720,
            "paper_texture": True,
            "session_density": "comfortable",
            "motion": "system",
        },
        "ai": {
            "default_provider": default_provider,
            "task_providers": {
                "wiki_discovery": "default",
                "wiki_drafting": "default",
            },
        },
        "wiki": {
            "default_mode": "standard",
            "guide_completed": False,
            "budget": {
                "max_requests": 24,
                "max_input_tokens": 300000,
                "max_output_tokens": 40000,
            },
        },
        "memory": {"enabled": True},
        "search": {"provider": "auto", "permission": "ask", "jina_fallback": True},
        "skills": {"enabled_names": sorted(set(skill_names or []))},
    }


_ENUMS = {
    "assistant.teaching_style": {"guided", "explanatory", "practice"},
    "assistant.answer_depth": {"concise", "standard", "deep"},
    "assistant.feedback_strength": {"gentle", "direct"},
    "appearance.reading_font": {"jin-kai", "noto-serif"},
    "appearance.body_font_size": {15, 16, 17, 18},
    "appearance.content_width": {640, 720, 800},
    "appearance.session_density": {"comfortable", "compact"},
    "appearance.motion": {"system", "reduced"},
    "search.provider": {"auto", "tavily", "exa"},
    "search.permission": {"ask", "auto"},
    "wiki.default_mode": {"catalog", "standard", "deep"},
}
_STRINGS = {
    "assistant.display_name": 60,
    "user.display_name": 60,
    "user.profile": 1000,
    "user.long_term_goal": 500,
    "ai.default_provider": 80,
    "ai.task_providers.wiki_discovery": 80,
    "ai.task_providers.wiki_drafting": 80,
}
_BOOLEANS = {"appearance.paper_texture", "memory.enabled", "search.jina_fallback", "wiki.guide_completed"}
_LISTS = {"skills.enabled_names"}
_INTEGERS = {
    "wiki.budget.max_requests": (1, 500),
    "wiki.budget.max_input_tokens": (1000, 10000000),
    "wiki.budget.max_output_tokens": (1000, 1000000),
}
_CHAT_KEYS = {
    "assistant.teaching_style",
    "assistant.answer_depth",
    "assistant.feedback_strength",
    "memory.enabled",
}


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    current = payload
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _flatten_patch(patch: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    flattened: list[tuple[str, Any]] = []
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.extend(_flatten_patch(value, path))
        else:
            flattened.append((path, value))
    return flattened


class PreferenceService:
    def __init__(
        self,
        default_provider: str = "",
        skill_names: list[str] | None = None,
        home: str | None = None,
    ):
        self.home = Path(home).expanduser().resolve() if home else _home()
        self.path = self.home / "preferences.json"
        self.proposal_path = self.home / "settings-proposals.json"
        self.defaults = default_preferences(default_provider, skill_names)

    def get(self) -> dict[str, Any]:
        value = copy.deepcopy(self.defaults)
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        for path, raw in _flatten_patch(stored):
            if path in {"schema_version", "revision"}:
                value[path] = raw
            elif self._valid(path, raw):
                _set_path(value, path, raw)
        value["schema_version"] = SCHEMA_VERSION
        value["revision"] = int(value.get("revision") or 0)
        return value

    def patch(
        self,
        revision: int,
        patch: dict[str, Any],
        available_providers: set[str],
        available_skills: set[str],
    ) -> dict[str, Any]:
        current = self.get()
        if revision != current["revision"]:
            raise RuntimeError("preferences_revision_conflict")
        flattened = _flatten_patch(patch)
        if not flattened:
            return current
        updated = copy.deepcopy(current)
        for path, value in flattened:
            if not self._valid(path, value):
                raise ValueError(f"Unsupported preference value: {path}")
            if path == "ai.default_provider" and value not in available_providers:
                raise ValueError("The selected provider is not available")
            if path.startswith("ai.task_providers.") and value != "default" and value not in available_providers:
                raise ValueError("The selected task provider is not available")
            if path == "skills.enabled_names":
                value = sorted({str(item) for item in value if str(item) in available_skills})
            _set_path(updated, path, value)
        updated["schema_version"] = SCHEMA_VERSION
        updated["revision"] = current["revision"] + 1
        _atomic_json(self.path, updated)
        return updated

    @staticmethod
    def _valid(path: str, value: Any) -> bool:
        if path in _ENUMS:
            return value in _ENUMS[path]
        if path in _STRINGS:
            return isinstance(value, str) and len(value.strip()) <= _STRINGS[path]
        if path in _BOOLEANS:
            return isinstance(value, bool)
        if path in _LISTS:
            return isinstance(value, list) and len(value) <= 100 and all(isinstance(item, str) for item in value)
        if path in _INTEGERS:
            minimum, maximum = _INTEGERS[path]
            return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum
        return False

    def create_proposal(self, message: str) -> dict[str, Any] | None:
        current = self.get()
        changes = self._proposal_changes(message, current)
        if not changes:
            return None
        proposal = {
            "proposal_id": uuid.uuid4().hex,
            "status": "pending",
            "revision": current["revision"],
            "changes": changes,
        }
        proposals = self._load_proposals()
        proposals.insert(0, proposal)
        _atomic_json(self.proposal_path, {"proposals": proposals[:100]})
        return proposal

    def resolve_proposal(
        self,
        proposal_id: str,
        action: str,
        available_providers: set[str],
        available_skills: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        proposals = self._load_proposals()
        proposal = next((item for item in proposals if item.get("proposal_id") == proposal_id), None)
        if proposal is None:
            raise FileNotFoundError("Settings proposal not found")
        if proposal.get("status") != "pending":
            raise ValueError("Settings proposal has already been resolved")
        preferences = None
        if action == "apply":
            patch: dict[str, Any] = {}
            for change in proposal.get("changes") or []:
                if change.get("key") not in _CHAT_KEYS:
                    raise ValueError("Settings proposal contains a protected preference")
                _set_path(patch, change["key"], change.get("after"))
            preferences = self.patch(
                int(proposal.get("revision") or 0),
                patch,
                available_providers,
                available_skills,
            )
            proposal["status"] = "applied"
        elif action == "reject":
            proposal["status"] = "rejected"
        else:
            raise ValueError("Unsupported proposal action")
        _atomic_json(self.proposal_path, {"proposals": proposals})
        return proposal, preferences

    def _load_proposals(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.proposal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return list(value.get("proposals") or [])

    @staticmethod
    def _proposal_changes(message: str, current: dict[str, Any]) -> list[dict[str, Any]]:
        text = re.sub(r"\s+", "", message).lower()
        candidates: list[tuple[str, str, Any]] = []
        if any(token in text for token in ("回答短一点", "简短一点", "回答简洁", "少说一点")):
            candidates.append(("assistant.answer_depth", "回答深度", "concise"))
        elif any(token in text for token in ("回答详细", "讲深入", "更深入", "详细一点")):
            candidates.append(("assistant.answer_depth", "回答深度", "deep"))
        elif any(token in text for token in ("标准回答", "恢复标准", "正常详细")):
            candidates.append(("assistant.answer_depth", "回答深度", "standard"))
        if any(token in text for token in ("引导我", "苏格拉底", "多提问")):
            candidates.append(("assistant.teaching_style", "教学方式", "guided"))
        elif any(token in text for token in ("直接讲解", "讲解式", "直接告诉我")):
            candidates.append(("assistant.teaching_style", "教学方式", "explanatory"))
        elif any(token in text for token in ("陪我练", "陪练", "多练习")):
            candidates.append(("assistant.teaching_style", "教学方式", "practice"))
        if any(token in text for token in ("反馈直接", "直接批评", "严格一点")):
            candidates.append(("assistant.feedback_strength", "反馈方式", "direct"))
        elif any(token in text for token in ("反馈温和", "温和一点", "别太直接")):
            candidates.append(("assistant.feedback_strength", "反馈方式", "gentle"))
        if any(token in text for token in ("关闭记忆", "不要记忆", "停用记忆")):
            candidates.append(("memory.enabled", "学习记忆", False))
        elif any(token in text for token in ("开启记忆", "打开记忆", "启用记忆")):
            candidates.append(("memory.enabled", "学习记忆", True))

        changes = []
        seen = set()
        for key, label, after in candidates:
            if key in seen:
                continue
            seen.add(key)
            before = _get_path(current, key)
            if before != after:
                changes.append({"key": key, "label": label, "before": before, "after": after})
        return changes
