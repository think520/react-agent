import { useCallback, useLayoutEffect, useRef } from "react";

/**
 * 引用稳定、内容总是最新的回调：只用于**事件里**调用的函数（渲染期调用会读到上一帧）。
 * 外壳把几十个回调经 Outlet context 交给页面，它们每次渲染都是新函数，会让 context
 * 每次都是新对象、页面跟着整页重渲染。
 */
export function useStableCallback<A extends unknown[], R>(fn: (...args: A) => R): (...args: A) => R {
  const ref = useRef(fn);
  useLayoutEffect(() => { ref.current = fn; });
  return useCallback((...args: A) => ref.current(...args), []);
}
