import os
from dataclasses import dataclass

from .manifest import load_manifest
from .paths import knowledge_dir


@dataclass
class CourseSummary:
    name: str
    file_count: int
    chunk_count: int
    error_count: int


@dataclass
class LibrarySummary:
    courses: list  # list[CourseSummary]
    total_files: int
    total_chunks: int
    total_errors: int
    graph_nodes: int
    graph_relationships: int
    graph_nodes_by_type: dict  # label -> count
    graph_relationships_by_type: dict  # type -> count
    graph_backend: str
    last_sync: str | None


def _count_by_key(items: list[dict], key: str) -> dict[str, int]:
    """Count occurrences of a key value in a list of dicts."""
    counts: dict[str, int] = {}
    for item in items:
        val = item.get(key, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return counts


def build_library_summary(workspace: str) -> LibrarySummary:
    """Build a complete summary of the knowledge base."""
    storage_dir = knowledge_dir(workspace)
    manifest = load_manifest(workspace)
    documents = manifest.get("documents", [])
    last_sync = manifest.get("last_sync")

    # Aggregate by course
    courses: dict[str, CourseSummary] = {}
    total_chunks = 0
    total_errors = 0

    for doc in documents:
        course_name = doc.get("course") or "未分类"
        if course_name not in courses:
            courses[course_name] = CourseSummary(
                name=course_name, file_count=0, chunk_count=0, error_count=0
            )
        cs = courses[course_name]
        cs.file_count += 1
        cs.chunk_count += doc.get("chunk_count", 0)
        if doc.get("status") == "error":
            cs.error_count += 1
            total_errors += 1
        total_chunks += doc.get("chunk_count", 0)

    # A portable database may exist before a manifest has been written.
    if total_chunks == 0:
        db_path = os.path.join(storage_dir, "knowledge.db")
        if os.path.exists(db_path):
            try:
                from rag.sqlite_store import KBSQLiteStore

                store = KBSQLiteStore(workspace)
                store.init_db()
                try:
                    total_chunks = store.count_chunks()
                finally:
                    store.close()
            except OSError:
                pass

    # Graph stats
    graph_nodes = 0
    graph_relationships = 0
    graph_nodes_by_type: dict[str, int] = {}
    graph_relationships_by_type: dict[str, int] = {}
    graph_backend = "concept_sqlite"

    concept_path = os.path.join(storage_dir, "concept_graph.db")
    if os.path.exists(concept_path):
        try:
            from graph.concept_store import ConceptStore

            store = ConceptStore(concept_path)
            concepts = store.list_concepts(limit=10000)
            relations = store.list_relationships()
            graph_nodes = len(concepts)
            graph_relationships = len(relations)
            for concept in concepts:
                level = concept.get("level", "core")
                graph_nodes_by_type[level] = graph_nodes_by_type.get(level, 0) + 1
            for rel in relations:
                rtype = rel.get("rel_type", "unknown")
                graph_relationships_by_type[rtype] = graph_relationships_by_type.get(rtype, 0) + 1
        except OSError:
            pass

    total_files = len(documents)

    return LibrarySummary(
        courses=list(courses.values()),
        total_files=total_files,
        total_chunks=total_chunks,
        total_errors=total_errors,
        graph_nodes=graph_nodes,
        graph_relationships=graph_relationships,
        graph_nodes_by_type=graph_nodes_by_type,
        graph_relationships_by_type=graph_relationships_by_type,
        graph_backend=graph_backend,
        last_sync=last_sync,
    )


def format_library_summary(summary: LibrarySummary) -> str:
    """Format library summary for human-readable display."""
    lines = []
    lines.append(f"总计: {summary.total_files} 个文件, {summary.total_chunks} 个 chunk")
    if summary.total_errors > 0:
        lines.append(f"错误: {summary.total_errors} 个文件导入失败")
    lines.append(f"图谱: {summary.graph_nodes} 个节点, {summary.graph_relationships} 个关系")
    lines.append(f"图谱后端: {summary.graph_backend}")
    if summary.last_sync:
        lines.append(f"上次同步: {summary.last_sync}")

    if summary.courses:
        lines.append("\n课程:")
        for cs in sorted(summary.courses, key=lambda c: c.name):
            err = f" (含 {cs.error_count} 个错误)" if cs.error_count else ""
            lines.append(f"  {cs.name}: {cs.file_count} 个文件, {cs.chunk_count} 个 chunk{err}")

    if summary.graph_nodes_by_type:
        lines.append("\n图谱节点类型:")
        for label, count in sorted(summary.graph_nodes_by_type.items()):
            lines.append(f"  {label}: {count}")

    return "\n".join(lines)
