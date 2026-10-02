import { useCallback, useEffect, useRef, useState } from "react";

/**
 * W1 E16：「高亮几秒」的计时。
 *
 * 确认新概念之后，界面上要把它**短暂**标出来再自己消失 ——
 * 永久高亮等于没有重点，而两次确认各自的定时器互抢又会提前清掉后一次。
 * 所以：只留一个定时器，新的高亮会重新计时；卸载时清掉。
 */
export function useTemporaryHighlight(durationMs = 4000) {
  const [highlighted, setHighlighted] = useState<string[]>([]);
  const timer = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const highlight = useCallback((ids: string[]) => {
    clearTimer();
    const unique = [...new Set((ids || []).filter((id) => Boolean(id)))];
    setHighlighted(unique);
    if (!unique.length) return;
    timer.current = window.setTimeout(() => {
      timer.current = null;
      setHighlighted([]);
    }, Math.max(1, durationMs));
  }, [clearTimer, durationMs]);

  useEffect(() => clearTimer, [clearTimer]);

  return { highlighted, highlight };
}
