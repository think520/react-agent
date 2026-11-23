"""Pure prerequisite graph traversal and topological ordering helpers."""

from __future__ import annotations

import heapq
from collections import deque
from typing import Any, Iterable

PREREQUISITE_REL_TYPE = "前置知识"


def _concept_terms(concept: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    name = str(concept.get("name") or "").strip()
    if name:
        terms.append(name)
    raw_aliases = concept.get("aliases") or []
    if isinstance(raw_aliases, str):
        raw_aliases = [raw_aliases]
    for alias in raw_aliases:
        cleaned = str(alias or "").strip()
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms


def _index_concepts(
    concepts: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_id: dict[str, dict[str, Any]] = {}
    term_to_id: dict[str, str] = {}
    for item in concepts:
        cid = str(item.get("concept_id") or "").strip()
        if not cid:
            continue
        by_id[cid] = item
        for term in _concept_terms(item):
            term_to_id.setdefault(term.casefold(), cid)
    return by_id, term_to_id


def _incoming_prerequisites(
    by_id: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Build ``to_id -> [from_id, ...]`` and unique valid ``(from_id, to_id)`` edges."""
    incoming: dict[str, list[str]] = {}
    edges: list[tuple[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for rel in relationships:
        if str(rel.get("rel_type") or "").strip() != PREREQUISITE_REL_TYPE:
            continue
        from_id = str(rel.get("from_id") or "").strip()
        to_id = str(rel.get("to_id") or "").strip()
        if not from_id or not to_id or from_id == to_id:
            continue
        if from_id not in by_id or to_id not in by_id:
            continue
        pair = (from_id, to_id)
        if pair in seen_edges:
            continue
        seen_edges.add(pair)
        edges.append(pair)
        incoming.setdefault(to_id, []).append(from_id)
    return incoming, edges


def find_prerequisites(
    concept_name: str,
    concepts: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    max_depth: int = 2,
) -> list[dict[str, Any]]:
    """Find up to ``max_depth`` hops of upstream prerequisites for ``concept_name``.

    Canonical direction: ``(from_id, to_id, rel_type='前置知识')`` means
    ``from_id`` is a prerequisite of ``to_id``.
    """
    needle = str(concept_name or "").strip().casefold()
    if not needle:
        return []
    by_id, term_to_id = _index_concepts(concepts)
    start_id = term_to_id.get(needle)
    if not start_id:
        return []

    incoming, _ = _incoming_prerequisites(by_id, relationships)
    depth_limit = max(1, min(int(max_depth), 3))
    visited: set[str] = {start_id}
    queue: deque[tuple[str, int, str | None]] = deque([(start_id, 0, None)])
    found: list[dict[str, Any]] = []

    while queue:
        cur_id, depth, first_hop_name = queue.popleft()
        if depth >= depth_limit:
            continue
        next_depth = depth + 1
        prereq_ids = sorted(
            incoming.get(cur_id, []),
            key=lambda cid: (str(by_id[cid].get("name") or "").casefold(), cid),
        )
        for prereq_id in prereq_ids:
            if prereq_id in visited:
                continue
            visited.add(prereq_id)
            prereq_name = str(by_id[prereq_id].get("name") or "").strip()
            if not prereq_name:
                continue
            via = first_hop_name if next_depth > 1 else None
            found.append({
                "concept_id": prereq_id,
                "name": prereq_name,
                "depth": next_depth,
                "via": via,
            })
            next_first = prereq_name if next_depth == 1 else first_hop_name
            queue.append((prereq_id, next_depth, next_first))

    found.sort(key=lambda item: (item["depth"], item["name"].casefold(), item["concept_id"]))
    return found


def _match_scope_ids(
    by_id: dict[str, dict[str, Any]],
    term_to_id: dict[str, str],
    scope_names: Iterable[str],
) -> list[str]:
    matched_ids: list[str] = []
    seen: set[str] = set()
    scopes = [str(item or "").strip().casefold() for item in scope_names if str(item or "").strip()]
    for scope in scopes:
        exact_id = term_to_id.get(scope)
        if exact_id and exact_id not in seen:
            seen.add(exact_id)
            matched_ids.append(exact_id)
        for cid, concept in sorted(
            by_id.items(),
            key=lambda kv: (-len(str(kv[1].get("name") or "")), kv[0]),
        ):
            if cid in seen:
                continue
            for term in _concept_terms(concept):
                folded = term.casefold()
                if len(folded) >= 2 and folded in scope:
                    seen.add(cid)
                    matched_ids.append(cid)
                    break
    return matched_ids


def topological_prerequisite_order(
    concepts: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    scope_names: Iterable[str] | None = None,
    max_nodes: int = 30,
) -> dict[str, Any]:
    """Compute deterministic topological prerequisite order using Kahn's algorithm.

    Returns ``ordered_concepts`` (prerequisites before dependents), ``edges`` as
    ``(prereq_name, target_name)`` pairs, ``cycle_concepts``, and ``has_cycles``.
    """
    by_id, term_to_id = _index_concepts(concepts)
    incoming, all_edges = _incoming_prerequisites(by_id, relationships)
    if not all_edges:
        return {
            "ordered_concepts": [],
            "edges": [],
            "cycle_concepts": [],
            "has_cycles": False,
        }

    cap = max(1, int(max_nodes))
    selected_ids: list[str] = []
    seen_ids: set[str] = set()

    matched_targets = _match_scope_ids(by_id, term_to_id, scope_names or [])
    if matched_targets:
        queue: deque[str] = deque(matched_targets)
        for cid in matched_targets:
            if cid not in seen_ids:
                seen_ids.add(cid)
                selected_ids.append(cid)
        while queue and len(selected_ids) < cap:
            cur_id = queue.popleft()
            prereqs = sorted(
                incoming.get(cur_id, []),
                key=lambda cid: (str(by_id[cid].get("name") or "").casefold(), cid),
            )
            for prereq_id in prereqs:
                if prereq_id not in seen_ids:
                    seen_ids.add(prereq_id)
                    selected_ids.append(prereq_id)
                    queue.append(prereq_id)
                    if len(selected_ids) >= cap:
                        break
    else:
        edge_nodes = sorted(
            {cid for pair in all_edges for cid in pair},
            key=lambda cid: (str(by_id[cid].get("name") or "").casefold(), cid),
        )
        for cid in edge_nodes[:cap]:
            seen_ids.add(cid)
            selected_ids.append(cid)

    node_set = set(selected_ids)
    sub_edges = [(u, v) for u, v in all_edges if u in node_set and v in node_set]
    if not sub_edges:
        return {
            "ordered_concepts": [],
            "edges": [],
            "cycle_concepts": [],
            "has_cycles": False,
        }

    # Restrict to nodes actually connected by prerequisite edges in the subgraph.
    connected = {cid for edge in sub_edges for cid in edge}
    indegree: dict[str, int] = {cid: 0 for cid in connected}
    outgoing: dict[str, list[str]] = {cid: [] for cid in connected}
    for prereq_id, target_id in sub_edges:
        outgoing[prereq_id].append(target_id)
        indegree[target_id] += 1

    heap: list[tuple[str, str]] = [
        (str(by_id[cid].get("name") or "").casefold(), cid)
        for cid, deg in indegree.items()
        if deg == 0
    ]
    heapq.heapify(heap)

    ordered_ids: list[str] = []
    while heap:
        _, cid = heapq.heappop(heap)
        ordered_ids.append(cid)
        for nxt in outgoing.get(cid, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(heap, (str(by_id[nxt].get("name") or "").casefold(), nxt))

    remaining = sorted(
        [cid for cid, deg in indegree.items() if deg > 0],
        key=lambda cid: (str(by_id[cid].get("name") or "").casefold(), cid),
    )
    cycle_concepts = [str(by_id[cid].get("name") or cid) for cid in remaining]
    all_ordered_ids = [*ordered_ids, *remaining]

    ordered_concepts = [str(by_id[cid].get("name") or cid) for cid in all_ordered_ids]
    edge_names = [
        (str(by_id[u].get("name") or u), str(by_id[v].get("name") or v))
        for u, v in sorted(
            sub_edges,
            key=lambda e: (
                str(by_id[e[0]].get("name") or "").casefold(),
                str(by_id[e[1]].get("name") or "").casefold(),
            ),
        )
    ]
    return {
        "ordered_concepts": ordered_concepts,
        "edges": edge_names,
        "cycle_concepts": cycle_concepts,
        "has_cycles": bool(cycle_concepts),
    }
