import json
import re

import pytest

from providers.types import LLMResponse
from wiki.orchestration import WikiOrchestrator, wiki_coverage


class OrchestrationProvider:
    def complete(self, messages, tools=None):
        prompt = messages[0]["content"]
        source_id = (re.search(r"\[(S\d+)\]", prompt) or [None, "S1"])[1]
        if "Do not write page bodies" in prompt:
            return LLMResponse(content=json.dumps({"pages": [{
                "title": "共享概念",
                "page_type": "wiki_concept",
                "summary": "跨资料复用的概念。",
                "tags": ["概念"],
                "related": [],
                "source_ids": [source_id],
            }]}))
        title = re.search(r"^Title: (.+)$", prompt, flags=re.MULTILINE).group(1)
        page_type = re.search(r"^Page type: (.+)$", prompt, flags=re.MULTILINE).group(1)
        return LLMResponse(content=json.dumps({"pages": [{
            "title": title,
            "page_type": page_type,
            "summary": f"{title} 的摘要。",
            "body": "## 定义\n\n这是一个有原文依据的小型页面。",
            "tags": [],
            "related": [],
            "claims": [{"text": "内容来自原始资料。", "source_ids": [source_id]}],
        }]}))


class RecordingProvider(OrchestrationProvider):
    def __init__(self):
        self.discovery_prompts = []

    def complete(self, messages, tools=None):
        if "Do not write page bodies" in messages[0]["content"]:
            self.discovery_prompts.append(messages[0]["content"])
        return super().complete(messages, tools=tools)


def material(index: int, text: str | None = None):
    return {
        "document_id": f"doc-{index}",
        "title": f"资料 {index}",
        "source": f"raw/inbox/{index}.md",
        "course": "课程",
        "sections": [{
            "chunk_id": f"chunk-{index}",
            "heading": f"章节 {index}",
            "text": text or f"资料 {index} 解释共享概念。",
        }],
    }


def test_orchestrated_plan_batches_sources_and_guarantees_source_pages(tmp_path):
    documents = [material(index) for index in range(6)]
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), OrchestrationProvider())

    plan = orchestrator.create_plan(documents, scope_mode="uncovered")

    source_changes = [item for item in plan["changes"] if item["page_type"] == "wiki_source"]
    concept_changes = [item for item in plan["changes"] if item["page_type"] == "wiki_concept"]
    assert len(plan["batches"]) == 2
    assert [len(item["document_ids"]) for item in plan["batches"]] == [5, 1]
    assert len(source_changes) == 6
    assert len({item["source_refs"][0]["document_id"] for item in source_changes}) == 6
    assert len(concept_changes) == 1
    assert concept_changes[0]["source_count"] == 2


def test_large_library_discovery_reads_every_batch_instead_of_only_the_first_document(tmp_path):
    documents = [material(index) for index in range(1, 43)]
    provider = RecordingProvider()
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), provider)

    plan = orchestrator.create_plan(documents, scope_mode="uncovered")

    discovered_text = "\n".join(provider.discovery_prompts)
    assert len(plan["batches"]) == 9
    assert len([item for item in plan["changes"] if item["page_type"] == "wiki_source"]) == 42
    assert all(f"资料 {index} 解释共享概念" in discovered_text for index in range(1, 43))


def test_duplicate_source_titles_receive_distinct_traceable_pages(tmp_path):
    documents = [material(index) for index in range(1, 7)]
    documents[-1]["title"] = documents[0]["title"]
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), OrchestrationProvider())

    plan = orchestrator.create_plan(documents, scope_mode="selected_only")

    source_changes = [item for item in plan["changes"] if item["page_type"] == "wiki_source"]
    assert len({item["title"] for item in source_changes}) == 6
    assert len({item["target"] for item in source_changes}) == 6


def test_coverage_is_rebuilt_from_source_pages_and_detects_stale_material(tmp_path):
    document = material(1)
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), OrchestrationProvider())
    plan = orchestrator.create_plan([document], scope_mode="uncovered")

    orchestrator.workflow.apply_plan(plan["plan_id"])

    covered = wiki_coverage(str(tmp_path), [document])[0]
    changed = wiki_coverage(str(tmp_path), [material(1, "资料内容已经发生变化。")])[0]
    assert covered["status"] == "covered"
    assert covered["linked_page_count"] >= 1
    assert changed["status"] == "stale"


def test_coverage_ignores_section_edge_whitespace(tmp_path):
    document = material(1, "  资料内容前后有空白。\n")
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), OrchestrationProvider())
    plan = orchestrator.create_plan([document], scope_mode="uncovered")

    orchestrator.workflow.apply_plan(plan["plan_id"])

    assert wiki_coverage(str(tmp_path), [document])[0]["status"] == "covered"


def test_coverage_resolves_legacy_document_ids_by_unique_source_title(tmp_path):
    concepts = tmp_path / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "共享概念.md").write_text(
        "---\ntype: wiki_concept\ntitle: 共享概念\nsource_refs:\n"
        "  - {document_id: legacy-old-id, source: obsidian/course/lesson.md, title: 资料 1}\n"
        "---\n\n# 共享概念\n",
        encoding="utf-8",
    )

    coverage = wiki_coverage(str(tmp_path), [material(1)])[0]

    assert coverage["status"] == "partial"
    assert coverage["linked_page_count"] == 1


def test_large_existing_page_becomes_split_candidate_instead_of_short_update(tmp_path):
    concepts = tmp_path / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "共享概念.md").write_text(
        "---\ntype: wiki_concept\ntitle: 共享概念\ngenerated_by: bobodan\n---\n\n# 共享概念\n\n"
        + ("已有的重要内容。" * 800),
        encoding="utf-8",
    )
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), OrchestrationProvider())

    plan = orchestrator.create_plan([material(1)], scope_mode="smart_library")

    change = next(item for item in plan["changes"] if item["title"] == "共享概念")
    assert change["kind"] == "split"
    assert plan["summary"]["split"] == 1


def test_cancelled_orchestration_task_is_not_retryable(tmp_path):
    orchestrator = WikiOrchestrator(str(tmp_path), str(tmp_path), OrchestrationProvider())

    with pytest.raises(RuntimeError, match="Wiki run cancelled"):
        orchestrator.create_plan(
            [material(1)],
            scope_mode="uncovered",
            cancel_check=lambda: True,
        )

    task = orchestrator.workflow.tasks.list()[0]
    assert task["status"] == "cancelled"
    assert task["retryable"] is False
