"""ConceptService — business logic for knowledge map (P5E.6).

Used by web/backend/routers/graph.py.
Returns structured dicts: {"ok": bool, ...}.
"""

from __future__ import annotations

import os
import time
from typing import Any

from graph.concept_store import ConceptStore
from knowledge.paths import knowledge_path


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


def _store(workspace: str) -> ConceptStore:
    db_path = knowledge_path(workspace, "concept_graph.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return ConceptStore(db_path)


class ConceptService:
    """Business logic layer for the concept knowledge map."""

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace
        self._store = _store(workspace)

    # ------------------------------------------------------------------
    # Graph state
    # ------------------------------------------------------------------

    def get_graph_state(
        self,
        *,
        topic_id: str | None = None,
        include_candidates: bool = False,
        view_id: str = "default",
    ) -> dict[str, Any]:
        try:
            state = self._store.get_graph_state(
                topic_id=topic_id,
                include_candidates=include_candidates,
                view_id=view_id,
            )
            return _ok(**state)
        except Exception as exc:
            return _err(str(exc))

    def get_subgraph(
        self, concept_id: str, *, view_id: str = "default"
    ) -> dict[str, Any]:
        try:
            data = self._store.get_subgraph(concept_id, view_id=view_id)
            if data is None:
                return _err("concept_not_found")
            return _ok(**data)
        except Exception as exc:
            return _err(str(exc))

    # ------------------------------------------------------------------
    # Concepts CRUD
    # ------------------------------------------------------------------

    def get_concept(self, concept_id: str) -> dict[str, Any]:
        c = self._store.get_concept(concept_id)
        if c is None:
            return _err("concept_not_found")
        rels = self._store.relationships_for_concept(concept_id)
        ev_map: dict[str, list[dict[str, Any]]] = {}
        for rel in rels:
            ev_map[rel["rel_id"]] = self._store.evidence_for_relationship(
                rel["rel_id"]
            )
        return _ok(concept=c, relationships=rels, evidence=ev_map)

    def upsert_concept(
        self,
        *,
        concept_id: str | None = None,
        name: str,
        level: str = "core",
        definition: str = "",
        aliases: list[str] | None = None,
        topic_ids: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        if not name.strip():
            return _err("name_required")
        if level not in {"cluster", "core", "detail"}:
            return _err("invalid_level")
        try:
            c = self._store.upsert_concept(
                concept_id=concept_id,
                name=name.strip(),
                level=level,
                definition=definition,
                aliases=aliases,
                topic_ids=topic_ids,
                note=note,
            )
            return _ok(concept=c)
        except Exception as exc:
            return _err(str(exc))

    def delete_concept(self, concept_id: str) -> dict[str, Any]:
        deleted = self._store.delete_concept(concept_id)
        if not deleted:
            return _err("concept_not_found")
        return _ok()

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def add_relationship(
        self,
        *,
        from_id: str,
        to_id: str,
        rel_type: str,
        evidence_level: str = "user",
        note: str = "",
    ) -> dict[str, Any]:
        _valid_rel_types = {"属于", "前置知识", "组成部分", "对比", "应用于", "来源于"}
        if rel_type not in _valid_rel_types and not rel_type.startswith("user:"):
            return _err(f"invalid_rel_type: {rel_type}")
        if not self._store.get_concept(from_id):
            return _err("from_concept_not_found")
        if not self._store.get_concept(to_id):
            return _err("to_concept_not_found")
        try:
            rel = self._store.upsert_relationship(
                from_id=from_id,
                to_id=to_id,
                rel_type=rel_type,
                evidence_level=evidence_level,
                note=note,
            )
            return _ok(relationship=rel)
        except Exception as exc:
            return _err(str(exc))

    def delete_relationship(self, rel_id: str) -> dict[str, Any]:
        deleted = self._store.delete_relationship(rel_id)
        if not deleted:
            return _err("relationship_not_found")
        return _ok()

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------

    def list_candidates(self, *, status: str = "pending") -> dict[str, Any]:
        try:
            items = self._store.list_candidates(status=status)
            return _ok(candidates=items, count=len(items))
        except Exception as exc:
            return _err(str(exc))

    def confirm_candidate(self, candidate_id: str) -> dict[str, Any]:
        """Confirm a candidate: create concept + suggested relationships."""
        cand = self._store.get_candidate(candidate_id)
        if cand is None:
            return _err("candidate_not_found")
        if cand["status"] != "pending":
            return _err("candidate_not_pending")

        # Create the concept
        concept = self._store.upsert_concept(
            name=cand["name"],
            level=cand["level"],
            definition=cand["definition"],
        )

        # Create suggested relationships where both ends exist
        created_rels: list[dict[str, Any]] = []
        for sug in cand.get("suggested_rels", []):
            other = self._store.get_concept_by_name(sug.get("to_name", ""))
            if other is None:
                continue
            rel_type = sug.get("rel_type", "属于")
            rel = self._store.upsert_relationship(
                from_id=concept["concept_id"],
                to_id=other["concept_id"],
                rel_type=rel_type,
                evidence_level="source",
            )
            created_rels.append(rel)
            # Add evidence if excerpt available
            if cand.get("excerpt") and cand.get("source_doc_id"):
                self._store.add_evidence(
                    rel_id=rel["rel_id"],
                    document_id=cand["source_doc_id"],
                    document_title=cand.get("source_doc_title", ""),
                    excerpt=cand["excerpt"],
                )

        self._store.update_candidate_status(candidate_id, "confirmed")
        return _ok(concept=concept, relationships=created_rels)

    def reject_candidate(
        self, candidate_id: str, *, suppress_days: int = 14
    ) -> dict[str, Any]:
        cand = self._store.get_candidate(candidate_id)
        if cand is None:
            return _err("candidate_not_found")
        suppress_until = time.time() + suppress_days * 86400 if suppress_days > 0 else None
        self._store.update_candidate_status(
            candidate_id, "rejected", suppressed_until=suppress_until
        )
        return _ok()

    def demote_candidate_to_label(self, candidate_id: str) -> dict[str, Any]:
        cand = self._store.get_candidate(candidate_id)
        if cand is None:
            return _err("candidate_not_found")
        self._store.update_candidate_status(candidate_id, "label")
        return _ok()

    # ------------------------------------------------------------------
    # Extract concepts from a document
    # ------------------------------------------------------------------

    def extract_from_document(
        self,
        *,
        document_id: str,
        document_title: str,
        content: str,
        llm_provider: Any,
        document_path: str = "",
    ) -> dict[str, Any]:
        """Run LLM extraction and store results as pending candidates."""
        from wiki.extractor import ConceptExtractor
        extractor = ConceptExtractor(llm_provider)
        result = extractor.extract(
            document_id=document_id,
            document_title=document_title,
            document_path=document_path,
            content=content,
        )

        if result.get("error"):
            return _err(result["error"])

        stored: list[dict[str, Any]] = []
        for item in result["core_concepts"]:
            # Build suggested_rels for this candidate
            suggested_rels = [
                {"rel_type": r["rel_type"], "to_name": r["to"]}
                for r in result["relationships"]
                if r["from"] == item["name"]
            ]
            cand = self._store.add_candidate(
                name=item["name"],
                level="core",
                definition=item["definition"],
                confidence=item["confidence"],
                source_doc_id=document_id,
                source_doc_title=document_title,
                excerpt=item["excerpt"],
                suggested_rels=suggested_rels,
            )
            stored.append(cand)

        for item in result["detail_concepts"]:
            suggested_rels = [
                {"rel_type": r["rel_type"], "to_name": r["to"]}
                for r in result["relationships"]
                if r["from"] == item["name"]
            ]
            cand = self._store.add_candidate(
                name=item["name"],
                level="detail",
                definition=item["definition"],
                confidence=item["confidence"],
                source_doc_id=document_id,
                source_doc_title=document_title,
                excerpt=item["excerpt"],
                suggested_rels=suggested_rels,
            )
            stored.append(cand)

        pending = self._store.pending_candidates_count()
        return _ok(
            stored=len(stored),
            tags=result["tags"],
            pending_total=pending,
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def save_positions(
        self,
        positions: list[dict[str, Any]],
        *,
        view_id: str = "default",
    ) -> dict[str, Any]:
        try:
            self._store.save_positions(positions, view_id=view_id)
            return _ok(saved=len(positions))
        except Exception as exc:
            return _err(str(exc))
