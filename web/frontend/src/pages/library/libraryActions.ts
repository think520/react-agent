/**
 * LibraryPage 的材料族处理器（2026-10-17 M2 store-lift：从 LibraryPage.tsx 整块搬出，行为不变）。
 * 选择 / 概念提取 / 文件夹 / 归档 / 整理建议 / 文件夹同步 —— 依赖折叠为一个 ctx。
 */
import { ApiError, api } from "../../lib/api";
import type { KnowledgeSyncSummary, OrganizationProposal } from "../../lib/api";
import { matchesWikiView } from "./wikiView";
import type { WikiViewType } from "./wikiView";
import {} from "../../lib/errors";
import {} from "../../stores/noticeStore";
import type { Dispatch, SetStateAction } from "react";
import type { SetURLSearchParams } from "react-router-dom";
import type { NavigateFunction } from "react-router-dom";
import type {
  DocumentExtractionStatus, DocumentSection, DocumentSummary, LibrarySummary, WikiPlan,
} from "../../types";

export interface LibraryMaterialContext {
  openTab: (documentId: string) => void;
  setSelectedId: (next: string | null | ((current: string | null) => string | null)) => void;
  setSearchParams: SetURLSearchParams;
  collection: "material" | "wiki";
  wikiView: WikiViewType;
  setCollection: (next: "material" | "wiki") => void;
  setWikiView: (next: WikiViewType) => void;
  documents: DocumentSummary[];
  selected: DocumentSummary | undefined;
  sections: DocumentSection[];
  setSections: (next: DocumentSection[]) => void;
  extractionStatuses: Record<string, DocumentExtractionStatus>;
  setExtractionStatuses: (next: Record<string, DocumentExtractionStatus> | ((current: Record<string, DocumentExtractionStatus>) => Record<string, DocumentExtractionStatus>)) => void;
  startingExtractionId: string | null;
  setStartingExtractionId: (next: string | null) => void;
  selectedFolder: string;
  setSelectedFolder: (next: string) => void;
  syncingFolder: boolean;
  setSyncingFolder: (next: boolean) => void;
  setSyncSummary: Dispatch<SetStateAction<KnowledgeSyncSummary | null>>;
  documentQuery: string;
  setHits: Dispatch<SetStateAction<Array<{ chunk_id: string; document_id: string; collection?: string; title?: string; source?: string; text?: string }>>>;
  activeLibrary: LibrarySummary | null;
  navigate: NavigateFunction;
  loadTree: () => Promise<void>;
  loadDocuments: () => Promise<void>;
  loadArchive: () => Promise<void>;
  loadOrganizeState: () => Promise<void>;
  setDocumentScope: (ids: string[]) => void;
  setError: (next: string) => void;
  setNotice: (next: string) => void;
  setOrganizeBusy: (next: boolean) => void;
  setOrganizeProposals: Dispatch<SetStateAction<OrganizationProposal[] | null>>;
  setOrganizeSource: (next: string) => void;
  setOrganizeDegraded: (next: string) => void;
  setWikiPlan: Dispatch<SetStateAction<WikiPlan | null>>;
  setWikiPlanOpen: (next: boolean) => void;
  confirm: (options: { title: string; detail: string; confirmLabel: string; danger?: boolean }) => Promise<boolean>;
}

export function createLibraryMaterialActions(ctx: LibraryMaterialContext) {
  const {
    openTab,
    setSelectedId,
    setSearchParams,
    collection,
    wikiView,
    setCollection,
    setWikiView,
    documents,
    selected,
    sections,
    setSections,
    extractionStatuses,
    setExtractionStatuses,
    startingExtractionId,
    setStartingExtractionId,
    selectedFolder,
    setSelectedFolder,
    syncingFolder,
    setSyncingFolder,
    setSyncSummary,
    activeLibrary,
    navigate,
    loadTree,
    loadDocuments,
    loadArchive,
    loadOrganizeState,
    setDocumentScope,
    setError,
    setNotice,
    setOrganizeBusy,
    setOrganizeProposals,
    setOrganizeSource,
    setOrganizeDegraded,
    setWikiPlan,
    setWikiPlanOpen,
    confirm,
  } = ctx;

  function selectDocument(documentId: string) {
    // ④：打开阅读区的一个标签页（已开只激活）。
    openTab(documentId);
    setSelectedId(documentId);
    setSearchParams({ collection, document: documentId, ...(collection === "wiki" ? { wikiView } : {}) }, { replace: true });
  }

  function selectCollection(next: "material" | "wiki") {
    setCollection(next);
    setSelectedId(null);
    setSections([]);
    setWikiPlan(null);
    setWikiPlanOpen(false);
    if (next === "wiki") setWikiView("knowledge");
    setSearchParams({ collection: next }, { replace: true });
  }

  function selectWikiView(next: WikiViewType) {
    setWikiView(next);
    const first = documents.find((document) => matchesWikiView(document, next));
    setSelectedId(first?.document_id || null);
    setSections([]);
    setSearchParams({ collection: "wiki", wikiView: next, ...(first ? { document: first.document_id } : {}) }, { replace: true });
  }

  function askAboutDocument() {
    if (!selected) return;
    setDocumentScope([selected.document_id]);
    navigate("/chat");
  }

  function documentContentVersion(doc: DocumentSummary) {
    return doc.content_hash || [doc.updated_at || "", doc.chunk_count || 0].join(":");
  }

  function openExtractionReview(doc: DocumentSummary, status: DocumentExtractionStatus) {
    navigate("/knowledge-map", {
      state: {
        extractionRunId: status.run.run_id,
        extractingDocumentId: doc.document_id,
        extractingDocumentTitle: doc.title || doc.source,
      },
    });
  }

  async function extractAndReview(doc: DocumentSummary, force = false) {
    if (startingExtractionId || !sections.length) return;
    const existing = extractionStatuses[doc.document_id];
    if (!force && existing && existing.status !== "failed") {
      openExtractionReview(doc, existing);
      return;
    }
    if (force && !(await confirm({ title: `重新提取「${doc.title || doc.source}」的概念？`, detail: "这会再次调用模型并消耗 Token。", confirmLabel: "重新提取" }))) return;

    setStartingExtractionId(doc.document_id);
    const content = sections.map((s) => s.text).join("\n\n");
    setError("");
    try {
      const request = {
        document_id: doc.document_id,
        document_title: doc.title || doc.source,
        content,
        sections,
        content_version: documentContentVersion(doc),
        force,
      };
      let extractionRunId: string | undefined;
      try {
        const { run } = await api.graphStartExtraction(request);
        extractionRunId = run.run_id;
        setExtractionStatuses((current) => ({
          ...current,
          [doc.document_id]: {
            status: run.status === "failed" ? "failed" : run.status === "completed" || run.status === "completed_with_warnings" ? "review" : "extracting",
            pending_count: 0,
            run,
          },
        }));
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 404) throw reason;
        await api.graphExtract(request);
      }
      navigate("/knowledge-map", {
        state: {
          extractionRunId,
          extractingDocumentId: doc.document_id,
          extractingDocumentTitle: doc.title || doc.source,
        },
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法启动概念提取。");
    } finally {
      setStartingExtractionId(null);
    }
  }

  async function retryFailedSections(doc: DocumentSummary) {
    const previous = extractionStatuses[doc.document_id]?.run;
    if (!previous?.failed_sections?.length || startingExtractionId || !sections.length) return;
    setStartingExtractionId(doc.document_id);
    setError("");
    try {
      const { run } = await api.graphRetryFailedSections(previous.run_id, {
        document_id: doc.document_id,
        document_title: doc.title || doc.source,
        content: sections.map((section) => section.text).join("\n\n"),
        sections,
        content_version: documentContentVersion(doc),
      });
      navigate("/knowledge-map", {
        state: {
          extractionRunId: run.run_id,
          extractingDocumentId: doc.document_id,
          extractingDocumentTitle: doc.title || doc.source,
        },
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法重试失败章节。");
    } finally {
      setStartingExtractionId(null);
    }
  }

  async function createFolder(relativePath: string) {
    if (!activeLibrary) return;
    try {
      await api.createFolder(relativePath);
      await Promise.all([loadTree(), loadDocuments()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "新建文件夹失败。");
    }
  }

  async function deleteFolder(relativePath: string) {
    if (!activeLibrary) return;
    const confirmed = await confirm({
      title: `删掉文件夹「${relativePath}」？`,
      detail: "只是删掉这个容器：里面的资料会移回资料库根目录，一份都不会删。如果还有非资料文件，文件夹会保留。",
      confirmLabel: "删文件夹",
    });
    if (!confirmed) return;
    try {
      const result = await api.deleteFolder(relativePath);
      setNotice(
        result.kept_directory
          ? `已移出 ${result.moved.length} 份资料；文件夹因为还有非资料文件而保留。`
          : `已移出 ${result.moved.length} 份资料，并删掉空文件夹。`,
      );
      if (selectedFolder === relativePath) setSelectedFolder("");
      await Promise.all([loadTree(), loadDocuments()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删文件夹失败。");
    }
  }

  async function moveDocument(documentId: string, newRelativePath: string) {
    if (!activeLibrary) return;
    try {
      const result = await api.moveDocument(documentId, newRelativePath);
      setNotice(`已移动「${result.migration.relative_path}」；引用与证据已跟着迁移。`);
      await Promise.all([loadTree(), loadDocuments()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "移动失败。");
    }
  }

  async function archiveDocument(documentId: string, title: string) {
    if (!activeLibrary) return;
    const confirmed = await confirm({
      title: `归档「${title}」？`,
      detail: "文件会移进资料库归档区并从索引移除；随时可以在「已归档」里恢复原位。",
      confirmLabel: "归档",
    });
    if (!confirmed) return;
    try {
      await api.deleteDocument(documentId);
      setNotice("已归档，可在「已归档」里恢复。");
      await Promise.all([loadTree(), loadDocuments(), loadArchive()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "归档失败。");
    }
  }

  async function restoreArchived(entryId: string) {
    try {
      await api.restoreArchived(entryId);
      setNotice("已恢复到原来的位置并重新索引。");
      await Promise.all([loadTree(), loadDocuments(), loadArchive()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复失败。");
    }
  }

  async function loadOrganizeProposals() {
    setOrganizeBusy(true);
    setError("");
    try {
      const result = await api.organizationProposals();
      setOrganizeProposals(result.proposals);
      setOrganizeSource(result.source);
      setOrganizeDegraded(result.degraded);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取整理建议失败。");
    } finally {
      setOrganizeBusy(false);
    }
  }

  /** ⑤：让模型归类 —— 仍然只提议；模型不可用时如实降级，并说明这次是规则建议。 */
  async function loadAiProposals() {
    setOrganizeBusy(true);
    setError("");
    try {
      const result = await api.aiOrganizationProposals();
      setOrganizeProposals(result.proposals);
      setOrganizeSource(result.source);
      setOrganizeDegraded(result.degraded);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 归类失败。");
    } finally {
      setOrganizeBusy(false);
    }
  }

  async function applyProposal(proposal: OrganizationProposal) {
    setOrganizeBusy(true);
    setError("");
    try {
      const result = await api.applyOrganization(proposal.items, proposal.suggested_folder);
      setOrganizeProposals([]);
      setNotice(`已把 ${result.moved.length} 份资料收进「${proposal.suggested_folder}」；引用与证据已跟着迁移。`);
      // 台账写在服务端，界面以它为准（刷新/重启后一致）。
      await Promise.all([loadTree(), loadDocuments(), loadOrganizeState()]);
    } catch (reason) {
      // 审查 F07：部分失败时，**当场**把服务端台账读回来 —— 用户要立刻看到
      // "已经搬走了哪几份"，并且当场就能撤销，而不是刷新以后才发现。
      const details = reason instanceof ApiError
        ? reason.details as { moved?: { from: string }[]; failed?: { from: string; error?: string }[] } | undefined
        : undefined;
      const movedCount = details?.moved?.length || 0;
      const failedCount = details?.failed?.length || 0;
      const message = failedCount > 0
        ? `整理没有全部完成：已搬走 ${movedCount} 份，${failedCount} 份没搬成（${details?.failed?.[0]?.error || "原因未知"}）。已经搬走的部分可以撤销。`
        : reason instanceof Error ? reason.message : "整理失败。";
      // 先刷新（loadDocuments 开头会 setError("")，会把刚写的错误冲掉），再设错误信息。
      await Promise.all([loadTree(), loadDocuments(), loadOrganizeState()]);
      setError(message);
    } finally {
      setOrganizeBusy(false);
    }
  }

  async function undoOrganize() {
    setOrganizeBusy(true);
    setError("");
    try {
      const result = await api.undoOrganization();
      const skipped = result.skipped || [];
      // 审查 F03：有跳过的项要**如实说**（原位已经有文件，我们选择不覆盖），
      // 而且台账还留着，用户处理完冲突可以再撤销一次。
      setNotice(
        skipped.length
          ? `已还回 ${result.restored.length} 份；${skipped.length} 份因为原位已经有文件被跳过（没有覆盖），台账保留着。`
          : `已撤销整理，${result.restored.length} 份资料回到原位。`,
      );
      await Promise.all([loadTree(), loadDocuments(), loadOrganizeState()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销失败。");
    } finally {
      setOrganizeBusy(false);
    }
  }

  async function syncLibraryFolder() {
    if (!activeLibrary || syncingFolder) return;
    setSyncingFolder(true);
    setError("");
    try {
      const summary = await api.syncLibrary(activeLibrary.library_id);
      setSyncSummary(summary);
      await Promise.all([loadDocuments(), loadTree()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "同步资料库文件夹失败。");
    } finally {
      setSyncingFolder(false);
    }
  }

  function effectiveExtractionStatus(document: DocumentSummary) {
    const status = extractionStatuses[document.document_id];
    const currentVersion = documentContentVersion(document);
    const extractedVersion = status?.run.content_version || "";
    if (
      status
      && (status.status === "completed" || status.status === "review")
      && extractedVersion
      && currentVersion
      && extractedVersion !== currentVersion
    ) {
      return "stale" as const;
    }
    return status ? status.status : "not_started" as const;
  }



  return {
    selectDocument,
    selectCollection,
    selectWikiView,
    askAboutDocument,
    documentContentVersion,
    openExtractionReview,
    extractAndReview,
    retryFailedSections,
    createFolder,
    deleteFolder,
    moveDocument,
    archiveDocument,
    restoreArchived,
    loadOrganizeProposals,
    loadAiProposals,
    applyProposal,
    undoOrganize,
    syncLibraryFolder,
    effectiveExtractionStatus,
  };
}
