import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from .paths import knowledge_path

REPORT_FILENAME = "import_report.json"


@dataclass
class ImportReport:
    timestamp: str = ""
    mode: str = "incremental"
    scanned_files: int = 0
    updated_files: int = 0
    error_files: int = 0
    chunk_count: int = 0
    relationship_count: int = 0
    graph_backend: str = "local"
    errors: list = None  # list of {"source": str, "error": str}

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def save_import_report(workspace: str, report: ImportReport) -> None:
    """Write .knowledge/import_report.json."""
    path = knowledge_path(workspace, REPORT_FILENAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)


def load_import_report(workspace: str) -> ImportReport | None:
    """Load .knowledge/import_report.json or None if missing."""
    path = knowledge_path(workspace, REPORT_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ImportReport(**data)
    except (json.JSONDecodeError, OSError, TypeError):
        return None
