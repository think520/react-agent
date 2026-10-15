import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { DocumentEditor } from "./DocumentEditor";

/**
 * W1 E7：编辑器里的「插入划线汇总」—— 只重写托管区块，其他内容一个字不改。
 */

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      documentContent: vi.fn(),
      documentAnchors: vi.fn(),
      editDocument: vi.fn(),
      documentVersions: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.mocked(api.documentContent).mockResolvedValue({
    content: "# 我的笔记\n\n手写的内容。", content_hash: "h1",
  } as never);
  vi.mocked(api.documentAnchors).mockResolvedValue({
    anchors: [{ anchor_id: "a1", document_id: "doc-1", chunk_id: "c1", quote: "贪心策略",
                char_start: null, char_end: null, note: "", created_at: "",
                resolution: { status: "exact", char_start: 0, char_end: 4 } }],
    count: 1,
  } as never);
  vi.mocked(api.documentVersions).mockResolvedValue({ versions: [] } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("插入划线汇总时只写托管区块，不动手写内容", async () => {
  render(<DocumentEditor documentId="doc-1" title="我的笔记" onClose={() => {}} onSaved={() => {}} />);

  // 等正文真的加载出来再点（否则点的是空文档）。
  const textarea = await screen.findByRole("textbox") as HTMLTextAreaElement;
  await waitFor(() => expect(textarea.value).toContain("手写的内容。"));

  const sync = screen.getByRole("button", { name: /插入划线汇总/ });
  fireEvent.click(sync);

  await waitFor(() => expect(screen.getByText(/已写入 1 条划线的汇总/)).toBeTruthy());
  expect(textarea.value).toContain("手写的内容。");
  expect(textarea.value).toContain("bobodan:managed:highlights:doc-1 start");
  expect(textarea.value).toContain("贪心策略");
});

it("再点一次不重复插入（没有变化就不改正文）", async () => {
  render(<DocumentEditor documentId="doc-1" title="我的笔记" onClose={() => {}} onSaved={() => {}} />);

  const textarea = await screen.findByRole("textbox") as HTMLTextAreaElement;
  await waitFor(() => expect(textarea.value).toContain("手写的内容。"));

  fireEvent.click(screen.getByRole("button", { name: /插入划线汇总/ }));
  await waitFor(() => expect(screen.getByText(/已写入 1 条划线的汇总/)).toBeTruthy());
  const afterFirst = textarea.value;

  fireEvent.click(screen.getByRole("button", { name: /插入划线汇总/ }));

  await waitFor(() => expect(screen.getByText("划线汇总没有变化，正文未改动。")).toBeTruthy());
  expect(textarea.value).toBe(afterFirst);
});
