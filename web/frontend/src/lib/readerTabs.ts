/**
 * 阅读区标签页模型（E17 ④）。
 *
 * 设计：docs/LIBRARY_TREE_DESIGN.md §3.3 决定 13 —— 阅读区是标签页：双击打开、
 * 关掉最后一个自动收起、**每篇记住读到哪**。这里把规则写成纯函数，UI 只负责画；
 * 参考项目（openhanako preview-actions / OpenMAIC workspace-panes）都是这个形状。
 */

export interface ReaderTab {
  documentId: string;
  title: string;
}

export interface ReaderTabsState {
  tabs: ReaderTab[];
  activeId: string | null;
  /** document_id → 阅读位置（0–100）。关掉标签页也留着，下次打开接着读。 */
  positions: Record<string, number>;
}

export const EMPTY_TABS: ReaderTabsState = { tabs: [], activeId: null, positions: {} };

/** 打开（或激活）一个标签页：已开就只激活，不重复开。 */
export function openTab(state: ReaderTabsState, documentId: string, title = ""): ReaderTabsState {
  if (!documentId) return state;
  const existing = state.tabs.find((tab) => tab.documentId === documentId);
  const tabs = existing
    ? state.tabs.map((tab) => (tab.documentId === documentId ? { ...tab, title: tab.title || title } : tab))
    : [...state.tabs, { documentId, title }];
  return { ...state, tabs, activeId: documentId };
}

/** 关掉一个标签页：激活右邻居，没有右邻居就激活左邻居；关掉最后一个则收起。 */
export function closeTab(state: ReaderTabsState, documentId: string): ReaderTabsState {
  const index = state.tabs.findIndex((tab) => tab.documentId === documentId);
  if (index < 0) return state;
  const tabs = state.tabs.filter((tab) => tab.documentId !== documentId);
  if (state.activeId !== documentId) return { ...state, tabs };
  const next = tabs[index] ?? tabs[index - 1] ?? null;
  return { ...state, tabs, activeId: next ? next.documentId : null };
}

export function activateTab(state: ReaderTabsState, documentId: string): ReaderTabsState {
  if (!state.tabs.some((tab) => tab.documentId === documentId)) return state;
  return { ...state, activeId: documentId };
}

/** 记住一篇资料的阅读位置（越界值会被夹到 0–100 的整数）。 */
export function rememberPosition(
  state: ReaderTabsState,
  documentId: string,
  position: number,
): ReaderTabsState {
  if (!documentId || !Number.isFinite(position)) return state;
  const clamped = Math.max(0, Math.min(100, Math.round(position)));
  if (state.positions[documentId] === clamped) return state;
  return { ...state, positions: { ...state.positions, [documentId]: clamped } };
}

export function positionFor(state: ReaderTabsState, documentId: string | null): number {
  if (!documentId) return 0;
  return state.positions[documentId] ?? 0;
}

const STORAGE_PREFIX = "bobodan:reader-tabs:";

export function storageKey(libraryId: string | null | undefined): string {
  return STORAGE_PREFIX + (libraryId || "default");
}

export function serialize(state: ReaderTabsState): string {
  return JSON.stringify(state);
}

export function deserialize(raw: string | null): ReaderTabsState {
  if (!raw) return EMPTY_TABS;
  try {
    const parsed = JSON.parse(raw) as Partial<ReaderTabsState>;
    const tabs = Array.isArray(parsed.tabs)
      ? parsed.tabs
          .filter((tab): tab is ReaderTab => Boolean(tab && typeof tab.documentId === "string"))
          .map((tab) => ({ documentId: tab.documentId, title: typeof tab.title === "string" ? tab.title : "" }))
      : [];
    const positions: Record<string, number> = {};
    if (parsed.positions && typeof parsed.positions === "object") {
      for (const [key, value] of Object.entries(parsed.positions)) {
        if (typeof value === "number" && Number.isFinite(value)) {
          positions[key] = Math.max(0, Math.min(100, Math.round(value)));
        }
      }
    }
    const activeId = tabs.some((tab) => tab.documentId === parsed.activeId) ? (parsed.activeId as string) : null;
    return { tabs, activeId, positions };
  } catch {
    return EMPTY_TABS;
  }
}
/**
 * 阅读位置 → 滚动像素（E17 ④）。
 *
 * 存的是百分比，恢复时要夹到真实可滚动范围里：容器还没量出来（高度 0）时
 * 返回 0，绝不写 NaN 或负数进 scrollTop。
 */
export function scrollTargetFor(position: number, scrollHeight: number, clientHeight: number): number {
  if (!Number.isFinite(position) || position <= 0) return 0;
  const available = scrollHeight - clientHeight;
  if (!Number.isFinite(available) || available <= 0) return 0;
  const clamped = Math.max(0, Math.min(100, position));
  return Math.round((clamped / 100) * available);
}
