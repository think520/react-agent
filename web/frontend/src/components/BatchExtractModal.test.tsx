import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { BatchExtractModal } from "./BatchExtractModal";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      documents: vi.fn(),
      graphExtractionStatuses: vi.fn(),
      graphStartBatchExtraction: vi.fn(),
    },
  };
});

const DOCS = [
  {
    document_id: "doc-1",
    source: "ml/attention.md",
    title: "注意力机制",
    course: "ML",
    kind: "markdown",
    chunk_count: 5,
    updated_at: "2026-11-01",
    content_hash: "h1",
  },
  {
    document_id: "doc-2",
    source: "ml/transformer.md",
    title: "Transformer",
    course: "ML",
    kind: "markdown",
    chunk_count: 4,
    updated_at: "2026-11-01",
    content_hash: "h2",
  },
  {
    document_id: "doc-empty",
    source: "ml/empty.pdf",
    title: "空扫描件",
    course: "ML",
    kind: "pdf",
    chunk_count: 0,
    updated_at: "2026-11-01",
    content_hash: "h3",
  },
];

beforeEach(() => {
  vi.mocked(api.documents).mockResolvedValue(DOCS as never);
  vi.mocked(api.graphExtractionStatuses).mockResolvedValue({
    documents: {
      "doc-1": { status: "completed", pending_count: 0, run: { run_id: "r1" } as never },
    },
  });
  vi.mocked(api.graphStartBatchExtraction).mockResolvedValue({
    runs: [],
    items: [{ document_id: "doc-2", status: "queued" }],
    started_count: 1,
    skipped_count: 0,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("BatchExtractModal", () => {
  it("lists searchable materials, pre-selects unextracted docs, and submits batch extraction", async () => {
    const onClose = vi.fn();
    const onStarted = vi.fn();
    render(<BatchExtractModal onClose={onClose} onStarted={onStarted} />);

    expect(await screen.findByText("注意力机制")).toBeTruthy();
    expect(screen.getByText("Transformer")).toBeTruthy();
    expect(screen.queryByText("空扫描件")).toBeNull();
    expect(screen.getByText("已提取")).toBeTruthy();
    expect(screen.getByText("未提取")).toBeTruthy();

    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes[0].checked).toBe(false);
    expect(checkboxes[1].checked).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /开始提取（1）/ }));

    await waitFor(() => {
      expect(api.graphStartBatchExtraction).toHaveBeenCalledWith({ document_ids: ["doc-2"] });
    });
    expect(onStarted).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("pre-selects matching initialFilenames and shows errors when batch fails", async () => {
    vi.mocked(api.graphStartBatchExtraction).mockRejectedValue(new Error("模型服务不可用"));
    const onClose = vi.fn();
    render(<BatchExtractModal initialFilenames={["attention.md"]} onClose={onClose} />);

    expect(await screen.findByText("注意力机制")).toBeTruthy();
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes[0].checked).toBe(true);
    expect(checkboxes[1].checked).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /开始提取（1）/ }));
    expect(await screen.findByText("模型服务不可用")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });
});
