import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/**
 * 常驻可见的自绘滚动条（2026-09-24）。
 *
 * 为什么需要它：在 Windows 11 + Chromium 上原生滚动条是**覆盖式**的 —— 实测
 * `::-webkit-scrollbar { width: 20px }`、`scrollbar-width: thin`、什么都不写，四种写法
 * 的 `offsetWidth - clientWidth` 全是 0，也就是它不占布局、平时根本不画出来。
 * 用户想拖它翻长文时抓不到（"收了右栏就没有滑动条了"）。
 *
 * 所以阅读区自己画一条：常驻可见、可拖、点轨道跳转、滚动或悬停时加深。
 * **只负责显示与拖动**：滚动仍然由目标容器的原生滚动承担，滚轮、键盘、PageDown
 * 一律不受影响；原生条由使用方用 CSS 隐藏，避免出现两条。
 */
export function ScrollIndicator({ targetRef }: { targetRef: RefObject<HTMLElement | null> }) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [thumb, setThumb] = useState<{ top: number; height: number } | null>(null);
  const [active, setActive] = useState(false);
  const draggingRef = useRef<{ startY: number; startTop: number } | null>(null);
  const idleTimer = useRef<number | null>(null);

  /** 按当前滚动位置重算滑块（几何全来自真实布局，没布局就整个不渲染）。 */
  const sync = useCallback(() => {
    const target = targetRef.current;
    const track = trackRef.current;
    if (!target || !track) return;
    const { scrollHeight, clientHeight, scrollTop } = target;
    const trackHeight = track.clientHeight;
    if (!trackHeight || !clientHeight || scrollHeight <= clientHeight + 1) {
      setThumb(null);
      return;
    }
    const height = Math.max(32, Math.round((clientHeight / scrollHeight) * trackHeight));
    const travel = trackHeight - height;
    const progress = scrollTop / (scrollHeight - clientHeight);
    setThumb({ top: Math.round(Math.min(Math.max(progress, 0), 1) * travel), height });
  }, [targetRef]);

  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;
    const onScroll = () => {
      sync();
      setActive(true);
      if (idleTimer.current) window.clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(() => setActive(false), 900);
    };
    target.addEventListener("scroll", onScroll, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => sync());
    observer?.observe(target);
    if (target.firstElementChild) observer?.observe(target.firstElementChild);
    sync();
    window.addEventListener("resize", sync);
    return () => {
      target.removeEventListener("scroll", onScroll);
      observer?.disconnect();
      window.removeEventListener("resize", sync);
      if (idleTimer.current) window.clearTimeout(idleTimer.current);
    };
  }, [sync, targetRef]);

  /** 把滑块位置换算成 scrollTop：拖动与点轨道共用同一套比例。 */
  const scrollToRatio = useCallback((ratio: number) => {
    const target = targetRef.current;
    if (!target) return;
    const range = target.scrollHeight - target.clientHeight;
    target.scrollTop = Math.min(Math.max(ratio, 0), 1) * range;
  }, [targetRef]);

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      const drag = draggingRef.current;
      const track = trackRef.current;
      const target = targetRef.current;
      if (!drag || !track || !target) return;
      const range = target.scrollHeight - target.clientHeight;
      const travel = track.clientHeight - (thumb?.height || 0);
      if (travel <= 0) return;
      const next = drag.startTop + ((event.clientY - drag.startY) / travel) * range;
      target.scrollTop = Math.min(Math.max(next, 0), range);
    };
    const onUp = () => { draggingRef.current = null; };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [targetRef, thumb?.height]);

  return (
    <div
      className={"scroll-indicator" + (active ? " active" : "")}
      ref={trackRef}
      aria-hidden="true"
      onPointerDown={(event) => {
        // 点在轨道上：直接跳到那个位置（滑块自己会拦住它自己的 pointerdown）。
        const track = trackRef.current;
        if (!track) return;
        const ratio = (event.clientY - track.getBoundingClientRect().top) / track.clientHeight;
        scrollToRatio(ratio);
      }}
    >
      {thumb && (
        <div
          className="scroll-indicator-thumb"
          style={{ top: thumb.top, height: thumb.height }}
          onPointerDown={(event) => {
            event.stopPropagation();
            draggingRef.current = { startY: event.clientY, startTop: targetRef.current?.scrollTop || 0 };
            setActive(true);
          }}
        />
      )}
    </div>
  );
}
