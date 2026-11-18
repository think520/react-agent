import { ArrowRight, BookOpen, BookOpenCheck, Brain, FilePlus2, FolderOpen } from "lucide-react";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import { BobodanProcess } from "../../pages/chat/chatPrimitives";
import { BrandIllustration, ErrorNotice } from "../common";
import type { ActivePracticeSummary, DataLoadStatus, DocumentSummary, ReviewQueue } from "../../types";
import { selectWelcomePrimaryAction, type WelcomePrimaryAction } from "../../lib/welcomeAction";

/** Chat 的空态（W-F7）：欢迎语 + 快捷入口。 */
export function ChatWelcome({ libraryName, error, composer, wikiPlanLoading, status, brandState, documentImporting, documents, documentsUnavailable, review, reviewStatus, activePractices, activePracticeStatus, onApplyPrompt, onImport, onOpenPractice, onOpenExperience, onPrimaryAction }: {
  libraryName: string;
  error: string;
  composer: React.ReactNode;
  wikiPlanLoading: boolean;
  status: string | null;
  brandState: ProcessBrandState;
  documentImporting: boolean;
  documents: DocumentSummary[];
  documentsUnavailable?: boolean;
  review: ReviewQueue | null;
  reviewStatus: DataLoadStatus;
  activePractices: ActivePracticeSummary[];
  activePracticeStatus: DataLoadStatus;
  onApplyPrompt: (prompt: string) => void;
  onImport: () => void;
  onOpenPractice: () => void;
  onOpenExperience: () => void;
  onPrimaryAction: (action: WelcomePrimaryAction) => void;
}) {
  const primaryAction = selectWelcomePrimaryAction({ documents, documentsUnavailable, review, reviewStatus, activePractices, activePracticeStatus });
  return <div className="welcome-view">
    <div className="welcome-identity">
      <BrandIllustration state="ready" size={112} alt="Bobodan" />
      <h2>今天想学点什么？</h2>
      <div className="welcome-context">
        <span><FolderOpen size={14} />{libraryName || "尚未选择资料库"}</span>
        <span><Brain size={14} />记忆随学习沉淀</span>
      </div>
    </div>
    {error && <ErrorNotice message={error} />}
    {composer}
    {wikiPlanLoading && <BobodanProcess state={brandState} detail={status || "正在生成 Wiki 计划"} />}
    <button className="primary-button welcome-primary-action" type="button" disabled={primaryAction.kind === "loading"} onClick={() => onPrimaryAction(primaryAction)}>
      {primaryAction.label}<ArrowRight size={16} />
    </button>
    <div className="starter-actions">
      <button onClick={() => onApplyPrompt("根据我的资料，帮我梳理今天最值得学习的三个知识点。")}>梳理学习重点</button>
      <button onClick={() => onApplyPrompt("请先用直觉解释，再给出严谨推导。")}>先讲直觉，再补证明</button>
      <button disabled={documentImporting} onClick={onImport}><FilePlus2 size={15} />{documentImporting ? "正在导入" : "导入资料"}</button>
      <button onClick={onOpenPractice}><BookOpen size={15} />开始练习</button>
      <button onClick={onOpenExperience}><BookOpenCheck size={15} />体验示例课</button>
    </div>
  </div>;
}
