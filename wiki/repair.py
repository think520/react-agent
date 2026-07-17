"""Persistent, user-confirmed Wiki repair plans."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from .index import WikiIndexer
from .reliability import WIKI_WRITE_LOCK, atomic_json, now
from .workflow import WikiWorkflow


class WikiRepairStore:
    def __init__(self, workspace: str, vault_path: str):
        self.workspace = os.path.abspath(workspace)
        self.vault_path = os.path.abspath(vault_path)
        self.root = os.path.join(self.workspace, ".bobodan", "wiki", "repair-plans")

    def _path(self, plan_id: str) -> str:
        if len(plan_id) != 32 or any(char not in "0123456789abcdef" for char in plan_id):
            raise ValueError("Invalid Wiki repair plan id")
        return os.path.join(self.root, f"{plan_id}.json")

    def get(self, plan_id: str) -> dict[str, Any]:
        with open(self._path(plan_id), "r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, plan: dict[str, Any]) -> dict[str, Any]:
        plan["updated_at"] = now()
        atomic_json(self._path(plan["plan_id"]), plan)
        return plan

    def create(self, health: dict[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []

        def add(issue_type: str, title: str, execution: str, resolution: str, page_id: str | None = None):
            items.append({
                "item_id": uuid.uuid4().hex,
                "issue_type": issue_type,
                "page_id": page_id,
                "title": title,
                "execution": execution,
                "resolution": resolution,
                "status": "pending",
            })

        for vault in health.get("vaults") or []:
            for value in vault.get("index_mismatches") or []:
                add("index_mismatch", str(value), "local", "reindex")
            for value in vault.get("broken_links") or []:
                add("broken_link", f"{value.get('source') or '页面'} → {value.get('target') or '未知目标'}", "manual", "relink")
            for value in vault.get("orphans") or []:
                add("orphan", str(value), "manual", "review")
            for value in vault.get("missing") or []:
                add("missing", str(value), "ai", "regenerate")
            for value in vault.get("stale") or []:
                add("stale", str(value), "ai", "regenerate")
            for value in vault.get("duplicate_candidates") or []:
                title = value.get("canonical_title") if isinstance(value, dict) else value
                add("duplicate", str(title), "manual", "merge")
            for value in [*(vault.get("contradiction_candidates") or []), *(vault.get("semantic_candidates") or [])]:
                title = value.get("reason") if isinstance(value, dict) else value
                add("semantic", str(title), "ai", "review")
        if health.get("total_pages") and not any(item["resolution"] == "reindex" for item in items):
            add("index_check", "重建 Wiki 页面索引", "local", "reindex")
        plan = {
            "plan_id": uuid.uuid4().hex,
            "status": "planned",
            "created_at": now(),
            "health_snapshot": {key: value for key, value in health.items() if key != "ok"},
            "items": items,
        }
        return self.save(plan)

    def apply(self, plan_id: str) -> dict[str, Any]:
        plan = self.get(plan_id)
        if plan.get("status") not in {"planned", "partial"}:
            raise ValueError("This Wiki repair plan cannot be applied")
        with WIKI_WRITE_LOCK:
            workflow = WikiWorkflow(self.workspace, self.vault_path)
            checkpoint_id = workflow._create_checkpoint(plan_id)
            applied = 0
            try:
                if any(item["execution"] == "local" and item["status"] == "pending" for item in plan["items"]):
                    WikiIndexer(self.vault_path).rebuild_from_disk()
                for item in plan["items"]:
                    if item["execution"] == "local" and item["status"] == "pending":
                        item["status"] = "applied"
                        applied += 1
            except Exception:
                workflow.restore_checkpoint(checkpoint_id)
                raise
        pending = sum(item["status"] in {"pending", "ready"} for item in plan["items"])
        plan.update({
            "status": "partial" if pending else "applied",
            "checkpoint_id": checkpoint_id,
            "applied_count": applied,
            "pending_count": pending,
        })
        return self.save(plan)
