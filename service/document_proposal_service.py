"""LB-1.2: AI collaboration editing (proposal -> confirm -> apply -> undo).

AI keeps read-only on raw/; instead it produces an edit proposal (diff + reason
+ impact preview). The user confirms before anything is written, and every
apply records a checkpoint so it can be undone (reusing the LB-1.1 version
mechanism and the Wiki plan->confirm->checkpoint->undo workflow).

Proposals are only allowed for Markdown/text materials; AI never writes files
directly. New-material creation also goes through proposal confirmation.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

from service._result import err as _err, ok as _ok


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def line_diff(old: str, new: str) -> list[dict[str, str]]:
    """Return a compact unified diff as add/remove/context records."""
    records: list[dict[str, str]] = []
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm=""):
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            records.append({"type": "add", "line": line[1:]})
        elif line.startswith("-"):
            records.append({"type": "remove", "line": line[1:]})
        else:
            records.append({"type": "context", "line": line})
    return records


def parse_proposal_response(text: str) -> tuple[str, str]:
    """Parse an LLM proposal response into (reason, new_content)."""
    reason = ""
    content = (text or "").strip()
    marker = "CONTENT:"
    if marker in content:
        before, after = content.split(marker, 1)
        reason_part = before.replace("REASON:", "").strip()
        reason = reason_part.splitlines()[0].strip() if reason_part else ""
        content = after.strip()
    else:
        # Fallback: treat the whole response as new content.
        content = content.strip()
    return reason, content


class DocumentProposalService:
    def __init__(self, workspace: str) -> None:
        from service.document_edit_service import DocumentEditService
        from service.kb_service import KBService

        self.workspace = os.path.abspath(workspace)
        self.kb = KBService(self.workspace)
        self.editor = DocumentEditService(self.workspace)

    @property
    def proposals_dir(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "proposals")

    def _proposal_path(self, proposal_id: str) -> str:
        return os.path.join(self.proposals_dir, f"{proposal_id}.json")

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        path = self._proposal_path(proposal_id)
        if not os.path.isfile(path):
            return _err("Proposal not found", code="proposal_not_found")
        with open(path, "r", encoding="utf-8") as handle:
            return _ok(proposal=json.load(handle))

    def create_proposal(
        self,
        document_id: str,
        instruction: str,
        provider: Any,
    ) -> dict[str, Any]:
        read = self.editor.read(document_id)
        if not read.get("ok"):
            return read
        if not read.get("editable"):
            return _err("Only Markdown/text materials can be edited", code="document_read_only")

        original = read["content"]
        prompt = (
            "You are proposing an edit to a Markdown study material. "
            f"User instruction: {instruction}\n\n"
            "Current content:\n---\n" + original + "\n---\n\n"
            "Respond with the full edited Markdown content. First line is "
            "'REASON: <one-line reason>', then a line 'CONTENT:', then the full "
            "new Markdown content."
        )
        try:
            response = provider.complete([{"role": "user", "content": prompt}])
        except Exception as exc:  # noqa: BLE001
            return _err(f"Failed to generate proposal: {exc}", code="proposal_generation_failed")

        reason, new_content = parse_proposal_response(str(getattr(response, "content", "") or ""))
        if not new_content.strip():
            return _err("The model did not produce editable content", code="proposal_generation_failed")

        impact = self.kb.document_impact(document_id)
        proposal = {
            "proposal_id": uuid.uuid4().hex,
            "kind": "edit",
            "status": "proposed",
            "document_id": document_id,
            "title": read["document"].get("title") or read["document"].get("source") or "",
            "instruction": instruction,
            "reason": reason,
            "new_content": new_content,
            "original_content": original,
            "diff": line_diff(original, new_content),
            "impact": impact.get("affected_pages", []) if impact.get("ok") else [],
            "impact_count": impact.get("affected_count", 0) if impact.get("ok") else 0,
            "checkpoint_id": None,
            "created_at": _now(),
        }
        _atomic_write(self._proposal_path(proposal["proposal_id"]), proposal)
        return _ok(proposal=proposal)

    def create_new_document_proposal(
        self,
        title: str,
        content: str,
        reason: str,
    ) -> dict[str, Any]:
        proposal = {
            "proposal_id": uuid.uuid4().hex,
            "kind": "create",
            "status": "proposed",
            "document_id": None,
            "title": title,
            "instruction": "",
            "reason": reason,
            "new_content": content,
            "original_content": "",
            "diff": line_diff("", content),
            "impact": [],
            "impact_count": 0,
            "checkpoint_id": None,
            "created_at": _now(),
        }
        _atomic_write(self._proposal_path(proposal["proposal_id"]), proposal)
        return _ok(proposal=proposal)

    def apply_proposal(self, proposal_id: str, config: dict | None = None) -> dict[str, Any]:
        result = self.get_proposal(proposal_id)
        if not result.get("ok"):
            return result
        proposal = result["proposal"]
        if proposal.get("status") == "applied":
            return _err("Proposal already applied", code="proposal_already_applied")

        if proposal.get("kind") == "create":
            path = self._write_new_document(proposal)
        else:
            edit = self.editor.edit(
                proposal["document_id"],
                proposal["new_content"],
                conflict_action="overwrite",
                config=config,
            )
            if not edit.get("ok"):
                return edit
            path = None

        self.kb._sync_registered_sources(mode="incremental", config=config or {})
        proposal["status"] = "applied"
        proposal["applied_at"] = _now()
        if path:
            proposal["created_path"] = path
        _atomic_write(self._proposal_path(proposal_id), proposal)
        return _ok(proposal=proposal)

    def undo_proposal(self, proposal_id: str, config: dict | None = None) -> dict[str, Any]:
        result = self.get_proposal(proposal_id)
        if not result.get("ok"):
            return result
        proposal = result["proposal"]
        if proposal.get("status") != "applied":
            return _err("Only applied proposals can be undone", code="proposal_not_applied")

        if proposal.get("kind") == "create":
            path = proposal.get("created_path")
            if path and os.path.isfile(path):
                archive_dir = os.path.join(self.workspace, ".bobodan", "archive", "raw")
                os.makedirs(archive_dir, exist_ok=True)
                shutil.move(path, os.path.join(archive_dir, os.path.basename(path)))
        else:
            restored = self.editor.edit(
                proposal["document_id"],
                proposal["original_content"],
                conflict_action="overwrite",
                config=config,
            )
            if not restored.get("ok"):
                return restored

        self.kb._sync_registered_sources(mode="incremental", config=config or {})
        proposal["status"] = "undone"
        proposal["undone_at"] = _now()
        _atomic_write(self._proposal_path(proposal_id), proposal)
        return _ok(proposal=proposal)

    def _write_new_document(self, proposal: dict[str, Any]) -> str:
        title = str(proposal.get("title") or "untitled").strip()
        safe = "".join(ch for ch in title if ch.isalnum() or ch in "-_ ").strip() or "untitled"
        if not safe.lower().endswith(".md"):
            safe = safe + ".md"
        inbox = os.path.join(self.workspace, "raw", "inbox")
        os.makedirs(inbox, exist_ok=True)
        target = os.path.join(inbox, safe)
        counter = 2
        while os.path.exists(target):
            stem, ext = os.path.splitext(safe)
            target = os.path.join(inbox, f"{stem} ({counter}){ext}")
            counter += 1
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(proposal["new_content"])
        return target
