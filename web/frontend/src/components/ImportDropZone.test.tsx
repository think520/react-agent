import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ImportDropZone } from "./ImportDropZone";

/**
 * E8：拖拽热区。核对结论是前端**完全没有** drag 处理。
 * 参考 openhanako：dragCounter + 覆盖层 + **窗口级兜底**（松手在窗口外 / Escape / 失焦时
 * 收不到成对的 dragleave，计数器会卡住，覆盖层就再也退不掉）。
 */

afterEach(cleanup);

function dropEvent(files: File[]) {
  return { dataTransfer: { files, types: ["Files"] } };
}

it("拖进来显示热区，拖出去就收起来", () => {
  render(<ImportDropZone onFiles={() => {}}><div>内容区</div></ImportDropZone>);

  fireEvent.dragEnter(screen.getByTestId("import-drop-zone"), dropEvent([]));
  expect(screen.getByText(/松开就导入/)).toBeTruthy();

  fireEvent.dragLeave(screen.getByTestId("import-drop-zone"), dropEvent([]));
  expect(screen.queryByText(/松开就导入/)).toBeNull();
});

it("松手把文件交给导入通道", () => {
  const onFiles = vi.fn();
  render(<ImportDropZone onFiles={onFiles}><div>内容区</div></ImportDropZone>);

  const files = [new File(["# a"], "a.md", { type: "text/markdown" })];
  fireEvent.dragEnter(screen.getByTestId("import-drop-zone"), dropEvent(files));
  fireEvent.drop(screen.getByTestId("import-drop-zone"), dropEvent(files));

  expect(onFiles).toHaveBeenCalledTimes(1);
  expect(onFiles.mock.calls[0][0].map((file: File) => file.name)).toEqual(["a.md"]);
  expect(screen.queryByText(/松开就导入/)).toBeNull();
});

it("窗口失焦/松手在窗口外时，热区不会卡住", () => {
  render(<ImportDropZone onFiles={() => {}}><div>内容区</div></ImportDropZone>);

  fireEvent.dragEnter(screen.getByTestId("import-drop-zone"), dropEvent([]));
  expect(screen.getByText(/松开就导入/)).toBeTruthy();

  fireEvent.blur(window);
  expect(screen.queryByText(/松开就导入/)).toBeNull();

  fireEvent.dragEnter(screen.getByTestId("import-drop-zone"), dropEvent([]));
  fireEvent(window, new Event("dragend"));
  expect(screen.queryByText(/松开就导入/)).toBeNull();
});

it("没有资料库时（enabled=false）不摆热区，也不吃拖拽", () => {
  const onFiles = vi.fn();
  render(<ImportDropZone onFiles={onFiles} enabled={false}><div>内容区</div></ImportDropZone>);

  fireEvent.dragEnter(screen.getByTestId("import-drop-zone"), dropEvent([]));
  expect(screen.queryByText(/松开就导入/)).toBeNull();
  fireEvent.drop(screen.getByTestId("import-drop-zone"), dropEvent([new File(["x"], "x.md")]));
  expect(onFiles).not.toHaveBeenCalled();
});
