import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { ConceptNode, KnowledgeContextArtifact, KnowledgeContextRelationship } from "../../types";
import { KnowledgeContextCard } from "./KnowledgeContextCard";

afterEach(cleanup);

function makeConcept(concept_id: string, name: string, definition = ""): ConceptNode {
  return {
    concept_id,
    name,
    level: "core",
    definition,
    aliases: [],
    topic_ids: [],
    note: "",
    created_at: 0,
    updated_at: 0,
    x: 0,
    y: 0,
  };
}

function makeRel(
  rel_id: string,
  from_id: string,
  from_name: string,
  to_id: string,
  to_name: string,
  rel_type: string,
  evidence_status: "valid" | "stale" | "missing" = "stale",
): KnowledgeContextRelationship {
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
    evidence_status,
    valid_evidence_count: evidence_status === "valid" ? 1 : 0,
    stale_evidence_count: evidence_status === "stale" ? 1 : 0,
    evidence: [],
  };
}

function makeArtifact(): KnowledgeContextArtifact {
  return {
    type: "knowledge_context",
    artifact_id: "kc-1",
    context: {
      operation: "neighbors",
      root: makeConcept("c-llm", "大模型", "超大规模深度神经网络模型"),
      concepts: [
        makeConcept("c-param", "参数规模"),
        makeConcept("c-llm", "大模型"),
        makeConcept("c-data", "训练数据规模"),
        makeConcept("c-tr", "Transformer"),
      ],
      relationships: [
        makeRel("r1", "c-param", "参数规模", "c-llm", "大模型", "组成部分"),
        makeRel("r2", "c-data", "训练数据规模", "c-llm", "大模型", "组成部分"),
        makeRel("r3", "c-tr", "Transformer", "c-llm", "大模型", "前置知识"),
        makeRel("r4", "c-ssl", "自监督学习", "c-llm", "大模型", "应用于"),
      ],
    },
  };
}

describe("KnowledgeContextCard", () => {
  it("highlights root concept, consolidates stale badge once, and folds extra relations", () => {
    const onOpenConcept = vi.fn();
    const onOpenMap = vi.fn();
    const onShowContext = vi.fn();

    render(
      <KnowledgeContextCard
        artifact={makeArtifact()}
        onOpenConcept={onOpenConcept}
        onOpenMap={onOpenMap}
        onShowContext={onShowContext}
      />,
    );

    expect(screen.getAllByText("部分来源已更新")).toHaveLength(1);
    expect(screen.queryByText("来源已变化")).toBeNull();

    expect(screen.queryByText("自监督学习")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /展开其余 1 条关系/ }));
    expect(screen.getByText("自监督学习")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "知识地图" }));
    expect(onOpenMap).toHaveBeenCalledWith("c-llm");
  });
});
