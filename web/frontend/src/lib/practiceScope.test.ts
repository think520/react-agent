import { describe, expect, it } from "vitest";

import type { DocumentSummary } from "../types";
import { derivePracticeScopeGroups, resolveEffectivePracticeScope } from "./practiceScope";

function doc(overrides: Partial<DocumentSummary> & { document_id: string; source: string }): DocumentSummary {
  return {
    kind: "md",
    title: overrides.title || overrides.source,
    collection: "material",
    content_role: "content",
    ...overrides,
  };
}

describe("practiceScope", () => {
  it("groups materials by course metadata first, then folder path, ignoring wiki pages", () => {
    const groups = derivePracticeScopeGroups([
      doc({ document_id: "d1", source: "algo/dijkstra.md", course: "数据结构与算法" }),
      doc({ document_id: "d2", source: "algo/dp.md", course: "数据结构与算法" }),
      doc({ document_id: "d3", source: "course/操作系统/调度.md" }),
      doc({ document_id: "d4", source: "raw/inbox/机器学习/transformer.md", relative_path: "机器学习/transformer.md" }),
      doc({ document_id: "d5", source: "standalone.md" }),
      doc({ document_id: "w1", source: "wiki/concept.md", collection: "wiki", course: "数据结构与算法" }),
    ]);

    expect(groups.map((item) => ({ label: item.label, count: item.count, course: item.course }))).toEqual([
      { label: "操作系统", count: 1, course: undefined },
      { label: "机器学习", count: 1, course: undefined },
      { label: "数据结构与算法", count: 2, course: "数据结构与算法" },
    ]);
  });

  it("intersects desk selection when inside the picked group, else uses full group IDs", () => {
    const groups = derivePracticeScopeGroups([
      doc({ document_id: "d1", source: "a.md", course: "算法" }),
      doc({ document_id: "d2", source: "b.md", course: "算法" }),
      doc({ document_id: "d3", source: "os/c.md" }),
    ]);
    const algo = groups.find((item) => item.label === "算法")!;

    expect(resolveEffectivePracticeScope(algo, [])).toEqual({
      course: "算法",
      documentIds: ["d1", "d2"],
    });
    expect(resolveEffectivePracticeScope(algo, ["d2", "d3"])).toEqual({
      course: "算法",
      documentIds: ["d2"],
    });
    expect(resolveEffectivePracticeScope(null, ["d3"])).toEqual({
      documentIds: ["d3"],
    });
  });
});
