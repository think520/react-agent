/** LibraryPage 头部区（2026-10-17 M2 store-lift · 分块搬出）。只渲染，动作/状态由页面传入。 */
import {} from "../../lib/documentLinks";
import {} from "react";
import { CheckCircle2, FolderOpen, FolderTree, Library, MoreHorizontal, RefreshCw, Save, Settings2, ShieldCheck, Sparkles, Trash2, Upload, Wrench, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {} from "react-router-dom";
import { DropdownSelect } from "../../components/DropdownSelect";
import {} from "../../components/ImportDropZone";
import { ImportReportPanel } from "../../components/ImportReportPanel";
import {} from "../../components/DocumentEditor";
import type { AppOutletContext } from "../../components/AppShell";
import { createLibraryWikiActions } from "./libraryWikiActions";
import {} from "./wikiView";
import {} from "./LibraryTreePanel";
import { createLibraryMaterialActions } from "./libraryActions";
import { ErrorNotice, IconButton, LoadingState } from "../../components/common";
import { WikiPlanCard } from "../../components/WikiPlanCard";
import {} from "../../lib/api";
import type { KnowledgeSyncSummary, KnowledgeTree } from "../../lib/api";
import {} from "../../components/DocumentReader";
import {} from "../../components/ScrollIndicator";
import {} from "../../stores/readerTabsStore";
import { Modal } from "../../ui/Modal";
import type { DocumentSummary, WikiEditablePage, WikiGenerationMode, WikiHealth, WikiPlan, WikiRepairPlan, WikiRunEstimate, WikiScopeMode, WikiTask } from "../../types";

import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { LibrarySummary } from "../../types";

import type { WikiViewType } from "./wikiView";

type MaterialActions = ReturnType<typeof createLibraryMaterialActions>;
type WikiActions = ReturnType<typeof createLibraryWikiActions>;

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

function progressPercent(progress: { phase: string; filesDone: number; filesTotal: number; sourcesDone: number; sourcesTotal: number }): number {
  const [done, total] = progress.phase === "indexing"
    ? [progress.sourcesDone, progress.sourcesTotal]
    : [progress.filesDone, progress.filesTotal];
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

export interface LibraryHeaderProps {
  activeLibrary: LibrarySummary | null;
  collection: "material" | "wiki";
  libraries: LibrarySummary[];
  loadDocuments: () => Promise<void>;
  openLibrarySetup: () => void;
  switchLibrary: AppOutletContext["switchLibrary"];
  startDocumentImport: AppOutletContext["startDocumentImport"];
  documentImporting: boolean;
  documentImportNotice: AppOutletContext["documentImportNotice"];
  documentImportError: AppOutletContext["documentImportError"];
  documentImportErrorCode: AppOutletContext["documentImportErrorCode"];
  documentImportDuplicateCount: AppOutletContext["documentImportDuplicateCount"];
  importDuplicatesAsCopies: AppOutletContext["importDuplicatesAsCopies"];
  documentImportVersion: AppOutletContext["documentImportVersion"];
  documentImportProgress: AppOutletContext["documentImportProgress"];
  documentImportResults: AppOutletContext["documentImportResults"];
  documentImportCanRetry: AppOutletContext["documentImportCanRetry"];
  cancelDocumentImport: AppOutletContext["cancelDocumentImport"];
  retryFailedImports: AppOutletContext["retryFailedImports"];
  dismissImportReport: AppOutletContext["dismissImportReport"];
  tree: KnowledgeTree | null;
  treeCollapsed: boolean;
  setTreeCollapsed: Dispatch<SetStateAction<boolean>>;
  selected: DocumentSummary | undefined;
  selectedDocumentIds: string[];
  uncoveredCount: number;
  notice: string;
  confirmElement: ReactNode;
  syncSummary: KnowledgeSyncSummary | null;
  syncingFolder: boolean;
  setSyncSummary: Dispatch<SetStateAction<KnowledgeSyncSummary | null>>;
  maintenanceOpen: boolean;
  maintenanceLoading: boolean;
  setMaintenanceOpen: Dispatch<SetStateAction<boolean>>;
  repairPlan: WikiRepairPlan | null;
  wikiHealth: WikiHealth | null;
  wikiTasks: WikiTask[];
  wikiPlan: WikiPlan | null;
  wikiPlanOpen: boolean;
  wikiPlanLoading: boolean;
  wikiScopeMode: WikiScopeMode;
  wikiView: WikiViewType;
  wikiGenerationMode: WikiGenerationMode;
  wikiTopic: string;
  wikiInstruction: string;
  wikiEstimate: WikiRunEstimate | null;
  wikiEditor: WikiEditablePage | null;
  wikiEditorOpen: boolean;
  wikiEditorPreview: boolean;
  wikiEditorSaving: boolean;
  setWikiPlan: Dispatch<SetStateAction<WikiPlan | null>>;
  setWikiPlanOpen: Dispatch<SetStateAction<boolean>>;
  setWikiScopeMode: Dispatch<SetStateAction<WikiScopeMode>>;
  setWikiGenerationMode: Dispatch<SetStateAction<WikiGenerationMode>>;
  setWikiTopic: Dispatch<SetStateAction<string>>;
  setWikiInstruction: Dispatch<SetStateAction<string>>;
  setWikiEstimate: Dispatch<SetStateAction<WikiRunEstimate | null>>;
  setWikiEditor: Dispatch<SetStateAction<WikiEditablePage | null>>;
  setWikiEditorOpen: Dispatch<SetStateAction<boolean>>;
  setWikiEditorPreview: Dispatch<SetStateAction<boolean>>;
  progressPercent: (progress: NonNullable<AppOutletContext["documentImportProgress"]>) => number;
  selectCollection: MaterialActions["selectCollection"];
  selectWikiView: MaterialActions["selectWikiView"];
  syncLibraryFolder: MaterialActions["syncLibraryFolder"];
  checkWiki: WikiActions["checkWiki"];
  organizeWiki: WikiActions["organizeWiki"];
  applyRepairPlan: WikiActions["applyRepairPlan"];
  draftRepairPlan: WikiActions["draftRepairPlan"];
  reviewWikiSemantics: WikiActions["reviewWikiSemantics"];
  retryWikiTask: WikiActions["retryWikiTask"];
  cancelWikiTask: WikiActions["cancelWikiTask"];
  planWiki: WikiActions["planWiki"];
  startEstimatedWiki: WikiActions["startEstimatedWiki"];
  resumeWikiPlan: WikiActions["resumeWikiPlan"];
  openWikiProviderSettings: WikiActions["openWikiProviderSettings"];
  continueWikiBatch: WikiActions["continueWikiBatch"];
  applyWikiPlan: WikiActions["applyWikiPlan"];
  recoverWikiPlan: WikiActions["recoverWikiPlan"];
  undoWikiPlan: WikiActions["undoWikiPlan"];
  openWikiEditor: WikiActions["openWikiEditor"];
  updateWikiEditor: WikiActions["updateWikiEditor"];
  saveWikiEditor: WikiActions["saveWikiEditor"];
  archiveSelectedWikiPage: WikiActions["archiveSelectedWikiPage"];
}

export function LibraryHeader(props: LibraryHeaderProps) {
  const {
    activeLibrary,
    collection,
    libraries,
    loadDocuments,
    openLibrarySetup,
    switchLibrary,
    startDocumentImport,
    documentImporting,
    documentImportNotice,
    documentImportError,
    documentImportErrorCode,
    documentImportDuplicateCount,
    importDuplicatesAsCopies,
    documentImportProgress,
    documentImportResults,
    documentImportCanRetry,
    cancelDocumentImport,
    retryFailedImports,
    dismissImportReport,
    tree,
    treeCollapsed,
    setTreeCollapsed,
    selected,
    selectedDocumentIds,
    uncoveredCount,
    notice,
    confirmElement,
    syncSummary,
    syncingFolder,
    setSyncSummary,
    maintenanceOpen,
    maintenanceLoading,
    setMaintenanceOpen,
    repairPlan,
    wikiHealth,
    wikiTasks,
    wikiPlan,
    wikiPlanOpen,
    wikiPlanLoading,
    wikiScopeMode,
    wikiView,
    wikiGenerationMode,
    wikiTopic,
    wikiInstruction,
    wikiEstimate,
    wikiEditor,
    wikiEditorOpen,
    wikiEditorPreview,
    wikiEditorSaving,
    setWikiPlan,
    setWikiPlanOpen,
    setWikiScopeMode,
    setWikiGenerationMode,
    setWikiTopic,
    setWikiInstruction,
    setWikiEstimate,
    setWikiEditorOpen,
    setWikiEditorPreview,
    selectCollection,
    selectWikiView,
    syncLibraryFolder,
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
  } = props;

  return (
    <>
  <header className="library-toolbar">
    <div className="library-toolbar-context">
      <Library size={18} aria-hidden="true" />
      <div>
        <span>{collection === "wiki" ? "历史整理" : "资料库"}</span>
        {collection === "material" && libraries.filter((item) => item.available).length > 0 ? (
          <DropdownSelect ariaLabel="切换资料库" value={activeLibrary?.library_id || ""} onChange={(value) => void switchLibrary(value)} options={libraries.filter((item) => item.available).map((library) => ({ value: library.library_id, label: library.name }))} />
        ) : <strong>{collection === "wiki" ? activeLibrary?.name || "资料库" : "尚未创建资料库"}</strong>}
      </div>
      {/* 2026-09-24：树的开关挪到左上角（原来埋在右侧按钮组里，用户找不着）。
          位置就在「资料库 / vault」右边，和 Obsidian 的侧栏开关同一个角落的意思。 */}
      {collection === "material" && tree && (
        <button
          className="quiet-button"
          type="button"
          aria-pressed={!treeCollapsed}
          title={treeCollapsed ? "显示文件夹树" : "收起文件夹树，把宽度留给正文"}
          onClick={() => setTreeCollapsed((collapsed) => !collapsed)}
        >
          <FolderTree size={15} />文件夹
        </button>
      )}
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
  {(documentImportNotice || notice) && <div className="success-notice"><CheckCircle2 size={17} /><span>{documentImportNotice || notice}</span>{documentImportDuplicateCount > 0 && <button className="text-link" type="button" onClick={importDuplicatesAsCopies}>重复文件仍要另存副本</button>}</div>}
  {documentImportError && <ErrorNotice message={documentImportError} code={documentImportErrorCode} />}
  {/* E8：导入是**运行态** —— 运行中显示进度，并且当场能取消（协作式：文件边界生效）。 */}
  {documentImportProgress && (
    <div className="import-progress" role="status">
      <div className="import-progress-body">
        <div className="import-progress-line">
          <strong>{documentImportProgress.phase === "indexing" ? "正在建立索引" : "正在收下文件"}</strong>
          <span className="text-faint">
            {documentImportProgress.phase === "indexing"
              ? `${documentImportProgress.sourcesDone}/${documentImportProgress.sourcesTotal} 份资料`
              : `${documentImportProgress.filesDone}/${documentImportProgress.filesTotal} 份文件`}
            {documentImportProgress.current ? ` · ${documentImportProgress.current}` : ""}
          </span>
        </div>
        <div className="import-progress-track" aria-hidden="true">
          <div
            className="import-progress-fill"
            style={{
              width: `${progressPercent(documentImportProgress)}%`,
            }}
          />
        </div>
      </div>
      <button className="quiet-button" onClick={cancelDocumentImport}>取消导入</button>
    </div>
  )}
  {/* E8：逐文件说清楚这次导入（文件名 + 可行动原因 + 重试），不再只有一句汇总。 */}
  {documentImportResults && (
    <ImportReportPanel
      results={documentImportResults}
      canRetry={documentImportCanRetry}
      onRetryFailed={retryFailedImports}
      onDismiss={dismissImportReport}
    />
  )}
    </>
  );
}
