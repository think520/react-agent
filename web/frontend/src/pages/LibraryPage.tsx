import { useEffect, useRef, useState } from "react";
import { BookmarkCheck, CheckCircle2, FilePlus2, FileText, FolderOpen, Library, Plus, Quote, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, Trash2, Upload, Wrench, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { BrandIllustration, EmptyState, ErrorNotice, IconButton, LoadingState, formatRelativeDate } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { api } from "../lib/api";
import type { DocumentSection, DocumentSummary, WikiHealth, WikiPlan, WikiTask } from "../types";

export function LibraryPage() {
  const {
    activeLibrary,
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
  const [wikiTasks, setWikiTasks] = useState<WikiTask[]>([]);
  const [wikiInstruction, setWikiInstruction] = useState("");
  const [wikiScopeMode, setWikiScopeMode] = useState<"selection" | "document" | "course">("selection");
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
      const nextDocuments = await api.documents(collection);
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
      setNotice("已生成 Wiki 修复预览；确认前不会改动任何页面。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Wiki 整理失败。" );
    } finally {
      setMaintenanceLoading(false);
    }
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
    const documentIds = collection === "material"
      ? (wikiScopeMode === "selection" && selectedDocumentIds.length
          ? selectedDocumentIds
          : wikiScopeMode === "document" && selectedId
            ? [selectedId]
            : [])
      : [];
    const wikiDocumentIds = collection === "wiki" && selectedId ? [selectedId] : [];
    const course = collection === "material" && wikiScopeMode === "course" ? selected?.course || null : null;
    if (!documentIds.length && !wikiDocumentIds.length && !course) {
      setError(collection === "wiki" ? "请先选择一个需要更新的 Wiki 页面。" : "请先选择至少一份学习资料。" );
      return;
    }
    const command = `${collection === "wiki" ? "/wiki update" : "/wiki plan"}${wikiInstruction.trim() ? ` ${wikiInstruction.trim()}` : ""}`;
    localStorage.setItem("bobodan:draft:new", command);
    localStorage.setItem("bobodan:wiki-scope", JSON.stringify({ documentIds, wikiDocumentIds, course }));
    setWikiPlanOpen(false);
    navigate("/chat");
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

  return (
    <section className="page-scroll" ref={pageRef} onScroll={recordReadingProgress}>
      <div className="page-container library-container">
        <header className="page-heading">
          <div><span>Library</span><h2>资料库</h2><p>{collection === "material" ? "把学习材料放在这里，Bobodan 会建立可追踪的本地索引。" : "Wiki 是由 Bobodan 从学习资料中整理出的规范概念页。"}</p></div>
          <div className="heading-actions">
            {activeLibrary && <button className="quiet-button" onClick={() => void loadDocuments()}><RefreshCw size={16} />刷新</button>}
            {collection === "wiki" && <button className="quiet-button" onClick={() => void openWikiMaintenance()}><Wrench size={16} />维护 Wiki</button>}
            {collection === "wiki" && <button className="primary-button" disabled={!selectedId} onClick={() => { setWikiPlan(null); setWikiPlanOpen(true); }}><Sparkles size={16} />更新 Wiki</button>}
            {collection === "material" && documents.length > 0 && <button className="quiet-button" onClick={() => { setWikiScopeMode(selectedDocumentIds.length ? "selection" : "document"); setWikiPlan(null); setWikiPlanOpen(true); }}><Sparkles size={16} />整理成 Wiki</button>}
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
        <div className="library-tabs" role="tablist" aria-label="资料库分类">
          <button role="tab" aria-selected={collection === "material"} className={collection === "material" ? "active" : ""} onClick={() => selectCollection("material")}>学习资料</button>
          <button role="tab" aria-selected={collection === "wiki"} className={collection === "wiki" ? "active" : ""} onClick={() => selectCollection("wiki")}>Wiki</button>
        </div>
        {wikiPlanOpen && !wikiPlan && <section className="wiki-plan-compose" aria-label="创建 Wiki 整理计划">
          <div className="wiki-plan-compose-copy">
            <span>{collection === "wiki" ? "Update Wiki" : "Generate Wiki"}</span>
            <h3>{collection === "wiki" ? "根据原始资料更新当前页面" : "把选中的资料整理成 Wiki"}</h3>
            <p>{collection === "wiki"
              ? `当前页面：${selected?.title || "未选择"}`
              : `整理范围：${selectedDocumentIds.length || (selectedId ? 1 : 0)} 份学习资料`}</p>
          </div>
          {collection === "material" && <label className="wiki-scope-field">
            <span>整理范围</span>
            <select value={wikiScopeMode} onChange={(event) => setWikiScopeMode(event.target.value as "selection" | "document" | "course")}>
              {selectedDocumentIds.length > 0 && <option value="selection">当前学习范围（{selectedDocumentIds.length} 份）</option>}
              {selected && <option value="document">当前资料：{selected.title || selected.source}</option>}
              {selected?.course && <option value="course">课程：{selected.course}</option>}
            </select>
          </label>}
          <label>
            <span>整理要求</span>
            <textarea value={wikiInstruction} onChange={(event) => setWikiInstruction(event.target.value)} placeholder="例如：重点整理核心概念、适用条件和常见误区" rows={3} />
          </label>
          <footer>
            <button className="quiet-button" disabled={wikiPlanLoading} onClick={() => setWikiPlanOpen(false)}>取消</button>
            <button className="primary-button" disabled={wikiPlanLoading} onClick={() => void planWiki()}><Sparkles size={16} />{wikiPlanLoading ? "正在规划" : "生成计划"}</button>
          </footer>
        </section>}
        {wikiPlan && <WikiPlanCard
          plan={wikiPlan}
          busy={wikiPlanLoading}
          onApply={wikiPlan.status === "planned" ? () => void applyWikiPlan() : undefined}
          onKeepExisting={wikiPlan.status === "planned" && wikiPlan.staging?.length ? () => void recoverWikiPlan("keep_existing") : undefined}
          onRegenerate={wikiPlan.status === "planned" && wikiPlan.staging?.length ? () => void recoverWikiPlan("regenerate") : undefined}
          onUndo={wikiPlan.status === "applied" && wikiPlan.checkpoint_id ? () => void undoWikiPlan() : undefined}
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
          <footer><button className="quiet-button" disabled={maintenanceLoading} onClick={() => void checkWiki()}><RefreshCw size={15} />重新检查</button><button className="quiet-button" disabled={maintenanceLoading} onClick={() => void reviewWikiSemantics()}><Sparkles size={15} />AI 语义检查</button><button className="primary-button" disabled={maintenanceLoading} onClick={() => void organizeWiki()}><Wrench size={15} />{maintenanceLoading ? "正在生成" : "生成修复计划"}</button></footer>
        </section>}
        {(documentImportNotice || notice) && <div className="success-notice"><CheckCircle2 size={17} />{documentImportNotice || notice}</div>}
        {documentImportError && <ErrorNotice message={documentImportError} />}
        {error && <ErrorNotice message={error} action={<button className="quiet-button" onClick={() => void loadDocuments()}>重试</button>} />}
        {loading ? <div className="illustrated-loading"><BrandIllustration state="reading" size={76} /><LoadingState label={collection === "wiki" ? "正在整理 Wiki…" : "正在读取本地资料…"} /></div> : documents.length ? (
          <div className="library-workspace">
            <aside className="document-rail">
              <div className="rail-label"><FolderOpen size={15} />{collection === "wiki" ? "规范页面" : "我的资料"} <span>{documents.length}</span></div>
              <label className="document-search"><Search size={14} /><input value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder="搜索资料" aria-label="搜索资料" /></label>
              {filteredDocuments.map((document) => (
                <div className={`document-row-wrap ${selectedId === document.document_id ? "active" : ""}`} key={document.document_id}>
                  <button className="document-row" onClick={() => selectDocument(document.document_id)}>
                    <span className="document-kind"><FileText size={17} /></span>
                    <span><strong>{document.title || document.source}</strong><small>{document.course || (document.origin === "legacy_index" ? "已有知识库" : document.kind || "资料")} · {document.chunk_count ? `${document.chunk_count} 个片段` : formatRelativeDate(document.updated_at)}</small></span>
                    <i className={document.vector_status === "error" ? "error" : "ready"} title={document.vector_status || "已建立索引"} />
                  </button>
                  {collection === "material" && <IconButton
                    className={`document-scope ${selectedDocumentIds.includes(document.document_id) ? "selected" : ""}`}
                    label={selectedDocumentIds.includes(document.document_id) ? `移出学习范围 ${document.title || document.source}` : `加入学习范围 ${document.title || document.source}`}
                    onClick={() => toggleDocumentScope(document.document_id)}
                  >{selectedDocumentIds.includes(document.document_id) ? <BookmarkCheck size={14} /> : <Plus size={14} />}</IconButton>}
                  {collection === "material" && document.managed && <IconButton className="document-delete" label={`删除 ${document.title || document.source}`} disabled={deletingId === document.document_id} onClick={() => void deleteDocument(document)}><Trash2 size={14} /></IconButton>}
                </div>
              ))}
              {!filteredDocuments.length && <p className="document-search-empty">没有找到匹配的资料。</p>}
            </aside>
            <article className="document-reader">
              {selected && <header><span>{selected.collection === "wiki" ? `Wiki · ${selected.wiki_type === "concept" ? "概念" : "实体"}` : selected.kind || "本地资料"}{selected.course ? ` · ${selected.course}` : ""}</span><h2>{selected.title || selected.source}</h2>{selected.summary && <p>{selected.summary}</p>}</header>}
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
