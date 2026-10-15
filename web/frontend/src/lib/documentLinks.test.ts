import { describe, expect, it } from "vitest";

import { readerLocation } from "./documentLinks";

describe("document link landing", () => {
  it("lands in the reader with the cited chunk", () => {
    expect(readerLocation({ document_id: "doc-1", collection: "material", source_id: "chunk-9" })).toBe(
      "/library/read/doc-1?collection=material&chunk=chunk-9",
    );
  });

  it("still lands in the reader when there is no chunk", () => {
    expect(readerLocation({ document_id: "doc-1", collection: "material" })).toBe(
      "/library/read/doc-1?collection=material",
    );
  });

  it("keeps the wiki collection", () => {
    expect(readerLocation({ document_id: "doc-2", collection: "wiki", chunk_id: "c1" })).toBe(
      "/library/read/doc-2?collection=wiki&chunk=c1",
    );
  });

  it("returns nothing for a source without a document", () => {
    expect(readerLocation({ collection: "material", source_id: "https://example.com" })).toBe(null);
    expect(readerLocation(null)).toBe(null);
  });

  it("prefers an explicit chunk_id over source_id", () => {
    expect(readerLocation({ document_id: "d", chunk_id: "real", source_id: "other" })).toBe(
      "/library/read/d?collection=material&chunk=real",
    );
  });
});
