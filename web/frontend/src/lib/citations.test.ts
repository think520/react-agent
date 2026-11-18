import { describe, expect, it } from "vitest";

import type { SourceRef } from "../types";
import { transformCitationNodes, type CitationTarget } from "./citations";

const sources: SourceRef[] = [
  { source_type: "local", source_id: "c1", title: "最短路径", document_id: "d1", chunk_id: "c1", cite_label: "Sa1b2c3" },
  { source_type: "web", source_id: "w1", title: "Guide", url: "https://example.com", cite_label: "Sffee01" },
];

describe("citation markers", () => {
  it("links only known citations in Markdown text nodes, preserving inline and fenced code", () => {
    const targets = new Map<string, CitationTarget>();
    const tree = {
      type: "root",
      children: [
        { type: "paragraph", children: [
          { type: "text", value: "先看网页 [Sffee01]，再看资料 " },
          { type: "inlineCode", value: "[Sa1b2c3]" },
          { type: "text", value: "，旧标签 [S000000]，回到网页 [Sffee01]。" },
        ] },
        { type: "code", lang: "text", value: "[Sa1b2c3]" },
        { type: "paragraph", children: [{ type: "link", url: "https://example.com", children: [{ type: "text", value: "[Sa1b2c3]" }] }] },
      ],
    };

    transformCitationNodes(tree as never, { sources, targets });

    expect([...targets.values()].map((target) => [target.label, target.index])).toEqual([["Sffee01", 1]]);
    const root = tree as unknown as { children: Array<{ type: string; value?: string; children?: Array<{ type: string; value?: string; url?: string; children?: Array<{ value?: string }> }> }> };
    expect(root.children[0].children).toEqual([
      { type: "text", value: "先看网页 " },
      { type: "link", url: "cite:Sffee01", children: [{ type: "text", value: "1" }] },
      { type: "text", value: "，再看资料 " },
      { type: "inlineCode", value: "[Sa1b2c3]" },
      { type: "text", value: "，旧标签 [S000000]，回到网页 " },
      { type: "link", url: "cite:Sffee01", children: [{ type: "text", value: "1" }] },
      { type: "text", value: "。" },
    ]);
    expect(root.children[1].value).toBe("[Sa1b2c3]");
    expect(root.children[2].children?.[0].children?.[0].value).toBe("[Sa1b2c3]");
  });
});
