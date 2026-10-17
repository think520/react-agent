/**
 * LibraryPage 的 wiki 处理器族（2026-10-17 M2 store-lift：从 LibraryPage.tsx 整块搬出，行为不变）。
 * 依赖折叠成一个 ctx 对象；组件每帧 createLibraryWikiActions(ctx) 并解构，调用点不变。
 */
import { api } from "../../lib/api";
import {} from "../../lib/errors";
import {} from "../../stores/noticeStore";
import type { Dispatch, SetStateAction } from "react";
import { useHandoffStore } from "../../stores/handoffStore";
import type { SetURLSearchParams } from "react-router-dom";
import type { NavigateFunction } from "react-router-dom";
import type {
  DocumentSummary, LibrarySummary, SettingsSummary, WikiEditablePage, WikiGenerationMode, WikiHealth,
  WikiPlan, WikiRepairPlan, WikiRunEstimate, WikiScopeMode, WikiTask,
} from "../../types";

type WikiView = "knowledge" | "sources" | "notes" | "all";

export interface LibraryWikiContext {
  confirm: (options: { title: string; detail: string; confirmLabel: string; danger?: boolean }) => Promise<boolean>;
  collection: "material" | "wiki";
  wikiView: WikiView;
  wikiScopeMode: WikiScopeMode;
  wikiGenerationMode: WikiGenerationMode;
  selectedId: string | null;
  setSelectedId: (next: string | null | ((current: string | null) => string | null)) => void;
  selectedDocumentIds: string[];
  selected: DocumentSummary | undefined;
  wikiInstruction: string;
  wikiTopic: string;
  wikiPlan: WikiPlan | null;
  setWikiPlan: Dispatch<SetStateAction<WikiPlan | null>>;
  wikiPlanOpen: boolean;
  setWikiPlanOpen: Dispatch<SetStateAction<boolean>>;
  wikiPlanLoading: boolean;
  setWikiPlanLoading: Dispatch<SetStateAction<boolean>>;
  wikiEstimate: WikiRunEstimate | null;
  setWikiEstimate: Dispatch<SetStateAction<WikiRunEstimate | null>>;
  wikiEditor: WikiEditablePage | null;
  setWikiEditor: Dispatch<SetStateAction<WikiEditablePage | null>>;
  wikiEditorOpen: boolean;
  setWikiEditorOpen: Dispatch<SetStateAction<boolean>>;
  wikiEditorPreview: boolean;
  setWikiEditorPreview: Dispatch<SetStateAction<boolean>>;
  wikiEditorSaving: boolean;
  setWikiEditorSaving: Dispatch<SetStateAction<boolean>>;
  wikiTasks: WikiTask[];
  setWikiTasks: Dispatch<SetStateAction<WikiTask[]>>;
  setCollection: Dispatch<SetStateAction<"material" | "wiki">>;
  settings: SettingsSummary | null;
  activeLibrary: LibrarySummary | null;
  navigate: NavigateFunction;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  loadDocuments: () => Promise<void>;
  repairPlan: WikiRepairPlan | null;
  setRepairPlan: Dispatch<SetStateAction<WikiRepairPlan | null>>;
  setWikiHealth: Dispatch<SetStateAction<WikiHealth | null>>;
  setMaintenanceLoading: Dispatch<SetStateAction<boolean>>;
  setNotice: Dispatch<SetStateAction<string>>;
  setError: Dispatch<SetStateAction<string>>;
}

export function createLibraryWikiActions(ctx: LibraryWikiContext) {
  const {
    repairPlan, setRepairPlan, setWikiHealth, setMaintenanceLoading, setNotice, setError,

    collection,
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
    setWikiPlanOpen,
    setWikiPlanLoading,
    setWikiEstimate,
    wikiEditor,
    setWikiEditor,
    setWikiEditorOpen,
    setWikiEditorPreview,
    setWikiEditorSaving,
    setWikiTasks,
    setCollection,
    settings,
    activeLibrary,
    navigate,
    searchParams,
    setSearchParams,
    loadDocuments,
    confirm,
  } = ctx;

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


  return {
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
  };
}
