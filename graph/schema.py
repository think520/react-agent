NODE_LABELS = {
    "Course",
    "Chapter",
    "Concept",
    "Document",
    "Note",
    "Experiment",
    "Question",
    "Tag",
    "Memory",
}

RELATIONSHIP_TYPES = {
    "BELONGS_TO",
    "IN_CHAPTER",
    "MENTIONED_IN",
    "RELATED_TO",
    "PREREQUISITE_OF",
    "USES",
    "SIMILAR_TO",
    "TAGGED_AS",
    "DERIVED_FROM",
    "REMEMBERS",
}


def node_id(label: str, name: str) -> str:
    if label not in NODE_LABELS:
        raise ValueError(f"Unknown graph node label: {label}")
    clean = str(name).strip()
    if not clean:
        raise ValueError("Graph node name cannot be empty")
    return f"{label}:{clean.casefold()}"
