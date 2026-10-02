import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ReaderAnchorsPanel, anchorStatusLabel } from "./ReaderAnchorsPanel";

/**
 * W1 E7：划线列表要说清"还指不指得到"，并且能定位、能删。
 */

afterEach(cleanup);

const anchors = [
  { anchor_id: "a1", chunk_id: "c1", quote: "贪心策略", resolution: { status: "exact", char_start: 20, char_end: 24 } },
  { anchor_id: "a2", chunk_id: "c1", quote: "已经被改掉的句子", resolution: { status: "stale", char_start: null, char_end: null } },
];

it("显示引文与现状（失效的划线要说出来）", () => {
  render(<ReaderAnchorsPanel anchors={anchors} onLocate={() => {}} onDelete={() => {}} />);

  expect(screen.getByText("贪心策略")).toBeTruthy();
  expect(screen.getByText("位置未变")).toBeTruthy();
  expect(screen.getByText("已失效，需重新指认")).toBeTruthy();
});

it("点引文或定位按钮都能回到那一段", () => {
  const onLocate = vi.fn();
  render(<ReaderAnchorsPanel anchors={anchors} onLocate={onLocate} onDelete={() => {}} />);

  fireEvent.click(screen.getByText("贪心策略"));
  expect(onLocate).toHaveBeenCalledWith(anchors[0]);

  fireEvent.click(screen.getAllByLabelText("定位到这段")[1]);
  expect(onLocate).toHaveBeenCalledWith(anchors[1]);
});

it("删除按钮带上那条划线", () => {
  const onDelete = vi.fn();
  render(<ReaderAnchorsPanel anchors={anchors} onLocate={() => {}} onDelete={onDelete} />);

  fireEvent.click(screen.getAllByLabelText("删除这条划线")[0]);

  expect(onDelete).toHaveBeenCalledWith(anchors[0]);
});

it("没有划线时不占地方", () => {
  const { container } = render(<ReaderAnchorsPanel anchors={[]} onLocate={() => {}} onDelete={() => {}} />);

  expect(container.textContent).toBe("");
});

it("未知状态如实显示原值，不编中文", () => {
  expect(anchorStatusLabel("some_new_status")).toBe("some_new_status");
  expect(anchorStatusLabel(undefined)).toBe("");
});
