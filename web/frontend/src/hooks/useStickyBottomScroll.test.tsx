import { act, cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStickyBottomScroll, WHEEL_RELEASE_MS } from "./useStickyBottomScroll";

/**
 * W3 F7：自动滚动的**行为**（jsdom 没有布局，所以测量值由我们在真元素上伪造）。
 *
 * 用 React 真正渲染出来的那个 div：MutationObserver / 手势事件 / rAF 都是真的，只有浏览器
 * 不提供的部分（布局）被替换掉。
 */

let frames: Array<(now: number) => void> = [];
let frameSeq = 0;
let clock = 1000;

function flushFrames(count = 3) {
  for (let i = 0; i < count; i += 1) {
    const queued = frames;
    frames = [];
    clock += 16;
    for (const callback of queued) callback(clock);
  }
}

interface FakeScroller {
  element: HTMLDivElement;
  writes: number[];
  top: number;
  setTop(value: number): void;
  setHeight(value: number): void;
}

function installMetrics(element: HTMLDivElement): FakeScroller {
  let top = 0;
  let height = 1000;
  const writes: number[] = [];
  Object.defineProperty(element, "scrollTop", {
    get: () => top,
    set: (value: number) => { top = value; writes.push(value); },
    configurable: true,
  });
  Object.defineProperty(element, "scrollHeight", { get: () => height, configurable: true });
  Object.defineProperty(element, "clientHeight", { get: () => 400, configurable: true });
  return {
    element,
    writes,
    get top() { return top; },
    setTop: (value: number) => { top = value; },
    setHeight: (value: number) => { height = value; },
  };
}

let pinRef: { current: (() => void) | null } = { current: null };

function Harness({ revision }: { revision: number }) {
  const { ref, pinToBottom } = useStickyBottomScroll<HTMLDivElement>([revision]);
  useEffect(() => { pinRef.current = pinToBottom; }, [pinToBottom]);
  return <div ref={ref} data-testid="scroller" />;
}

async function mount(revision = 1): Promise<FakeScroller> {
  render(<Harness revision={revision} />);
  await act(async () => { await Promise.resolve(); });
  const element = screen.getByTestId("scroller") as HTMLDivElement;
  const fake = installMetrics(element);
  // 挂上新测量值后再走一帧，让 hook 用真实数字判断一次。
  await act(async () => { flushFrames(); });
  fake.writes.length = 0;
  return fake;
}

beforeEach(() => {
  frames = [];
  frameSeq = 0;
  clock = 1000;
  pinRef = { current: null };
  vi.stubGlobal("requestAnimationFrame", (callback: (now: number) => void) => {
    frames.push(callback);
    frameSeq += 1;
    return frameSeq;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("useStickyBottomScroll（W3 F7）", () => {
  it("内容变长（MutationObserver）会跟到底部，且一帧只写一次", async () => {
    const fake = await mount();
    fake.setTop(600); // 1000 - 400 → 在底部

    await act(async () => {
      fake.setHeight(1400);
      fake.element.appendChild(document.createElement("span"));
      fake.element.appendChild(document.createElement("span"));
      fake.element.appendChild(document.createElement("span"));
      await Promise.resolve(); // 让 MutationObserver 回调跑
      flushFrames(1); // 只走一帧
    });

    // 单写者：三次内容变化在这一帧里只造成一次写。
    expect(fake.writes).toHaveLength(1);

    await act(async () => { flushFrames(30); }); // 缓动是渐进的，跑到收敛
    expect(fake.top).toBeGreaterThan(995);
  });

  it("手势期间绝不写滚动位置，松手后恢复跟随", async () => {
    const fake = await mount();
    fake.setTop(600);

    await act(async () => {
      fake.element.dispatchEvent(new Event("touchstart"));
      fake.setHeight(1500);
      fake.element.appendChild(document.createElement("span"));
      await Promise.resolve();
      flushFrames(5);
    });
    expect(fake.writes).toHaveLength(0); // 手势里一次都没写

    // 松手时用户离底部 500px（内容在手指底下长出来了）→ 尊重用户位置，不硬拽。
    await act(async () => {
      fake.element.dispatchEvent(new Event("touchend"));
      flushFrames(5);
    });
    expect(fake.writes).toHaveLength(0);

    // 用户自己滚回底部 → 恢复跟随（下一次内容增长会跟到底）。
    await act(async () => {
      fake.setTop(1100);
      fake.element.dispatchEvent(new Event("scroll"));
      fake.setHeight(1700);
      fake.element.appendChild(document.createElement("span"));
      await Promise.resolve();
      flushFrames(40);
    });
    expect(fake.top).toBeGreaterThan(1295);
  });

  it("用户滚上去不再跟随，但发消息（pinToBottom）会重新跟随", async () => {
    const fake = await mount();
    fake.setTop(600);

    await act(async () => {
      fake.setTop(0);
      fake.element.dispatchEvent(new Event("scroll"));
      flushFrames();
    });
    const before = fake.writes.length;

    await act(async () => {
      fake.setHeight(1600);
      fake.element.appendChild(document.createElement("span"));
      await Promise.resolve();
      flushFrames();
    });
    expect(fake.writes.length).toBe(before); // 不打扰正在读上面的用户

    await act(async () => {
      pinRef.current?.();
      flushFrames();
    });
    expect(fake.top).toBe(1200);
  });

  it("聊天滚动容器关掉浏览器自带的滚动锚定", () => {
    const css = readFileSync(resolve(process.cwd(), "src", "styles.css"), "utf8");
    const start = css.indexOf(".chat-scroll {");
    expect(start).toBeGreaterThan(-1);
    const rule = css.slice(start, css.indexOf("}", start));
    expect(rule).toContain("overflow-anchor: none");
  });

  it("用键盘或滚动条回到上次自动写入的底部后，恢复跟随", async () => {
    const fake = await mount();
    await act(async () => { flushFrames(40); });
    expect(fake.top).toBeGreaterThan(595);

    await act(async () => {
      // 先接收自动滚动自己的事件，再用 Home / End 或滚动条离开并返回底部。
      fake.element.dispatchEvent(new Event("scroll"));
      fake.setTop(0);
      fake.element.dispatchEvent(new Event("scroll"));
      flushFrames();
      fake.setTop(600);
      fake.element.dispatchEvent(new Event("scroll"));
      flushFrames();
    });
    await act(async () => {
      fake.setHeight(1400);
      fake.element.appendChild(document.createElement("span"));
      await Promise.resolve();
      flushFrames(40);
    });

    expect(fake.top).toBeGreaterThan(995);
  });

  it.each([1, 3])("发送后的第 %i 帧遇到滚轮，暂停期间零写入，释放后仍然回底", async (frameCount) => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const fake = await mount();
    await act(async () => {
      flushFrames(40);
      fake.setTop(0);
      fake.element.dispatchEvent(new Event("scroll"));
      flushFrames();
      pinRef.current?.();
      flushFrames(frameCount);
    });
    if (frameCount === 1) expect(fake.top).toBe(0); // 首帧缓动系数为 0。
    else expect(fake.top).toBeGreaterThan(0);
    expect(fake.top).toBeLessThan(595);
    const writesBeforeGesture = fake.writes.length;

    await act(async () => {
      fake.element.dispatchEvent(new Event("wheel"));
      flushFrames(5);
    });
    expect(fake.writes).toHaveLength(writesBeforeGesture);

    await act(async () => {
      vi.advanceTimersByTime(WHEEL_RELEASE_MS + 1);
      flushFrames(40);
    });
    expect(fake.top).toBeGreaterThan(595);

    // 回底请求已消费：之后的新手势仍可离开底部，不会被持续拉回。
    await act(async () => {
      fake.element.dispatchEvent(new Event("wheel"));
      fake.setTop(0);
      fake.element.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(WHEEL_RELEASE_MS + 1);
      flushFrames(40);
    });
    expect(fake.top).toBe(0);
  });
});

  it("刚发消息时来了一下滚轮，松手后仍然会回底（pin 不该被手势吞掉）", async () => {
    const fake = await mount();
    fake.setTop(0); // 用户之前滚到了最上面
    await act(async () => {
      fake.element.dispatchEvent(new Event("scroll"));
      flushFrames();
    });

    await act(async () => {
      pinRef.current?.(); // 用户发送消息
      fake.element.dispatchEvent(new Event("wheel")); // 恰好一次滚轮余波
      flushFrames();
    });
    // 松手（滚轮空闲计时器到点）之后仍然应当回到最新消息 —— 缓动要跑到收敛。
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200));
      flushFrames(40);
    });

    expect(fake.top).toBeGreaterThan(595);
  });
