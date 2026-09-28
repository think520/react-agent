import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { NotesPage } from "./NotesPage";

/**
 * 笔记草稿。
 *
 * 2026-09-28 审查（`docs/reviews/2026-09-28-remediation-code-review.md` F01）确认四条边界
 * 曾经全是坏的：同一篇笔记重开会被服务端旧正文盖掉、A 的草稿被 B 顶掉（共用一个 key）、
 * 输入后 250ms 内 pagehide 不落盘、清空正文后离开旧正文又回来。
 * 下面 `describe("R02 草稿隔离与恢复")` 就是那四条探针（从
 * `docs/reviews/evidence/2026-09-28/drafts-probe-source.tsx.txt` 转正，按"资料库 + 笔记"的新 key 形状改写）。
 */

const hoisted = vi.hoisted(() => ({ ctx: {} as Record<string, unknown> }));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useOutletContext: () => hoisted.ctx };
});

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      memoryKnowledge: vi.fn(),
      createMemoryKnowledge: vi.fn(),
      updateMemoryKnowledge: vi.fn(),
      deleteMemoryKnowledge: vi.fn(),
    },
  };
});

/** 草稿按"资料库 + 笔记"存；新笔记用 new 这个槽位。 */
const keyFor = (draftId: string) => `bobodan:note-draft:lib-1:${draftId}`;
const originalA = ["# Note A", "", "Saved A"].join("\n");
const editedA = ["# Note A", "", "Unsaved A must survive"].join("\n");
const originalB = ["# Note B", "", "Saved B"].join("\n");

function renderPage() {
  return render(<MemoryRouter><NotesPage /></MemoryRouter>);
}

function seedTwoNotes() {
  vi.mocked(api.memoryKnowledge).mockResolvedValue({ items: [
    { id: "a", title: "Note A", content: "Saved A", revision: 1, scope: "library", pinned: false, references: [], updated_at: "2026-09-28" },
    { id: "b", title: "Note B", content: "Saved B", revision: 1, scope: "library", pinned: false, references: [], updated_at: "2026-09-28" },
  ] } as never);
}

beforeEach(() => {
  localStorage.clear();
  hoisted.ctx = {
    documents: [],
    activeLibrary: { library_id: "lib-1", name: "测试资料库", available: true },
    settings: { preferences: { memory: { enabled: true } } },
  };
  vi.mocked(api.memoryKnowledge).mockResolvedValue({ items: [] });
  vi.mocked(api.createMemoryKnowledge).mockResolvedValue({ item: {} } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("NotesPage drafts", () => {
  it("restores an unsaved draft after leaving the page", async () => {
    const first = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), {
      target: { value: "# 向量检索\n\n这是还没有保存的理解。" },
    });
    first.unmount();

    renderPage();

    await waitFor(() => expect(screen.getByRole("textbox", { name: "笔记正文" }))
      .toHaveValue("# 向量检索\n\n这是还没有保存的理解。"));
  });

  it("clears the local draft after a successful save", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), {
      target: { value: "# 标题\n\n正文" },
    });
    // 先确认草稿**真的落过盘**，否则"保存后为空"这条断言会假通过。
    await waitFor(() => expect(localStorage.getItem(keyFor("new"))).toContain("正文"));
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));

    await waitFor(() => expect(api.createMemoryKnowledge).toHaveBeenCalled());
    await waitFor(() => expect(localStorage.getItem(keyFor("new"))).toBeNull());
  });

  it("shows the 5000 character limit before the backend can reject the note", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), {
      target: { value: "# 标题\n\n" + "字".repeat(5001) },
    });

    expect(screen.getByText(/5001\/5000/)).toHaveClass("over-limit");
    expect(screen.getByRole("button", { name: "保存笔记" })).toBeDisabled();
    expect(api.createMemoryKnowledge).not.toHaveBeenCalled();
  });
});

describe("R02 草稿隔离与恢复（F01）", () => {
  it("重开同一篇笔记，恢复的是没保存的那次修改", async () => {
    seedTwoNotes();
    renderPage();
    const edit = (await screen.findAllByRole("button", { name: "编辑" }))[0];
    fireEvent.click(edit);
    expect(screen.getByRole("textbox", { name: "笔记正文" })).toHaveValue(originalA);

    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), { target: { value: editedA } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "笔记正文" }), { key: "Escape" });
    expect(JSON.parse(localStorage.getItem(keyFor("a"))!).markdown).toBe(editedA);

    fireEvent.click(edit);
    expect(screen.getByRole("textbox", { name: "笔记正文" })).toHaveValue(editedA);
  });

  it("编辑另一篇笔记不会顶掉上一篇的草稿", async () => {
    seedTwoNotes();
    const page = renderPage();
    const edit = await screen.findAllByRole("button", { name: "编辑" });
    fireEvent.click(edit[0]);
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), { target: { value: editedA } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "笔记正文" }), { key: "Escape" });

    fireEvent.click(edit[1]);
    expect(screen.getByRole("textbox", { name: "笔记正文" })).toHaveValue(originalB);
    fireEvent.keyDown(screen.getByRole("textbox", { name: "笔记正文" }), { key: "Escape" });

    page.unmount();
    renderPage();
    await screen.findAllByRole("button", { name: "编辑" });
    fireEvent.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    expect(screen.getByRole("textbox", { name: "笔记正文" })).toHaveValue(editedA);
  });

  it("防抖窗口内触发 pagehide 也要落盘", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), { target: { value: editedA } });
    fireEvent(window, new Event("pagehide"));
    expect(localStorage.getItem(keyFor("new"))).not.toBeNull();
  });

  it("清空正文之后不该把旧正文找回来", async () => {
    const page = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), { target: { value: editedA } });
    await waitFor(() => expect(localStorage.getItem(keyFor("new"))).toContain("Unsaved A must survive"));

    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), { target: { value: "" } });
    page.unmount();
    renderPage();
    expect(localStorage.getItem(keyFor("new"))).toBeNull();
    expect(screen.queryByRole("textbox", { name: "笔记正文" })).toBeNull();
  });
});
