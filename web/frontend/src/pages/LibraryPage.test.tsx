import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryPage } from "./LibraryPage";
import { api } from "../lib/api";
import { useReaderTabsStore } from "../stores/readerTabsStore";

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
      organizationProposals: vi.fn(),
      aiOrganizationProposals: vi.fn(),
      organizationState: vi.fn(),
      applyOrganization: vi.fn(),
      undoOrganization: vi.fn(),
      document: vi.fn(),
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
  // 标签条是模块级 zustand store（跨用例存活）：不清掉的话，上一个用例打开的标签
  // 会让下一个用例一进页面就渲染阅读区，断言"进页面只有树与提示"就假失败。
  useReaderTabsStore.setState({ openIds: [], scrolls: {} });
  hoisted.ctx = buildContext();
  vi.mocked(api.documents).mockResolvedValue([]);
  vi.mocked(api.graphExtractionStatuses).mockResolvedValue({ documents: {} } as never);
  vi.mocked(api.document).mockResolvedValue({ ok: true, document: {}, sections: [] } as never);
});

afterEach(() => {
  // 这个仓库的 vitest setup 没有注册自动 cleanup：两个用例若共享 DOM，
  // 第二个用例会因为"找到多个 alert/status"而在 waitFor 里超时。
  cleanup();
  vi.clearAllMocks();
});


/** 树里的一个文件（② 的只读树是资料库唯一的导航：平铺列表已按用户要求去掉）。 */
function treeFile(name: string, documentId: string, title: string) {
  return {
    type: "file", name, path: name, size: 10, modified_at: "2026-09-24T00:00:00+00:00",
    indexed: true, document_id: documentId, title, extraction_status: "complete", chunk_count: 2,
  };
}

function treeWith(files: unknown[]) {
  return { ok: true, tree: {
    type: "folder", name: "vault", path: "", material_count: files.length, indexed_count: files.length,
    ignored_count: 0, ignored_here: [], children: [], files,
  } };
}

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

  // 2026-09-24 用户要求：「我的资料」平铺列表和文件夹树功能重复、还占一栏，去掉了。
  // 这条钉住"资料库只有一套导航（树）"，以及树里的搜索框仍然在（它原来长在列表里）。
  it("资料库只有文件夹树这一套导航，没有重复的平铺列表", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("第一课.md", "doc-1", "第一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1",
      source: "course-2/第一课.md",
      relative_path: "第一课.md",
      kind: "course_document",
      title: "第一课",
      collection: "material",
      content_role: "content",
    }] as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("文件夹")).toBeTruthy(); // 树面板
    expect(await screen.findByText("第一课.md")).toBeTruthy();
    expect(screen.getByLabelText("搜索资料")).toBeTruthy(); // 搜索框搬进了树面板
    expect(document.querySelector(".document-rail")).toBeNull();
    expect(screen.queryByText("我的资料")).toBeNull();
  });

  it("打开的资料进标签条，关掉最后一个就收起", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("第一课.md", "doc-1", "第一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1",
      source: "course-2/第一课.md",
      relative_path: "第一课.md",
      kind: "course_document",
      title: "第一课",
      collection: "material",
      content_role: "content",
    }] as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText("第一课.md"));
    const tab = await screen.findByRole("tab", { name: "第一课" });
    expect(tab.getAttribute("aria-selected")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "关闭 第一课" }));
    await waitFor(() => expect(screen.queryByRole("tab", { name: "第一课" })).toBeNull());
  });

  // ④（E17）待修：资料库页选一份资料，选中→加载→渲染这条链必须跑通。
  // 2026-09-24 真实动线实测：把 selectDocument 的 material 分支从 navigate 改成就地
  // 选中之后，URL 与标签条都对了（tabs=1），但 sections=0 且 header 没渲染 ——
  // 说明 selected 仍为 null（documents 与 selectedId 没接上）。
  // 去掉 .skip 就是这条链的复现测试；它红了才说明修好了（详见设计文档 §9 执行手册）。
  it("选中资料后，资料库页的阅读区必须渲染出正文", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("第一课.md", "doc-1", "第一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1",
      source: "course-2/第一课.md",
      relative_path: "第一课.md",
      kind: "course_document",
      title: "第一课",
      collection: "material",
      content_role: "content",
    }] as never);
    vi.mocked(api.document).mockResolvedValue({
      ok: true,
      document: {
        document_id: "doc-1",
        source: "course-2/第一课.md",
        kind: "course_document",
        title: "第一课",
        collection: "material",
        content_role: "content",
      },
      sections: [
        { chunk_id: "c1", text: "第一节正文", heading: "第一节" },
        { chunk_id: "c2", text: "第二节正文", heading: "第二节" },
      ],
    } as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText("第一课.md"));

    await waitFor(() => expect(document.querySelectorAll(".reader-prose section").length).toBeGreaterThan(0));
    expect(await screen.findByRole("tab", { name: "第一课" })).toBeTruthy();

    // 目录：④ 第 3 步之后，资料库页的阅读区就是 DocumentReader 本身，"目录"因此是它的
    // 章节导轨（右缘悬停区），而不再是页面自己的 <details>。一条断言同时钉住这两件事。
    const railZone = document.querySelector(".chapter-rail-zone");
    expect(railZone).not.toBeNull();
    fireEvent.mouseEnter(railZone!);
    const rail = document.querySelector(".chapter-rail");
    expect(rail).not.toBeNull();
    const railButtons = () => Array.from(rail!.querySelectorAll("button"));
    expect(railButtons().map((button) => button.textContent)).toEqual(
      expect.arrayContaining(["第一节", "第二节"]),
    );
    // 点一下真的会跳到那一段（jsdom 没有 scrollIntoView，补个记录落点的桩）。
    const landed: string[] = [];
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function recordLanding() {
      landed.push((this as HTMLElement).dataset.chunkId || "");
    };
    fireEvent.click(railButtons().find((button) => button.textContent === "第二节")!);
    Element.prototype.scrollIntoView = originalScrollIntoView;
    expect(landed).toContain("c2");
  });

  it("整理建议：看建议 → 执行 → 再撤销", async () => {
    // 整理面板只挂在「有资料 + 有文件夹树」的工作区里，所以这里必须有真实列表。
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("第一课.md", "doc-1", "第一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1",
      source: "散落的一课.md",
      relative_path: "散落的一课.md",
      kind: "course_document",
      title: "散落的一课",
      collection: "material",
      content_role: "content",
    }] as never);
    vi.mocked(api.organizationProposals).mockResolvedValue({ ok: true, proposals: [{
      kind: "loose_materials",
      title: "库根散落的资料",
      reason: "这些资料直接躺在资料库根目录。",
      items: ["散落的一课.md"],
      suggested_folder: "未归类",
      requires_confirmation: true,
    }] } as never);
    vi.mocked(api.applyOrganization).mockResolvedValue({ ok: true, moved: [{ document_id: "d1", from: "散落的一课.md", to: "未归类/散落的一课.md" }] } as never);
    vi.mocked(api.undoOrganization).mockResolvedValue({ ok: true, restored: ["散落的一课.md"] } as never);
    // 刷新之后：清单不在前端手里了，界面的"可撤销"必须来自服务端台账。
    vi.mocked(api.organizationState).mockResolvedValue({ ok: true, pending_undo: {
      batch_id: "batch-1",
      created_at: "2026-09-24T12:00:00Z",
      target_folder: "未归类",
      moves: [{ document_id: "d1", from: "散落的一课.md", to: "未归类/散落的一课.md" }],
    } } as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    // 刷新后（进页面就查一次台账）：复盘"上一步"确实可撤销，而不是靠前端记忆。
    expect(await screen.findByText("撤销这一步整理")).toBeTruthy();
    expect(screen.getByText(/上一步：1 份资料收进「未归类」/)).toBeTruthy();

    fireEvent.click(await screen.findByText("看看有什么可以整理的"));
    expect(await screen.findByText(/库根散落的资料/)).toBeTruthy();
    // 建议面板在 <details> 里（jsdom 不会展开），点按钮用文本定位
    fireEvent.click(screen.getByText("收进「未归类」"));
    await waitFor(() => expect(api.applyOrganization).toHaveBeenCalledWith(["散落的一课.md"], "未归类"));
    fireEvent.click(await screen.findByText("撤销这一步整理"));
    // 不带清单：撤销的是服务端记下的那一步。
    await waitFor(() => expect(api.undoOrganization).toHaveBeenCalledWith());
  });

  it("AI 归类：界面如实说明这是 AI 提的，而且没确认前一份文件都不动", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("第一课.md", "doc-1", "第一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1", source: "散落的一课.md", relative_path: "散落的一课.md",
      kind: "course_document", title: "散落的一课", collection: "material", content_role: "content",
    }] as never);
    vi.mocked(api.aiOrganizationProposals).mockResolvedValue({ ok: true, source: "model", degraded: "", proposals: [{
      kind: "ai_group",
      title: "归到「课程笔记」",
      reason: "看起来是同一门课。",
      items: ["散落的一课.md"],
      suggested_folder: "课程笔记",
      requires_confirmation: true,
      source: "model",
    }] } as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText("让 AI 归类"));
    expect(await screen.findByText(/AI 提议/)).toBeTruthy();
    expect(screen.getByText("收进「课程笔记」")).toBeTruthy();
    expect(api.aiOrganizationProposals).toHaveBeenCalled();
    expect(api.applyOrganization).not.toHaveBeenCalled(); // 确认之前，一份文件都不许动
  });

  it("模型不可用时，界面说清楚这次是规则建议", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("第一课.md", "doc-1", "第一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1", source: "散落的一课.md", relative_path: "散落的一课.md",
      kind: "course_document", title: "散落的一课", collection: "material", content_role: "content",
    }] as never);
    vi.mocked(api.aiOrganizationProposals).mockResolvedValue({ ok: true, source: "rules", degraded: "model_unavailable", proposals: [{
      kind: "loose_materials",
      title: "库根散落的资料",
      reason: "这些资料直接躺在资料库根目录。",
      items: ["散落的一课.md"],
      suggested_folder: "未归类",
      requires_confirmation: true,
    }] } as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText("让 AI 归类"));
    expect(await screen.findByText(/模型这次没能参与/)).toBeTruthy();
  });

  // 2026-09-24 用户截图：三栏一起挤，正文只剩四百来像素；随后用户要求把重复的平铺列表去掉。
  // 现在的规则：进页面是"树 + 提示"，点树里的资料才出现正文；列表那一栏彻底不存在。
  it("进页面只有树与提示，点树里的资料才出现正文", async () => {
    vi.mocked(api.knowledgeTree).mockResolvedValue(treeWith([treeFile("散落的一课.md", "doc-1", "散落的一课")]) as never);
    vi.mocked(api.documents).mockResolvedValue([{
      document_id: "doc-1", source: "散落的一课.md", relative_path: "散落的一课.md",
      kind: "course_document", title: "散落的一课", collection: "material", content_role: "content",
    }] as never);
    vi.mocked(api.document).mockResolvedValue({
      ok: true,
      document: { document_id: "doc-1", source: "散落的一课.md", kind: "course_document", title: "散落的一课", collection: "material", content_role: "content" },
      sections: [{ chunk_id: "c1", text: "正文", heading: "第一节" }],
    } as never);

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <LibraryPage />
      </MemoryRouter>,
    );

    // 进页面：不自动打开第一份资料，右侧是一句"从哪开始"的提示，而不是空白栏。
    expect(await screen.findByText("从左边选一份资料开始阅读")).toBeTruthy();
    expect(document.querySelector(".document-reader")).toBeNull();
    expect(document.querySelector(".document-rail")).toBeNull();

    fireEvent.click(await screen.findByText("散落的一课.md"));

    await waitFor(() => expect(document.querySelector(".document-reader")).not.toBeNull());
    await waitFor(() => expect(document.querySelectorAll(".reader-tabs .reader-tab").length).toBe(1));
    expect(document.querySelector(".document-rail")).toBeNull();
  });
});