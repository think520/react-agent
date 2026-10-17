import {} from "../lib/documentLinks";
import { useCallback, useEffect, useRef, useState } from "react";
import { FilePlus2, FolderOpen } from "lucide-react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import {} from "../components/DropdownSelect";
import { ImportDropZone } from "../components/ImportDropZone";
import {} from "../components/ImportReportPanel";
import { DocumentEditor } from "../components/DocumentEditor";

import type { AppOutletContext } from "../components/AppShell";
import { createLibraryWikiActions } from "./library/libraryWikiActions";
import { matchesWikiView } from "./library/wikiView";
import type {} from "./library/wikiView";
import { LibraryTreePanel } from "./library/LibraryTreePanel";
import { LibraryHeader } from "./library/LibraryHeader";
import { LibraryReadingArea } from "./library/LibraryReadingArea";
import { createLibraryMaterialActions } from "./library/libraryActions";
import { BrandIllustration, EmptyState, ErrorNotice, LoadingState } from "../components/common";
import {} from "../components/WikiPlanCard";
import { api } from "../lib/api";
import type { ArchivedEntry, KnowledgeSyncSummary, KnowledgeTree, OrganizationBatch, OrganizationProposal } from "../lib/api";
import {} from "../components/DocumentReader";
import {} from "../components/ScrollIndicator";
import {} from "../components/LibraryTree";
import { useReaderTabsStore } from "../stores/readerTabsStore";
import { useConfirm } from "../ui/Modal";
import {} from "../stores/handoffStore";
import type { DocumentExtractionStatus, DocumentSection, DocumentSummary, WikiEditablePage, WikiGenerationMode, WikiHealth, WikiPlan, WikiRepairPlan, WikiRunEstimate, WikiScopeMode, WikiTask } from "../types";

type WikiView = "knowledge" | "sources" | "notes" | "all";

/** 同步明细里的一组来源（新增 / 移除 / 跳过 …），最多列 20 条。 */

function wikiViewForType(type: DocumentSummary["wiki_type"]): WikiView {
  if (type === "source") return "sources";
  if (type === "note") return "notes";
  return "knowledge";
}


/** E8：进度百分比。收下阶段看文件数，建索引阶段看来源数；总量未知时给 0（不假装有进度）。 */
function progressPercent(progress: { phase: string; filesDone: number; filesTotal: number; sourcesDone: number; sourcesTotal: number }): number {
  const [done, total] = progress.phase === "indexing"
    ? [progress.sourcesDone, progress.sourcesTotal]
    : [progress.filesDone, progress.filesTotal];
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

export function LibraryPage() {
  const {
    activeLibrary,
    settings,
    libraries,
    openLibrarySetup,
    switchLibrary,
    startDocumentImport,
    documentImporting,
    documentImportNotice,
    documentImportError,
    documentImportErrorCode,
    documentImportDuplicateCount,
    importDuplicatesAsCopies,
    documentImportVersion,
    importDroppedFiles,
    documentImportProgress,
    cancelDocumentImport,
    documentImportResults,
    documentImportCanRetry,
    retryFailedImports,
    dismissImportReport,
    selectedDocumentIds,
    setDocumentScope,
  } = useOutletContext<AppOutletContext>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { confirm, confirmElement } = useConfirm();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [collection, setCollection] = useState<"material" | "wiki">(
    searchParams.get("collection") === "wiki" ? "wiki" : "material",
  );
  const [wikiView, setWikiView] = useState<WikiView>(() => {
    const requested = searchParams.get("wikiView");
    return requested === "sources" || requested === "notes" || requested === "all" ? requested : "knowledge";
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sections, setSections] = useState<DocumentSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // ①（E17）：文件夹同步 —— 用户在资源管理器里把资料剪进资料库文件夹后，
  // 需要有一个明确入口去发现它们，并看到「这次到底动了什么」。
  const [syncingFolder, setSyncingFolder] = useState(false);
  const [syncSummary, setSyncSummary] = useState<KnowledgeSyncSummary | null>(null);
  // ②（E17）：只读文件夹树 + 当前选中的文件夹（"" = 根）。
  const [tree, setTree] = useState<KnowledgeTree | null>(null);
  const [selectedFolder, setSelectedFolder] = useState("");
  // ③：已归档的资料（归档只是移走，永远可恢复）。
  const [archive, setArchive] = useState<ArchivedEntry[]>([]);
  // ⑤：整理建议（只提议 → 执行 → 一键撤销）。
  const [organizeProposals, setOrganizeProposals] = useState<OrganizationProposal[] | null>(null);
  // ⑤：可撤销的那一步由**服务端台账**说了算（刷新页面后仍然撤销得回来）。
  const [organizePending, setOrganizePending] = useState<OrganizationBatch | null>(null);
  const [organizeBusy, setOrganizeBusy] = useState(false);
  // ⑤：这份建议到底是谁提的（模型 / 规则），以及模型为什么没参与 —— 界面要如实说。
  const [organizeSource, setOrganizeSource] = useState("");
  const [organizeDegraded, setOrganizeDegraded] = useState("");
  // ④：阅读区标签页（每篇记住读到哪；关掉最后一个自动收起）。
  // ④：复用既有的标签模型（ReaderPage 也用它）：openIds + 每篇滚动位置。
  const openIds = useReaderTabsStore((state) => state.openIds);
  const openTab = useReaderTabsStore((state) => state.open);
  const closeTab = useReaderTabsStore((state) => state.close);
  const scrollFor = useReaderTabsStore((state) => state.scrollFor);
  // ④：树栏可收起（用户："文件树那一栏占用了很多"）。选择记在本地，下次照旧。
  const [treeCollapsed, setTreeCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem("bobodan:library-tree:collapsed") === "1";
    } catch {
      return false;
    }
  });
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  // ④：编辑器保存后让阅读器重新拉一次小节（阅读器自己持有小节加载）。
  const [readerReloadToken, setReaderReloadToken] = useState(0);
  const [startingExtractionId, setStartingExtractionId] = useState<string | null>(null);
  const [extractionStatuses, setExtractionStatuses] = useState<Record<string, DocumentExtractionStatus>>({});
  const [documentQuery, setDocumentQuery] = useState("");
  // ④ 搜索命中 → 定位：标题过滤之外，再问一次后端的原文检索，命中直接深链到阅读器
  // 的那一段（?chunk= 通道已在 2026-09-23 验证可用）。
  const [hits, setHits] = useState<Array<{ chunk_id: string; document_id: string; collection?: string; title?: string; source?: string; text?: string }>>([]);
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [wikiHealth, setWikiHealth] = useState<WikiHealth | null>(null);
  const [wikiPlan, setWikiPlan] = useState<WikiPlan | null>(null);
  const [wikiPlanOpen, setWikiPlanOpen] = useState(false);
  const [wikiPlanLoading, setWikiPlanLoading] = useState(false);
  const [wikiEstimate, setWikiEstimate] = useState<WikiRunEstimate | null>(null);
  const [wikiGenerationMode, setWikiGenerationMode] = useState<WikiGenerationMode>(settings?.preferences.wiki?.default_mode || "standard");
  const [repairPlan, setRepairPlan] = useState<WikiRepairPlan | null>(null);
  const [wikiEditorOpen, setWikiEditorOpen] = useState(false);
  const [wikiEditorPreview, setWikiEditorPreview] = useState(false);
  const [wikiEditor, setWikiEditor] = useState<WikiEditablePage | null>(null);
  const [wikiEditorSaving, setWikiEditorSaving] = useState(false);
  const [wikiTasks, setWikiTasks] = useState<WikiTask[]>([]);
  const [wikiInstruction, setWikiInstruction] = useState("");
  const [wikiTopic, setWikiTopic] = useState("");
  const [wikiScopeMode, setWikiScopeMode] = useState<WikiScopeMode>("uncovered");
  // 资料库页自己管滚动：正文列是滚动容器，阅读进度与标签位置都记在它身上（不再是整页）。
  const readerScrollRef = useRef<HTMLElement | null>(null);
  const selectedIdRef = useRef(selectedId);
  const searchParamsRef = useRef(searchParams);
  const wikiViewRef = useRef(wikiView);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);

  // （原来这里在整页滚动容器上存取 "bobodan:library-scroll"：那是"我的资料"平铺列表时代的
  //  遗留物，列表已经删掉、整页也不再滚，逐文档的阅读位置由标签条的 scrollFor 负责，故移除。）
  useEffect(() => { searchParamsRef.current = searchParams; }, [searchParams]);
  useEffect(() => { wikiViewRef.current = wikiView; }, [wikiView]);

  const loadDocuments = useCallback(async () => {
    if (!activeLibrary) {
      setDocuments([]);
      setSelectedId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const nextDocuments = await api.documents(collection);
      setDocuments(nextDocuments);
      const requested = searchParamsRef.current.get("document");
      const requestedTitle = searchParamsRef.current.get("title");
      const requestedDocument = nextDocuments.find((item) => item.document_id === requested)
        || nextDocuments.find((item) => item.title === requestedTitle);
      if (collection === "wiki" && requestedDocument) setWikiView(wikiViewForType(requestedDocument.wiki_type));
      // ④：资料库**不再自动打开第一份资料** —— 进页面就该看见列表，
      // "打开"是用户动作（双击/点击），只有 wiki 视图才需要一个兜底页面。
      // 否则窄窗口一进来就变成"树 + 列表 + 正文"三栏挤在一起，正文只剩四百来像素。
      const preferredDocument = collection === "wiki"
        ? nextDocuments.find((item) => matchesWikiView(item, wikiViewRef.current))
        : undefined;
      const nextSelected = requestedDocument?.document_id
        || nextDocuments.find((item) => item.document_id === selectedIdRef.current)?.document_id
        || preferredDocument?.document_id
        || null;
      // 深链接（?document=…）算"明确打开"：进阅读模式并进标签条。
      if (requestedDocument && collection === "material") openTab(requestedDocument.document_id);
      setSelectedId(nextSelected);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取资料库。" );
    } finally {
      setLoading(false);
    }
  }, [activeLibrary, collection, openTab]);

  useEffect(() => { void loadDocuments(); }, [documentImportVersion, loadDocuments]);

  const loadArchive = useCallback(async () => {
    if (!activeLibrary) {
      setArchive([]);
      return;
    }
    try {
      const result = await api.knowledgeArchive();
      setArchive(result.entries);
    } catch {
      // 归档列表读不到不影响浏览；不把整页变成错误页。
      setArchive([]);
    }
  }, [activeLibrary]);

  useEffect(() => { void loadArchive(); }, [loadArchive]);

  const loadTree = useCallback(async () => {
    if (!activeLibrary) {
      setTree(null);
      return;
    }
    try {
      const result = await api.knowledgeTree();
      setTree(result.tree);
    } catch {
      // 树只是导航层：读不到时保持资料列表可用，不把整页变成错误页。
      setTree(null);
    }
  }, [activeLibrary]);

  // ⑤：可撤销的那一步记在服务端台账里，刷新页面（甚至重启）之后照样撤得回来。
  const loadOrganizeState = useCallback(async () => {
    if (!activeLibrary || collection !== "material") {
      setOrganizePending(null);
      return;
    }
    try {
      setOrganizePending((await api.organizationState()).pending_undo);
    } catch {
      // 读不到"可撤销状态"不该打断阅读：面板里仍然可以看建议、做整理。
      setOrganizePending(null);
    }
  }, [activeLibrary, collection]);
  useEffect(() => { void loadOrganizeState(); }, [loadOrganizeState]);
  useEffect(() => {
    try {
      window.localStorage.setItem("bobodan:library-tree:collapsed", treeCollapsed ? "1" : "0");
    } catch {
      // 无痕模式等写不了 localStorage：只是记不住，不该影响阅读。
    }
  }, [treeCollapsed]);

  useEffect(() => { void loadTree(); }, [loadTree, documentImportVersion]);

  useEffect(() => {
    if (!activeLibrary || collection !== "material") {
      setExtractionStatuses({});
      return;
    }
    let cancelled = false;
    let timer: number | undefined;

    async function refreshExtractionStatuses() {
      try {
        const result = await api.graphExtractionStatuses();
        if (cancelled) return;
        setExtractionStatuses(result.documents);
        if (Object.values(result.documents).some((item) => item.status === "extracting")) {
          timer = window.setTimeout(refreshExtractionStatuses, 1500);
        }
      } catch {
        // Extraction status should not block reading the library.
      }
    }

    void refreshExtractionStatuses();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeLibrary, collection]);

  const planningWikiRunId = wikiPlan?.status === "planning"
    ? wikiPlan.run_id || wikiPlan.plan_id
    : null;
  useEffect(() => {
    if (!planningWikiRunId) return;
    const timer = window.setInterval(() => {
      void api.wikiRun(planningWikiRunId).then(setWikiPlan).catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [planningWikiRunId]);

  useEffect(() => {
    const requestedCollection = searchParams.get("collection") === "wiki" ? "wiki" : "material";
    if (requestedCollection !== collection) setCollection(requestedCollection);
  }, [collection, searchParams]);

  // ④：小节加载、相关笔记、阅读进度、选区工具条、目录都归 DocumentReader（唯一实现）。
  // 外壳只留两件事：知道"当前这份资料的小节"（提取概念要用），以及恢复标签的滚动位置。
  useEffect(() => {
    setSections([]);
  }, [selectedId]);

  // ④：切到一份资料并把内容渲染出来之后，恢复到上次读到的位置。
  // 只做一次（用 ref 记已恢复的 document_id），避免用户往下读时被反复拽回。
  const restoredRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedId || sections.length === 0) return;
    if (restoredRef.current === selectedId) return;
    restoredRef.current = selectedId;
    const element = readerScrollRef.current;
    if (!element) return;
    const target = scrollFor(selectedId);
    if (target <= 0) return;
    element.scrollTop = target;
  }, [selectedId, sections.length, scrollFor]);

  const selected = documents.find((document) => document.document_id === selectedId);
  const {
    checkWiki,
    organizeWiki,
    applyRepairPlan,
    draftRepairPlan,
    reviewWikiSemantics,
    retryWikiTask,
    cancelWikiTask,
    planWiki,
    startEstimatedWiki,
    resumeWikiPlan,
    openWikiProviderSettings,
    continueWikiBatch,
    applyWikiPlan,
    recoverWikiPlan,
    undoWikiPlan,
    openWikiEditor,
    updateWikiEditor,
    saveWikiEditor,
    archiveSelectedWikiPage,
  // 误报：工厂只是收下这些值（函数体内才读 ref.current / 调用回调），render 期并不访问。
  // eslint-disable-next-line react-hooks/refs -- factory only stores the values; refs are read inside handlers
  } = createLibraryWikiActions({
    confirm,
    repairPlan,
    setRepairPlan,
    setWikiHealth,
    setMaintenanceLoading,
    setNotice,
    setError,
    collection,
    wikiView,
    wikiScopeMode,
    wikiGenerationMode,
    selectedId,
    setSelectedId,
    selectedDocumentIds,
    selected,
    wikiInstruction,
    wikiTopic,
    wikiPlan,
    setWikiPlan,
    wikiPlanOpen,
    setWikiPlanOpen,
    wikiPlanLoading,
    setWikiPlanLoading,
    wikiEstimate,
    setWikiEstimate,
    wikiEditor,
    setWikiEditor,
    wikiEditorOpen,
    setWikiEditorOpen,
    wikiEditorPreview,
    setWikiEditorPreview,
    wikiEditorSaving,
    setWikiEditorSaving,
    wikiTasks,
    setWikiTasks,
    setCollection,
    settings,
    activeLibrary,
    navigate,
    searchParams,
    setSearchParams,
    loadDocuments,
  });

  const filteredDocuments = documents.filter((document) => {
    if (collection === "wiki" && !matchesWikiView(document, wikiView)) return false;
    // ②：选中某个文件夹时，右侧只显示这个文件夹里的资料（按真实相对路径前缀）。
    if (collection === "material" && selectedFolder) {
      const prefix = selectedFolder + "/";
      if (!(document.relative_path || "").startsWith(prefix)) return false;
    }
    const query = documentQuery.trim().toLocaleLowerCase();
    if (!query) return true;
    return [document.title, document.source, document.course, document.kind]
      .some((value) => value?.toLocaleLowerCase().includes(query));
  });
  useEffect(() => {
    const query = documentQuery.trim();
    if (query.length < 2) { setHits([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api.searchKnowledge(query, collection)
        .then((result) => { if (!cancelled) setHits((result.results || []).slice(0, 5)); })
        .catch(() => { if (!cancelled) setHits([]); });
    }, 300);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [documentQuery, collection]);

  const uncoveredCount = documents.length;
  const wikiTypeLabels: Record<NonNullable<DocumentSummary["wiki_type"]>, string> = {
    source: "资料索引",
    entity: "实体",
    concept: "概念",
    analysis: "综合分析",
    question: "问题与发现",
    note: "个人笔记",
  };

  const {
    selectDocument,
    selectCollection,
    selectWikiView,
    askAboutDocument,
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
  // 误报：工厂只收下这些值，ref 的 .current 只在处理器内部读。
  // eslint-disable-next-line react-hooks/refs -- factory only stores the values; refs are read inside handlers
  } = createLibraryMaterialActions({
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
    documentQuery,
    setHits,
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
  });

  return (
    <section className="page-scroll library-scroll">
      <div className="page-container library-container">
        <LibraryHeader
              activeLibrary={activeLibrary} collection={collection} libraries={libraries} loadDocuments={loadDocuments}
              openLibrarySetup={openLibrarySetup} switchLibrary={switchLibrary} startDocumentImport={startDocumentImport} documentImporting={documentImporting}
              documentImportNotice={documentImportNotice} documentImportError={documentImportError} documentImportErrorCode={documentImportErrorCode} documentImportDuplicateCount={documentImportDuplicateCount}
              importDuplicatesAsCopies={importDuplicatesAsCopies} documentImportVersion={documentImportVersion} documentImportProgress={documentImportProgress} documentImportResults={documentImportResults}
              documentImportCanRetry={documentImportCanRetry} cancelDocumentImport={cancelDocumentImport} retryFailedImports={retryFailedImports} dismissImportReport={dismissImportReport}
              tree={tree} treeCollapsed={treeCollapsed} setTreeCollapsed={setTreeCollapsed} selected={selected}
              selectedDocumentIds={selectedDocumentIds} uncoveredCount={uncoveredCount} notice={notice} confirmElement={confirmElement}
              syncSummary={syncSummary} syncingFolder={syncingFolder} setSyncSummary={setSyncSummary} maintenanceOpen={maintenanceOpen}
              maintenanceLoading={maintenanceLoading} setMaintenanceOpen={setMaintenanceOpen} repairPlan={repairPlan} wikiHealth={wikiHealth}
              wikiTasks={wikiTasks} wikiPlan={wikiPlan} wikiPlanOpen={wikiPlanOpen} wikiPlanLoading={wikiPlanLoading}
              wikiScopeMode={wikiScopeMode} wikiView={wikiView} wikiGenerationMode={wikiGenerationMode} wikiTopic={wikiTopic}
              wikiInstruction={wikiInstruction} wikiEstimate={wikiEstimate} wikiEditor={wikiEditor} wikiEditorOpen={wikiEditorOpen}
              wikiEditorPreview={wikiEditorPreview} wikiEditorSaving={wikiEditorSaving} setWikiPlan={setWikiPlan} setWikiPlanOpen={setWikiPlanOpen}
              setWikiScopeMode={setWikiScopeMode} setWikiGenerationMode={setWikiGenerationMode} setWikiTopic={setWikiTopic} setWikiInstruction={setWikiInstruction}
              setWikiEstimate={setWikiEstimate} setWikiEditor={setWikiEditor} setWikiEditorOpen={setWikiEditorOpen} setWikiEditorPreview={setWikiEditorPreview}
              progressPercent={progressPercent} selectCollection={selectCollection} selectWikiView={selectWikiView} syncLibraryFolder={syncLibraryFolder}
              checkWiki={checkWiki} organizeWiki={organizeWiki} applyRepairPlan={applyRepairPlan} draftRepairPlan={draftRepairPlan}
              reviewWikiSemantics={reviewWikiSemantics} retryWikiTask={retryWikiTask} cancelWikiTask={cancelWikiTask} planWiki={planWiki}
              startEstimatedWiki={startEstimatedWiki} resumeWikiPlan={resumeWikiPlan} openWikiProviderSettings={openWikiProviderSettings} continueWikiBatch={continueWikiBatch}
              applyWikiPlan={applyWikiPlan} recoverWikiPlan={recoverWikiPlan} undoWikiPlan={undoWikiPlan} openWikiEditor={openWikiEditor}
              updateWikiEditor={updateWikiEditor} saveWikiEditor={saveWikiEditor} archiveSelectedWikiPage={archiveSelectedWikiPage}
        />
        {error && <ErrorNotice message={error} action={<button className="quiet-button" onClick={() => void loadDocuments()}>重试</button>} />}
        {/* E8：整页都是拖拽热区（没有资料库时先引导新建，并记住拖进来的文件）。 */}
        <ImportDropZone onFiles={importDroppedFiles} enabled={Boolean(activeLibrary)}>
        {loading ? <div className="illustrated-loading"><BrandIllustration state="reading" size={76} /><LoadingState label={collection === "wiki" ? "正在整理 Wiki…" : "正在读取本地资料…"} /></div> : documents.length ? (
          <div
            className={
              "library-workspace"
              + (collection === "material" ? " list-only" : "")
              // 收起树时**不给 with-tree**：网格自然回到单栏，正文拿到全部宽度。
              + (collection === "material" && tree && !treeCollapsed ? " with-tree" : "")

            }
          >
            {collection === "material" && tree && !treeCollapsed && (
            <LibraryTreePanel
              archive={archive} restoreArchived={restoreArchived} tree={tree} documentQuery={documentQuery}
              setDocumentQuery={setDocumentQuery} hits={hits} navigate={navigate} collection={collection}
              selectedFolder={selectedFolder} setSelectedFolder={setSelectedFolder} selectedId={selectedId} selectDocument={selectDocument}
              moveDocument={moveDocument} archiveDocument={archiveDocument} createFolder={createFolder} deleteFolder={deleteFolder}
              organizeProposals={organizeProposals} organizeBusy={organizeBusy} organizeSource={organizeSource} organizeDegraded={organizeDegraded}
              organizePending={organizePending} loadOrganizeProposals={loadOrganizeProposals} loadAiProposals={loadAiProposals} applyProposal={applyProposal}
              undoOrganize={undoOrganize}
            />
            )}
            {/* 资料库不再有"我的资料"平铺列表：它和左边的文件夹树功能重复，还白占一栏
                （2026-09-24 用户要求）。wiki 的三个视图仍然用这一栏。 */}
            <LibraryReadingArea
              retryFailedSections={retryFailedSections}
              searchParams={searchParams}
              setError={setError}
              setSections={setSections}
              readerReloadToken={readerReloadToken}
              askAboutDocument={askAboutDocument}
              setEditingDocumentId={setEditingDocumentId}
              closeTab={closeTab} openIds={openIds} collection={collection} wikiView={wikiView}
              documentQuery={documentQuery} setDocumentQuery={setDocumentQuery} documents={documents} effectiveExtractionStatus={effectiveExtractionStatus}
              extractAndReview={extractAndReview} extractionStatuses={extractionStatuses} filteredDocuments={filteredDocuments} hits={hits}
              navigate={navigate} openExtractionReview={openExtractionReview} readerScrollRef={readerScrollRef} sections={sections}
              selectDocument={selectDocument} selected={selected} selectedId={selectedId} setSelectedId={setSelectedId}
              startingExtractionId={startingExtractionId} wikiTypeLabels={wikiTypeLabels}
            />
          </div>
        ) : (
          <EmptyState state={collection === "wiki" ? "listening" : "reading"}
            title={collection === "wiki" ? "还没有 Wiki 页面" : "先放进第一份学习资料"}
            description={collection === "wiki" ? "从学习资料生成的概念与实体会整理在这里。" : "支持 Markdown、PDF、Word 和 PowerPoint。没有资料库也没关系，选择文件后会继续引导。"}
            action={collection === "material" ? <div className="library-empty-actions"><button className="primary-button" onClick={startDocumentImport}><FilePlus2 size={17} />导入资料</button><button className="quiet-button" onClick={() => openLibrarySetup({ initialMode: "open" })}><FolderOpen size={16} />打开或接入已有资料库</button></div> : undefined}
          />
        )}
        </ImportDropZone>
      </div>
      {editingDocumentId && selected && (
        <DocumentEditor
          documentId={editingDocumentId}
          title={selected.title || selected.source}
          onClose={() => setEditingDocumentId(null)}
          onSaved={() => {
            setEditingDocumentId(null);
            void loadDocuments();
            setReaderReloadToken((token) => token + 1);
          }}
        />
      )}
    </section>
  );
}
