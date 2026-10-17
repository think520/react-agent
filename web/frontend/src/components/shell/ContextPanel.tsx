/**
 * 右侧「学习上下文」面板（2026-10-17 M2 拆分：从 AppShell 的 JSX 抽出，行为不变）。
 */
import { X } from "lucide-react";

import { useUiStore } from "../../stores/uiStore";
import { IconButton } from "../common";
import { ConceptSidebar } from "../ConceptSidebar";
import { LearningContext } from "./LearningContext";
import type { Attribution, DocumentSummary, KnowledgeContext, ReviewQueue } from "../../types";

export interface ContextPanelView {
  contextOpen: boolean;
  conceptDetailId: string | null;
  desktop: boolean;
  rightAutoCollapsed: boolean;
  setPreview: (side: "left" | "right", open: boolean) => void;
  setContextOpen: (open: boolean) => void;
  setConceptDetailId: (conceptId: string | null) => void;
  openConceptDetail: (conceptId: string) => void;
  documents: DocumentSummary[];
  review: ReviewQueue | null;
  selectedDocumentIds: string[];
  toggleDocumentScope: (documentId: string) => void;
  knowledgeContext: KnowledgeContext | null;
  sourceContext: Attribution | null;
  openMapForConcept: (conceptId: string) => void;
}

export function ContextPanel({ view }: { view: ContextPanelView }) {
  const {
    contextOpen, conceptDetailId, desktop, rightAutoCollapsed,
    setPreview, setContextOpen, setConceptDetailId, openConceptDetail,
    documents, review, selectedDocumentIds, toggleDocumentScope,
    knowledgeContext, sourceContext, openMapForConcept,
  } = view;
  return (
      <aside className={`context-panel ${contextOpen ? "open" : ""}`} aria-label="学习上下文">
        <div className="context-header">
          <strong>{conceptDetailId ? "概念详情" : "学习书桌"}</strong>
          <IconButton
            label={conceptDetailId ? "返回学习书桌" : "关闭上下文"}
            onClick={() => conceptDetailId
              ? setConceptDetailId(null)
              : desktop && rightAutoCollapsed
                ? setPreview("right", false)
                : setContextOpen(false)}
          ><X /></IconButton>
        </div>
        {conceptDetailId ? (
          <ConceptSidebar
            embedded
            conceptId={conceptDetailId}
            onClose={() => setConceptDetailId(null)}
            onNavigateConcept={openConceptDetail}
            onConceptUpdated={() => useUiStore.getState().bumpGraphRevision()}
          />
        ) : (
          <LearningContext
            documents={documents}
            review={review}
            selectedDocumentIds={selectedDocumentIds}
            toggleDocumentScope={toggleDocumentScope}
            knowledgeContext={knowledgeContext}
            sourceContext={sourceContext}
            onOpenConcept={openConceptDetail}
            onOpenMap={openMapForConcept}
          />
        )}
      </aside>
  );
}
