"""Check the small set of dependency directions that define the runtime layers."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Boundary:
    source_prefix: str
    forbidden_prefixes: tuple[str, ...]
    message: str


BOUNDARIES = (
    Boundary(
        "web/backend/routers",
        ("sqlite3", "core" + ".db", "rag.sqlite_store", "knowledge.paths"),
        "Routers must call a service instead of reaching into storage directly.",
    ),
    Boundary(
        "providers",
        ("tools",),
        "Providers must not depend on the tool layer.",
    ),
    Boundary(
        "rag",
        ("quiz", "learning"),
        "RAG must not depend on learning or quiz orchestration.",
    ),
    Boundary(
        "knowledge",
        ("cli", "web"),
        "Knowledge code must not depend on presentation layers.",
    ),
    Boundary(
        "memory",
        ("cli", "web"),
        "Memory code must not depend on presentation layers.",
    ),
    Boundary(
        "quiz",
        ("cli", "web"),
        "Quiz code must not depend on presentation layers.",
    ),
    Boundary(
        "learning",
        ("cli", "web"),
        "Learning code must not depend on presentation layers.",
    ),
    Boundary(
        "graph",
        ("cli", "web"),
        "Graph code must not depend on presentation layers.",
    ),
    Boundary(
        "wiki",
        ("cli", "web"),
        "Wiki code must not depend on presentation layers.",
    ),
)


def _module_names(tree: ast.AST) -> list[tuple[str, int]]:
    modules: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append((node.module, node.lineno))
    return modules


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def find_violations(path: Path, source: str) -> list[str]:
    relative = path.resolve().relative_to(REPO_ROOT).as_posix()
    tree = ast.parse(source, filename=relative)
    violations: list[str] = []

    for boundary in BOUNDARIES:
        if not relative.startswith(f"{boundary.source_prefix}/"):
            continue
        for module, lineno in _module_names(tree):
            target = next(
                (prefix for prefix in boundary.forbidden_prefixes if _matches_prefix(module, prefix)),
                None,
            )
            if target is None:
                continue
            violations.append(
                f"{relative}:{lineno}: imports {module}; {boundary.message}"
            )
    return violations


def _python_files() -> list[Path]:
    roots = (
        "agents",
        "cli",
        "core",
        "graph",
        "knowledge",
        "learning",
        "memory",
        "providers",
        "quiz",
        "rag",
        "service",
        "tools",
        "web",
        "wiki",
    )
    return [path for root in roots for path in (REPO_ROOT / root).rglob("*.py")]


def main() -> int:
    violations: list[str] = []
    for path in _python_files():
        violations.extend(find_violations(path, path.read_text(encoding="utf-8")))

    if violations:
        print("Architecture boundary violations:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1

    print("Architecture boundaries passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
