/**
 * Chat 页的 UI 状态（2026-10-17 M2 store-lift 第 1 步）。
 *
 * 借鉴 openhanako 的 store 约定：状态在 zustand，读写由模块级 setter 完成 ——
 * 组件只订阅需要的字段；将来的 `chatActions` 直接用 `useChatUiStore.getState()/setState()`，
 * 不再需要往 hook 里传 30 多个依赖（这正是 M2 两次拆分失败的根因）。
 */
import { create } from "zustand";

import type { ChatReference } from "../types";

const emptySelections: Record<string, string[]> = {};

export interface ChatUiState {
  sending: boolean;
  practiceStarting: string;
  inlineError: string;
  paletteIndex: number;
  paletteDismissed: boolean;
  wikiPlanLoading: boolean;
  references: ChatReference[];
  webOnce: boolean;
  webSelections: Record<string, string[]>;
  mentionTab: "document" | "session";
  mentionIndex: number;
  mentionDismissed: boolean;
}

const initialState: ChatUiState = {
  sending: false,
  practiceStarting: "",
  inlineError: "",
  paletteIndex: 0,
  paletteDismissed: false,
  wikiPlanLoading: false,
  references: [],
  webOnce: false,
  webSelections: emptySelections,
  mentionTab: "document",
  mentionIndex: 0,
  mentionDismissed: false,
};

export const useChatUiStore = create<ChatUiState>(() => ({ ...initialState }));

/** 重置（会话切换 / 测试用）：只重置 UI 字段，不清其他 store。 */
export function resetChatUiState() {
  useChatUiStore.setState({ ...initialState });
}

type Updater<T> = T | ((current: T) => T);

function apply<T>(value: Updater<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

export const setSending = (value: Updater<boolean>) => useChatUiStore.setState((state) => ({ sending: apply(value, state.sending) }));
export const setPracticeStarting = (value: Updater<string>) => useChatUiStore.setState((state) => ({ practiceStarting: apply(value, state.practiceStarting) }));
export const setInlineError = (value: Updater<string>) => useChatUiStore.setState((state) => ({ inlineError: apply(value, state.inlineError) }));
export const setPaletteIndex = (value: Updater<number>) => useChatUiStore.setState((state) => ({ paletteIndex: apply(value, state.paletteIndex) }));
export const setPaletteDismissed = (value: Updater<boolean>) => useChatUiStore.setState((state) => ({ paletteDismissed: apply(value, state.paletteDismissed) }));
export const setWikiPlanLoading = (value: Updater<boolean>) => useChatUiStore.setState((state) => ({ wikiPlanLoading: apply(value, state.wikiPlanLoading) }));
export const setReferences = (value: Updater<ChatReference[]>) => useChatUiStore.setState((state) => ({ references: apply(value, state.references) }));
export const setWebOnce = (value: Updater<boolean>) => useChatUiStore.setState((state) => ({ webOnce: apply(value, state.webOnce) }));
export const setWebSelections = (value: Updater<Record<string, string[]>>) => useChatUiStore.setState((state) => ({ webSelections: apply(value, state.webSelections) }));
export const setMentionTab = (value: Updater<"document" | "session">) => useChatUiStore.setState((state) => ({ mentionTab: apply(value, state.mentionTab) }));
export const setMentionIndex = (value: Updater<number>) => useChatUiStore.setState((state) => ({ mentionIndex: apply(value, state.mentionIndex) }));
export const setMentionDismissed = (value: Updater<boolean>) => useChatUiStore.setState((state) => ({ mentionDismissed: apply(value, state.mentionDismissed) }));
