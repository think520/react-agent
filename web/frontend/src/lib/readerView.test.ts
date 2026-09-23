import { describe, expect, it } from "vitest";

import { documentExtension, inlineOriginalKind, resolveReaderView } from "./readerView";

describe("reader view rules", () => {
  it("defaults to the original file for a markdown document", () => {
    const decision = resolveReaderView({
      hasOriginal: true,
      source: "course/笔记.md",
      preference: "original",
      forcedSections: false,
    });

    expect(decision.view).toBe("original");
    expect(decision.inlineKind).toBe("markdown");
    expect(decision.showSwitch).toBe(true);
  });

  it("hands PDFs to the in-page viewer", () => {
    const decision = resolveReaderView({
      hasOriginal: true,
      source: "course/paper.pdf",
      preference: "original",
      forcedSections: false,
    });

    expect(decision.view).toBe("original");
    expect(decision.inlineKind).toBe("pdf");
    expect(decision.showSwitch).toBe(true);
  });

  it("keeps the section view for formats the browser cannot lay out", () => {
    const decision = resolveReaderView({
      hasOriginal: true,
      source: "course/报告.docx",
      preference: "original",
      forcedSections: false,
    });

    expect(decision.view).toBe("sections");
    expect(decision.showSwitch).toBe(false);
    expect(decision.offerSystemOpen).toBe(true);
  });

  it("hides the switch when there is no original at all", () => {
    const decision = resolveReaderView({
      hasOriginal: false,
      source: "course/只剩索引.md",
      preference: "original",
      forcedSections: false,
    });

    expect(decision.view).toBe("sections");
    expect(decision.showSwitch).toBe(false);
    expect(decision.offerSystemOpen).toBe(false);
  });

  it("forces the section view for a jump, without touching the preference", () => {
    const preference = "original" as const;
    const jumped = resolveReaderView({
      hasOriginal: true,
      source: "course/笔记.md",
      preference,
      forcedSections: true,
    });
    const normal = resolveReaderView({
      hasOriginal: true,
      source: "course/笔记.md",
      preference,
      forcedSections: false,
    });

    expect(jumped.view).toBe("sections");
    expect(normal.view).toBe("original");
  });

  it("honours a remembered section preference", () => {
    const decision = resolveReaderView({
      hasOriginal: true,
      source: "course/笔记.md",
      preference: "sections",
      forcedSections: false,
    });

    expect(decision.view).toBe("sections");
    expect(decision.showSwitch).toBe(true);
  });

  it("reads extensions defensively", () => {
    expect(documentExtension("course/笔记.MD")).toBe("md");
    expect(documentExtension(undefined)).toBe("");
    expect(inlineOriginalKind("course/没有扩展名")).toBe(null);
  });
});
