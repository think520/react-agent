"""Prevent new test files from introducing additional LLM provider seams."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = REPO_ROOT / "tests"

# Existing doubles are intentionally grandfathered. Migrate them when touching
# the file; new provider doubles belong in tests/llm_fake.py.
LEGACY_FILES = {
    "test_agent_loop.py",
    "test_agent_loop_ag2.py",
    "test_agent_service.py",
    "test_agents_runner.py",
    "test_call_role.py",
    "test_agent_cancellation.py",
    "test_concept_service.py",
    "test_context_projection.py",
    "test_document_proposal_service.py",
    "test_kb_service.py",
    "test_mcp_agent_loop.py",
    "test_prompt_blocks.py",
    "test_question_pipeline.py",
    "test_runtime_facade.py",
    "test_tool_timeouts.py",
    "test_embedding_signature.py",
    "test_index_stall_wiring.py",
    "test_organization_ai.py",
    "test_providers.py",
    "test_repl.py",
    "test_research_service.py",
    "test_retrieval_status.py",
    "test_review_fixes.py",
    "test_skills.py",
    "test_stream_guard.py",
    "test_web_backend.py",
    "test_wiki_orchestration.py",
    "test_wiki_workflow.py",
}


def _is_provider_double(name: str) -> bool:
    return name.endswith("Provider") or "LLM" in name


def find_violations() -> list[str]:
    violations: list[str] = []
    for path in TEST_ROOT.glob("test_*.py"):
        if path.name in LEGACY_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _is_provider_double(node.name):
                relative = path.relative_to(REPO_ROOT).as_posix()
                violations.append(
                    f"{relative}:{node.lineno}: local provider double {node.name}; "
                    "use the scripted_provider fixture from tests/llm_fake.py"
                )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("New test provider doubles are not allowed:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("Test double boundary passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
