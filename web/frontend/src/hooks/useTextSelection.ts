import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export interface SelectionAnchor {
  x: number;
  y: number;
  placement: "above" | "below";
}

export interface TextSelectionState {
  quote: string;
  range: Range | null;
  anchor: SelectionAnchor | null;
}

const EMPTY_SELECTION: TextSelectionState = {
  quote: "",
  range: null,
  anchor: null,
};

function anchorFromRange(range: Range): SelectionAnchor | null {
  const rect = typeof range.getBoundingClientRect === "function"
    ? range.getBoundingClientRect()
    : elementForNode(range.startContainer)?.getBoundingClientRect();
  if (!rect || (rect.width === 0 && rect.height === 0)) return null;
  const placement = rect.top < 76 ? "below" : "above";
  return {
    x: rect.left + rect.width / 2,
    y: placement === "above" ? rect.top - 10 : rect.bottom + 10,
    placement,
  };
}

function elementForNode(node: Node | null): Element | null {
  if (!node) return null;
  return node instanceof Element ? node : node.parentElement;
}

/**
 * Tracks browser text selection inside `containerRef` and computes viewport-aware
 * coordinates for a floating SelectionActionBar without breaking native copy/paste.
 */
export function useTextSelection(
  containerRef: RefObject<HTMLElement | null>,
  options?: {
    enabled?: boolean;
    matchSelector?: string;
    maxLength?: number;
  },
) {
  const enabled = options?.enabled ?? true;
  const matchSelector = options?.matchSelector;
  const maxLength = options?.maxLength ?? 1200;

  const [state, setState] = useState<TextSelectionState>(EMPTY_SELECTION);
  const rangeRef = useRef<Range | null>(null);

  const clearSelection = useCallback(() => {
    rangeRef.current = null;
    setState(EMPTY_SELECTION);
    window.getSelection()?.removeAllRanges();
  }, []);

  const captureNow = useCallback(() => {
    if (!enabled) return;
    const container = containerRef.current;
    const sel = window.getSelection();
    if (!container || !sel || sel.rangeCount === 0 || sel.isCollapsed) {
      rangeRef.current = null;
      setState(EMPTY_SELECTION);
      return;
    }
    const text = sel.toString().trim();
    if (text.length < 2) {
      rangeRef.current = null;
      setState(EMPTY_SELECTION);
      return;
    }
    const range = sel.getRangeAt(0);
    const startEl = elementForNode(range.startContainer);
    const endEl = elementForNode(range.endContainer);
    if (!startEl || !endEl || !container.contains(startEl) || !container.contains(endEl)) {
      return;
    }
    if (startEl.closest("input, textarea, button, [data-selection-toolbar]")) {
      return;
    }
    if (matchSelector && (!startEl.closest(matchSelector) || !endEl.closest(matchSelector))) {
      return;
    }
    const cloned = range.cloneRange();
    rangeRef.current = cloned;
    setState({
      quote: text.slice(0, maxLength),
      range: cloned,
      anchor: anchorFromRange(cloned),
    });
  }, [containerRef, enabled, matchSelector, maxLength]);

  useEffect(() => {
    if (!enabled) {
      rangeRef.current = null;
    }
  }, [enabled]);

  useEffect(() => {
    const reposition = () => {
      const range = rangeRef.current;
      if (!range) return;
      const anchor = anchorFromRange(range);
      if (anchor) {
        setState((curr) => (curr.quote ? { ...curr, anchor } : curr));
      }
    };
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Element | null;
      if (target?.closest("[data-selection-toolbar]")) return;
      if (rangeRef.current) {
        rangeRef.current = null;
        setState(EMPTY_SELECTION);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && rangeRef.current) {
        rangeRef.current = null;
        setState(EMPTY_SELECTION);
        window.getSelection()?.removeAllRanges();
      }
    };
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return { selection: enabled ? state : EMPTY_SELECTION, clearSelection, captureNow };
}
