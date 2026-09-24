import { useCallback, useEffect, useMemo, useState } from "react";

import {
  EMPTY_TABS,
  activateTab,
  closeTab,
  deserialize,
  openTab,
  positionFor,
  rememberPosition,
  serialize,
  storageKey,
  type ReaderTabsState,
} from "../lib/readerTabs";

/**
 * 阅读区标签页（E17 ④）：状态按资料库存在 localStorage。
 *
 * 每篇的阅读位置也一起存 —— 关掉标签页再打开，接着上次的位置读。
 */
export function useReaderTabs(libraryId: string | null | undefined) {
  const key = useMemo(() => storageKey(libraryId), [libraryId]);
  const [state, setState] = useState<ReaderTabsState>(() => {
    try {
      return deserialize(localStorage.getItem(key));
    } catch {
      return EMPTY_TABS;
    }
  });

  // 切换资料库时换成那个库的标签页集合。
  useEffect(() => {
    try {
      setState(deserialize(localStorage.getItem(key)));
    } catch {
      setState(EMPTY_TABS);
    }
  }, [key]);

  useEffect(() => {
    try {
      localStorage.setItem(key, serialize(state));
    } catch {
      // 存不下不影响阅读，只是下次不记得标签页。
    }
  }, [key, state]);

  const open = useCallback((documentId: string, title = "") => {
    setState((current) => openTab(current, documentId, title));
  }, []);
  const activate = useCallback((documentId: string) => {
    setState((current) => activateTab(current, documentId));
  }, []);
  const close = useCallback((documentId: string) => {
    setState((current) => closeTab(current, documentId));
  }, []);
  const remember = useCallback((documentId: string, position: number) => {
    setState((current) => rememberPosition(current, documentId, position));
  }, []);
  const positionOf = useCallback(
    (documentId: string | null) => positionFor(state, documentId),
    [state],
  );

  return { ...state, open, activate, close, remember, positionOf };
}
