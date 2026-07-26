import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * One-shot cross-page hand-offs (chat → practice, library → chat).
 *
 * Replaces the previous localStorage message bus (`bobodan:practice-topic`,
 * `bobodan:practice-web-research`, `bobodan:wiki-scope`, `bobodan:draft:new`
 * as a cross-page channel). Values persist across refreshes and are cleared
 * by the consuming page ("consume" semantics).
 */

export interface WikiScopeHandoff {
  scopeMode?: "uncovered" | "smart_library" | "selected_only" | "course";
  documentIds?: string[];
  wikiDocumentIds?: string[];
  course?: string | null;
  topic?: string;
}

interface HandoffState {
  practiceTopic: string | null;
  practiceWebResearchId: string | null;
  wikiScope: WikiScopeHandoff | null;
  chatDraft: string | null;
  setPracticeTopic: (topic: string) => void;
  setPracticeWebResearch: (researchId: string | null) => void;
  clearPracticeHandoff: () => void;
  setWikiScope: (scope: WikiScopeHandoff) => void;
  clearWikiScope: () => void;
  setChatDraft: (draft: string) => void;
  consumeChatDraft: () => string | null;
}

function readLegacy<T>(key: string, parse: (raw: string) => T): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    localStorage.removeItem(key);
    return parse(raw);
  } catch {
    return null;
  }
}

export const useHandoffStore = create<HandoffState>()(
  persist(
    (set, get) => ({
      practiceTopic: readLegacy("bobodan:practice-topic", (raw) => raw),
      practiceWebResearchId: readLegacy("bobodan:practice-web-research", (raw) => raw),
      wikiScope: readLegacy("bobodan:wiki-scope", (raw) => JSON.parse(raw) as WikiScopeHandoff),
      chatDraft: null,
      setPracticeTopic: (topic) => set({ practiceTopic: topic }),
      setPracticeWebResearch: (researchId) => set({ practiceWebResearchId: researchId }),
      clearPracticeHandoff: () => set({ practiceTopic: null, practiceWebResearchId: null }),
      setWikiScope: (scope) => set({ wikiScope: scope }),
      clearWikiScope: () => set({ wikiScope: null }),
      setChatDraft: (draft) => set({ chatDraft: draft }),
      consumeChatDraft: () => {
        const draft = get().chatDraft;
        if (draft !== null) set({ chatDraft: null });
        return draft;
      },
    }),
    {
      name: "bobodan:handoff",
      partialize: (state) => ({
        practiceTopic: state.practiceTopic,
        practiceWebResearchId: state.practiceWebResearchId,
        wikiScope: state.wikiScope,
        chatDraft: state.chatDraft,
      }),
    },
  ),
);
