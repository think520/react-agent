import { describe, expect, it } from "vitest";

import type { SourceRef } from "../types";
import { citationTargets, linkCitations } from "./citations";

const sources: SourceRef[] = [
  { source_type: "local", source_id: "c1", title: "最短路径", document_id: "d1", chunk_id: "c1", cite_label: "Sa1b2c3" },
  { source_type: "web", source_id: "w1", title: "Guide", url: "https://example.com", cite_label: "Sffee00" },
];

describe("citation markers", () => {
  it("numbers known labels by first appearance and links them", () => {
    const text = "先看网页 [Sffee00]，再看资料 [Sa1b2c3]，回到网页 [Sffee00]。";
    const targets = citationTargets(text, sources);

    expect([...targets.values()].map((target) => [target.label, target.index])).toEqual([["Sffee00", 1], ["Sa1b2c3", 2]]);
    expect(linkCitations(text, targets)).toBe("先看网页 [1](cite:Sffee00)，再看资料 [2](cite:Sa1b2c3)，回到网页 [1](cite:Sffee00)。");
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
