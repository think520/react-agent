import { useEffect, useRef } from "react";

import { TAU_MS, easedPosition, easingFactor, shouldJumpInstant } from "../lib/scrollEasing";

/**
 * Continuous bottom-scroll (FE-2): follows new content with rAF exponential
 * easing (tau = 85ms), jumps instantly on large deltas (>720px), and cancels
 * following as soon as the user scrolls away from the bottom. A ResizeObserver
 * re-follows when content grows without a scroll event.
 */
export function useStickyBottomScroll<T extends HTMLElement>(deps: unknown[]) {
  const scrollRef = useRef<T | null>(null);
  const followingRef = useRef(true);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (!followingRef.current) return;

    const target = element.scrollHeight - element.clientHeight;
    const start = element.scrollTop;
    const distance = target - start;

    if (shouldJumpInstant(distance) || typeof requestAnimationFrame !== "function") {
      element.scrollTop = target;
      return;
    }
    if (Math.abs(distance) < 1) return;

    const begin = performance.now();
    const cancel = () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
    const animate = (now: number) => {
      if (!followingRef.current) return;
      const factor = easingFactor(now - begin, TAU_MS);
      element.scrollTop = easedPosition(start, target, factor);
      if (factor < 1 && followingRef.current) rafRef.current = requestAnimationFrame(animate);
    };
    cancel();
    rafRef.current = requestAnimationFrame(animate);
    return cancel;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // Track user intervention: scrolling away from the bottom stops following.
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const onScroll = () => {
      const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
      followingRef.current = distanceFromBottom < 40;
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    return () => element.removeEventListener("scroll", onScroll);
  }, []);

  // Re-follow when content grows (e.g. images/late-render) without a scroll.
  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (followingRef.current) element.scrollTop = element.scrollHeight;
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return scrollRef;
}
