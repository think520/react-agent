import { useCallback, useEffect, useRef } from "react";

import { TAU_MS, easedPosition, easingFactor } from "../lib/scrollEasing";
import { shouldFollow, shouldJump } from "../lib/scrollFollow";

/** 滚轮停多久算手势结束（毫秒）；触摸用 touchend 判定，不需要这个。 */
export const WHEEL_RELEASE_MS = 140;

/**
 * 连续底部滚动（FE-2 / W3 F7）。
 *
 * F7 之前的三个问题：
 * 1) **多个写者** —— rAF 动画、scroll 事件、ResizeObserver 各自直接写 `scrollTop`，互相盖；
 * 2) **内容变长但容器不变**时收不到通知（ResizeObserver 看的是容器自己的盒子，不是内容）；
 * 3) 用户手势期间没有保护，动画会跟手指抢滚动。
 *
 * 现在的结构：
 * - **单写者**：所有触发都进 `schedule()`，一帧只排一次；`scrollTop` 只在 `step()` 里被写；
 * - **MutationObserver**（childList + subtree + characterData）管内容变长，与 rAF 合帧；
 * - **手势释放**：touchstart/touchmove 与 wheel 期间绝不动，touchend/touchcancel（滚轮用
 *   `WHEEL_RELEASE_MS` 空闲）之后恢复；
 * - **用户消息才回底**：`pinToBottom()` 由调用方在用户发消息时调用 —— 即使之前滚到了上面也重新
 *   跟随；助手流式输出本身不会把视图拽回去。
 *
 * 决策本身是纯函数（`lib/scrollFollow.ts`），这里只把它接到 DOM 事件上。
 */
export function useStickyBottomScroll<T extends HTMLElement>(deps: unknown[]) {
  const scrollRef = useRef<T | null>(null);
  const followingRef = useRef(true);
  const interactingRef = useRef(false);
  const pinnedRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const animBeginRef = useRef<number | null>(null);
  // `step` 需要排下一帧、也就是引用自己；React Compiler 的 lint 不允许函数里的前向自引用，
  // 所以把实现放在 effect 内（函数声明可以自引用），对外只留一个 ref。
  const stepRef = useRef<((now: number) => void) | null>(null);
  //: 同一份「跟随判定」也供手势结束时复用（避免两处各写一遍）。
  const refreshFollowRef = useRef<(() => void) | null>(null);
  //: 我们自己最后写进去的位置 —— 用来把"我们造成的 scroll 事件"和用户滚动区分开。
  const lastWrittenRef = useRef<number | null>(null);

  const schedule = useCallback(() => {
    if (rafRef.current !== null) return; // 已经排了一帧 → 合帧
    const run = stepRef.current;
    if (typeof requestAnimationFrame !== "function" || !run) {
      run?.(0);
      return;
    }
    rafRef.current = requestAnimationFrame((now) => {
      rafRef.current = null;
      run(now);
    });
  }, []);

  /** 用户发消息时调用：无条件回到跟随（下一帧生效）。 */
  const pinToBottom = useCallback(() => {
    pinnedRef.current = true;
    followingRef.current = true;
    animBeginRef.current = null;
    schedule();
  }, [schedule]);

  // 跟随引擎：唯一的写者 + 跟随判定都在这里。
  useEffect(() => {
    function refreshFollow() {
      const element = scrollRef.current;
      if (!element) return;
      followingRef.current = shouldFollow({
        metrics: {
          scrollTop: element.scrollTop,
          scrollHeight: element.scrollHeight,
          clientHeight: element.clientHeight,
        },
        interacting: interactingRef.current,
        pinned: pinnedRef.current,
      });
    }

    function step(now: number) {
      const element = scrollRef.current;
      if (!element) return;
      // 注意：**不在这里**重新判定「离底部多远」—— 内容变长时 scrollTop 不变、距离会瞬间
      // 变成几百像素，那样就会把"内容长出来了"误读成"用户滚走了"（经典 sticky-bottom 陷阱）。
      // 跟随与否只由用户意图决定：滚动事件（且不是我们自己写的）、手势、发消息。
      // 手势期间绝不写：用户手指/滚轮还在动的时候，动画不许抢。
      if (!followingRef.current || interactingRef.current) {
        animBeginRef.current = null;
        return;
      }
      const target = element.scrollHeight - element.clientHeight;
      const distance = target - element.scrollTop;
      if (Math.abs(distance) < 1) {
        animBeginRef.current = null;
        return;
      }
      if (shouldJump(distance) || typeof requestAnimationFrame !== "function") {
        element.scrollTop = target;
        lastWrittenRef.current = target;
        animBeginRef.current = null;
        return;
      }
      const begin = animBeginRef.current ?? now;
      animBeginRef.current = begin;
      const factor = easingFactor(now - begin, TAU_MS);
      element.scrollTop = easedPosition(element.scrollTop, target, factor);
      lastWrittenRef.current = element.scrollTop;
      if (factor < 1) {
        rafRef.current = requestAnimationFrame((next) => {
          rafRef.current = null;
          step(next);
        });
      } else {
        animBeginRef.current = null;
      }
    }

    stepRef.current = step;
    refreshFollowRef.current = refreshFollow;
    return () => {
      stepRef.current = null;
      refreshFollowRef.current = null;
    };
  }, []);

  // 内容变化（deps）→ 跟随。
  useEffect(() => {
    if (followingRef.current) schedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // 用户手势：手指/滚轮期间绝不写位置；结束后恢复。
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    let wheelTimer: ReturnType<typeof setTimeout> | null = null;
    const beginGesture = () => { interactingRef.current = true; };
    const endGesture = () => {
      interactingRef.current = false;
      pinnedRef.current = false;
      animBeginRef.current = null;
      // 松手之后按「用户现在停在哪」决定：在底部附近就继续跟随，否则不打扰。
      refreshFollowRef.current?.();
      if (followingRef.current) schedule();
    };
    const onWheel = () => {
      beginGesture();
      if (wheelTimer) clearTimeout(wheelTimer);
      wheelTimer = setTimeout(endGesture, WHEEL_RELEASE_MS);
    };
    const onScroll = () => {
      if (interactingRef.current) return; // 手势中：不抢
      const written = lastWrittenRef.current;
      if (written !== null && Math.abs(element.scrollTop - written) < 2) {
        // 这一跳是我们自己写的（缓动每帧都会触发 scroll）→ 不代表用户意图。
        return;
      }
      pinnedRef.current = false;
      // 用户自己滚回底部 → 继续跟随；滚上去 → 停下。
      const nearBottom = shouldFollow({
        metrics: {
          scrollTop: element.scrollTop,
          scrollHeight: element.scrollHeight,
          clientHeight: element.clientHeight,
        },
        interacting: false,
        pinned: false,
      });
      followingRef.current = nearBottom;
      if (nearBottom) schedule();
    };
    element.addEventListener("touchstart", beginGesture, { passive: true });
    element.addEventListener("touchmove", beginGesture, { passive: true });
    element.addEventListener("touchend", endGesture, { passive: true });
    element.addEventListener("touchcancel", endGesture, { passive: true });
    element.addEventListener("wheel", onWheel, { passive: true });
    element.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      if (wheelTimer) clearTimeout(wheelTimer);
      element.removeEventListener("touchstart", beginGesture);
      element.removeEventListener("touchmove", beginGesture);
      element.removeEventListener("touchend", endGesture);
      element.removeEventListener("touchcancel", endGesture);
      element.removeEventListener("wheel", onWheel);
      element.removeEventListener("scroll", onScroll);
    };
  }, [schedule]);

  // 内容变长但容器盒子没变（图片、晚渲染的块）→ MutationObserver，与 rAF 合帧。
  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof MutationObserver === "undefined") return;
    const observer = new MutationObserver(() => {
      if (followingRef.current) schedule();
    });
    observer.observe(element, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [schedule]);

  // 容器自身尺寸变化（窗口缩放等）→ 同上。
  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (followingRef.current) schedule();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [schedule]);

  useEffect(() => () => {
    if (rafRef.current !== null && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(rafRef.current);
    }
    rafRef.current = null;
  }, []);

  return { ref: scrollRef, pinToBottom };
}