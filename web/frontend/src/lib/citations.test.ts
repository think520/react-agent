import { describe, expect, it } from "vitest";

import type { SourceRef } from "../types";
import { citationTargets, linkCitations } from "./citations";

const sources: SourceRef[] = [
  { source_type: "local", source_id: "c1", title: "最短路径", document_id: "d1", chunk_id: "c1", cite_label: "Sa1b2c3" },
  { source_type: "web", source_id: "w1", title: "Guide", url: "https://example.com", cite_label: "Sffee01" },
];

describe("citation markers", () => {
  it("numbers known labels by first appearance and links them", () => {
    const text = "先看网页 [Sffee01]，再看资料 [Sa1b2c3]，回到网页 [Sffee01]。";
    const targets = citationTargets(text, sources);

    expect([...targets.values()].map((target) => [target.label, target.index])).toEqual([["Sffee01", 1], ["Sa1b2c3", 2]]);
    expect(linkCitations(text, targets)).toBe("先看网页 [1](cite:Sffee01)，再看资料 [2](cite:Sa1b2c3)，回到网页 [1](cite:Sffee01)。");
  });

  it("leaves unknown labels and ordinary brackets untouched", () => {
    const text = "旧标签 [S000000]，数组 a[1]，链接 [x](https://e.com)。";
    const targets = citationTargets(text, sources);

    expect(targets.size).toBe(0);
    expect(linkCitations(text, targets)).toBe(text);
  });

  it("does not resolve labels when the message has no attribution", () => {
    expect(citationTargets("x [Sa1b2c3]", undefined).size).toBe(0);
  });
});

describe("citation shape (2026-11-11 pre-merge review)", () => {
  it("does not treat link text or math notation as a citation", () => {
    const linked: SourceRef[] = [{ source_type: "local", source_id: "c1", title: "t", cite_label: "Sa1b2c3" }];
    expect(citationTargets("见 [Sa1b2c3](https://example.com)", linked).size).toBe(0);
    expect(citationTargets("矩阵 [S3] 与 [Step1]", linked).size).toBe(0);
  });
});
