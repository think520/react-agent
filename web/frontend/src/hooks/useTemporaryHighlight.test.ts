import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useTemporaryHighlight } from "./useTemporaryHighlight";

/**
 * W1 E16：确认新概念之后要把它**高亮几秒**再自己消失。
 * 计时是这件事的核心（"数秒"而不是永久），单独钉住它。
 */

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("高亮一段时间后自己消失", () => {
  const { result } = renderHook(() => useTemporaryHighlight(3000));

  act(() => result.current.highlight(["c-1"]));
  expect(result.current.highlighted).toEqual(["c-1"]);

  act(() => { vi.advanceTimersByTime(2999); });
  expect(result.current.highlighted).toEqual(["c-1"]);

  act(() => { vi.advanceTimersByTime(1); });
  expect(result.current.highlighted).toEqual([]);
});

it("再次高亮会重新计时（不是两次各自的定时器抢着清）", () => {
  const { result } = renderHook(() => useTemporaryHighlight(3000));

  act(() => result.current.highlight(["c-1"]));
  act(() => { vi.advanceTimersByTime(2000); });
  act(() => result.current.highlight(["c-2"]));

  act(() => { vi.advanceTimersByTime(2000); });
  // 距第二次高亮才 2 秒，仍在高亮中。
  expect(result.current.highlighted).toEqual(["c-2"]);

  act(() => { vi.advanceTimersByTime(1000); });
  expect(result.current.highlighted).toEqual([]);
});

it("去重并忽略空 id（批量确认时可能重复）", () => {
  const { result } = renderHook(() => useTemporaryHighlight(1000));

  act(() => result.current.highlight(["c-1", "c-1", "", "c-2"]));

  expect(result.current.highlighted).toEqual(["c-1", "c-2"]);
});

it("空列表直接清掉高亮", () => {
  const { result } = renderHook(() => useTemporaryHighlight(1000));

  act(() => result.current.highlight(["c-1"]));
  act(() => result.current.highlight([]));

  expect(result.current.highlighted).toEqual([]);
});

it("卸载后不再更新状态（避免定时器打到已卸载组件）", () => {
  const { result, unmount } = renderHook(() => useTemporaryHighlight(1000));
  act(() => result.current.highlight(["c-1"]));

  unmount();
  expect(() => act(() => { vi.advanceTimersByTime(2000); })).not.toThrow();
});
