import { useRef } from "react";

/**
 * CJK IME 合成守卫（M4，2026-10-17）。
 * compositionstart → compositionend 之间，Enter / Esc / 方向键快捷键都必须忽略；
 * 另外把 keyCode 229 也算作合成中（部分 IME 在提交候选词的 Enter 上只给 229）。
 */
export function useCompositionGuard() {
  const composingRef = useRef(false);
  return {
    compositionProps: {
      onCompositionStart: () => { composingRef.current = true; },
      onCompositionEnd: () => { composingRef.current = false; },
    },
    isComposing: (event?: { keyCode?: number }) => composingRef.current || event?.keyCode === 229,
  };
}

export function isImeKeyEvent(event: { nativeEvent?: { isComposing?: boolean }; keyCode?: number }): boolean {
  return Boolean(event.nativeEvent?.isComposing) || event.keyCode === 229;
}
