import { describe, expect, it } from "vitest";

import { DRAG_DEAD_ZONE_PX, exceedsDragDeadZone } from "./pointer";

describe("指针死区（M4）", () => {
  it("位移小于 4px 视为点击", () => {
    expect(exceedsDragDeadZone({ x: 10, y: 10 }, { x: 13, y: 12 })).toBe(false);
  });

  it("位移达到 4px 视为拖拽", () => {
    expect(DRAG_DEAD_ZONE_PX).toBe(4);
    expect(exceedsDragDeadZone({ x: 10, y: 10 }, { x: 14, y: 10 })).toBe(true);
    expect(exceedsDragDeadZone({ x: 10, y: 10 }, { x: 13, y: 13 })).toBe(true);
  });

  it("没有按下起点时不当作拖拽", () => {
    expect(exceedsDragDeadZone(null, { x: 50, y: 50 })).toBe(false);
  });
});
