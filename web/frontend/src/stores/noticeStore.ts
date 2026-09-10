import { create } from "zustand";

export type NoticeTone = "error" | "info" | "success";

export interface AppNotice {
  id: string;
  message: string;
  code?: string;
  tone: NoticeTone;
}

interface NoticeState {
  notices: AppNotice[];
  pushNotice: (notice: { message: string; code?: string; tone?: NoticeTone }) => void;
  dismissNotice: (id: string) => void;
  clearNotices: () => void;
}

/** Keeps the surface readable: newest last, oldest dropped past the cap. */
export const MAX_NOTICES = 3;

let noticeSeq = 0;

/**
 * App-level notice surface (E1). Operation failures are triggered from cards,
 * dialogs and side panels whose local error text is easy to miss, so they are
 * reported here and rendered above every page by NoticeCenter.
 *
 * Ephemeral UI state only: nothing here is persisted and no business state is
 * duplicated (the server remains the source of truth for outcomes).
 */
export const useNoticeStore = create<NoticeState>()((set) => ({
  notices: [],
  pushNotice: ({ message, code, tone = "error" }) => {
    const text = message.trim();
    if (!text) return;
    set((state) => {
      // An identical message is already on screen; do not stack duplicates.
      if (state.notices.some((notice) => notice.message === text)) return state;
      const next = [...state.notices, { id: `notice-${++noticeSeq}`, message: text, code, tone }];
      return { notices: next.slice(-MAX_NOTICES) };
    });
  },
  dismissNotice: (id) => set((state) => ({ notices: state.notices.filter((notice) => notice.id !== id) })),
  clearNotices: () => set({ notices: [] }),
}));

/** Imperative helper for event handlers (outside the React render path). */
export function notifyError(message: string, code?: string) {
  useNoticeStore.getState().pushNotice({ message, code, tone: "error" });
}

/** Non-failure notice, e.g. an explained degradation (E3). */
export function notifyInfo(message: string) {
  useNoticeStore.getState().pushNotice({ message, tone: "info" });
}
