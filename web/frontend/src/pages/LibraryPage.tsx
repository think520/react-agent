import { useEffect, useRef, useState } from "react";
import { CheckCircle2, CheckSquare2, Edit3, FilePlus2, FileText, FolderOpen, Library, Plus, Quote, RefreshCw, Save, Search, Settings2, ShieldCheck, Sparkles, Square, Trash2, Upload, Wrench, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { BrandIllustration, EmptyState, ErrorNotice, IconButton, LoadingState, formatRelativeDate } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { api } from "../lib/api";
import type { DocumentSection, DocumentSummary, WikiDocumentCoverage, WikiEditablePage, WikiGenerationMode, WikiHealth, WikiPlan, WikiRepairPlan, WikiRunEstimate, WikiScopeMode, WikiTask } from "../types";

export function LibraryPage() {
  const {
    activeLibrary,
    settings,
    refreshSettings,
    libraries,
    openLibrarySetup,
    switchLibrary,
    startDocumentImport,
    documentImporting,
    documentImportNotice,
    documentImportError,
    documentImportVersion,
    selectedDocumentIds,
    toggleDocumentScope,
    setDocumentScope,
  } = useOutletContext<AppOutletContext>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [collection, setCollection] = useState<"material" | "wiki">(
    searchParams.get("collection") === "wiki" ? "wiki" : "material",
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sections, setSections] = useState<DocumentSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [highlightedChunk, setHighlightedChunk] = useState<string | null>(null);
  const [documentQuery, setDocumentQuery] = useState("");
  const [selectionQuote, setSelectionQuote] = useState("");
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [wikiHealth, setWikiHealth] = useState<WikiHealth | null>(null);
  const [wikiPlan, setWikiPlan] = useState<WikiPlan | null>(null);
  const [wikiPlanOpen, setWikiPlanOpen] = useState(false);
  const [wikiPlanLoading, setWikiPlanLoading] = useState(false);
  const [wikiEstimate, setWikiEstimate] = useState<WikiRunEstimate | null>(null);
  const [wikiGenerationMode, setWikiGenerationMode] = useState<WikiGenerationMode>(settings?.preferences.wiki?.default_mode || "standard");
  const [repairPlan, setRepairPlan] = useState<WikiRepairPlan | null>(null);
  const [guideOpen, setGuideOpen] = useState(() => !settings?.preferences.wiki?.guide_completed);
  const [wikiEditorOpen, setWikiEditorOpen] = useState(false);
  const [wikiEditorPreview, setWikiEditorPreview] = useState(false);
  const [wikiEditor, setWikiEditor] = useState<WikiEditablePage | null>(null);
  const [wikiEditorSaving, setWikiEditorSaving] = useState(false);
  const [wikiTasks, setWikiTasks] = useState<WikiTask[]>([]);
  const [wikiInstruction, setWikiInstruction] = useState("");
  const [wikiTopic, setWikiTopic] = useState("");
  const [wikiScopeMode, setWikiScopeMode] = useState<WikiScopeMode>("uncovered");
  const [wikiCoverage, setWikiCoverage] = useState<Record<string, WikiDocumentCoverage>>({});
  const [bulkCourse, setBulkCourse] = useState("");
  const lastScopeIndexRef = useRef<number | null>(null);
  const pageRef = useRef<HTMLElement>(null);
  const readingOpenedRef = useRef(false);
  const lastProgressRef = useRef(0);

  async function loadDocuments() {
    if (!activeLibrary) {
      setDocuments([]);
      setSelectedId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [loadedDocuments, coverageResult] = await Promise.all([
        api.documents(collection),
        collection === "material" ? api.wikiCoverage().catch(() => ({ documents: [], counts: {} })) : Promise.resolve({ documents: [], counts: {} }),
      ]);
      const coverage = Object.fromEntries(coverageResult.documents.map((item) => [item.document_id, item]));
      const nextDocuments = loadedDocuments.map((document) => ({ ...document, wiki_coverage: coverage[document.document_id] }));
      setWikiCoverage(coverage);
      setDocuments(nextDocuments);
      const requested = searchParams.get("document");
      const requestedTitle = searchParams.get("title");
      const nextSelected = nextDocuments.find((item) => item.document_id === requested)?.document_id
        || nextDocuments.find((item) => item.title === requestedTitle)?.document_id
        || nextDocuments.find((item) => item.document_id === selectedId)?.document_id
        || nextDocuments[0]?.document_id
        || null;
      setSelectedId(nextSelected);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取资料库。" );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadDocuments(); }, [activeLibrary?.library_id, collection, documentImportVersion]);

  useEffect(() => {
    if (!wikiPlan || wikiPlan.status !== "planning") return;
    const timer = window.setInterval(() => {
      void api.wikiRun(wikiPlan.run_id || wikiPlan.plan_id).then(setWikiPlan).catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [wikiPlan?.plan_id, wikiPlan?.status]);

  useEffect(() => {
    const requestedCollection = searchParams.get("collection") === "wiki" ? "wiki" : "material";
    if (requestedCollection !== collection) setCollection(requestedCollection);
  }, [searchParams]);

  useEffect(() => {
    setSelectionQuote("");
    if (!selectedId) { setSections([]); return; }
    setDetailLoading(true);
    void api.document(selectedId)
      .then((result) => setSections(result.sections))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  useEffect(() => {
    readingOpenedRef.current = false;
    lastProgressRef.current = 0;
    if (!selectedId || detailLoading || !sections.length) return;
    let visibleSeconds = 0;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      visibleSeconds += 1;
      if (visibleSeconds < 10 || readingOpenedRef.current) return;
      readingOpenedRef.current = true;
      void api.updateReadingProgress(selectedId, lastProgressRef.current, true).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [selectedId, detailLoading, sections.length]);

  function recordReadingProgress() {
    const element = pageRef.current;
    if (!element || !selectedId || !readingOpenedRef.current) return;
    const available = element.scrollHeight - element.clientHeight;
    const raw = available > 0 ? Math.round((element.scrollTop / available) * 100) : 100;
    const progress = raw >= 100 ? 100 : Math.floor(raw / 10) * 10;
    if (progress < 10 || progress <= lastProgressRef.current) return;
    lastProgressRef.current = progress;
    void api.updateReadingProgress(selectedId, progress).catch(() => undefined);
  }

  useEffect(() => {
    const chunkId = searchParams.get("chunk");
    if (detailLoading || !chunkId || !sections.length) return;
    const target = Array.from(document.querySelectorAll<HTMLElement>("[data-chunk-id]"))
      .find((element) => element.dataset.chunkId === chunkId);
    if (!target) return;
    setHighlightedChunk(chunkId);
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [detailLoading, searchParams, sections]);

  async function checkWiki() {
    setMaintenanceLoading(true);
    setError("");
    try { setWikiHealth(await api.wikiHealth()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "无法检查 Wiki。" ); }
    finally { setMaintenanceLoading(false); }
  }

  async function openWikiMaintenance() {
    setMaintenanceOpen(true);
    await Promise.all([
      wikiHealth ? Promise.resolve() : checkWiki(),
      api.wikiTasks().then((result) => setWikiTasks(result.tasks)).catch(() => setWikiTasks([])),
    ]);
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
      localStorage.setItem("bobodan:draft:new", command);
      localStorage.setItem("bobodan:wiki-scope", JSON.stringify({
        scopeMode: "selected_only", documentIds: [], wikiDocumentIds, course: null, topic: wikiTopic.trim(),
      }));
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
    if (mode === "deep" && !window.confirm("深度整理会处理完整范围，耗时和 Token 消耗可能明显增加。确认开始？")) return;
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

  async function toggleWikiGuide() {
    const next = !guideOpen;
    setGuideOpen(next);
    if (!next && settings && !settings.preferences.wiki?.guide_completed) {
      try {
        await api.patchPreferences(settings.preferences.revision, { wiki: { guide_completed: true } });
        await refreshSettings();
      } catch { /* The guide can still be collapsed for this session. */ }
    }
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
    if (!wikiEditor?.document_id || !window.confirm(`归档“${wikiEditor.title}”？之后可以通过数据恢复入口找回。`)) return;
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
    setSelectedId(documentId);
    setHighlightedChunk(null);
    setSearchParams({ collection, document: documentId }, { replace: true });
  }

  function selectCollection(next: "material" | "wiki") {
    setCollection(next);
    setSelectedId(null);
    setSections([]);
    setWikiPlan(null);
    setWikiPlanOpen(false);
    setSearchParams({ collection: next }, { replace: true });
  }

  function toggleScopeFromList(documentId: string, index: number, shiftKey: boolean) {
    if (shiftKey && lastScopeIndexRef.current !== null) {
      const start = Math.min(lastScopeIndexRef.current, index);
      const end = Math.max(lastScopeIndexRef.current, index);
      setDocumentScope(Array.from(new Set([
        ...selectedDocumentIds,
        ...filteredDocuments.slice(start, end + 1).map((item) => item.document_id),
      ])));
    } else {
      toggleDocumentScope(documentId);
    }
    lastScopeIndexRef.current = index;
  }

  function selectFilteredDocuments() {
    setDocumentScope(Array.from(new Set([
      ...selectedDocumentIds,
      ...filteredDocuments.map((item) => item.document_id),
    ])));
  }

  function selectCourseDocuments(course: string) {
    setBulkCourse(course);
    if (!course) return;
    setDocumentScope(Array.from(new Set([
      ...selectedDocumentIds,
      ...documents.filter((item) => item.course === course).map((item) => item.document_id),
    ])));
  }

  function captureSelection() {
    const text = window.getSelection()?.toString().trim() || "";
    setSelectionQuote(text.slice(0, 1200));
  }

  function askAboutSelection() {
    if (!selectionQuote || !selected) return;
    localStorage.setItem(
      "bobodan:draft:new",
      `请结合资料《${selected.title || selected.source}》解释下面这段内容：\n\n> ${selectionQuote.replace(/\n/g, "\n> ")}`,
    );
    if (!selectedDocumentIds.includes(selected.document_id) && selected.collection === "material") {
      toggleDocumentScope(selected.document_id);
    }
    navigate("/chat");
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
        ? `\n\n这会影响 ${impact.affected_count} 个 Wiki 页面${affected ? `：${affected}` : ""}。这些页面只会标记为待更新，不会自动删除。`
        : "";
      if (!window.confirm(`归档资料“${document.title || document.source}”？原文件会移入资料库归档区，并从当前索引移除。${impactMessage}`)) return;
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
  const filteredDocuments = documents.filter((document) => {
    const query = documentQuery.trim().toLocaleLowerCase();
    if (!query) return true;
    return [document.title, document.source, document.course, document.kind]
      .some((value) => value?.toLocaleLowerCase().includes(query));
  });
  const courses = Array.from(new Set(documents.map((document) => document.course).filter((value): value is string => Boolean(value)))).sort();
  const uncoveredCount = Object.keys(wikiCoverage).length
    ? Object.values(wikiCoverage).filter((item) => item.status !== "covered").length
    : documents.length;
  const coverageLabels: Record<WikiDocumentCoverage["status"], string> = {
    uncovered: "未整理",
    partial: "部分覆盖",
    covered: "已覆盖",
    stale: "原文已变化",
  };
  const wikiTypeLabels: Record<NonNullable<DocumentSummary["wiki_type"]>, string> = {
    source: "资料摘要",
    entity: "实体",
    concept: "概念",
    analysis: "综合分析",
    question: "问题与发现",
    note: "个人笔记",
  };

  return (
    <section className="page-scroll" ref={pageRef} onScroll={recordReadingProgress}>
      <div className="page-container library-container">
        <header className="page-heading">
          <div><span>Library</span><h2>资料库</h2><p>{collection === "material" ? "把学习材料放在这里，Bobodan 会建立可追踪的本地索引。" : "Wiki 是由 Bobodan 从学习资料中整理出的规范概念页。"}</p></div>
          <div className="heading-actions">
            {activeLibrary && <button className="quiet-button" onClick={() => void loadDocuments()}><RefreshCw size={16} />刷新</button>}
            {collection === "wiki" && <button className="quiet-button" onClick={() => void openWikiEditor()}><Plus size={16} />新建笔记</button>}
            {collection === "wiki" && <button className="quiet-button" onClick={() => void openWikiMaintenance()}><Wrench size={16} />维护 Wiki</button>}
            {collection === "wiki" && <button className="primary-button" disabled={!selectedId || wikiEditorSaving} onClick={() => void openWikiEditor(selectedId || undefined)}><Edit3 size={16} />编辑页面</button>}
            {collection === "material" && documents.length > 0 && <button className="quiet-button" onClick={() => { setWikiScopeMode(uncoveredCount ? "uncovered" : "smart_library"); setWikiPlan(null); setWikiPlanOpen(true); }}><Sparkles size={16} />{uncoveredCount ? `整理未覆盖资料 · ${uncoveredCount}` : "按主题更新 Wiki"}</button>}
            {collection === "material" && <button className="primary-button" disabled={documentImporting} onClick={startDocumentImport}><Upload size={16} />{documentImporting ? "正在建立索引" : "导入资料"}</button>}
          </div>
        </header>
        <section className="library-context-bar" aria-label="当前资料库">
          <div className="library-context-copy">
            <span className="library-context-icon"><Library size={18} /></span>
            <div><span>当前资料库</span><strong>{activeLibrary?.name || "尚未创建资料库"}</strong><small>{activeLibrary ? "资料、Wiki、对话和学习进度保存在这个本地文件夹中" : "导入第一份资料时，Bobodan 会引导你创建保存位置"}</small></div>
          </div>
          <div className="library-context-actions">
            {libraries.filter((item) => item.available).length > 0 && <label className="library-switcher"><span>切换</span><select aria-label="切换资料库" value={activeLibrary?.library_id || ""} onChange={(event) => void switchLibrary(event.target.value)}>{libraries.filter((item) => item.available).map((library) => <option value={library.library_id} key={library.library_id}>{library.name}</option>)}</select></label>}
            <button className="quiet-button" onClick={() => openLibrarySetup()}><Settings2 size={16} />资料库管理</button>
          </div>
        </section>
        <section className={`wiki-guide ${guideOpen ? "open" : "compact"}`} aria-label="Wiki 使用流程">
          <header><div><span>Wiki Workflow</span><strong>资料用于检索，Wiki 用于持续整理和记笔记</strong></div><button className="quiet-button" onClick={() => void toggleWikiGuide()}>{guideOpen ? "收起流程" : "查看流程"}</button></header>
          {guideOpen && <div className="wiki-guide-steps"><div><i>1</i><span><strong>导入资料</strong><small>原始资料保持只读，并直接支持对话检索。</small></span></div><div><i>2</i><span><strong>整理一批</strong><small>默认每次 5 份，开始前先查看耗时和 Token 估算。</small></span></div><div><i>3</i><span><strong>审查计划</strong><small>确认页面与来源后才写入 Wiki。</small></span></div><div><i>4</i><span><strong>学习与维护</strong><small>手写修改、补充笔记，并处理断链或过期内容。</small></span></div></div>}
        </section>
        <div className="library-tabs" role="tablist" aria-label="资料库分类">
          <button role="tab" aria-selected={collection === "material"} className={collection === "material" ? "active" : ""} onClick={() => selectCollection("material")}>学习资料</button>
          <button role="tab" aria-selected={collection === "wiki"} className={collection === "wiki" ? "active" : ""} onClick={() => selectCollection("wiki")}>Wiki</button>
        </div>
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
            <select value={wikiScopeMode} onChange={(event) => setWikiScopeMode(event.target.value as WikiScopeMode)}>
              <option value="uncovered">所有未覆盖或已变化资料</option>
              <option value="smart_library">智能全库（选择项作为重点）</option>
              {selectedDocumentIds.length > 0 && <option value="selected_only">严格仅选中（{selectedDocumentIds.length} 份）</option>}
              {selected?.course && <option value="course">课程：{selected.course}</option>}
            </select>
          </label>}
          {collection === "material" && <label className="wiki-scope-field">
            <span>整理深度</span>
            <select value={wikiGenerationMode} onChange={(event) => { setWikiGenerationMode(event.target.value as WikiGenerationMode); setWikiEstimate(null); }}>
              <option value="catalog">快速建档（不调用模型）</option>
              <option value="standard">标准整理（下一批 5 份）</option>
              <option value="deep">深度整理（完整范围）</option>
            </select>
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
            <div><span>预计页面</span><strong>{wikiEstimate.estimated_pages[0]}–{wikiEstimate.estimated_pages[1]}</strong><small>资料页与概念页</small></div>
            <div><span>模型请求</span><strong>{wikiEstimate.request_range[0]}–{wikiEstimate.request_range[1]}</strong><small>{wikiEstimate.generation_mode === "catalog" ? "不会调用模型" : `${wikiEstimate.provider} · ${wikiEstimate.model}`}</small></div>
            <div><span>预计耗时</span><strong>{Math.ceil(wikiEstimate.duration_range_seconds[0] / 60)}–{Math.max(1, Math.ceil(wikiEstimate.duration_range_seconds[1] / 60))} 分钟</strong><small>{wikiEstimate.rough ? "基于粗略区间" : "基于最近调用"}</small></div>
            {wikiEstimate.generation_mode !== "catalog" && <p>生成 Wiki 会消耗较多 Token，并可能需要较长时间。达到额度上限后会保存草稿并暂停，不会继续扣费。</p>}
          </section>}
          <footer>
            <button className="quiet-button" disabled={wikiPlanLoading} onClick={() => setWikiPlanOpen(false)}>取消</button>
            {wikiEstimate ? <button className="primary-button" disabled={wikiPlanLoading} onClick={() => void startEstimatedWiki()}><Sparkles size={16} />{wikiPlanLoading ? "正在启动" : "确认并开始"}</button> : <button className="primary-button" disabled={wikiPlanLoading} onClick={() => void planWiki()}><Sparkles size={16} />{wikiPlanLoading ? "正在估算" : "查看耗时与消耗"}</button>}
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
        {wikiEditorOpen && wikiEditor && <div className="wiki-editor-backdrop" role="presentation">
          <section className="wiki-editor" role="dialog" aria-modal="true" aria-label={wikiEditor.document_id ? "编辑 Wiki 页面" : "新建个人笔记"}>
            <header><div><span>{wikiEditor.page_type === "wiki_note" ? "Personal Note" : "Wiki Page"}</span><h3>{wikiEditor.document_id ? "编辑页面" : "新建个人笔记"}</h3><p>{wikiEditor.managed_by === "mixed" ? "这页包含你的手写修改，后续 AI 更新会先展示差异。" : "来源与系统字段保持只读，正文由你决定。"}</p></div><IconButton label="关闭编辑器" onClick={() => setWikiEditorOpen(false)}><X size={18} /></IconButton></header>
            <div className="wiki-editor-toolbar"><div role="tablist" aria-label="编辑模式"><button className={!wikiEditorPreview ? "active" : ""} onClick={() => setWikiEditorPreview(false)}>编辑</button><button className={wikiEditorPreview ? "active" : ""} onClick={() => setWikiEditorPreview(true)}>预览</button></div><small>修订 {wikiEditor.content_revision} · {wikiEditor.generated_by === "user" ? "个人笔记" : wikiEditor.managed_by === "mixed" ? "AI 与你共同维护" : "AI 整理页"}</small></div>
            <main>{wikiEditorPreview ? <article className="reader-prose wiki-editor-preview"><h1>{wikiEditor.title || "未命名笔记"}</h1><ReactMarkdown remarkPlugins={[remarkGfm]}>{wikiEditor.body || "还没有正文。"}</ReactMarkdown></article> : <div className="wiki-editor-fields"><label><span>标题</span><input value={wikiEditor.title} maxLength={160} onChange={(event) => updateWikiEditor({ title: event.target.value })} /></label><label><span>标签</span><input value={wikiEditor.tags.join("，")} onChange={(event) => updateWikiEditor({ tags: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })} placeholder="学习，概念" /></label><label><span>关联页面</span><input value={wikiEditor.related.join("，")} onChange={(event) => updateWikiEditor({ related: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })} placeholder="用页面标题建立关联" /></label><label className="wide"><span>Markdown 正文</span><textarea value={wikiEditor.body} onChange={(event) => updateWikiEditor({ body: event.target.value })} rows={18} /></label></div>}</main>
            <footer>{wikiEditor.document_id && <button className="danger-text-button" disabled={wikiEditorSaving} onClick={() => void archiveSelectedWikiPage()}><Trash2 size={15} />归档</button>}<div><button className="quiet-button" disabled={wikiEditorSaving} onClick={() => setWikiEditorOpen(false)}>取消</button><button className="primary-button" disabled={wikiEditorSaving || !wikiEditor.title.trim() || !wikiEditor.body.trim()} onClick={() => void saveWikiEditor()}><Save size={15} />{wikiEditorSaving ? "正在保存" : "保存页面"}</button></div></footer>
          </section>
        </div>}
        {(documentImportNotice || notice) && <div className="success-notice"><CheckCircle2 size={17} />{documentImportNotice || notice}</div>}
        {documentImportError && <ErrorNotice message={documentImportError} />}
        {error && <ErrorNotice message={error} action={<button className="quiet-button" onClick={() => void loadDocuments()}>重试</button>} />}
        {loading ? <div className="illustrated-loading"><BrandIllustration state="reading" size={76} /><LoadingState label={collection === "wiki" ? "正在整理 Wiki…" : "正在读取本地资料…"} /></div> : documents.length ? (
          <div className="library-workspace">
            <aside className="document-rail">
              <div className="rail-label"><FolderOpen size={15} />{collection === "wiki" ? "规范页面" : "我的资料"} <span>{documents.length}</span></div>
              <label className="document-search"><Search size={14} /><input value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder="搜索资料" aria-label="搜索资料" /></label>
              {collection === "material" && <div className="document-bulk-tools">
                <button type="button" onClick={selectFilteredDocuments}><CheckSquare2 size={13} />选择当前筛选</button>
                <select aria-label="按课程批量选择" value={bulkCourse} onChange={(event) => selectCourseDocuments(event.target.value)}><option value="">按课程选择</option>{courses.map((course) => <option value={course} key={course}>{course}</option>)}</select>
                {selectedDocumentIds.length > 0 && <button type="button" onClick={() => setDocumentScope([])}>清空 {selectedDocumentIds.length}</button>}
              </div>}
              {filteredDocuments.map((document, index) => (
                <div className={`document-row-wrap ${selectedId === document.document_id ? "active" : ""}`} key={document.document_id}>
                  <button className="document-row" onClick={() => selectDocument(document.document_id)}>
                    <span className="document-kind"><FileText size={17} /></span>
                    <span><strong>{document.title || document.source}</strong><small>{document.course || (document.origin === "legacy_index" ? "已有知识库" : document.kind || "资料")} · {document.wiki_coverage ? `${coverageLabels[document.wiki_coverage.status]} · 关联 ${document.wiki_coverage.linked_page_count} 页` : document.chunk_count ? `${document.chunk_count} 个片段` : formatRelativeDate(document.updated_at)}</small></span>
                    <i className={document.vector_status === "error" ? "error" : "ready"} title={document.vector_status || "已建立索引"} />
                  </button>
                  {collection === "material" && <IconButton
                    className={`document-scope ${selectedDocumentIds.includes(document.document_id) ? "selected" : ""}`}
                    label={selectedDocumentIds.includes(document.document_id) ? `取消优先资料 ${document.title || document.source}` : `设为优先资料 ${document.title || document.source}`}
                    onClick={(event) => { event.stopPropagation(); toggleScopeFromList(document.document_id, index, event.shiftKey); }}
                  >{selectedDocumentIds.includes(document.document_id) ? <CheckSquare2 size={14} /> : <Square size={14} />}</IconButton>}
                  {collection === "material" && document.managed && <IconButton className="document-delete" label={`删除 ${document.title || document.source}`} disabled={deletingId === document.document_id} onClick={() => void deleteDocument(document)}><Trash2 size={14} /></IconButton>}
                </div>
              ))}
              {!filteredDocuments.length && <p className="document-search-empty">没有找到匹配的资料。</p>}
            </aside>
            <article className="document-reader">
              {selected && <header><span>{selected.collection === "wiki" ? `Wiki · ${selected.wiki_type ? wikiTypeLabels[selected.wiki_type] : "页面"}` : selected.kind || "本地资料"}{selected.course ? ` · ${selected.course}` : ""}</span><h2>{selected.title || selected.source}</h2>{selected.summary && <p>{selected.summary}</p>}{selected.collection === "wiki" && <button className="quiet-button reader-edit" onClick={() => void openWikiEditor(selected.document_id)}><Edit3 size={15} />编辑</button>}</header>}
              {selectionQuote && <div className="selection-toolbar"><Quote size={15} /><span>已选择 {selectionQuote.length} 个字符</span><button className="quiet-button" onClick={askAboutSelection}>带到对话</button></div>}
              {detailLoading ? <LoadingState label="正在打开资料…" /> : sections.length ? <div className="reader-prose" onMouseUp={captureSelection}>{sections.map((section) => (
                <section className={highlightedChunk === section.chunk_id ? "highlighted" : ""} data-chunk-id={section.chunk_id} key={section.chunk_id}>
                  {section.heading && <h3>{section.heading}</h3>}
                  <div className="section-location">{section.page_start ? `第 ${section.page_start} 页` : section.slide_start ? `第 ${section.slide_start} 页` : "资料片段"}</div>
                  <div className="reader-section-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{section.text}</ReactMarkdown></div>
                </section>
              ))}</div> : <EmptyState compact title="没有可阅读的片段" description="这份资料可能仍在建立索引，刷新后再试一次。" />}
            </article>
          </div>
        ) : (
          <EmptyState state={collection === "wiki" ? "listening" : "reading"}
            title={collection === "wiki" ? "还没有 Wiki 页面" : "先放进第一份学习资料"}
            description={collection === "wiki" ? "从学习资料生成的概念与实体会整理在这里。" : "支持 Markdown、PDF、Word 和 PowerPoint。没有资料库也没关系，选择文件后会继续引导。"}
            action={collection === "material" ? <div className="library-empty-actions"><button className="primary-button" onClick={startDocumentImport}><FilePlus2 size={17} />导入资料</button><button className="quiet-button" onClick={() => openLibrarySetup({ initialMode: "open" })}><FolderOpen size={16} />打开或接入已有资料库</button></div> : undefined}
          />
        )}
      </div>
    </section>
  );
}
