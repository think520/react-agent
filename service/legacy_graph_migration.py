"""Preview and migrate the retired ``graph_store.json`` format.

The legacy graph is never queried by the Agent. Migration turns Concept nodes
into review candidates and graph-only Memory nodes into personal-knowledge
candidates. The source file is archived only after every selected item has
been accounted for.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from graph.concept_store import ConceptStore
from knowledge.paths import knowledge_path
from memory.legacy import LegacyMemoryReader
from service._result import err as _err, ok as _ok
from service.memory_service import MemoryService


_RELATION_TYPES = {
    "RELATED_TO": "user:旧图谱关联",
    "PREREQUISITE_OF": "前置知识",
    "USES": "应用于",
    "SIMILAR_TO": "对比",
    "DERIVED_FROM": "来源于",
}


class LegacyGraphMigrationService:
    def __init__(self, workspace: str, *, home: str | None = None) -> None:
        self.workspace = os.path.abspath(workspace)
        self.home = home
        self.source_path = Path(knowledge_path(self.workspace, "graph_store.json"))

    def _load(self) -> dict[str, Any]:
        if not self.source_path.is_file():
            return {"nodes": {}, "relationships": []}
        try:
            payload = json.loads(self.source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"旧版知识图谱无法读取: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("旧版知识图谱格式无效")
        return payload

    @staticmethod
    def _nodes(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw = payload.get("nodes") or {}
        if isinstance(raw, list):
            return {
                str(item.get("id") or f"node-{index}"): item
                for index, item in enumerate(raw)
                if isinstance(item, dict)
            }
        return {
            str(key): value
            for key, value in raw.items()
            if isinstance(value, dict)
        } if isinstance(raw, dict) else {}

    @staticmethod
    def _quality(node: dict[str, Any]) -> tuple[str, str]:
        properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
        content = str(
            properties.get("content")
            or properties.get("description")
            or properties.get("note")
            or ""
        ).strip()
        return ("complete", content) if content else ("name_only", str(node.get("name") or "").strip())

    def preview(self) -> dict[str, Any]:
        if not self.source_path.is_file():
            return _ok(detected=False, path=str(self.source_path), concepts=[], memories=[], excluded={}, relationships=0)
        try:
            payload = self._load()
        except ValueError as exc:
            return _err(str(exc))
        nodes = self._nodes(payload)
        legacy_memory_names = {
            entry.name.casefold()
            for entry in LegacyMemoryReader(self.workspace).list_entries()
        }
        personal_items = MemoryService(self.workspace, home=self.home).list_knowledge(limit=500).get("items", [])
        personal_titles = [str(item.get("title") or "") for item in personal_items]
        concepts = []
        memories = []
        excluded: dict[str, int] = {}
        for node_id, node in nodes.items():
            label = str(node.get("label") or "unknown")
            name = str(node.get("name") or node_id.split(":", 1)[-1]).strip()
            if label == "Concept" and name:
                concepts.append({"id": node_id, "name": name})
                continue
            if label == "Memory" and name:
                quality, content = self._quality(node)
                covered = name.casefold() in legacy_memory_names
                duplicate = next((
                    title for title in personal_titles
                    if SequenceMatcher(None, title.casefold(), name.casefold()).ratio() >= 0.82
                ), None)
                memories.append({
                    "id": node_id,
                    "name": name,
                    "content": content,
                    "quality": quality,
                    "covered_by_legacy_memory": covered,
                    "possible_duplicate": duplicate,
                    "recommended": not covered,
                })
                continue
            excluded[label] = excluded.get(label, 0) + 1
        semantic_relations = [
            rel for rel in payload.get("relationships", [])
            if isinstance(rel, dict) and rel.get("type") in _RELATION_TYPES
        ]
        return _ok(
            detected=True,
            path=str(self.source_path),
            concepts=concepts,
            memories=memories,
            excluded=excluded,
            relationships=len(semantic_relations),
        )

    def migrate(
        self,
        *,
        concept_ids: list[str],
        memory_ids: list[str],
        archive: bool = True,
    ) -> dict[str, Any]:
        try:
            payload = self._load()
        except ValueError as exc:
            return _err(str(exc))
        if not self.source_path.is_file():
            return _err("未检测到旧版知识图谱")
        nodes = self._nodes(payload)
        requested_concept_ids = list(dict.fromkeys(concept_ids))
        requested_memory_ids = list(dict.fromkeys(memory_ids))
        selected_concepts = {
            node_id: nodes[node_id]
            for node_id in requested_concept_ids
            if node_id in nodes and nodes[node_id].get("label") == "Concept"
        }
        selected_memories = {
            node_id: nodes[node_id]
            for node_id in requested_memory_ids
            if node_id in nodes and nodes[node_id].get("label") == "Memory"
        }
        invalid_ids = [
            *[node_id for node_id in requested_concept_ids if node_id not in selected_concepts],
            *[node_id for node_id in requested_memory_ids if node_id not in selected_memories],
        ]
        if invalid_ids:
            return _err(
                "迁移选择包含不存在或类型不匹配的节点，旧文件未归档",
                invalid_ids=invalid_ids,
            )
        concept_names = {
            node_id: str(node.get("name") or node_id.split(":", 1)[-1]).strip()
            for node_id, node in selected_concepts.items()
        }
        suggestions: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in selected_concepts}
        for rel in payload.get("relationships", []):
            if not isinstance(rel, dict) or rel.get("type") not in _RELATION_TYPES:
                continue
            start_id, end_id = str(rel.get("start") or ""), str(rel.get("end") or "")
            if start_id not in selected_concepts or end_id not in selected_concepts:
                continue
            suggestions[start_id].append({
                "rel_type": _RELATION_TYPES[str(rel["type"])],
                "to_name": concept_names[end_id],
                "direction": "outgoing",
                "enabled": True,
            })

        concept_store = ConceptStore(knowledge_path(self.workspace, "concept_graph.db"))
        concept_candidates = []
        for node_id, node in selected_concepts.items():
            properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            candidate = concept_store.add_candidate(
                name=concept_names[node_id],
                level="core",
                definition=str(properties.get("definition") or properties.get("description") or ""),
                confidence="low",
                source_doc_id="legacy_graph",
                source_doc_title="旧版知识图谱",
                excerpt="来自旧版索引，需人工审查后才能用于回答。",
                suggested_rels=suggestions[node_id],
            )
            concept_candidates.append(candidate)

        memory_service = MemoryService(self.workspace, home=self.home)
        legacy_memory_names = {
            entry.name.casefold()
            for entry in LegacyMemoryReader(self.workspace).list_entries()
        }
        memory_candidates = []
        memory_skipped = []
        for node_id, node in selected_memories.items():
            name = str(node.get("name") or node_id.split(":", 1)[-1]).strip()
            if name.casefold() in legacy_memory_names:
                memory_skipped.append({"id": node_id, "reason": "covered_by_legacy_memory"})
                continue
            quality, content = self._quality(node)
            result = memory_service.add_candidate(
                scope="global",
                kind="profile_fact",
                operation="create",
                title=name,
                content=content,
                confidence=0.8 if quality == "complete" else 0.35,
                reason=(
                    "从旧版知识图谱导入。"
                    + ("该节点只有名称，确认前请补充内容。" if quality == "name_only" else "")
                ),
                evidence=[{"source_type": "legacy_graph", "source_id": node_id, "quality": quality}],
                generated_by="legacy_graph_import",
            )
            if result.get("candidate"):
                memory_candidates.append(result["candidate"])
            else:
                memory_skipped.append({"id": node_id, "reason": "duplicate_candidate"})

        accounted = (
            len(concept_candidates) == len(selected_concepts)
            and len(memory_candidates) + len(memory_skipped) == len(selected_memories)
        )
        if not accounted:
            return _err("迁移校验失败，旧文件未归档")

        archive_path = None
        checksum = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        if archive:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            target = self.source_path.with_name(f"{self.source_path.name}.archived")
            if target.exists():
                target = self.source_path.with_name(f"{self.source_path.name}.{timestamp}.archived")
            metadata = {
                "migrated_at": datetime.now(timezone.utc).isoformat(),
                "source": str(self.source_path),
                "archive": str(target),
                "sha256": checksum,
                "concept_candidates": len(concept_candidates),
                "memory_candidates": len(memory_candidates),
                "memory_skipped": memory_skipped,
            }
            metadata_path = target.with_name(f"{target.name}.migration.json")
            try:
                os.replace(self.source_path, target)
                metadata_path.write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                if target.exists() and not self.source_path.exists():
                    try:
                        os.replace(target, self.source_path)
                    except OSError:
                        return _err(
                            f"迁移已完成，但归档元数据写入失败；旧文件保留在 {target}: {exc}",
                            code="legacy_archive_metadata_failed",
                            archive_path=str(target),
                            sha256=checksum,
                        )
                return _err(
                    f"旧版知识图谱归档失败，源文件未删除: {exc}",
                    code="legacy_archive_failed",
                    sha256=checksum,
                )
            archive_path = str(target)

        return _ok(
            concept_candidates=concept_candidates,
            memory_candidates=memory_candidates,
            memory_skipped=memory_skipped,
            archived=bool(archive_path),
            archive_path=archive_path,
            sha256=checksum,
        )
