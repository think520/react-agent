from obsidian.vault import ScannedNote


class Neo4jGraphStore:
    """Thin Neo4j adapter. It is optional and loaded only when configured."""

    backend_name = "neo4j"

    def __init__(self, uri: str, username: str, password: str):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("neo4j driver is not installed") from exc
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def replace_from_notes(self, notes: list[ScannedNote]) -> int:
        count = 0
        with self.driver.session() as session:
            for scanned in notes:
                note = scanned.note
                session.execute_write(self._merge_note, scanned)
                count += 1 + len(note.links) + len(note.tags)
        return count

    @staticmethod
    def _merge_note(tx, scanned: ScannedNote) -> None:
        note = scanned.note
        tx.run(
            """
            MERGE (c:Concept {name: $title})
            SET c.aliases = $aliases
            MERGE (n:Note {path: $path})
            SET n.title = $title
            MERGE (c)-[:MENTIONED_IN {source: $path}]->(n)
            """,
            title=note.title,
            aliases=note.aliases,
            path=scanned.rel_path,
        )

        if note.course:
            tx.run(
                """
                MATCH (c:Concept {name: $title})
                MERGE (course:Course {name: $course})
                MERGE (c)-[:BELONGS_TO {source: $path}]->(course)
                """,
                title=note.title,
                course=note.course,
                path=scanned.rel_path,
            )
        if note.chapter:
            tx.run(
                """
                MATCH (c:Concept {name: $title})
                MERGE (chapter:Chapter {name: $chapter})
                MERGE (c)-[:IN_CHAPTER {source: $path}]->(chapter)
                """,
                title=note.title,
                chapter=note.chapter,
                path=scanned.rel_path,
            )
        for tag in note.tags:
            tx.run(
                """
                MATCH (c:Concept {name: $title})
                MERGE (tag:Tag {name: $tag})
                MERGE (c)-[:TAGGED_AS {source: $path}]->(tag)
                """,
                title=note.title,
                tag=tag,
                path=scanned.rel_path,
            )
        for link in note.links:
            tx.run(
                """
                MATCH (c:Concept {name: $title})
                MERGE (target:Concept {name: $target})
                MERGE (c)-[r:RELATED_TO {source: $path}]->(target)
                SET r.alias = $alias
                """,
                title=note.title,
                target=link.target,
                alias=link.alias,
                path=scanned.rel_path,
            )

    def query(self, concept: str, intent: str = "related", limit: int = 20) -> dict:
        rel_filter = {
            "related": ["RELATED_TO"],
            "tags": ["TAGGED_AS"],
            "tagged": ["TAGGED_AS"],
            "mentions": ["MENTIONED_IN"],
            "sources": ["MENTIONED_IN"],
            "course": ["BELONGS_TO", "IN_CHAPTER"],
        }.get(intent, ["RELATED_TO", "TAGGED_AS", "MENTIONED_IN", "BELONGS_TO", "IN_CHAPTER"])

        with self.driver.session() as session:
            records = session.run(
                """
                MATCH (c:Concept {name: $concept})-[r]-(n)
                WHERE type(r) IN $rel_types
                RETURN c, r, n
                LIMIT $limit
                """,
                concept=concept,
                rel_types=rel_filter,
                limit=limit,
            )
            nodes = {}
            relationships = []
            for record in records:
                c = record["c"]
                n = record["n"]
                r = record["r"]
                nodes[str(c.id)] = {"id": str(c.id), "labels": list(c.labels), "properties": dict(c)}
                nodes[str(n.id)] = {"id": str(n.id), "labels": list(n.labels), "properties": dict(n)}
                relationships.append(
                    {
                        "start": str(r.start_node.id),
                        "type": r.type,
                        "end": str(r.end_node.id),
                        "properties": dict(r),
                    }
                )

        return {
            "concept": concept,
            "intent": intent,
            "nodes": list(nodes.values()),
            "relationships": relationships,
            "source": self.backend_name,
        }
