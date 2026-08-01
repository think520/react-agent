"""ConceptService — business logic for knowledge map (P5E.6).

Used by web/backend/routers/graph.py.
Returns structured dicts: {"ok": bool, ...}.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Any

from graph.concept_store import ConceptStore
from knowledge.paths import knowledge_path
from service._result import err as _err, ok as _ok


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

    def get_status(self) -> dict[str, Any]:
        try:
            status = self._store.graph_status()
            return _ok(
                available=True,
                has_reviewed_graph=status["concept_count"] > 0,
                **status,
            )
        except Exception as exc:
            return _err(str(exc))

    def search(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        if not query.strip():
            return _err("query_required")
        try:
            concepts = self._store.search_concepts(
                query.strip(),
                limit=max(1, min(limit, 20)),
            )
            return _ok(operation="search", concepts=concepts, count=len(concepts))
        except Exception as exc:
            return _err(str(exc))

    def neighbors(
        self,
        *,
        concept_id: str | None = None,
        concept: str | None = None,
        depth: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        resolved = self._resolve_concept(concept_id=concept_id, concept=concept)
        if not resolved.get("ok"):
            return resolved
        root = resolved["concept"]
        max_depth = max(1, min(depth, 2))
        max_relationships = max(1, min(limit, 50))
        relationships = self._store.list_relationships()
        discovered = {root["concept_id"]}
        frontier = {root["concept_id"]}
        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for rel in relationships:
                if rel["from_id"] in frontier:
                    other_id = rel["to_id"]
                elif rel["to_id"] in frontier:
                    other_id = rel["from_id"]
                else:
                    continue
                if rel["rel_id"] not in selected_ids:
                    selected.append(self._relationship_payload(rel))
                    selected_ids.add(rel["rel_id"])
                if other_id not in discovered:
                    discovered.add(other_id)
                    next_frontier.add(other_id)
                if len(selected) >= max_relationships:
                    break
            frontier = next_frontier
            if not frontier or len(selected) >= max_relationships:
                break
        concepts = [
            item
            for item_id in discovered
            if (item := self._store.get_concept(item_id)) is not None
        ]
        return _ok(
            operation="neighbors",
            root=root,
            depth=max_depth,
            concepts=concepts,
            relationships=selected,
        )

    def path(
        self,
        *,
        from_concept_id: str | None = None,
        from_concept: str | None = None,
        to_concept_id: str | None = None,
        to_concept: str | None = None,
        max_depth: int = 4,
    ) -> dict[str, Any]:
        source = self._resolve_concept(
            concept_id=from_concept_id,
            concept=from_concept,
        )
        if not source.get("ok"):
            return source
        target = self._resolve_concept(
            concept_id=to_concept_id,
            concept=to_concept,
        )
        if not target.get("ok"):
            return target
        source_id = source["concept"]["concept_id"]
        target_id = target["concept"]["concept_id"]
        relationships = self._store.list_relationships()
        by_node: dict[str, list[dict[str, Any]]] = {}
        for rel in relationships:
            by_node.setdefault(rel["from_id"], []).append(rel)
            by_node.setdefault(rel["to_id"], []).append(rel)

        depth_limit = max(1, min(max_depth, 6))
        queue = deque([(source_id, [], [source_id])])
        visited = {source_id}
        found_relations: list[dict[str, Any]] | None = None
        found_nodes: list[str] | None = None
        while queue:
            node_id, rel_path, node_path = queue.popleft()
            if len(rel_path) >= depth_limit:
                continue
            for rel in by_node.get(node_id, []):
                next_id = rel["to_id"] if rel["from_id"] == node_id else rel["from_id"]
                if next_id in visited:
                    continue
                next_rel_path = [*rel_path, rel]
                next_node_path = [*node_path, next_id]
                if next_id == target_id:
                    found_relations = next_rel_path
                    found_nodes = next_node_path
                    queue.clear()
                    break
                visited.add(next_id)
                queue.append((next_id, next_rel_path, next_node_path))

        if found_relations is None or found_nodes is None:
            return _ok(
                operation="path",
                found=False,
                concepts=[source["concept"], target["concept"]],
                relationships=[],
            )
        concepts = [
            item
            for concept_key in found_nodes
            if (item := self._store.get_concept(concept_key)) is not None
        ]
        return _ok(
            operation="path",
            found=True,
            concepts=concepts,
            relationships=[
                self._relationship_payload(rel) for rel in found_relations
            ],
        )

    def _resolve_concept(
        self,
        *,
        concept_id: str | None,
        concept: str | None,
    ) -> dict[str, Any]:
        if concept_id:
            item = self._store.get_concept(concept_id)
            return _ok(concept=item) if item else _err("concept_not_found")
        if not concept or not concept.strip():
            return _err("concept_required")
        item = self._store.get_concept_by_name(concept.strip())
        if item:
            return _ok(concept=item)
        matches = self._store.search_concepts(concept.strip(), limit=5)
        if len(matches) == 1:
            return _ok(concept=matches[0])
        if matches:
            return {
                "ok": False,
                "error": "concept_ambiguous",
                "matches": matches,
            }
        return _err("concept_not_found")

    def _relationship_payload(self, rel: dict[str, Any]) -> dict[str, Any]:
        evidence = self._store.evidence_for_relationship(rel["rel_id"])
        valid = [item for item in evidence if not item.get("location_stale")]
        stale = [item for item in evidence if item.get("location_stale")]
        if valid:
            evidence_status = "valid"
        elif stale:
            evidence_status = "stale"
        else:
            evidence_status = "missing"
        return {
            **rel,
            "evidence_status": evidence_status,
            "valid_evidence_count": len(valid),
            "stale_evidence_count": len(stale),
            "evidence": [
                {
                    **item,
                    "excerpt": str(item.get("excerpt") or "")[:300],
                }
                for item in evidence[:5]
            ],
        }

    def refresh_document_evidence(
        self,
        document_id: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_id = {
            str(chunk.get("id") or chunk.get("chunk_id")): chunk
            for chunk in chunks
            if chunk.get("id") or chunk.get("chunk_id")
        }
        repaired = 0
        stale = 0
        for evidence in self._store.evidence_for_document(document_id):
            chunk_id = evidence.get("chunk_id")
            if chunk_id and chunk_id in by_id:
                self._store.update_evidence_location(
                    evidence["evidence_id"],
                    chunk_id=chunk_id,
                    location_stale=False,
                )
                continue
            matched_chunk_id = self._match_excerpt_to_chunks(
                str(evidence.get("excerpt") or ""),
                chunks,
            )
            if matched_chunk_id:
                self._store.update_evidence_location(
                    evidence["evidence_id"],
                    chunk_id=matched_chunk_id,
                    location_stale=False,
                )
                repaired += 1
            else:
                self._store.update_evidence_location(
                    evidence["evidence_id"],
                    chunk_id=chunk_id,
                    location_stale=True,
                )
                stale += 1
        return _ok(repaired=repaired, stale=stale)

    def mark_document_evidence_stale(self, document_id: str) -> dict[str, Any]:
        changed = 0
        for evidence in self._store.evidence_for_document(document_id):
            changed += int(self._store.update_evidence_location(
                evidence["evidence_id"],
                chunk_id=evidence.get("chunk_id"),
                location_stale=True,
            ))
        return _ok(stale=changed)

    @staticmethod
    def _match_excerpt_to_chunks(
        excerpt: str,
        chunks: list[dict[str, Any]],
    ) -> str | None:
        needle = " ".join(excerpt.split())
        if not needle:
            return None
        for chunk in chunks:
            text = " ".join(str(chunk.get("text") or "").split())
            if needle in text or (len(needle) >= 80 and needle[:80] in text):
                value = chunk.get("id") or chunk.get("chunk_id")
                return str(value) if value else None
        return None

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
        except ValueError as exc:
            message = str(exc)
            if message.startswith("concept_name_conflict:"):
                name = message.split(":", 1)[1] if ":" in message else message
                return _err(f"已存在同名概念：{name}", code="conflict")
            return _err(message)
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
        _valid_rel_types = {"属于", "前置知识", "组成部分", "对比", "应用于", "来源于", "影响", "优化", "示例"}
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

    def list_candidates(
        self,
        *,
        status: str = "pending",
        source_doc_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            items = self._store.list_candidates(
                status=status,
                source_doc_id=source_doc_id,
            )
            return _ok(candidates=items, count=len(items))
        except Exception as exc:
            return _err(str(exc))

    def confirm_candidate(
        self,
        candidate_id: str,
        *,
        relation_edits: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result = self.confirm_candidates(
            [candidate_id],
            relation_edits=relation_edits or [],
        )
        if result.get("ok") and result.get("concepts"):
            return {**result, "concept": result["concepts"][0]}
        return result

    def confirm_candidates(
        self,
        candidate_ids: list[str],
        *,
        relation_edits: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        candidates = []
        for candidate_id in dict.fromkeys(candidate_ids):
            cand = self._store.get_candidate(candidate_id)
            if cand is None:
                return _err("candidate_not_found")
            if cand["status"] != "pending":
                return _err("candidate_not_pending")
            candidates.append(cand)

        edits_by_candidate: dict[str, list[dict[str, Any]]] = {}
        for edit in relation_edits or []:
            edits_by_candidate.setdefault(str(edit.get("candidate_id") or ""), []).append(edit)
        valid_rel_types = {"属于", "前置知识", "组成部分", "对比", "应用于", "来源于", "影响", "优化", "示例"}
        for cand in candidates:
            suggestions = list(cand.get("suggested_rels") or [])
            for edit in edits_by_candidate.get(cand["candidate_id"], []):
                index = int(edit.get("index", -1))
                if not 0 <= index < len(suggestions):
                    continue
                updated = dict(suggestions[index])
                rel_type = str(edit.get("rel_type") or updated.get("rel_type") or "属于")
                if rel_type not in valid_rel_types:
                    return _err(f"invalid_rel_type: {rel_type}")
                updated["rel_type"] = rel_type
                updated["enabled"] = bool(edit.get("enabled", True))
                updated["direction"] = "incoming" if edit.get("direction") == "incoming" else "outgoing"
                suggestions[index] = updated
            self._store.update_candidate_suggested_rels(cand["candidate_id"], suggestions)
            cand["suggested_rels"] = suggestions

        concepts = []
        for cand in candidates:
            concept = self._store.get_concept_by_name(cand["name"])
            if concept is None:
                concept = self._store.upsert_concept(
                    name=cand["name"],
                    level=cand["level"],
                    definition=cand["definition"],
                )
            concepts.append(concept)
        document_ids = {cand.get("source_doc_id", "") for cand in candidates}
        for cand in candidates:
            self._store.update_candidate_status(cand["candidate_id"], "confirmed")
        created_rels = []
        for document_id in document_ids:
            created_rels.extend(self._materialize_confirmed_candidate_relationships(document_id))
        return _ok(concepts=concepts, relationships=created_rels)

    def _materialize_confirmed_candidate_relationships(self, document_id: str) -> list[dict[str, Any]]:
        candidates = self._store.list_candidates(status="confirmed", source_doc_id=document_id)
        existing = {
            (rel["from_id"], rel["to_id"], rel["rel_type"]): rel
            for rel in self._store.list_relationships()
        }
        created = []
        for cand in candidates:
            source = self._store.get_concept_by_name(cand["name"])
            if source is None:
                continue
            for suggestion in cand.get("suggested_rels") or []:
                if suggestion.get("enabled") is False:
                    continue
                target = self._store.get_concept_by_name(str(suggestion.get("to_name") or ""))
                if target is None:
                    continue
                from_id, to_id = source["concept_id"], target["concept_id"]
                if suggestion.get("direction") == "incoming":
                    from_id, to_id = to_id, from_id
                rel_type = str(suggestion.get("rel_type") or "属于")
                key = (from_id, to_id, rel_type)
                rel = existing.get(key)
                is_new = rel is None
                if rel is None:
                    rel = self._store.upsert_relationship(
                        from_id=from_id,
                        to_id=to_id,
                        rel_type=rel_type,
                        evidence_level="source",
                    )
                excerpt = str(suggestion.get("excerpt") or cand.get("excerpt") or "")[:300]
                if excerpt and document_id:
                    evidence = self._store.evidence_for_relationship(rel["rel_id"])
                    if not any(
                        item["document_id"] == document_id and item["excerpt"] == excerpt
                        for item in evidence
                    ):
                        self._store.add_evidence(
                            rel_id=rel["rel_id"],
                            document_id=document_id,
                            chunk_id=self._find_chunk_id(document_id, excerpt),
                            document_title=cand.get("source_doc_title", ""),
                            excerpt=excerpt,
                        )
                existing[key] = rel
                if is_new:
                    created.append(rel)
        return created

    def _find_chunk_id(self, document_id: str, excerpt: str) -> str | None:
        if not document_id or not excerpt.strip():
            return None
        try:
            from service.kb_service import KBService

            result = KBService(self._workspace).get_document(document_id)
            if not result.get("ok"):
                return None
            return self._match_excerpt_to_chunks(
                excerpt,
                result.get("sections", []),
            )
        except Exception:
            return None

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

    def create_extraction_run(
        self,
        *,
        document_id: str,
        document_title: str,
        content_version: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        try:
            latest = self._store.get_latest_extraction_run(document_id)
            if latest and latest["status"] in {"queued", "running"}:
                return _ok(run=latest, started=False)
            if (
                latest
                and latest["status"] == "completed"
                and latest.get("content_version", "") == content_version
                and not force
            ):
                return _ok(run=latest, started=False)
            run = self._store.create_extraction_run(
                document_id=document_id,
                document_title=document_title,
                content_version=content_version,
            )
            return _ok(run=run, started=True)
        except Exception as exc:
            return _err(str(exc))

    def list_extraction_statuses(self) -> dict[str, Any]:
        try:
            pending_counts = self._store.pending_candidates_count_by_document()
            documents: dict[str, dict[str, Any]] = {}
            for run in self._store.list_latest_extraction_runs():
                pending_count = pending_counts.get(run["document_id"], 0)
                if run["status"] in {"queued", "running"}:
                    status = "extracting"
                elif run["status"] == "failed":
                    status = "failed"
                elif pending_count:
                    status = "review"
                else:
                    status = "completed"
                documents[run["document_id"]] = {
                    "status": status,
                    "pending_count": pending_count,
                    "run": run,
                }
            return _ok(documents=documents)
        except Exception as exc:
            return _err(str(exc))

    def get_extraction_run(self, run_id: str) -> dict[str, Any]:
        run = self._store.get_extraction_run(run_id)
        if run is None:
            return _err("extraction_run_not_found")
        return _ok(run=run)

    def fail_extraction_run(self, run_id: str, error: str) -> None:
        self._store.update_extraction_run(run_id, status="failed", error=error)

    def execute_extraction_run(
        self,
        *,
        run_id: str,
        document_id: str,
        document_title: str,
        content: str,
        llm_provider: Any,
        document_path: str = "",
        sections: list[dict[str, Any]] | None = None,
        incremental: bool = False,
    ) -> dict[str, Any]:
        self._store.update_extraction_run(run_id, status="running", stage="scanning_sections")
        try:
            def progress(stage: str, _payload: dict[str, Any]) -> None:
                self._store.update_extraction_run(run_id, status="running", stage=stage)

            result = self.extract_from_document(
                document_id=document_id,
                document_title=document_title,
                document_path=document_path,
                content=content,
                llm_provider=llm_provider,
                sections=sections,
                progress=progress,
                incremental=incremental,
            )
            if not result.get("ok"):
                error = str(result.get("error") or "概念提取失败")
                self._store.update_extraction_run(
                    run_id,
                    status="failed",
                    error=error,
                )
                return result
            self._store.update_extraction_run(
                run_id,
                status="completed_with_warnings" if result.get("warnings") else "completed",
                stage="ready_for_review",
                stored_count=int(result.get("stored", 0)),
                warnings=result.get("warnings") or [],
                failed_sections=result.get("failed_sections") or [],
            )
            return result
        except Exception as exc:
            self._store.update_extraction_run(
                run_id,
                status="failed",
                error=str(exc),
            )
            return _err(str(exc))

    def extract_from_document(
        self,
        *,
        document_id: str,
        document_title: str,
        content: str,
        llm_provider: Any,
        document_path: str = "",
        sections: list[dict[str, Any]] | None = None,
        progress: Any = None,
        incremental: bool = False,
    ) -> dict[str, Any]:
        """Run LLM extraction and store results as pending candidates."""
        from wiki.extractor import ConceptExtractor
        extractor = ConceptExtractor(llm_provider)
        result = extractor.extract(
            document_id=document_id,
            document_title=document_title,
            document_path=document_path,
            content=content,
            sections=sections,
            progress=progress,
        )

        if result.get("error"):
            return _err(result["error"])

        if not incremental:
            self._store.archive_pending_candidates(document_id)
        stored: list[dict[str, Any]] = []
        for item in result["core_concepts"]:
            existing = self._store.get_candidate_by_document_and_name(document_id, item["name"])
            if existing and existing["status"] in {"confirmed", "rejected", "label"}:
                continue
            # Build suggested_rels for this candidate
            suggested_rels = [
                {"rel_type": r["rel_type"], "to_name": r["to"], "excerpt": r.get("excerpt", "")}
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
            existing = self._store.get_candidate_by_document_and_name(document_id, item["name"])
            if existing and existing["status"] in {"confirmed", "rejected", "label"}:
                continue
            suggested_rels = [
                {"rel_type": r["rel_type"], "to_name": r["to"], "excerpt": r.get("excerpt", "")}
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
            warnings=result.get("warnings") or [],
            failed_sections=result.get("failed_sections") or [],
            quality=result.get("quality") or {},
            supplemented=bool(result.get("supplemented")),
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
