import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryTree, collectFiles, filterTree, treeStatusTone } from "./LibraryTree";
import type { KnowledgeTreeFolder } from "../lib/api";

/**
 * ②（E17）：只读文件夹树。
 * 设计 §3.3 —— 文件夹行给「资料数 + N 份未提取」，文件行给状态点，
 * 被忽略的文件在文件夹行上可展开核对（而不是静默消失）。
 */

function file(overrides: Partial<Parameters<typeof treeStatusTone>[0]> & { name: string; path: string }) {
  return {
    type: "file" as const,
    size: 10,
    modified_at: "2026-09-24T00:00:00+00:00",
    indexed: true,
    document_id: "doc-1",
    title: overrides.name,
    extraction_status: "complete" as const,
    chunk_count: 3,
    ...overrides,
  };
}

const tree: KnowledgeTreeFolder = {
  type: "folder",
  name: "vault",
  path: "",
  material_count: 2,
  indexed_count: 1,
  ignored_count: 2,
  ignored_here: [],
  children: [
    {
      type: "folder",
      name: "ai-agents-from-zero",
      path: "ai-agents-from-zero",
      material_count: 2,
      indexed_count: 1,
      ignored_count: 2,
      ignored_here: [{ name: "README.md", path: "ai-agents-from-zero/README.md", reason: "repo_metadata" }],
      children: [
        {
          type: "folder",
          name: "assets",
          path: "ai-agents-from-zero/assets",
          material_count: 0,
          indexed_count: 0,
          ignored_count: 1,
          ignored_here: [{ name: "logo.png", path: "ai-agents-from-zero/assets/logo.png", reason: "unsupported_type" }],
          children: [],
          files: [],
        },
      ],
      files: [
        file({ name: "1-1-学习.md", path: "ai-agents-from-zero/1-1-学习.md", document_id: "doc-1" }),
        file({
          name: "还没同步.md",
          path: "ai-agents-from-zero/还没同步.md",
          indexed: false,
          document_id: null,
          extraction_status: null,
          chunk_count: 0,
        }),
      ],
    },
  ],
  files: [],
};

// 树把展开状态记在 localStorage（设计 §3.3），用例之间必须清掉，
    // 否则前一个用例展开过的文件夹会让后一个用例找不到「展开 …」按钮。
    beforeEach(() => localStorage.clear());
afterEach(cleanup);

describe("资料库文件夹树", () => {
  it("文件夹行给出资料数与未提取数，展开后才显示文件", () => {
    render(<LibraryTree tree={tree} selectedFolder="" onSelectFolder={() => {}} onOpenDocument={() => {}} />);

    const row = screen.getByRole("button", { name: "ai-agents-from-zero" }).closest(".library-tree-row");
    expect(row?.textContent).toContain("2 份");
    expect(row?.textContent).toContain("1 份未提取");

    // 未展开时看不到文件
    expect(screen.queryByText("1-1-学习.md")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /展开 ai-agents-from-zero/ }));
    expect(screen.getByText("1-1-学习.md")).toBeTruthy();
  });

  it("点文件打开它，未索引的文件不可点但看得见", () => {
    const onOpenDocument = vi.fn();
    render(<LibraryTree tree={tree} selectedFolder="" onSelectFolder={() => {}} onOpenDocument={onOpenDocument} />);
    fireEvent.click(screen.getByRole("button", { name: /展开 ai-agents-from-zero/ }));

    fireEvent.click(screen.getByText("1-1-学习.md"));
    expect(onOpenDocument).toHaveBeenCalledWith("doc-1");

    const pending = screen.getByRole("button", { name: /还没同步.md/ });
    expect((pending as HTMLButtonElement).disabled).toBe(true);
  });

  it("被忽略的文件按文件夹计数并可展开核对原因", () => {
    render(<LibraryTree tree={tree} selectedFolder="" onSelectFolder={() => {}} onOpenDocument={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /展开 ai-agents-from-zero/ }));

    const summary = screen.getByText("另有 2 个文件已忽略");
    fireEvent.click(summary);
    expect(screen.getByText("README.md")).toBeTruthy();
    expect(screen.getByText("仓库元文件")).toBeTruthy();
  });

  it("选中文件夹时该行处于选中态", () => {
    render(
      <LibraryTree
        tree={tree}
        selectedFolder="ai-agents-from-zero"
        onSelectFolder={() => {}}
        onOpenDocument={() => {}}
      />,
    );
    const folderRow = screen.getByRole("button", { name: "ai-agents-from-zero" }).closest(".library-tree-row");
    expect(folderRow?.className).toContain("selected");
  });

  it("collectFiles 递归收集，状态点区分未索引与失败", () => {
    expect(collectFiles(tree)).toHaveLength(2);
    expect(treeStatusTone(file({ name: "a.md", path: "a.md", indexed: false }))).toBe("unindexed");
    expect(treeStatusTone(file({ name: "b.md", path: "b.md", extraction_status: "error" }))).toBe("failed");
    expect(treeStatusTone(file({ name: "c.md", path: "c.md", extraction_status: "empty" }))).toBe("empty");
  });

  it("搜索时过滤树并保留命中项的祖先链", () => {
    render(
      <LibraryTree
        tree={tree}
        query="1-1"
        selectedFolder=""
        onSelectFolder={() => {}}
        onOpenDocument={() => {}}
      />,
    );
    // 祖先文件夹仍在（否则命中的文件会悬空）
    expect(screen.getByRole("button", { name: "ai-agents-from-zero" })).toBeTruthy();
    // 搜索期间自动展开命中路径
    fireEvent.click(screen.getByRole("button", { name: /展开 ai-agents-from-zero/ }));
    expect(screen.getByText("1-1-学习.md")).toBeTruthy();
    expect(screen.queryByText("还没同步.md")).toBeNull();
  });

  it("filterTree 对空查询原样返回，无命中时返回 null", () => {
    expect(filterTree(tree, "  ")).toBe(tree);
    expect(filterTree(tree, "根本不存在的名字")).toBeNull();
    const hit = filterTree(tree, "assets");
    expect(hit?.children.map((child) => child.name)).toEqual(["ai-agents-from-zero"]);
    expect(hit?.children[0].children.map((child) => child.name)).toEqual(["assets"]);
  });
});