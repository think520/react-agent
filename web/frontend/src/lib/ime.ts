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

/**
 * 全局单键快捷键（`[`、`]`、`+`、`-`、Shift+J …）该不该忽略这次按键。
 *
 * 焦点在可输入的地方、或输入法正在合成时，按键属于用户在打的字，不是命令 ——
 * 否则在阅读器里搜「a[1]」会关掉目录，在知识地图搜索框里打「-」会改聚焦层级（2026-11-11 审查）。
 * Escape 不受这条限制，由调用方自己决定。
 */
export function shouldIgnoreShortcut(event: KeyboardEvent): boolean {
  if (event.isComposing || event.keyCode === 229) return true;
  if (event.ctrlKey || event.metaKey || event.altKey) return true;
  const target = (event.target instanceof Element ? event.target : document.activeElement) as HTMLElement | null;
  if (!target) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (target as HTMLInputElement).type;
    return !["checkbox", "radio", "button", "submit", "reset", "range", "color", "file"].includes(type);
  }
  return Boolean(target.closest("[role='dialog'], [contenteditable='true'], .cm-editor"));
}
