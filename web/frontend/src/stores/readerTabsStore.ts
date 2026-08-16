import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Reader multi-document tab state (TASKS_LIBRARY_REWORK task 2.3.1).
 * Tracks which documents are open as tabs plus a per-tab scroll position so
 * switching does not lose reading progress.
 */

interface ReaderTabsState {
  openIds: string[];
  scrolls: Record<string, number>;
  open: (id: string) => void;
  close: (id: string) => void;
  setScroll: (id: string, top: number) => void;
  scrollFor: (id: string) => number;
}

export const useReaderTabsStore = create<ReaderTabsState>()(
  persist(
    (set, get) => ({
      openIds: [],
      scrolls: {},
      open: (id) => set((state) => ({
        openIds: state.openIds.includes(id) ? state.openIds : [...state.openIds, id].slice(-12),
      })),
      close: (id) => set((state) => {
        const openIds = state.openIds.filter((item) => item !== id);
        const scrolls = { ...state.scrolls };
        delete scrolls[id];
        return { openIds, scrolls };
      }),
      setScroll: (id, top) => set((state) => ({ scrolls: { ...state.scrolls, [id]: top } })),
      scrollFor: (id) => get().scrolls[id] || 0,
    }),
    { name: "bobodan:reader-tabs" },
  ),
);
