import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryPage } from "./LibraryPage";
import { api } from "../lib/api";

/**
 * ①（E17）：资料库文件夹同步的入口与摘要。
 *
 * 修前状态：`api.ts` 里有 `syncLibrary()`，但**全前端零调用** —— 用户在
 * 资源管理器里把资料剪进资料库文件夹后，界面里没有任何办法发现它们。
 * 这条测试钉住：按钮真的会打 `/sync`，并把摘要（新增/更新/移除/跳过/
 * 失败）如实渲染出来。
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
      documents: vi.fn(),
      graphExtractionStatuses: vi.fn(),
      syncLibrary: vi.fn(),
    },
  };
});

function buildContext() {
  return {
    settings: null,
    refreshSettings: vi.fn(),
    refreshSessions: vi.fn(),
    documents: [],
    selectedDocumentIds: [],
    selectedDocuments: [],
    toggleDocumentScope: vi.fn(),
    setDocumentScope: vi.fn(),
    clearDocumentScope: vi.fn(),
    libraries: [{ library_id: "lib-1", name: "vault", available: true }],
    activeLibrary: { library_id: "lib-1", name: "vault", available: true },
    openLibrarySetup: vi.fn(),
    createLibrary: vi.fn(),
    switchLibrary: vi.fn(),
    startDocumentImport: vi.fn(),
    documentImporting: false,
    documentImportNotice: "",
    documentImportError: "",
    documentImportVersion: 0,
    libraryReady: true,
  };
}

beforeEach(() => {
  hoisted.ctx = buildContext();
  vi.mocked(api.documents).mockResolvedValue([]);
  vi.mocked(api.graphExtractionStatuses).mockResolvedValue({ documents: {} } as never);
});

afterEach(() => {
  // 这个仓库的 vitest setup 没有注册自动 cleanup：两个用例若共享 DOM，
  // 第二个用例会因为"找到多个 alert/status"而在 waitFor 里超时。
  cleanup();
  vi.clearAllMocks();
});

describe("资料库文件夹同步", () => {
  it("按钮会同步并渲染可行动的摘要", async () => {
    vi.mocked(api.syncLibrary).mockResolvedValue({
      ok: true,
      scanned_files: 47,
      updated_files: 3,
      changed_files: 2,
      error_files: 1,
      errors: [{ source: "course-2/broken.pdf", error: "解析失败" }],
      extraction_counts: { complete: 1, partial: 0, empty: 1, error: 0 },
      added_files: ["course-2/new.md"],
      removed_files: ["course/course-pack/dup.docx"],
      duplicates_cleaned: ["course/course-pack/dup.docx"],
      pending_removal: ["course-2/moved.md"],
      skipped_files: ["course-2/README.md", "course-2/requirements.txt"],
    });

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /同步文件夹/ }));

    expect(api.syncLibrary).toHaveBeenCalledWith("lib-1");
    const summary = await screen.findByRole("status");
    expect(summary.textContent).toContain("新增 1");
    expect(summary.textContent).toContain("更新 2");
    expect(summary.textContent).toContain("移除 1");
    expect(summary.textContent).toContain("待确认移除 1");
    expect(summary.textContent).toContain("跳过 2");
    expect(summary.textContent).toContain("失败 1");
    // 摘要出现后必须重新拉一次列表，否则用户看不到新增的资料
    await waitFor(() => expect(api.documents).toHaveBeenCalledTimes(2));
  });

  it("失败时给出可读错误，不显示摘要", async () => {
    vi.mocked(api.syncLibrary).mockRejectedValue(new Error("资料库文件夹不可用"));

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /同步文件夹/ }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeNull());
    expect(screen.getByRole("alert").textContent).toContain("资料库文件夹不可用");
    expect(screen.queryByRole("status")).toBeNull();
  });
});