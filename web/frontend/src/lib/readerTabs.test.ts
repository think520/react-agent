import { describe, expect, it } from "vitest";

import {
  EMPTY_TABS,
  activateTab,
  closeTab,
  deserialize,
  openTab,
  positionFor,
  rememberPosition,
  serialize,
} from "./readerTabs";

/**
 * ④（E17）：阅读区标签页的规则。
 * 参考项目的一致做法：已开只激活、关当前激活右邻居、关最后一个自动收起、
 * 每篇记住读到哪（关掉也留着）。
 */
describe("阅读区标签页", () => {
  it("打开已存在的标签页只激活，不重复开", () => {
    let state = openTab(EMPTY_TABS, "doc-1", "第一课");
    state = openTab(state, "doc-2", "第二课");
    state = openTab(state, "doc-1");

    expect(state.tabs.map((tab) => tab.documentId)).toEqual(["doc-1", "doc-2"]);
    expect(state.activeId).toBe("doc-1");
    expect(state.tabs[0].title).toBe("第一课");
  });

  it("关掉当前标签页激活右邻居，没有右邻居则左邻居", () => {
    let state = openTab(openTab(openTab(EMPTY_TABS, "a"), "b"), "c");
    state = activateTab(state, "b");
    expect(closeTab(state, "b").activeId).toBe("c");

    state = openTab(state, "d");
    state = activateTab(state, "d");
    expect(closeTab(state, "d").activeId).toBe("c");
  });

  it("关掉最后一个标签页就收起（activeId 归空）", () => {
    const state = openTab(EMPTY_TABS, "only");
    const closed = closeTab(state, "only");
    expect(closed.tabs).toEqual([]);
    expect(closed.activeId).toBeNull();
  });

  it("关掉非当前标签页不影响激活项", () => {
    let state = openTab(openTab(EMPTY_TABS, "a"), "b");
    state = closeTab(state, "a");
    expect(state.activeId).toBe("b");
  });

  it("阅读位置被夹到 0–100 并保留在关掉之后", () => {
    let state = rememberPosition(EMPTY_TABS, "doc-1", 137);
    expect(positionFor(state, "doc-1")).toBe(100);
    state = rememberPosition(state, "doc-1", -5);
    expect(positionFor(state, "doc-1")).toBe(0);

    state = rememberPosition(state, "doc-2", 42);
    state = closeTab(openTab(state, "doc-2"), "doc-2");
    expect(positionFor(state, "doc-2")).toBe(42);
    expect(positionFor(state, null)).toBe(0);
  });

  it("序列化能往返，坏数据退回空状态", () => {
    let state = openTab(EMPTY_TABS, "doc-1", "第一课");
    state = rememberPosition(state, "doc-1", 30);
    expect(deserialize(serialize(state))).toEqual(state);

    expect(deserialize("not json")).toEqual(EMPTY_TABS);
    expect(deserialize(JSON.stringify({ tabs: [{ title: "没有 id" }], activeId: "x", positions: { a: "nan" } }))).toEqual(
      { tabs: [], activeId: null, positions: {} },
    );
  });
});
