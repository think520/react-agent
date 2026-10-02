import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { LibrarySetupDialog } from "./LibrarySetupDialog";

/**
 * W1 E2：新建资料库的默认值只能有**一个**来源（后端）。
 *
 * 旧实现前端硬编码 «~/Documents/Bobodan»，后端却是 «~/Documents/Bobodan 资料库» ——
 * 用户看到的预填路径与真正创建的根目录不是一处；而且「保存到这个目录」填的其实是**父目录**，
 * 界面从来没显示过将来真正会创建在哪。
 */

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, libraryDefaults: vi.fn(), libraryRootPreview: vi.fn() },
  };
});

function renderDialog() {
  return render(<LibrarySetupDialog
    onClose={() => {}}
    onComplete={() => {}}
    onCreate={async () => {}}
    onOpen={async () => {}}
    onPreviewMigration={async () => ({}) as never}
    onMigrate={async () => {}}
  />);
}

beforeEach(() => {
  vi.mocked(api.libraryDefaults).mockResolvedValue({
    name: "Bobodan 资料库",
    parent_path: "C:/Users/x/Documents",
    root_path: "C:/Users/x/Documents/Bobodan 资料库",
  });
  vi.mocked(api.libraryRootPreview).mockResolvedValue({
    name: "Bobodan 资料库",
    parent_path: "C:/Users/x/Documents",
    root_path: "C:/Users/x/Documents/Bobodan 资料库",
  });
});

afterEach(cleanup);

it("用后端给的默认值预填，并显示将来真正创建的目录", async () => {
  renderDialog();

  const pathInput = await screen.findByLabelText(/保存到这个目录/) as HTMLInputElement;
  await waitFor(() => expect(pathInput.value).toBe("C:/Users/x/Documents"));
  const nameInput = screen.getByLabelText(/资料库名称/) as HTMLInputElement;
  expect(nameInput.value).toBe("Bobodan 资料库");
  // 「父目录 + 名称」的最终结果要说出来，而不是只给一个可能不是最终位置的路径。
  expect(await screen.findByText(/将创建：/)).toBeTruthy();
});

it("改名之后预览重新问后端（规则不在前端复制一份）", async () => {
  renderDialog();
  const nameInput = await screen.findByLabelText(/资料库名称/);
  vi.mocked(api.libraryRootPreview).mockResolvedValue({
    name: "线性代数",
    parent_path: "C:/Users/x/Documents",
    root_path: "C:/Users/x/Documents/线性代数",
  });

  fireEvent.change(nameInput, { target: { value: "线性代数" } });

  await waitFor(() =>
    expect(api.libraryRootPreview).toHaveBeenCalledWith("线性代数", "C:/Users/x/Documents"));
  expect(await screen.findByText("C:/Users/x/Documents/线性代数")).toBeTruthy();
});
