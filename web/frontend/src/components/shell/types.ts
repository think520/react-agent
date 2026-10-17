/**
 * AppShell 与页面共享的类型（2026-10-17 M2 拆分：从 AppShell.tsx 抽出，纯类型、零行为）。
 */
import type { ImportBatchResult } from "../../lib/api";
import type { ImportRunProgress } from "../../hooks/useImportRun";
import type { LibrarySetupMode } from "../LibrarySetupDialog";
import type {
  Attribution,
  ChatSessionSummary,
  DocumentSummary,
  KnowledgeContext,
  LibrarySummary,
  SettingsSummary,
} from "../../types";

export interface LibrarySetupOptions {
  initialMode?: LibrarySetupMode;
  importCount?: number;
}

export interface AppOutletContext {
  sessions: ChatSessionSummary[];
  settings: SettingsSummary | null;
  refreshSettings: () => Promise<SettingsSummary | null>;
  refreshSessions: () => Promise<void>;
  openContext: () => void;
  conceptDetailId: string | null;
  openConceptDetail: (conceptId: string) => void;
  closeConceptDetail: () => void;
  showKnowledgeContext: (context: KnowledgeContext) => void;
  receiveKnowledgeContext: (context: KnowledgeContext) => void;
  clearKnowledgeContext: () => void;
  showSourceContext: (attribution: Attribution) => void;
  documents: DocumentSummary[];
  selectedDocumentIds: string[];
  selectedDocuments: DocumentSummary[];
  toggleDocumentScope: (documentId: string) => void;
  setDocumentScope: (documentIds: string[]) => void;
  clearDocumentScope: () => void;
  libraries: LibrarySummary[];
  activeLibrary: LibrarySummary | null;
  openLibrarySetup: (options?: LibrarySetupOptions) => void;
  createLibrary: (name: string, parentPath: string) => Promise<LibrarySummary>;
  switchLibrary: (libraryId: string) => Promise<void>;
  startDocumentImport: () => void;
  documentImporting: boolean;
  documentImportNotice: string;
  documentImportError: string;
  documentImportDuplicateCount: number;
  importDuplicatesAsCopies: () => void;
  documentImportVersion: number;
  /** E8：本次导入的**逐文件**结果（失败清单 UI 用），null 表示还没有结果。 */
  documentImportResults: ImportBatchResult[] | null;
  /** W1 E1：这次导入失败的结构化错误码（界面据此给"下一步"）。 */
  documentImportErrorCode: string;
  /** E8：运行中的进度（null = 没有正在跑的导入）。 */
  documentImportProgress: ImportRunProgress | null;
  /** E8：取消正在跑的导入（协作式：文件边界生效，已收下的保持收下）。 */
  cancelDocumentImport: () => void;
  /** E8：拖拽进来的文件走同一条导入通道（没有资料库时先引导新建并记住文件）。 */
  importDroppedFiles: (files: File[]) => void;
  /** 还留着原文件对象时才为 true —— 不给假的"重试"按钮。 */
  documentImportCanRetry: boolean;
  retryFailedImports: () => void;
  dismissImportReport: () => void;
  libraryReady: boolean;
}
