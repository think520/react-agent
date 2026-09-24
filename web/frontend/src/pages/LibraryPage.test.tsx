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
      knowledgeTree: vi.fn(),
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
      scan_incomplete: false,
      incomplete_reasons: [],
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

  it("扫描不完整时明确说明并且不谎报移除", async () => {
    vi.mocked(api.syncLibrary).mockResolvedValue({
      ok: true,
      scanned_files: 47,
      updated_files: 0,
      changed_files: 0,
      error_files: 0,
      errors: [],
      extraction_counts: {},
      added_files: [],
      removed_files: [],
      duplicates_cleaned: [],
      pending_removal: [],
      skipped_files: [],
      scan_incomplete: true,
      incomplete_reasons: ["来源根不可用：D:\\课程包"],
    });

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /同步文件夹/ }));

    const summary = await screen.findByRole("status");
    expect(summary.textContent).toContain("本次扫描看不全");
    expect(summary.textContent).toContain("来源根不可用");
  });

  it("选中文件夹后，右侧列表只显示这个文件夹里的资料", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue({
      ok: true,
      tree: {
        type: "folder",
        name: "vault",
        path: "",
        material_count: 2,
        indexed_count: 2,
        ignored_count: 0,
        ignored_here: [],
        files: [],
        children: [
          {
            type: "folder",
            name: "课程包",
            path: "课程包",
            material_count: 1,
            indexed_count: 1,
            ignored_count: 0,
            ignored_here: [],
            children: [],
            files: [
              {
                type: "file",
                name: "第一课.md",
                path: "课程包/第一课.md",
                size: 10,
                modified_at: "2026-09-24T00:00:00+00:00",
                indexed: true,
                document_id: "doc-in",
                title: "第一课",
                extraction_status: "complete",
                chunk_count: 2,
              },
            ],
          },
        ],
      },
    });
    vi.mocked(api.documents).mockResolvedValue([
      {
        document_id: "doc-in",
        source: "course-2/第一课.md",
        relative_path: "课程包/第一课.md",
        kind: "course_document",
        title: "文件夹里的资料",
        collection: "material",
        content_role: "content",
      },
      {
        document_id: "doc-out",
        source: "course-2/第二课.md",
        relative_path: "另一门课/第二课.md",
        kind: "course_document",
        title: "文件夹外的资料",
        collection: "material",
        content_role: "content",
      },
    ] as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("文件夹里的资料")).toBeTruthy();
    expect(screen.getByText("文件夹外的资料")).toBeTruthy();

    fireEvent.click(await screen.findByRole("button", { name: "课程包" }));

    expect(screen.getByText("文件夹里的资料")).toBeTruthy();
    expect(screen.queryByText("文件夹外的资料")).toBeNull();
  });
});