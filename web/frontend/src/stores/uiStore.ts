import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Attribution, KnowledgeContext } from "../types";

export interface LearningProfile {
  displayName?: string;
  learningGoal?: string;
  memoryEnabled?: boolean;
  webEnabled?: boolean;
}

/** Mirrors LibrarySetupOptions in AppShell (kept structural to avoid a component import). */
export interface LibrarySetupDialogState {
  initialMode?: "create" | "open" | "migrate";
  importCount?: number;
}

interface UiState {
  // Persisted preferences (previously scattered localStorage keys).
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;
  documentScope: string[];
  strictDocumentScope: boolean;
  newSessionProvider: string;
  learningProfile: LearningProfile;
  // Ephemeral UI state (mobile overlays / hover previews / dialogs / context panel).
  mobileSidebarOpen: boolean;
  mobileContextOpen: boolean;
  leftPreview: boolean;
  rightPreview: boolean;
  onboardingOpen: boolean;
  librarySetup: LibrarySetupDialogState | null;
  conceptDetailId: string | null;
  graphRevision: number;
  knowledgeContext: KnowledgeContext | null;
  sourceContext: Attribution | null;
  setPanelOpen: (side: "left" | "right", open: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  setMobileContextOpen: (open: boolean) => void;
  setPreview: (side: "left" | "right", open: boolean) => void;
  togglePreview: (side: "left" | "right") => void;
  setOnboardingOpen: (open: boolean) => void;
  openLibrarySetup: (options?: LibrarySetupDialogState) => void;
  closeLibrarySetup: () => void;
  setConceptDetailId: (conceptId: string | null) => void;
  bumpGraphRevision: () => void;
  setKnowledgeContext: (context: KnowledgeContext | null) => void;
  setSourceContext: (attribution: Attribution | null) => void;
  setDocumentScope: (documentIds: string[]) => void;
  toggleDocumentScope: (documentId: string) => void;
  pruneDocumentScope: (validIds: string[]) => void;
  clearDocumentScope: () => void;
  setStrictDocumentScope: (strict: boolean) => void;
  toggleStrictDocumentScope: () => void;
  setNewSessionProvider: (provider: string) => void;
  setLearningProfile: (profile: LearningProfile) => void;
}

function readLegacyJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      // Legacy keys are only used as initial defaults for users migrating from
      // the pre-store version; the persisted "bobodan:ui" entry wins afterwards.
      leftSidebarOpen: localStorage.getItem("bobodan:sidebar:left") !== "false",
      rightSidebarOpen: localStorage.getItem("bobodan:sidebar:right") !== "false",
      documentScope: readLegacyJson<string[]>("bobodan:scope:documents", []),
      strictDocumentScope: localStorage.getItem("bobodan:scope:strict") === "true",
      newSessionProvider: localStorage.getItem("bobodan:provider:new") || "",
      learningProfile: readLegacyJson<LearningProfile>("bobodan:learning-profile", {}),
      mobileSidebarOpen: false,
      mobileContextOpen: false,
      leftPreview: false,
      rightPreview: false,
      onboardingOpen: false,
      librarySetup: null,
      conceptDetailId: null,
      graphRevision: 0,
      knowledgeContext: null,
      sourceContext: null,
      setPanelOpen: (side, open) => set(side === "left" ? { leftSidebarOpen: open } : { rightSidebarOpen: open }),
      setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
      setMobileContextOpen: (open) => set({ mobileContextOpen: open }),
      setPreview: (side, open) => set(side === "left" ? { leftPreview: open } : { rightPreview: open }),
      togglePreview: (side) => set((state) => side === "left"
        ? { leftPreview: !state.leftPreview }
        : { rightPreview: !state.rightPreview }),
      setOnboardingOpen: (open) => set({ onboardingOpen: open }),
      openLibrarySetup: (options = {}) => set({ librarySetup: options }),
      closeLibrarySetup: () => set({ librarySetup: null }),
      setConceptDetailId: (conceptId) => set({ conceptDetailId: conceptId }),
      bumpGraphRevision: () => set((state) => ({ graphRevision: state.graphRevision + 1 })),
      setKnowledgeContext: (context) => set({ knowledgeContext: context }),
      setSourceContext: (attribution) => set({ sourceContext: attribution }),
      setDocumentScope: (documentIds) => set({ documentScope: Array.from(new Set(documentIds)) }),
      toggleDocumentScope: (documentId) => set((state) => ({
        documentScope: state.documentScope.includes(documentId)
          ? state.documentScope.filter((id) => id !== documentId)
          : [...state.documentScope, documentId],
      })),
      pruneDocumentScope: (validIds) => set((state) => {
        const valid = new Set(validIds);
        const pruned = state.documentScope.filter((id) => valid.has(id));
        return pruned.length === state.documentScope.length ? {} : { documentScope: pruned };
      }),
      clearDocumentScope: () => set({ documentScope: [] }),
      setStrictDocumentScope: (strict) => set({ strictDocumentScope: strict }),
      toggleStrictDocumentScope: () => set((state) => ({ strictDocumentScope: !state.strictDocumentScope })),
      setNewSessionProvider: (provider) => set({ newSessionProvider: provider }),
      setLearningProfile: (profile) => set({ learningProfile: profile }),
    }),
    {
      name: "bobodan:ui",
      partialize: (state) => ({
        leftSidebarOpen: state.leftSidebarOpen,
        rightSidebarOpen: state.rightSidebarOpen,
        documentScope: state.documentScope,
        strictDocumentScope: state.strictDocumentScope,
        newSessionProvider: state.newSessionProvider,
        learningProfile: state.learningProfile,
      }),
    },
  ),
);
