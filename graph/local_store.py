import json
import os
from typing import Iterable

from obsidian.vault import ScannedNote

from .schema import RELATIONSHIP_TYPES, node_id


GRAPH_VERSION = 1


class LocalGraphStore:
    """JSON-backed graph store used when Neo4j is unavailable."""

    backend_name = "local_json"

    def __init__(self, graph_path: str):
        self.graph_path = graph_path
        self.nodes: dict[str, dict] = {}
        self.relationships: list[dict] = []

    def load(self) -> None:
        if not os.path.exists(self.graph_path):
            self.nodes = {}
            self.relationships = []
            return
        with open(self.graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.nodes = data.get("nodes", {})
        self.relationships = data.get("relationships", [])

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.graph_path), exist_ok=True)
        with open(self.graph_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": GRAPH_VERSION,
                    "backend": self.backend_name,
                    "nodes": self.nodes,
                    "relationships": self.relationships,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def clear(self) -> None:
        self.nodes = {}
        self.relationships = []

    def add_node(self, label: str, name: str, **properties) -> str:
        nid = node_id(label, name)
        existing = self.nodes.get(nid, {})
        merged = {**existing.get("properties", {}), **{k: v for k, v in properties.items() if v not in (None, [], {})}}
        self.nodes[nid] = {"id": nid, "label": label, "name": name, "properties": merged}
        return nid

    def add_relationship(self, start_id: str, rel_type: str, end_id: str, **properties) -> None:
        if rel_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unknown graph relationship type: {rel_type}")
        rel = {
            "start": start_id,
            "type": rel_type,
            "end": end_id,
            "properties": {k: v for k, v in properties.items() if v not in (None, [], {})},
        }
        key = (rel["start"], rel["type"], rel["end"])
        if any((item["start"], item["type"], item["end"]) == key for item in self.relationships):
            return
        self.relationships.append(rel)

    def replace_from_notes(self, notes: Iterable[ScannedNote]) -> int:
        """Rebuild the graph from parsed Obsidian notes."""
        self.clear()
        for scanned in notes:
            note = scanned.note
            concept_id = self.add_node("Concept", note.title, aliases=note.aliases)
            note_id = self.add_node("Note", scanned.rel_path, title=note.title, path=scanned.rel_path)
            self.add_relationship(concept_id, "MENTIONED_IN", note_id, source=scanned.rel_path)

            if note.course:
                course_id = self.add_node("Course", note.course)
                self.add_relationship(concept_id, "BELONGS_TO", course_id, source=scanned.rel_path)
            if note.chapter:
                chapter_id = self.add_node("Chapter", note.chapter)
                self.add_relationship(concept_id, "IN_CHAPTER", chapter_id, source=scanned.rel_path)

            for tag in note.tags:
                tag_id = self.add_node("Tag", tag)
                self.add_relationship(concept_id, "TAGGED_AS", tag_id, source=scanned.rel_path)

            for link in note.links:
                target_id = self.add_node("Concept", link.target)
                self.add_relationship(concept_id, "RELATED_TO", target_id, source=scanned.rel_path, alias=link.alias)

        self.save()
        return len(self.relationships)

    def _find_concept_id(self, concept: str) -> str | None:
        self.load()
        target = concept.casefold()
        for nid, node in self.nodes.items():
            if node.get("label") != "Concept":
                continue
            if node.get("name", "").casefold() == target:
                return nid
            aliases = node.get("properties", {}).get("aliases") or []
            if any(alias.casefold() == target for alias in aliases):
                return nid
        return None

    def query(self, concept: str, intent: str = "related", limit: int = 20) -> dict:
        self.load()
        concept_id = self._find_concept_id(concept)
        if not concept_id:
            return {
                "concept": concept,
                "intent": intent,
                "nodes": [],
                "relationships": [],
                "source": self.backend_name,
            }

        rel_filter = {
            "related": {"RELATED_TO"},
            "tags": {"TAGGED_AS"},
            "tagged": {"TAGGED_AS"},
            "mentions": {"MENTIONED_IN"},
            "sources": {"MENTIONED_IN"},
            "prerequisites": {"PREREQUISITE_OF"},
            "course": {"BELONGS_TO", "IN_CHAPTER"},
        }.get(intent, {"RELATED_TO", "TAGGED_AS", "MENTIONED_IN", "BELONGS_TO", "IN_CHAPTER"})

        selected = []
        node_ids = {concept_id}
        for rel in self.relationships:
            if rel["type"] not in rel_filter:
                continue
            if rel["start"] == concept_id or rel["end"] == concept_id:
                selected.append(rel)
                node_ids.add(rel["start"])
                node_ids.add(rel["end"])
            if len(selected) >= limit:
                break

        return {
            "concept": self.nodes[concept_id]["name"],
            "intent": intent,
            "nodes": [self.nodes[nid] for nid in sorted(node_ids) if nid in self.nodes],
            "relationships": selected,
            "source": self.backend_name,
        }
