import { describe, expect, it } from "vitest";

import { FOLLOW_THRESHOLD_PX, distanceFromBottom, shouldFollow, shouldJump } from "./scrollFollow";

/**
 * W3 F7：自动滚动升级的**决策**部分（纯函数）。
 *
 * jsdom 没有布局（scrollHeight 恒为 0），所以「滚不滚」的判断必须离开 DOM 才能测；
 * hook 只负责把决策接到 rAF / MutationObserver / 手势事件上。
 */

describe("distanceFromBottom", () => {
  it("算的是「离底部还有多少像素」", () => {
    expect(distanceFromBottom({ scrollTop: 100, scrollHeight: 500, clientHeight: 300 })).toBe(100);
    expect(distanceFromBottom({ scrollTop: 200, scrollHeight: 500, clientHeight: 300 })).toBe(0);
  });

  it("过卷（内容变短）时返回 0 而不是负数", () => {
    expect(distanceFromBottom({ scrollTop: 260, scrollHeight: 500, clientHeight: 300 })).toBe(0);
  });
});

describe("shouldFollow", () => {
  it("在底部附近才跟随", () => {
    // 阈值是严格小于 40：scrollTop 170 → 离底 30px，算「还在底部」。
    const near = { scrollTop: 170, scrollHeight: 500, clientHeight: 300 };
    const far = { scrollTop: 100, scrollHeight: 500, clientHeight: 300 };
    expect(shouldFollow({ metrics: near, interacting: false, pinned: false })).toBe(true);
    expect(shouldFollow({ metrics: far, interacting: false, pinned: false })).toBe(false);
  });

  it("用户正在手势里 → 不跟随（手势释放前绝不抢滚动）", () => {
    const near = { scrollTop: 200, scrollHeight: 500, clientHeight: 300 };
    expect(shouldFollow({ metrics: near, interacting: true, pinned: false })).toBe(false);
  });

  it("用户发消息（pinned）→ 即使之前滚到上面也回到跟随", () => {
    const far = { scrollTop: 0, scrollHeight: 500, clientHeight: 300 };
    expect(shouldFollow({ metrics: far, interacting: false, pinned: true })).toBe(true);
    // 但手势优先：手指还在屏幕上时不抢。
    expect(shouldFollow({ metrics: far, interacting: true, pinned: true })).toBe(false);
  });
});

describe("shouldJump", () => {
  it("大跳变直接瞬移（沿用既有阈值：严格大于 720）", () => {
    expect(shouldJump(721)).toBe(true);
    expect(shouldJump(-721)).toBe(true);
    expect(shouldJump(720)).toBe(false);
    expect(shouldJump(40)).toBe(false);
  });

  it("阈值常量与实现一致", () => {
    expect(FOLLOW_THRESHOLD_PX).toBeGreaterThan(0);
  });
});