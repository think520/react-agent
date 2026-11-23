import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import type { ChatArtifact, ChatMessage, ConceptNode, KnowledgeContextRelationship } from "../../types";
import { AssistantMessage, normalizeMessageArtifacts } from "./ChatMessage";

afterEach(cleanup);

function concept(concept_id: string, name: string): ConceptNode {
  return {
    concept_id,
    name,
    level: "core",
    definition: "",
    aliases: [],
    topic_ids: [],
    note: "",
    created_at: 0,
    updated_at: 0,
    x: 0,
    y: 0,
  };
}

function relation(rel_id: string, from_id: string, from_name: string, to_id: string, to_name: string, rel_type: string): KnowledgeContextRelationship {
  return {
    rel_id,
    from_id,
    from_name,
    to_id,
    to_name,
    rel_type,
    evidence_level: "source",
    note: "",
    created_at: 0,
    updated_at: 0,
    evidence_status: "valid",
    valid_evidence_count: 1,
    stale_evidence_count: 0,
    evidence: [],
  };
}

describe("AssistantMessage citations", () => {
  it("renders citation-like code literally and links only the prose marker", () => {
    const message: ChatMessage = {
      role: "assistant",
      content: "正文 [Sa1b2c3]，行内代码 `[Sa1b2c3]`。\n\n```ts\nconst cite = \"[Sa1b2c3]\";\n```",
      attribution: {
        kind: "local",
        status: "found",
        sources: [{ source_type: "local", source_id: "c1", title: "示例讲义", document_id: "doc1", chunk_id: "chunk1", cite_label: "Sa1b2c3" }],
      },
    };
    const { container } = render(<MemoryRouter><AssistantMessage
      message={message}
      index={0}
      assistantName="Bobodan"
      status={null}
      brandState={"ready" as ProcessBrandState}
      sending={false}
      error=""
      onPreparePractice={vi.fn()}
      onRetry={vi.fn()}
      renderArtifact={() => null}
      onOpenSources={vi.fn()}
    /></MemoryRouter>);

    expect(container.querySelectorAll(".citation-mark")).toHaveLength(1);
    expect(container.querySelector("code")?.textContent).toBe("[Sa1b2c3]");
    expect(container.querySelector("pre code")?.textContent?.trimEnd()).toBe('const cite = "[Sa1b2c3]";');
  });

  it("merges duplicate knowledge_context artifacts and drops empty ones", () => {
    const artifacts: ChatArtifact[] = [
      {
        type: "knowledge_context",
        artifact_id: "kc-empty",
        context: { operation: "search", concepts: [], relationships: [] },
      },
      {
        type: "knowledge_context",
        artifact_id: "kc-first",
        context: {
          operation: "search",
          concepts: [concept("c1", "大模型")],
          relationships: [],
        },
      },
      {
        type: "knowledge_context",
        artifact_id: "kc-second",
        context: {
          operation: "neighbors",
          root: concept("c1", "大模型"),
          concepts: [concept("c1", "大模型"), concept("c2", "Transformer")],
          relationships: [relation("r1", "c2", "Transformer", "c1", "大模型", "前置知识")],
        },
      },
    ];
    const normalized = normalizeMessageArtifacts(artifacts);
    expect(normalized).toHaveLength(1);
    const merged = normalized[0];
    expect(merged.type).toBe("knowledge_context");
    if (merged.type === "knowledge_context") {
      expect(merged.context.root?.concept_id).toBe("c1");
      expect(merged.context.concepts.map((c) => c.concept_id)).toEqual(["c1", "c2"]);
      expect(merged.context.relationships).toHaveLength(1);
    }
  });

  it("renders collapsible citation support warning only when finished message carries warnings", () => {
    const warnedMessage: ChatMessage = {
      role: "assistant",
      content: "Dijkstra 支持负权边 [Sa10001]。",
      attribution: {
        kind: "local",
        status: "found",
        sources: [{ source_type: "local", source_id: "c1", title: "算法讲义", document_id: "d1", chunk_id: "c1", cite_label: "Sa10001" }],
        support_warnings: [{
          cite_label: "Sa10001",
          claim: "Dijkstra 支持负权边",
          reason_code: "polarity_contradiction",
          reason: "关于负权边 / 非负权约束的表述与引用原文相反，请核对原文条件。",
          evidence_excerpt: "Dijkstra 要求所有边权为非负",
          source_title: "algo/dijkstra.md",
        }],
      },
    };
    const { container, rerender } = render(<MemoryRouter><AssistantMessage
      message={warnedMessage}
      index={0}
      assistantName="Bobodan"
      status={null}
      brandState={"ready" as ProcessBrandState}
      sending={false}
      error=""
      onPreparePractice={vi.fn()}
      onRetry={vi.fn()}
      renderArtifact={() => null}
      onOpenSources={vi.fn()}
    /></MemoryRouter>);

    expect(container.querySelector(".citation-support-warning")?.textContent).toContain("请核对原文（1）");
    expect(container.querySelector(".citation-support-warning-excerpt")?.textContent).toContain("Dijkstra 要求所有边权为非负");

    rerender(<MemoryRouter><AssistantMessage
      message={{ ...warnedMessage, pending: true }}
      index={0}
      assistantName="Bobodan"
      status="正在整理"
      brandState={"reading" as ProcessBrandState}
      sending
      error=""
      onPreparePractice={vi.fn()}
      onRetry={vi.fn()}
      renderArtifact={() => null}
      onOpenSources={vi.fn()}
    /></MemoryRouter>);

    expect(container.querySelector(".citation-support-warning")).toBeNull();
  });
});
