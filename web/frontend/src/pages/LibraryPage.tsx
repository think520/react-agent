import { readerLocation } from "../lib/documentLinks";
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, FilePlus2, FileText, FolderOpen, Library, List, MessageCircle, MoreHorizontal, Pencil, RefreshCw, Save, Search, Settings2, ShieldCheck, Sparkles, Trash2, Upload, Wrench, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { DropdownSelect } from "../components/DropdownSelect";
import { DocumentEditor } from "../components/DocumentEditor";

import type { AppOutletContext } from "../components/AppShell";
import { BrandIllustration, EmptyState, ErrorNotice, IconButton, LoadingState, formatRelativeDate } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { ApiError, api } from "../lib/api";
import type { ArchivedEntry, KnowledgeSyncSummary, KnowledgeTree, OrganizationBatch, OrganizationProposal } from "../lib/api";
import { DocumentReader } from "../components/DocumentReader";
import { LibraryTree } from "../components/LibraryTree";
import { useReaderTabsStore } from "../stores/readerTabsStore";
import { Modal, useConfirm } from "../ui/Modal";
import { useHandoffStore } from "../stores/handoffStore";
import type { DocumentExtractionStatus, DocumentSection, DocumentSummary, WikiEditablePage, WikiGenerationMode, WikiHealth, WikiPlan, WikiRepairPlan, WikiRunEstimate, WikiScopeMode, WikiTask } from "../types";

type WikiView = "knowledge" | "sources" | "notes" | "all";

/** 同步明细里的一组来源（新增 / 移除 / 跳过 …），最多列 20 条。 */
function SyncSourceList({ title, sources }: { title: string; sources: string[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="library-sync-group">
      <strong>{title} {sources.length}</strong>
      <ul>
        {sources.slice(0, 20).map((source) => <li key={source}>{source}</li>)}
        {sources.length > 20 && <li className="text-faint">…… 其余 {sources.length - 20} 条</li>}
      </ul>
    </div>
  );
}

function wikiViewForType(type: DocumentSummary["wiki_type"]): WikiView {
  if (type === "source") return "sources";
  if (type === "note") return "notes";
  return "knowledge";
}

function matchesWikiView(document: DocumentSummary, view: WikiView) {
  if (view === "all") return true;
  return wikiViewForType(document.wiki_type) === view;
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
    documentImportVersion,
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
  const [deletingId, setDeletingId] = useState<string | null>(null);
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
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  // ④："打开"= 有标签页（双击/点击打开），不是"列表里高亮"。
  const readingOpen = Boolean(selectedId && openIds.includes(selectedId));
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
  const pageRef = useRef<HTMLElement>(null);
  const selectedIdRef = useRef(selectedId);
  const searchParamsRef = useRef(searchParams);
  const wikiViewRef = useRef(wikiView);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);

  // TASKS_LIBRARY_REWORK task 1: restore list scroll on mount, save on unmount.
  useEffect(() => {
    const element = pageRef.current;
    if (element) element.scrollTop = Number(localStorage.getItem("bobodan:library-scroll")) || 0;
    return () => {
      if (element) localStorage.setItem("bobodan:library-scroll", String(element.scrollTop));
    };
  }, []);
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
    const element = pageRef.current;
    if (!element) return;
    const target = scrollFor(selectedId);
    if (target <= 0) return;
    element.scrollTop = target;
  }, [selectedId, sections.length, scrollFor]);

  async function checkWiki() {
    setMaintenanceLoading(true);
    setError("");
    try { setWikiHealth(await api.wikiHealth()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "无法检查 Wiki。" ); }
    finally { setMaintenanceLoading(false); }
  }

  async function organizeWiki() {
    setMaintenanceLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await api.maintainWiki();
      setWikiHealth(result.health);
      setRepairPlan(result.repair_plan);
      setNotice("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Wiki 整理失败。" );
    } finally {
      setMaintenanceLoading(false);
    }
  }

  async function applyRepairPlan() {
    if (!repairPlan) return;
    setMaintenanceLoading(true);
    try {
      const result = await api.applyWikiRepairPlan(repairPlan.plan_id);
      setRepairPlan(result);
      setWikiHealth(await api.wikiHealth());
      setNotice(`已应用 ${result.applied_count || 0} 项本地安全修复；其余项目仍等待审查。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法应用 Wiki 修复计划。" );
    } finally { setMaintenanceLoading(false); }
  }

  async function draftRepairPlan() {
    if (!repairPlan) return;
    setMaintenanceLoading(true);
    try { setRepairPlan(await api.draftWikiRepairPlan(repairPlan.plan_id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "AI 修复审核未完成。" ); }
    finally { setMaintenanceLoading(false); }
  }

  async function reviewWikiSemantics() {
    setMaintenanceLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await api.reviewWikiSemantics();
      setWikiHealth(result.health);
      setNotice("AI 语义检查已完成；发现项只是审核候选，不会自动修改 Wiki。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Wiki 语义检查失败。" );
    } finally {
      setMaintenanceLoading(false);
    }
  }

  async function retryWikiTask(taskId: string) {
    setMaintenanceLoading(true);
    setError("");
    try {
      await api.retryWikiTask(taskId);
      const [health, tasks] = await Promise.all([api.wikiHealth(), api.wikiTasks()]);
      setWikiHealth(health);
      setWikiTasks(tasks.tasks);
      setNotice("Wiki 任务已重新执行。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Wiki 任务重试失败。" );
    } finally {
      setMaintenanceLoading(false);
    }
  }

  async function cancelWikiTask(taskId: string) {
    setMaintenanceLoading(true);
    setError("");
    try {
      await api.cancelWikiTask(taskId);
      setWikiTasks((await api.wikiTasks()).tasks);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法取消 Wiki 任务。" );
    } finally {
      setMaintenanceLoading(false);
    }
  }

  async function planWiki() {
    const documentIds = collection === "material" && wikiScopeMode === "selected_only"
      ? selectedDocumentIds
      : collection === "material" && wikiScopeMode === "smart_library"
        ? selectedDocumentIds
        : [];
    const wikiDocumentIds = collection === "wiki" && selectedId ? [selectedId] : [];
    const course = collection === "material" && wikiScopeMode === "course" ? selected?.course || null : null;
    if (collection === "wiki" && !wikiDocumentIds.length) {
      setError("请先选择一个需要更新的 Wiki 页面。" );
      return;
    }
    if (collection === "wiki") {
      const command = `/wiki update${wikiInstruction.trim() ? ` ${wikiInstruction.trim()}` : ""}`;
      const handoff = useHandoffStore.getState();
      handoff.setChatDraft(command);
      handoff.setWikiScope({
        scopeMode: "selected_only", documentIds: [], wikiDocumentIds, course: null, topic: wikiTopic.trim(),
      });
      setWikiPlanOpen(false);
      navigate("/chat");
      return;
    }
    if (collection === "material" && wikiScopeMode === "selected_only" && !documentIds.length) {
      setError("严格选中模式需要至少选择一份学习资料。" );
      return;
    }
    setWikiPlanLoading(true);
    setError("");
    try {
      const estimate = await api.estimateWikiRun({
        action: "generate",
        scope_mode: wikiScopeMode,
        document_ids: documentIds,
        course,
        topic: wikiTopic.trim(),
        instruction: wikiInstruction.trim(),
        generation_mode: wikiGenerationMode,
        budget: settings?.preferences.wiki?.budget,
      });
      setWikiEstimate(estimate);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法估算本轮 Wiki 整理。" );
    } finally { setWikiPlanLoading(false); }
  }

  async function startEstimatedWiki(mode = wikiGenerationMode) {
    if (mode === "deep" && !(await confirm({ title: "开始深度整理？", detail: "深度整理会处理完整范围，耗时和 Token 消耗可能明显增加。", confirmLabel: "开始深度整理" }))) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      const documentIds = collection === "material" && ["selected_only", "smart_library"].includes(wikiScopeMode) ? selectedDocumentIds : [];
      const run = await api.createWikiRun({
        action: collection === "wiki" ? "update" : "generate",
        scope_mode: collection === "wiki" ? "selected_only" : wikiScopeMode,
        document_ids: collection === "wiki" && selectedId ? [] : documentIds,
        course: collection === "material" && wikiScopeMode === "course" ? selected?.course || null : null,
        topic: wikiTopic.trim(),
        instruction: wikiInstruction.trim(),
        generation_mode: mode,
        budget: settings?.preferences.wiki?.budget,
      });
      setWikiPlan(run);
      setWikiEstimate(null);
      setWikiPlanOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法启动 Wiki 整理。" );
    } finally { setWikiPlanLoading(false); }
  }

  async function resumeWikiPlan() {
    if (!wikiPlan?.run_id) return;
    setWikiPlanLoading(true);
    try {
      const result = await api.resumeWikiRun(wikiPlan.run_id, {
        max_requests: 24,
        max_input_tokens: 300000,
        max_output_tokens: 40000,
      });
      setWikiPlan(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法继续 Wiki 整理。" ); }
    finally { setWikiPlanLoading(false); }
  }

  function openWikiProviderSettings() {
    const next = new URLSearchParams(searchParams);
    next.set("settings", "ai");
    setSearchParams(next, { replace: true });
  }

  async function continueWikiBatch() {
    setWikiPlanLoading(true);
    setError("");
    try {
      const run = await api.createWikiRun({
        action: "generate",
        scope_mode: "uncovered",
        document_ids: [],
        topic: wikiTopic.trim(),
        instruction: wikiInstruction.trim(),
        generation_mode: "standard",
        budget: settings?.preferences.wiki?.budget,
      });
      setCollection("material");
      setSearchParams({ collection: "material" }, { replace: true });
      setWikiPlan(run);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法开始下一批 Wiki 整理。" ); }
    finally { setWikiPlanLoading(false); }
  }

  async function applyWikiPlan() {
    if (!wikiPlan) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      const applied = await api.applyWikiPlan(wikiPlan.plan_id);
      setWikiPlan(applied);
      setNotice("Wiki 已按确认的计划写入，并重新建立本地索引。" );
      if (collection === "material") {
        setCollection("wiki");
        setSearchParams({ collection: "wiki" }, { replace: true });
      } else {
        await loadDocuments();
      }
    } catch (reason) {
      let stagedFailure = false;
      try {
        const refreshed = await api.wikiPlan(wikiPlan.plan_id);
        stagedFailure = Boolean(refreshed.staging?.length);
        setWikiPlan(refreshed);
      } catch { /* keep current preview */ }
      if (!stagedFailure) setError(reason instanceof Error ? reason.message : "Wiki 写入失败。" );
    } finally {
      setWikiPlanLoading(false);
    }
  }

  async function recoverWikiPlan(strategy: "keep_existing" | "regenerate") {
    if (!wikiPlan) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      const result = await api.recoverWikiPlan(wikiPlan.plan_id, strategy);
      setWikiPlan(result);
      if (strategy === "keep_existing") {
        setNotice("已保留问题页面的原内容，并生成其余可安全写入的 Wiki 页面。" );
        setCollection("wiki");
        setSearchParams({ collection: "wiki" }, { replace: true });
      } else {
        setNotice("已补充安全更新要求并重新生成计划，请再次审查。" );
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法继续处理这份 Wiki 计划。" );
    } finally {
      setWikiPlanLoading(false);
    }
  }

  async function undoWikiPlan() {
    if (!wikiPlan?.checkpoint_id) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      await api.restoreWikiCheckpoint(wikiPlan.checkpoint_id);
      setWikiPlan(null);
      setWikiPlanOpen(false);
      setNotice("已撤销本轮 Wiki 整理，并恢复写入前的版本。" );
      await loadDocuments();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法撤销本轮 Wiki 整理。" );
    } finally {
      setWikiPlanLoading(false);
    }
  }

  async function openWikiEditor(documentId?: string) {
    setError("");
    setWikiEditorPreview(false);
    if (!documentId) {
      const empty: WikiEditablePage = {
        document_id: "",
        title: "",
        body: "",
        tags: [],
        related: [],
        page_type: "wiki_note",
        generated_by: "user",
        managed_by: "user",
        content_revision: 1,
        source_refs: [],
      };
      const stored = localStorage.getItem(`bobodan:wiki-draft:${activeLibrary?.library_id || "default"}:new`);
      try { setWikiEditor(stored ? { ...empty, ...JSON.parse(stored) } : empty); }
      catch { setWikiEditor(empty); }
      setWikiEditorOpen(true);
      return;
    }
    setWikiEditorSaving(true);
    try {
      const result = await api.wikiPage(documentId);
      const draftKey = `bobodan:wiki-draft:${activeLibrary?.library_id || "default"}:${documentId}`;
      const stored = localStorage.getItem(draftKey);
      try { setWikiEditor(stored ? { ...result.page, ...JSON.parse(stored) } : result.page); }
      catch { setWikiEditor(stored ? { ...result.page, body: stored } : result.page); }
      setWikiEditorOpen(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法打开 Wiki 编辑器。" ); }
    finally { setWikiEditorSaving(false); }
  }

  function updateWikiEditor(patch: Partial<WikiEditablePage>) {
    if (!wikiEditor) return;
    const next = { ...wikiEditor, ...patch };
    setWikiEditor(next);
    const draftKey = `bobodan:wiki-draft:${activeLibrary?.library_id || "default"}:${next.document_id || "new"}`;
    localStorage.setItem(draftKey, JSON.stringify({ title: next.title, body: next.body, tags: next.tags, related: next.related }));
  }

  async function saveWikiEditor() {
    if (!wikiEditor?.title.trim() || !wikiEditor.body.trim()) return;
    setWikiEditorSaving(true);
    try {
      if (wikiEditor.document_id) {
        const result = await api.updateWikiPage(wikiEditor.document_id, {
          expected_revision: wikiEditor.content_revision,
          title: wikiEditor.title,
          body: wikiEditor.body,
          tags: wikiEditor.tags,
          related: wikiEditor.related,
        });
        localStorage.removeItem(`bobodan:wiki-draft:${activeLibrary?.library_id || "default"}:${wikiEditor.document_id}`);
        setWikiEditor(result.page);
      } else {
        await api.createWikiPage({ title: wikiEditor.title, body: wikiEditor.body, tags: wikiEditor.tags, related: wikiEditor.related });
        localStorage.removeItem(`bobodan:wiki-draft:${activeLibrary?.library_id || "default"}:new`);
      }
      setWikiEditorOpen(false);
      setNotice("Wiki 页面已保存并重新建立索引。" );
      await loadDocuments();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法保存 Wiki 页面。" ); }
    finally { setWikiEditorSaving(false); }
  }

  async function archiveSelectedWikiPage() {
    if (!wikiEditor?.document_id || !(await confirm({ title: `归档“${wikiEditor.title}”？`, detail: "之后可以通过数据恢复入口找回。", confirmLabel: "归档页面", danger: true }))) return;
    setWikiEditorSaving(true);
    try {
      await api.archiveWikiPage(wikiEditor.document_id);
      setWikiEditorOpen(false);
      setSelectedId(null);
      setNotice("Wiki 页面已归档。" );
      await loadDocuments();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法归档 Wiki 页面。" ); }
    finally { setWikiEditorSaving(false); }
  }

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

  function selectWikiView(next: WikiView) {
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
      setOrganizePending({
        batch_id: result.batch_id,
        created_at: new Date().toISOString(),
        target_folder: proposal.suggested_folder,
        moves: result.moved,
      });
      setOrganizeProposals([]);
      setNotice(`已把 ${result.moved.length} 份资料收进「${proposal.suggested_folder}」；引用与证据已跟着迁移。`);
      // 台账已经写在服务端了，这里只是把"可撤销"立刻反映到界面上。
      await Promise.all([loadTree(), loadDocuments()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "整理失败。");
    } finally {
      setOrganizeBusy(false);
    }
  }

  async function undoOrganize() {
    setOrganizeBusy(true);
    setError("");
    try {
      const result = await api.undoOrganization();
      setNotice(`已撤销整理，${result.restored.length} 份资料回到原位。`);
      setOrganizePending(null);
      await Promise.all([loadTree(), loadDocuments()]);
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

  async function deleteDocument(document: DocumentSummary) {
    if (!document.managed || deletingId) return;
    setDeletingId(document.document_id);
    setError("");
    setNotice("");
    try {
      const impact = await api.documentImpact(document.document_id);
      const affected = impact.affected_pages.slice(0, 4).map((item) => item.title).join("、");
      const impactMessage = impact.affected_count
        ? `这会影响 ${impact.affected_count} 个 Wiki 页面${affected ? `：${affected}` : ""}。这些页面只会标记为待更新，不会自动删除。`
        : "";
      if (!(await confirm({ title: `归档资料“${document.title || document.source}”？`, detail: <>原文件会移入资料库归档区，并从当前索引移除。{impactMessage && <p>{impactMessage}</p>}</>, confirmLabel: "归档资料", danger: true }))) return;
      await api.deleteDocument(document.document_id);
      setNotice("资料已归档，本地索引已更新；关联 Wiki 已标记为待检查。");
      if (selectedId === document.document_id) {
        setSelectedId(null);
        setSearchParams({}, { replace: true });
      }
      await loadDocuments();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法删除这份资料。");
    } finally {
      setDeletingId(null);
    }
  }

  const selected = documents.find((document) => document.document_id === selectedId);
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

  function extractionStatusLabel(document: DocumentSummary) {
    const status = extractionStatuses[document.document_id];
    switch (effectiveExtractionStatus(document)) {
      case "extracting": return "正在提取";
      case "review": return `待审查 ${status?.pending_count || ""}`.trim();
      case "completed": return "已提取";
      case "failed": return "提取失败";
      case "stale": return "内容已更新";
      default: return "尚未提取";
    }
  }
  function textExtractionLabel(document: DocumentSummary) {
    switch (document.extraction_status) {
      case "empty": return "无可检索文本";
      case "partial": return `部分可检索（${document.extraction_extracted_units ?? 0}/${document.extraction_total_units ?? 0}）`;
      case "error": return "提取失败";
      default: return null;
    }
  }
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

  return (
    <section className="page-scroll" ref={pageRef}>
      <div className="page-container library-container">
        <header className="library-toolbar">
          <div className="library-toolbar-context">
            <Library size={18} aria-hidden="true" />
            <div>
              <span>{collection === "wiki" ? "历史整理" : "资料库"}</span>
              {collection === "material" && libraries.filter((item) => item.available).length > 0 ? (
                <DropdownSelect ariaLabel="切换资料库" value={activeLibrary?.library_id || ""} onChange={(value) => void switchLibrary(value)} options={libraries.filter((item) => item.available).map((library) => ({ value: library.library_id, label: library.name }))} />
              ) : <strong>{collection === "wiki" ? activeLibrary?.name || "资料库" : "尚未创建资料库"}</strong>}
            </div>
          </div>
          <div className="library-toolbar-actions">
            {collection === "wiki" && <button className="quiet-button" onClick={() => selectCollection("material")}>返回资料</button>}
            {activeLibrary && <IconButton label="刷新资料" onClick={() => void loadDocuments()}><RefreshCw size={16} /></IconButton>}
            {collection === "material" && activeLibrary && (
              <button className="quiet-button" type="button" disabled={syncingFolder} onClick={() => void syncLibraryFolder()}>
                <FolderOpen size={15} />{syncingFolder ? "正在同步文件夹…" : "同步文件夹"}
              </button>
            )}
            <details className="library-more-menu">
              <summary><MoreHorizontal size={17} /><span>更多</span></summary>
              <div>
                {collection === "material" && <button type="button" onClick={() => selectCollection("wiki")}>历史整理</button>}
                <button type="button" onClick={() => openLibrarySetup()}><Settings2 size={15} />资料库管理</button>
              </div>
            </details>
            {collection === "material" && <button className="primary-button" disabled={documentImporting} onClick={startDocumentImport}><Upload size={16} />{documentImporting ? "正在建立索引" : "导入资料"}</button>}
          </div>
        </header>
        {syncSummary && (
          <section className="library-sync-summary" role="status" aria-live="polite">
            <div className="library-sync-line">
              <CheckCircle2 size={17} />
              <span>
                已扫描 {syncSummary.scanned_files} 份资料：新增 {syncSummary.added_files.length}、更新 {syncSummary.changed_files}、移除{" "}
                {syncSummary.removed_files.length}
                {syncSummary.pending_removal.length > 0 ? `、待确认移除 ${syncSummary.pending_removal.length}` : ""}
                、跳过 {syncSummary.skipped_files.length}（仓库元文件）
                {syncSummary.error_files > 0 ? `、失败 ${syncSummary.error_files}` : ""}
              </span>
              <button className="quiet-button" type="button" onClick={() => setSyncSummary(null)}>收起</button>
            </div>
            {syncSummary.scan_incomplete && (
              <p className="library-sync-warning">
                本次扫描看不全，因此没有移除任何资料：{syncSummary.incomplete_reasons.join("；") || "原因未提供"}
              </p>
            )}
            <details className="library-sync-details">
              <summary>查看明细</summary>
              <div>
                <SyncSourceList title="新增" sources={syncSummary.added_files} />
                <SyncSourceList title="移除" sources={syncSummary.removed_files} />
                <SyncSourceList
                  title="内容与现存资料相同（可能是移动或改名）"
                  sources={syncSummary.duplicates_cleaned}
                />
                <SyncSourceList title="待确认移除（连续两次缺失才真正移除）" sources={syncSummary.pending_removal} />
                <SyncSourceList title="跳过（仓库元文件）" sources={syncSummary.skipped_files} />
                {syncSummary.errors.length > 0 && (
                  <div className="library-sync-group">
                    <strong>失败 {syncSummary.errors.length}</strong>
                    <ul>
                      {syncSummary.errors.slice(0, 20).map((item, index) => (
                        <li key={`${item.source || "unknown"}-${index}`}>{item.source || "（未知来源）"}：{item.error || "原因未提供"}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </details>
          </section>
        )}
        {collection === "wiki" && <div className="wiki-view-tabs" role="tablist" aria-label="Wiki 页面类型">
          <button role="tab" aria-selected={wikiView === "knowledge"} className={wikiView === "knowledge" ? "active" : ""} onClick={() => selectWikiView("knowledge")}>知识页</button>
          <button role="tab" aria-selected={wikiView === "sources"} className={wikiView === "sources" ? "active" : ""} onClick={() => selectWikiView("sources")}>资料索引</button>
          <button role="tab" aria-selected={wikiView === "all"} className={wikiView === "all" ? "active" : ""} onClick={() => selectWikiView("all")}>全部</button>
        </div>}
        {wikiPlanOpen && !wikiPlan && <section className="wiki-plan-compose" aria-label="创建 Wiki 整理计划">
          <div className="wiki-plan-compose-copy">
            <span>{collection === "wiki" ? "Update Wiki" : "Generate Wiki"}</span>
            <h3>{collection === "wiki" ? "根据原始资料更新当前页面" : "建立可追溯的全库 Wiki"}</h3>
            <p>{collection === "wiki"
              ? `当前页面：${selected?.title || "未选择"}`
              : wikiScopeMode === "uncovered"
                ? `将处理 ${uncoveredCount} 份未覆盖或已变化资料，每批最多 5 份`
                : wikiScopeMode === "selected_only"
                  ? `严格使用已选择的 ${selectedDocumentIds.length} 份资料`
                  : wikiScopeMode === "course"
                    ? `整理课程：${selected?.course || "请选择带课程信息的资料"}`
                    : `全库检索，并优先参考已选择的 ${selectedDocumentIds.length} 份资料`}</p>
          </div>
          {collection === "material" && <label className="wiki-scope-field">
            <span>整理范围</span>
            <DropdownSelect ariaLabel="整理范围" value={wikiScopeMode} onChange={(value) => setWikiScopeMode(value as WikiScopeMode)} options={[{ value: "uncovered", label: "所有未覆盖或已变化资料" }, { value: "smart_library", label: "智能全库（选择项作为重点）" }, ...(selectedDocumentIds.length > 0 ? [{ value: "selected_only", label: `严格仅选中（${selectedDocumentIds.length} 份）` }] : []), ...(selected?.course ? [{ value: "course", label: `课程：${selected.course}` }] : [])]} />
          </label>}
          {collection === "material" && <label className="wiki-scope-field">
            <span>整理深度</span>
            <DropdownSelect ariaLabel="整理深度" value={wikiGenerationMode} onChange={(value) => { setWikiGenerationMode(value as WikiGenerationMode); setWikiEstimate(null); }} options={[{ value: "catalog", label: "快速建档（不调用模型）" }, { value: "standard", label: "标准整理（下一批 5 份）" }, { value: "deep", label: "深度整理（完整范围）" }]} />
          </label>}
          {collection === "material" && wikiScopeMode === "smart_library" && <label>
            <span>主题或目标</span>
            <input value={wikiTopic} onChange={(event) => setWikiTopic(event.target.value)} placeholder="例如：LangChain Agent 与工具调用" />
          </label>}
          <label>
            <span>整理要求</span>
            <textarea value={wikiInstruction} onChange={(event) => setWikiInstruction(event.target.value)} placeholder="例如：重点整理核心概念、适用条件和常见误区" rows={3} />
          </label>
          {wikiEstimate && <section className="wiki-run-estimate" aria-label="Wiki 整理估算">
            <div><span>采用资料</span><strong>{wikiEstimate.document_count}</strong><small>{wikiEstimate.batch_count} 个批次</small></div>
            <div><span>预计页面</span><strong>{wikiEstimate.estimated_pages[0]}–{wikiEstimate.estimated_pages[1]}</strong><small>资料索引与知识页</small></div>
            <div><span>模型请求</span><strong>{wikiEstimate.request_range[0]}–{wikiEstimate.request_range[1]}</strong><small>{wikiEstimate.generation_mode === "catalog" ? "不会调用模型" : `${wikiEstimate.provider} · ${wikiEstimate.model}`}</small></div>
            <div><span>Token 范围</span><strong>{Math.round((wikiEstimate.input_token_range[0] + wikiEstimate.output_token_range[0]) / 1000)}k–{Math.ceil((wikiEstimate.input_token_range[1] + wikiEstimate.output_token_range[1]) / 1000)}k</strong><small>输入与输出合计</small></div>
            <div><span>预计耗时</span><strong>{Math.ceil(wikiEstimate.duration_range_seconds[0] / 60)}–{Math.max(1, Math.ceil(wikiEstimate.duration_range_seconds[1] / 60))} 分钟</strong><small>{wikiEstimate.historical_sample_size ? `${wikiEstimate.historical_sample_size} 次同模型请求 · ${wikiEstimate.confidence === "high" ? "较高" : wikiEstimate.confidence === "medium" ? "中等" : "较低"}可信度` : "没有可用历史样本"}</small></div>
            {wikiEstimate.generation_mode !== "catalog" && <p>这是范围估算，不是账单。本地草稿缓存尚未计入，命中时实际请求和耗时会更低；完成后以运行卡显示的真实用量为准。</p>}
          </section>}
          <footer>
            <button className="quiet-button" disabled={wikiPlanLoading} onClick={() => setWikiPlanOpen(false)}>取消</button>
            {wikiEstimate ? <button className="primary-button" disabled={wikiPlanLoading} onClick={() => void startEstimatedWiki()}><Sparkles size={16} />{wikiPlanLoading ? "正在启动" : "确认并开始"}</button> : <button className="primary-button" disabled={wikiPlanLoading} onClick={() => void planWiki()}><Sparkles size={16} />{wikiPlanLoading ? "正在估算" : collection === "wiki" ? "在对话中生成更新计划" : "查看耗时与消耗"}</button>}
          </footer>
        </section>}
        {wikiPlan && <WikiPlanCard
          plan={wikiPlan}
          busy={wikiPlanLoading}
          onApply={wikiPlan.status === "planned" ? () => void applyWikiPlan() : undefined}
          onKeepExisting={wikiPlan.status === "planned" && wikiPlan.staging?.length ? () => void recoverWikiPlan("keep_existing") : undefined}
          onRegenerate={wikiPlan.status === "planned" && wikiPlan.staging?.length ? () => void recoverWikiPlan("regenerate") : undefined}
          onUndo={wikiPlan.status === "applied" && wikiPlan.checkpoint_id ? () => void undoWikiPlan() : undefined}
          onResume={["paused_budget", "cancelled", "failed"].includes(wikiPlan.status) ? () => void resumeWikiPlan() : undefined}
          onCatalog={["paused_budget", "cancelled", "failed"].includes(wikiPlan.status) ? () => void startEstimatedWiki("catalog") : undefined}
          onSwitchProvider={wikiPlan.status === "failed" ? openWikiProviderSettings : undefined}
          onContinue={wikiPlan.status === "applied" && wikiPlan.remaining_document_ids?.length ? () => void continueWikiBatch() : undefined}
          onClose={() => { setWikiPlan(null); setWikiPlanOpen(false); }}
        />}
        {collection === "wiki" && maintenanceOpen && <section className="wiki-maintenance" aria-label="Wiki 维护">
          <header><div><span>Wiki Maintenance</span><h3>维护 Wiki</h3><p>结构问题由程序检查，矛盾、过时内容和知识缺口由 AI 作为候选提出；任何修复都需要再次确认。</p></div><IconButton label="关闭 Wiki 维护" onClick={() => setMaintenanceOpen(false)}><X size={17} /></IconButton></header>
          {maintenanceLoading && !wikiHealth ? <LoadingState label="正在检查 Wiki…" /> : wikiHealth && <>
            <div className="wiki-health-summary">
              <div><strong>{wikiHealth.total_pages}</strong><span>规范页面</span></div>
              <div><strong>{wikiHealth.orphan_count}</strong><span>孤立页</span></div>
              <div><strong>{wikiHealth.broken_link_count}</strong><span>断链</span></div>
              <div><strong>{wikiHealth.stale_count}</strong><span>过期页</span></div>
            </div>
            <div className={`wiki-health-state ${wikiHealth.healthy ? "healthy" : "attention"}`}><ShieldCheck size={17} /><span>{wikiHealth.healthy ? "Wiki 结构正常" : "发现需要检查的结构问题"}</span><small>{wikiHealth.vaults.map((item) => item.vault).join(" · ") || "尚未发现 Wiki 目录"}</small></div>
            {(!wikiHealth.healthy || (wikiHealth.semantic_candidate_count || 0) > 0) && <details className="wiki-health-details"><summary>查看问题详情</summary><div>{wikiHealth.vaults.map((vault) => <section key={vault.vault}><strong>{vault.vault}</strong>{vault.orphans.length > 0 && <p>孤立页：{vault.orphans.slice(0, 6).join("、")}</p>}{vault.broken_links.length > 0 && <p>断链：{vault.broken_links.slice(0, 6).map((item) => item.target).join("、")}</p>}{vault.stale.length > 0 && <p>过期页：{vault.stale.slice(0, 6).join("、")}</p>}{(vault.duplicate_candidates?.length || 0) > 0 && <p>重复候选：{vault.duplicate_candidates!.slice(0, 4).map((item) => item.canonical_title).join("、")}</p>}{(vault.semantic_candidates?.length || 0) > 0 && <p>AI 审核候选：{vault.semantic_candidates!.slice(0, 4).map((item) => item.reason).join("；")}</p>}{vault.errors.length > 0 && <p>读取错误：{vault.errors.slice(0, 3).join("；")}</p>}</section>)}</div></details>}
          </>}
          {wikiTasks.some((task) => task.status === "failed") && <section className="wiki-task-list" aria-label="失败的 Wiki 任务"><strong>需要处理的任务</strong>{wikiTasks.filter((task) => task.status === "failed").slice(0, 4).map((task) => <div key={task.task_id}><span><b>{task.operation === "plan" ? "生成计划" : "写入 Wiki"}</b><small>{task.error || "任务未完成"}</small></span><span>{task.retryable && <button className="quiet-button" disabled={maintenanceLoading} onClick={() => void retryWikiTask(task.task_id)}>重试</button>}<button className="icon-button" aria-label="取消任务" disabled={maintenanceLoading} onClick={() => void cancelWikiTask(task.task_id)}><X size={14} /></button></span></div>)}</section>}
          {repairPlan && <section className="wiki-repair-plan" aria-label="Wiki 修复计划"><header><div><strong>修复计划已准备</strong><small>{repairPlan.items.length} 个检查项 · {repairPlan.items.filter((item) => item.execution === "local" && item.status === "pending").length} 项可本地安全处理</small></div><span>{repairPlan.status === "applied" ? "已完成" : repairPlan.status === "partial" ? "部分完成" : "等待确认"}</span></header><div>{repairPlan.items.slice(0, 12).map((item) => <div key={item.item_id}><span><b>{item.title}</b><small>{item.execution === "local" ? "本地修复" : item.execution === "ai" ? "需要 AI 审核" : "需要人工确认"}</small></span><span>{item.page_id && item.execution !== "local" && <button className="quiet-button" onClick={() => void openWikiEditor(item.page_id || undefined)}>打开页面处理</button>}<i>{item.status === "applied" ? "已修复" : item.status === "ready" ? "候选已准备" : "待处理"}</i></span></div>)}</div>{repairPlan.ai_review?.length ? <div className="wiki-ai-review">{repairPlan.ai_review.slice(0, 6).map((item, index) => <article key={`${item.issue_type || "review"}-${index}`}><strong>{item.pages?.join("、") || "Wiki 审核候选"}</strong><p>{item.reason || item.suggestion || "请打开相关页面核对后再修改。"}</p></article>)}</div> : null}<footer>{repairPlan.items.some((item) => item.execution === "ai" && item.status === "pending") && <button className="quiet-button" disabled={maintenanceLoading} onClick={() => void draftRepairPlan()}><Sparkles size={15} />生成 AI 审核候选 · 约 1 次请求</button>}<button className="primary-button" disabled={maintenanceLoading || !repairPlan.items.some((item) => item.execution === "local" && item.status === "pending")} onClick={() => void applyRepairPlan()}><ShieldCheck size={15} />应用本地安全修复</button></footer></section>}
          <footer><button className="quiet-button" disabled={maintenanceLoading} onClick={() => void checkWiki()}><RefreshCw size={15} />重新检查</button><button className="quiet-button" disabled={maintenanceLoading} onClick={() => void reviewWikiSemantics()}><Sparkles size={15} />AI 语义检查</button><button className="primary-button" disabled={maintenanceLoading} onClick={() => void organizeWiki()}><Wrench size={15} />{maintenanceLoading ? "正在生成" : "生成修复计划"}</button></footer>
        </section>}
        {wikiEditorOpen && wikiEditor && <Modal onClose={() => setWikiEditorOpen(false)} ariaLabel={wikiEditor.document_id ? "编辑 Wiki 页面" : "新建个人笔记"} className="wiki-editor" backdropClassName="wiki-editor-backdrop">
            <header><div><span>{wikiEditor.page_type === "wiki_note" ? "Personal Note" : "Wiki Page"}</span><h3>{wikiEditor.document_id ? "编辑页面" : "新建个人笔记"}</h3><p>{wikiEditor.managed_by === "mixed" ? "这页包含你的手写修改，后续 AI 更新会先展示差异。" : "来源与系统字段保持只读，正文由你决定。"}</p></div><IconButton label="关闭编辑器" onClick={() => setWikiEditorOpen(false)}><X size={18} /></IconButton></header>
            <div className="wiki-editor-toolbar"><div role="tablist" aria-label="编辑模式"><button className={!wikiEditorPreview ? "active" : ""} onClick={() => setWikiEditorPreview(false)}>编辑</button><button className={wikiEditorPreview ? "active" : ""} onClick={() => setWikiEditorPreview(true)}>预览</button></div><small>修订 {wikiEditor.content_revision} · {wikiEditor.generated_by === "user" ? "个人笔记" : wikiEditor.managed_by === "mixed" ? "AI 与你共同维护" : "AI 整理页"}</small></div>
            <main>{wikiEditorPreview ? <article className="reader-prose wiki-editor-preview"><h1>{wikiEditor.title || "未命名笔记"}</h1><ReactMarkdown remarkPlugins={[remarkGfm]}>{wikiEditor.body || "还没有正文。"}</ReactMarkdown></article> : <div className="wiki-editor-fields"><label><span>标题</span><input value={wikiEditor.title} maxLength={160} onChange={(event) => updateWikiEditor({ title: event.target.value })} /></label><label><span>标签</span><input value={wikiEditor.tags.join("，")} onChange={(event) => updateWikiEditor({ tags: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })} placeholder="学习，概念" /></label><label><span>关联页面</span><input value={wikiEditor.related.join("，")} onChange={(event) => updateWikiEditor({ related: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })} placeholder="用页面标题建立关联" /></label><label className="wide"><span>Markdown 正文</span><textarea value={wikiEditor.body} onChange={(event) => updateWikiEditor({ body: event.target.value })} rows={18} /></label></div>}</main>
            <footer>{wikiEditor.document_id && <button className="danger-text-button" disabled={wikiEditorSaving} onClick={() => void archiveSelectedWikiPage()}><Trash2 size={15} />归档</button>}<div><button className="quiet-button" disabled={wikiEditorSaving} onClick={() => setWikiEditorOpen(false)}>取消</button><button className="primary-button" disabled={wikiEditorSaving || !wikiEditor.title.trim() || !wikiEditor.body.trim()} onClick={() => void saveWikiEditor()}><Save size={15} />{wikiEditorSaving ? "正在保存" : "保存页面"}</button></div></footer>
        </Modal>}
        {confirmElement}
        {(documentImportNotice || notice) && <div className="success-notice"><CheckCircle2 size={17} />{documentImportNotice || notice}</div>}
        {documentImportError && <ErrorNotice message={documentImportError} />}
        {error && <ErrorNotice message={error} action={<button className="quiet-button" onClick={() => void loadDocuments()}>重试</button>} />}
        {loading ? <div className="illustrated-loading"><BrandIllustration state="reading" size={76} /><LoadingState label={collection === "wiki" ? "正在整理 Wiki…" : "正在读取本地资料…"} /></div> : documents.length ? (
          <div
            className={
              "library-workspace"
              + (collection === "material" ? " list-only" : "")
              + (collection === "material" && tree ? " with-tree" : "")
              // ④：**真正打开了标签页**才算"在读"——页面自动选中第一份资料不算，
              // 否则一进资料库窄窗口就把列表（含搜索）藏起来，用户会以为资料没了。
              + (readingOpen ? " reading" : "")
            }
          >
            {collection === "material" && tree && (
              <aside className="library-tree-pane" aria-label="资料库文件夹">
                <div className="rail-label"><FolderOpen size={15} />文件夹</div>
                <LibraryTree
                  tree={tree}
                  query={documentQuery}
                  selectedFolder={selectedFolder}
                  onSelectFolder={setSelectedFolder}
                  activeDocumentId={selectedId}
                  onOpenDocument={(documentId) => selectDocument(documentId)}
                  onMoveDocument={(documentId, path) => void moveDocument(documentId, path)}
                  onArchiveDocument={(documentId, title) => void archiveDocument(documentId, title)}
                  onCreateFolder={(path) => void createFolder(path)}
                  onDeleteFolder={(path) => void deleteFolder(path)}
                />
                {collection === "material" && (
                  <details className="library-organize">
                    <summary>整理建议</summary>
                    <div>
                      {organizeProposals === null ? (
                        <>
                          <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void loadOrganizeProposals()}>
                            看看有什么可以整理的
                          </button>
                          <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void loadAiProposals()}>
                            让 AI 归类
                          </button>
                        </>
                      ) : organizeProposals.length === 0 ? (
                        <p className="text-faint">资料库已经很整齐了。</p>
                      ) : (
                        <>
                        <p className="text-faint">
                          {organizeSource === "model"
                            ? "AI 提议 —— 执行前由你确认，执行后可一键撤销。"
                            : organizeDegraded
                              ? "模型这次没能参与，下面是规则建议 —— 执行前由你确认，执行后可一键撤销。"
                              : "规则建议 —— 执行前由你确认，执行后可一键撤销。"}
                        </p>
                        {organizeProposals.map((proposal) => (
                          <div key={proposal.kind}>
                            <strong>{proposal.title}（{proposal.items.length} 份）</strong>
                            <p>{proposal.reason}</p>
                            <ul>
                              {proposal.items.slice(0, 8).map((item) => <li key={item}>{item}</li>)}
                              {proposal.items.length > 8 && <li className="text-faint">…… 其余 {proposal.items.length - 8} 份</li>}
                            </ul>
                            <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void applyProposal(proposal)}>
                              收进「{proposal.suggested_folder}」
                            </button>
                          </div>
                        ))}
                        </>
                      )}
                    </div>
                  </details>
                )}
                {collection === "material" && organizePending && (
                  <div className="library-organize-undo">
                    <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void undoOrganize()}>
                      撤销这一步整理
                    </button>
                    <small className="text-faint">
                      上一步：{organizePending.moves.length} 份资料收进「{organizePending.target_folder}」
                    </small>
                  </div>
                )}
                {archive.length > 0 && (
                  <details className="library-archive">
                    <summary>已归档 {archive.length} 份</summary>
                    <ul>
                      {archive.slice(0, 30).map((entry) => (
                        <li key={entry.entry_id}>
                          <span title={entry.original_path}>{entry.title || entry.original_path}</span>
                          <button className="quiet-button" type="button" onClick={() => void restoreArchived(entry.entry_id)}>
                            恢复
                          </button>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </aside>
            )}
            <aside className="document-rail">
              <div className="rail-label"><FolderOpen size={15} />{collection === "wiki" ? wikiView === "knowledge" ? "知识页面" : wikiView === "sources" ? "资料索引" : wikiView === "notes" ? "个人笔记" : "全部页面" : "我的资料"} <span>{filteredDocuments.length}</span></div>
              <label className="document-search"><Search size={14} /><input value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder="搜索资料" aria-label="搜索资料" /></label>
              {hits.length > 0 && (
                <div className="document-hits" aria-label="原文命中">
                  {hits.map((hit) => (
                    <button
                      key={hit.chunk_id}
                      className="document-hit"
                      type="button"
                      title={hit.text || ""}
                      onClick={() =>
                        navigate(
                          readerLocation({
                            document_id: hit.document_id,
                            collection: hit.collection ?? collection,
                            chunk_id: hit.chunk_id,
                          }) || "/library",
                        )
                      }
                    >
                      <Search size={13} />
                      <span>
                        <strong>{hit.title || hit.source}</strong>
                        <small>{(hit.text || "").replace(/\s+/g, " ").slice(0, 56)}</small>
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {filteredDocuments.map((document) => (
                <div className={`document-row-wrap ${selectedId === document.document_id ? "active" : ""}`} key={document.document_id}>
                  <button className="document-row" onClick={() => selectDocument(document.document_id)}>
                    <span className="document-kind"><FileText size={17} /></span>
                    <span><strong>{document.title || document.source}</strong><small>{collection === "wiki" ? (document.wiki_type ? wikiTypeLabels[document.wiki_type] : "历史整理") : document.course || (document.origin === "legacy_index" ? "已有知识库" : document.kind || "资料")} · {document.chunk_count ? `${document.chunk_count} 个片段` : formatRelativeDate(document.updated_at)}</small></span>
                    {collection === "material" ? (
                      <>
                        <span
                          className={`document-extraction-state ${effectiveExtractionStatus(document)}`}
                          title={extractionStatusLabel(document)}
                        >
                          {extractionStatusLabel(document)}
                        </span>
                        {textExtractionLabel(document) && (
                          <span className={`document-text-extraction ${document.extraction_status}`} title={`文本提取：${textExtractionLabel(document)}`}>
                            {textExtractionLabel(document)}
                          </span>
                        )}
                      </>
                    ) : (
                      <i className={document.vector_status === "error" ? "error" : "ready"} title={document.vector_status || "已建立索引"} />
                    )}
                  </button>
                  {collection === "material" && (document.kind === "md" || document.kind === "txt" || document.kind === "markdown") && <IconButton className="document-edit" label={`编辑 ${document.title || document.source}`} onClick={(event) => { event.stopPropagation(); setEditingDocumentId(document.document_id); }}><Pencil size={14} /></IconButton>}
                  {collection === "material" && document.managed && <IconButton className="document-delete" label={`删除 ${document.title || document.source}`} disabled={deletingId === document.document_id} onClick={() => void deleteDocument(document)}><Trash2 size={14} /></IconButton>}
                </div>
              ))}
              {!filteredDocuments.length && <p className="document-search-empty">没有找到匹配的资料。</p>}
            </aside>
            {/* ④：标签条和阅读区必须是**同一个网格列**。标签条曾经是 .library-workspace 的
                第 4 个直接子元素，一开标签 3 列网格就自动换行：阅读区被挤到下一行，
                列表被顶到阅读区的位置（2026-09-24 用户截图发现的布局塌陷）。
                没有选中资料又没有标签时整列不渲染 —— 否则会留一条空白栏。 */}
            {(selected || openIds.length > 0) && (
            <div className="library-reader-column">
            {openIds.length > 0 && (
              <div className="reader-tabs" role="tablist" aria-label="打开的资料">
                {openIds.map((tabId) => (
                  <span key={tabId} className={selectedId === tabId ? "reader-tab active" : "reader-tab"}>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedId === tabId}
                      onClick={() => {
                        selectDocument(tabId);
                      }}
                    >
                      {documents.find((item) => item.document_id === tabId)?.title || tabId}
                    </button>
                    <button
                      type="button"
                      className="reader-tab-close"
                      aria-label={`关闭 ${documents.find((item) => item.document_id === tabId)?.title || tabId}`}
                      onClick={() => {
                        const wasActive = selectedId === tabId;
                        closeTab(tabId);
                        if (wasActive) {
                          const remaining = openIds.filter((item) => item !== tabId);
                          const index = openIds.indexOf(tabId);
                          const next = remaining[index] ?? remaining[index - 1];
                          if (next) selectDocument(next);
                          else setSelectedId(null);
                        }
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <article className="document-reader">
              {selected && <header>
                <span>{selected.collection === "wiki" ? `历史整理 · ${selected.wiki_type ? wikiTypeLabels[selected.wiki_type] : "页面"}` : selected.kind || "本地资料"}{selected.course ? ` · ${selected.course}` : ""}</span>
                <h2>{selected.title || selected.source}</h2>
                {selected.collection === "material" && <div className="reader-actions">
                  <button className="quiet-button library-list-toggle" onClick={() => setSelectedId(null)}><List size={15} />资料列表</button>
                  {effectiveExtractionStatus(selected) === "not_started" && (
                    <button className="primary-button reader-extract" disabled={startingExtractionId === selected.document_id || !sections.length} onClick={() => void extractAndReview(selected)}><Sparkles size={15} />{startingExtractionId === selected.document_id ? "正在启动…" : "提取概念"}</button>
                  )}
                  {effectiveExtractionStatus(selected) === "extracting" && (
                    <button className="quiet-button reader-extract status-extracting" onClick={() => openExtractionReview(selected, extractionStatuses[selected.document_id]!) }><RefreshCw size={15} />正在提取 · 查看进度</button>
                  )}
                  {effectiveExtractionStatus(selected) === "review" && (
                    <button className="primary-button reader-extract" onClick={() => openExtractionReview(selected, extractionStatuses[selected.document_id]!) }><Sparkles size={15} />审查概念 · {extractionStatuses[selected.document_id]?.pending_count || 0}</button>
                  )}
                  {effectiveExtractionStatus(selected) === "completed" && (
                    <button className="quiet-button reader-extract status-completed" onClick={() => navigate("/knowledge-map")}><CheckCircle2 size={15} />已提取 · 查看图谱</button>
                  )}
                  {(effectiveExtractionStatus(selected) === "failed" || effectiveExtractionStatus(selected) === "stale") && (
                    <button className="primary-button reader-extract" disabled={startingExtractionId === selected.document_id || !sections.length} onClick={() => void extractAndReview(selected, true)}><RefreshCw size={15} />{effectiveExtractionStatus(selected) === "failed" ? "重新尝试" : "重新提取"}</button>
                  )}
                  <button className="quiet-button" onClick={askAboutDocument}><MessageCircle size={15} />基于此文档提问</button>
                  {(selected.kind === "md" || selected.kind === "txt" || selected.kind === "markdown" || selected.kind === "course_document" || selected.kind === "obsidian_note") && (
                    <button className="quiet-button" onClick={() => setEditingDocumentId(selected.document_id)}><Pencil size={15} />编辑</button>
                  )}
                  {["review", "completed"].includes(effectiveExtractionStatus(selected)) && (
                    <details className="reader-extract-more">
                      <summary className="icon-button" aria-label="更多概念操作" title="更多概念操作"><MoreHorizontal size={16} /></summary>
                      <div>
                        {!!extractionStatuses[selected.document_id]?.run.failed_sections?.length && <button onClick={() => void retryFailedSections(selected)}><RefreshCw size={14} />只重试失败章节</button>}
                        <button onClick={() => void extractAndReview(selected, true)}><RefreshCw size={14} />重新提取</button>
                      </div>
                    </details>
                  )}
                </div>}
                {selected.summary && <p>{selected.summary}</p>}
              </header>}
              {selected && (
                <DocumentReader
                  key={selected.document_id}
                  documentId={selected.document_id}
                  collection={selected.collection === "wiki" ? "wiki" : "material"}
                  chunkId={searchParams.get("chunk")}
                  documentSummary={selected}
                  scrollRef={pageRef}
                  onError={setError}
                  onSectionsLoaded={setSections}
                  reloadToken={readerReloadToken}
                />
              )}
            </article>
            </div>
            )}
          </div>
        ) : (
          <EmptyState state={collection === "wiki" ? "listening" : "reading"}
            title={collection === "wiki" ? "还没有 Wiki 页面" : "先放进第一份学习资料"}
            description={collection === "wiki" ? "从学习资料生成的概念与实体会整理在这里。" : "支持 Markdown、PDF、Word 和 PowerPoint。没有资料库也没关系，选择文件后会继续引导。"}
            action={collection === "material" ? <div className="library-empty-actions"><button className="primary-button" onClick={startDocumentImport}><FilePlus2 size={17} />导入资料</button><button className="quiet-button" onClick={() => openLibrarySetup({ initialMode: "open" })}><FolderOpen size={16} />打开或接入已有资料库</button></div> : undefined}
          />
        )}
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
