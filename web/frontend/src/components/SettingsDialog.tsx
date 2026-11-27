import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, Bot, BookOpenText, Brain, Check, ChevronLeft, CircleUserRound,
  Cpu, RefreshCw, Search, ShieldCheck, Sparkles, Wrench, X,
} from "lucide-react";

import { api } from "../lib/api";
import { useRagBackfillStore } from "../stores/ragBackfillStore";
import type {
  LegacyGraphPreview,
  LibrarySummary,
  MemoryOverview,
  RagSettingsResponse,
  RuntimeStatus,
  SettingsSummary,
} from "../types";
import { IconButton } from "./common";
import {} from "./ModelSelect";
import {} from "./DropdownSelect";
import { Modal, ConfirmDialog } from "../ui/Modal";
import { SearchField } from "../ui";
import { SettingsHeading, SettingsPage } from "./settings/SettingsPrimitives";
import { AppearanceSection } from "./settings/sections/AppearanceSection";
import { AssistantSection } from "./settings/sections/AssistantSection";
import { MeSection } from "./settings/sections/MeSection";
import { MemorySection } from "./settings/sections/MemorySection";
import { ModelsSection } from "./settings/sections/ModelsSection";
import { RagSection } from "./settings/sections/RagSection";
import { ExperimentsSection } from "./settings/sections/ExperimentsSection";
import { SecuritySection } from "./settings/sections/SecuritySection";
import { SkillsSection } from "./settings/sections/SkillsSection";
import { searchSettings } from "./settings/settingsSearchIndex";
import { useCompositionGuard } from "../lib/ime";
import { StatusSection } from "./settings/sections/StatusSection";

type SectionId = "assistant" | "me" | "appearance" | "models" | "rag" | "memory" | "skills" | "security" | "status" | "experiments";

const sections: Array<{ id: SectionId; label: string; icon: typeof Bot; aliases: string }> = [
  { id: "me", label: "我与学习", icon: CircleUserRound, aliases: "用户 称呼 简介 目标 学习" },
  { id: "assistant", label: "Bobodan", icon: Bot, aliases: "助手 人设 教学 回答 反馈 昵称" },
  { id: "appearance", label: "界面与阅读", icon: BookOpenText, aliases: "外观 字体 字号 宽度 纸纹 动效 会话密度" },
  { id: "models", label: "AI 与模型", icon: Cpu, aliases: "模型 provider 供应商 连接 deepseek minimax openai" },
  { id: "rag", label: "检索与 RAG", icon: Search, aliases: "检索 搜索 向量 嵌入 embedding hybrid fts 原文 降级" },
  { id: "memory", label: "记忆与数据", icon: Brain, aliases: "记忆 隐私 本地 数据 资料库" },
  { id: "skills", label: "Skills", icon: Wrench, aliases: "技能 命令 能力 skill" },
  { id: "security", label: "安全与隐私", icon: ShieldCheck, aliases: "安全 隐私 密钥 api key 日志 遥测" },
  { id: "status", label: "状态与关于", icon: Activity, aliases: "状态 后端 索引 版本 连接" },
  { id: "experiments", label: "实验", icon: Sparkles, aliases: "实验 开关 预览" },
];

/** 旧版 URL/入口的 section id 兼容（?settings=user / ?settings=ai 仍可用）。 */
const LEGACY_SECTION_IDS: Record<string, SectionId> = { user: "me", ai: "models" };

export function SettingsDialog({
  settings,
  activeLibrary,
  section,
  onSectionChange,
  onClose,
  onSettingsChange,
}: {
  settings: SettingsSummary;
  activeLibrary: LibrarySummary | null;
  section: string;
  onSectionChange: (section: SectionId) => void;
  onClose: () => void;
  onSettingsChange: (settings: SettingsSummary) => void;
}) {
  const requested = LEGACY_SECTION_IDS[section] ?? (section as SectionId);
  const active = sections.some((item) => item.id === requested) ? requested : "assistant";
  const [query, setQuery] = useState("");
  const ime = useCompositionGuard();
  const [searchIndex, setSearchIndex] = useState(0);
  const [preferences, setPreferences] = useState(settings.preferences);
  const [profile, setProfile] = useState({ ...settings.preferences.user });
  const [assistant, setAssistant] = useState({ ...settings.preferences.assistant });
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [searchTest, setSearchTest] = useState<Record<string, string>>({});
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [ragSettings, setRagSettings] = useState<RagSettingsResponse | null>(null);
  const [ragError, setRagError] = useState("");
  const [memoryOverview, setMemoryOverview] = useState<MemoryOverview | null>(null);
  const [legacyGraph, setLegacyGraph] = useState<LegacyGraphPreview | null>(null);
  const [legacyConceptIds, setLegacyConceptIds] = useState<string[]>([]);
  const [legacyMemoryIds, setLegacyMemoryIds] = useState<string[]>([]);
  const [migrationBusy, setMigrationBusy] = useState(false);
  const [usage, setUsage] = useState<Awaited<ReturnType<typeof api.llmUsage>> | null>(null);
  const [usageDays, setUsageDays] = useState<7 | 30>(7);
  const [confirmLegacy, setConfirmLegacy] = useState<"migrate" | "archive" | null>(null);
  const [dirtySource, setDirtySource] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const activeNavRef = useRef<HTMLButtonElement>(null);
  const storeLatestRag = useRagBackfillStore((state) => state.latestRag);

  useEffect(() => {
    setPreferences(settings.preferences);
    setProfile({ ...settings.preferences.user });
    setAssistant({ ...settings.preferences.assistant });
  }, [settings]);

  const refreshRagSettings = useCallback(async () => {
    if (typeof api.ragSettings !== "function") return null;
    setRagError("");
    try {
      const next = await api.ragSettings();
      setRagSettings(next);
      return next;
    } catch (reason) {
      setRagError(reason instanceof Error ? reason.message : "无法读取检索与 RAG 状态");
      return null;
    }
  }, []);

  useEffect(() => {
    if (active === "models" || active === "rag" || active === "status") {
      void refreshRagSettings();
    }
    if (active === "rag" || active === "models") {
      void useRagBackfillStore.getState().syncStatus();
    }
  }, [active, refreshRagSettings]);

  useEffect(() => {
    if (!storeLatestRag) return;
    setRagSettings(storeLatestRag);
    setRuntimeStatus(null);
  }, [storeLatestRag]);

  useEffect(() => {
    if (active !== "status" || runtimeStatus) return;
    void api.runtimeStatus().then(setRuntimeStatus).catch((reason: Error) => setError(reason.message));
  }, [active, runtimeStatus]);

  useEffect(() => {
    if (!activeLibrary) { setMemoryOverview(null); return; }
    void api.memoryOverview().then(setMemoryOverview).catch(() => setMemoryOverview(null));
  }, [activeLibrary]);

  useEffect(() => {
    setLegacyGraph(null);
    setLegacyConceptIds([]);
    setLegacyMemoryIds([]);
    setRagSettings(null);
    setRuntimeStatus(null);
  }, [activeLibrary?.library_id]);

  useEffect(() => {
    if (active !== "memory" || !activeLibrary || legacyGraph) return;
    let cancelled = false;
    void api.legacyGraphPreview().then((preview) => {
      if (cancelled) return;
      setLegacyGraph(preview);
      setLegacyConceptIds(preview.concepts.map((item) => item.id));
      setLegacyMemoryIds(preview.memories.filter((item) => item.recommended).map((item) => item.id));
    }).catch((reason: Error) => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [active, activeLibrary, legacyGraph]);

  useEffect(() => {
    if (active !== "models") return;
    setUsage(null);
    void api.llmUsage(usageDays).then(setUsage).catch(() => setUsage(null));
  }, [active, usageDays]);

  const matches = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) {
      return sections.map((item) => ({ id: item.id, label: item.label, icon: item.icon, tab: item.id, hint: "" }));
    }
    return searchSettings(needle).map((entry) => ({
      id: entry.id,
      label: entry.label,
      icon: sections.find((item) => item.id === entry.tab)?.icon || Bot,
      tab: entry.tab,
      hint: sections.find((item) => item.id === entry.tab)?.label || "",
    }));
  }, [query]);
  const recommendedMemories = legacyGraph?.memories.filter((item) => item.recommended) || [];
  const allConceptsSelected = Boolean(legacyGraph?.concepts.length)
    && legacyConceptIds.length === legacyGraph?.concepts.length;
  const allRecommendedMemoriesSelected = recommendedMemories.length > 0
    && recommendedMemories.every((item) => legacyMemoryIds.includes(item.id));

  useEffect(() => setSearchIndex(0), [query]);

  useEffect(() => {
    activeNavRef.current?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [active]);

  const handleDirtyChange = useCallback((source: string, dirty: boolean) => {
    setDirtySource((current) => {
      if (dirty) return source;
      return current === source ? null : current;
    });
  }, []);

  const handleRagDirty = useCallback((dirty: boolean) => handleDirtyChange("向量模型配置", dirty), [handleDirtyChange]);
  const handleProviderDirty = useCallback((dirty: boolean) => handleDirtyChange("供应商编辑", dirty), [handleDirtyChange]);

  const runWithDirtyCheck = useCallback((action: () => void) => {
    if (dirtySource) {
      setPendingAction(() => action);
      return;
    }
    action();
  }, [dirtySource]);

  const requestClose = useCallback(() => {
    runWithDirtyCheck(onClose);
  }, [runWithDirtyCheck, onClose]);

  async function patchPreferences(patch: Record<string, unknown>) {
    if (saving) return;
    const previous = preferences;
    setSaving(true);
    setError("");
    try {
      const result = await api.patchPreferences(preferences.revision, patch);
      setPreferences(result.preferences);
      onSettingsChange({ ...settings, preferences: result.preferences, default_provider: result.preferences.ai.default_provider, skills: settings.skills.map((skill) => ({ ...skill, enabled: result.preferences.skills.enabled_names.includes(skill.name) })) });
      setNotice("设置已保存");
      window.setTimeout(() => setNotice(""), 1600);
    } catch (reason) {
      setPreferences(previous);
      setError(reason instanceof Error ? reason.message : "设置没有保存成功。");
    } finally {
      setSaving(false);
    }
  }

  async function migrateLegacyGraph() {
    if (!legacyGraph?.detected || migrationBusy) return;
    setMigrationBusy(true);
    setError("");
    try {
      const result = await api.importLegacyGraph(legacyConceptIds, legacyMemoryIds);
      setNotice(`已创建 ${result.concept_candidates.length} 条概念候选和 ${result.memory_candidates.length} 条个人知识候选。`);
      setLegacyGraph({ ...legacyGraph, detected: false });
      void api.memoryOverview().then(setMemoryOverview).catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "旧版知识图谱迁移失败");
    } finally {
      setMigrationBusy(false);
      setConfirmLegacy(null);
    }
  }

  async function archiveLegacyGraphWithoutImport() {
    if (!legacyGraph?.detected || migrationBusy) return;
    setMigrationBusy(true);
    setError("");
    try {
      await api.importLegacyGraph([], []);
      setNotice("已按你的选择跳过全部旧数据，并保留归档文件和迁移校验记录。");
      setLegacyGraph({ ...legacyGraph, detected: false });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "旧版知识图谱归档失败");
    } finally {
      setMigrationBusy(false);
      setConfirmLegacy(null);
    }
  }

  async function saveAssistant() {
    await patchPreferences({ assistant });
  }

  async function saveProfile() {
    await patchPreferences({ user: profile });
  }

  async function testSearchProvider(name: "auto" | "tavily" | "exa") {
    setSearchTest((current) => ({ ...current, [name]: "正在测试…" }));
    try {
      const result = await api.searchProviderTest(name);
      setSearchTest((current) => ({ ...current, [name]: `${result.latency_ms}ms · 搜索正常` }));
    } catch (reason) {
      setSearchTest((current) => ({ ...current, [name]: reason instanceof Error ? reason.message : "搜索连接失败" }));
    }
  }

  function flashSetting(label: string) {
    const selector = ".settings-main .settings-section, .settings-main .setting-row, .settings-main .settings-field, .settings-main .settings-boundary, .settings-main .rag-footnote";
    const target = Array.from(document.querySelectorAll<HTMLElement>(selector)).find((element) => element.textContent?.includes(label));
    if (!target) return;
    target.scrollIntoView({ block: "center" });
    target.classList.add("settings-search-flash");
    window.setTimeout(() => target.classList.remove("settings-search-flash"), 1600);
  }

  function jumpTo(tab: SectionId, label?: string) {
    const perform = () => {
      onSectionChange(tab);
      setQuery("");
      if (label) window.setTimeout(() => flashSetting(label), 80);
    };
    if (tab !== active) {
      runWithDirtyCheck(perform);
      return;
    }
    perform();
  }

  function sectionContent() {
    if (active === "assistant") return <AssistantSection assistant={assistant} setAssistant={setAssistant} />;
    if (active === "me") return <MeSection profile={profile} setProfile={setProfile} />;
    if (active === "appearance") return <AppearanceSection appearance={preferences.appearance} patch={(patch) => void patchPreferences(patch)} />;
    if (active === "models") return <ModelsSection settings={settings} preferences={preferences} ragSettings={ragSettings} onRagRefresh={refreshRagSettings} usage={usage} usageDays={usageDays} setUsageDays={setUsageDays} patch={(patch) => void patchPreferences(patch)} searchTest={searchTest} testSearchProvider={testSearchProvider} onSettingsChange={onSettingsChange} onOpenRag={() => jumpTo("rag")} onDirtyChange={handleProviderDirty} />;
    if (active === "memory") return <MemorySection preferences={preferences} patch={(patch) => void patchPreferences(patch)} memoryOverview={memoryOverview} activeLibrary={activeLibrary} legacyGraph={legacyGraph} legacyConceptIds={legacyConceptIds} setLegacyConceptIds={setLegacyConceptIds} legacyMemoryIds={legacyMemoryIds} setLegacyMemoryIds={setLegacyMemoryIds} recommendedMemories={recommendedMemories} allConceptsSelected={allConceptsSelected} allRecommendedMemoriesSelected={allRecommendedMemoriesSelected} migrationBusy={migrationBusy} setConfirmLegacy={setConfirmLegacy} />;
    if (active === "skills") return <SkillsSection skills={settings.skills} preferences={preferences} patch={(patch) => void patchPreferences(patch)} />;
    if (active === "rag") return <RagSection ragData={ragSettings} loadError={ragError} onReload={() => void refreshRagSettings()} onRagUpdated={(next) => { setRagSettings(next); setRuntimeStatus(null); }} onOpenModels={() => jumpTo("models")} onStatusInvalidated={() => setRuntimeStatus(null)} onDirtyChange={handleRagDirty} />;
    if (active === "security") return <SecuritySection />;
    if (active === "experiments") return <ExperimentsSection />;
    return <StatusSection runtimeStatus={runtimeStatus} />;
  }

  return <Modal backdropClassName="settings-backdrop" onClose={requestClose} ariaLabel="设置">
    {/* Nested managers render alongside instead of replacing this dialog, so
        the Modal stack decides which layer Escape closes. */}
    {confirmLegacy && <ConfirmDialog
      busy={migrationBusy}
      danger={confirmLegacy === "archive"}
      title={confirmLegacy === "migrate" ? "迁移所选旧数据？" : "全部跳过并归档？"}
      detail={confirmLegacy === "migrate"
        ? "导入后，概念和记忆仍需在候选区确认。校验成功后会归档旧 JSON。"
        : "确认不导入任何旧概念或记忆，并将旧 JSON 归档？归档文件仍会保留在本地，但这些内容不会进入候选区。"}
      confirmLabel={confirmLegacy === "migrate" ? "迁移所选数据" : "跳过并归档"}
      onCancel={() => setConfirmLegacy(null)}
      onConfirm={() => void (confirmLegacy === "migrate" ? migrateLegacyGraph() : archiveLegacyGraphWithoutImport())}
    />}
    {pendingAction && (
      <ConfirmDialog
        danger
        title={`放弃未保存的${dirtySource || ""}修改？`}
        detail="离开当前页面后，尚未保存的修改将会丢失。"
        confirmLabel="放弃修改"
        cancelLabel="留在此处"
        onCancel={() => setPendingAction(null)}
        onConfirm={() => {
          const action = pendingAction;
          setDirtySource(null);
          setPendingAction(null);
          action();
        }}
      />
    )}
    <section className="settings-dialog">
      <header className="settings-dialog-header"><button className="settings-back" onClick={requestClose} aria-label="返回"><ChevronLeft size={18} /></button><strong>设置</strong><h2>{sections.find((item) => item.id === active)?.label}</h2><IconButton label="关闭设置" onClick={requestClose}><X size={18} /></IconButton></header>
      <div className="settings-dialog-body"><nav className="settings-nav" aria-label="设置分类"><SearchField className="settings-search" size="sm" value={query} onChange={setQuery} placeholder="搜索设置" ariaLabel="搜索设置" clearLabel="清空搜索" onCompositionStart={ime.compositionProps.onCompositionStart} onCompositionEnd={ime.compositionProps.onCompositionEnd} onKeyDown={(event) => { if (ime.isComposing(event)) return; if (!matches.length) return; if (event.key === "ArrowDown") { event.preventDefault(); setSearchIndex((current) => (current + 1) % matches.length); } else if (event.key === "ArrowUp") { event.preventDefault(); setSearchIndex((current) => (current - 1 + matches.length) % matches.length); } else if (event.key === "Enter") { event.preventDefault(); jumpTo(matches[Math.min(searchIndex, matches.length - 1)].tab, matches[Math.min(searchIndex, matches.length - 1)].label); } }} />{matches.length > 0 ? matches.map(({ id, label, icon: Icon, tab, hint }, index) => <button ref={active === id ? activeNavRef : undefined} className={`${active === tab ? "active" : ""} ${query && searchIndex === index ? "search-active" : ""}`} key={id} onClick={() => jumpTo(tab, query ? label : undefined)} title={hint ? `${label} · ${hint}` : label}><Icon size={18} /><span>{label}</span>{hint && <small>{hint}</small>}{id === "memory" && Boolean(memoryOverview?.pending_candidate_count) && <i className="settings-nav-badge">{memoryOverview?.pending_candidate_count}</i>}</button>) : <p className="sidebar-empty">没有匹配的设置项。</p>}</nav><main className="settings-main">{error && <div className="settings-error">{error}</div>}{notice && <div className="settings-notice"><Check size={16} />{notice}</div>}<SettingsHeading title={sections.find((item) => item.id === active)?.label || ""} /><SettingsPage tab={active}>{sectionContent()}</SettingsPage></main></div>
      {(active === "assistant" || active === "me") && (
        <footer className="settings-dialog-footer">
          {active === "assistant" ? (
            <button className="primary-button" disabled={saving} onClick={() => void saveAssistant()}>
              <Check size={16} />{saving ? "正在保存…" : "保存助手设置"}
            </button>
          ) : (
            <button className="primary-button" disabled={saving} onClick={() => void saveProfile()}>
              <Check size={16} />{saving ? "正在保存…" : "保存我的资料"}
            </button>
          )}
        </footer>
      )}
    </section>
  </Modal>;
}

export function SettingsUnavailableDialog({
  reconnecting,
  onRetry,
  onClose,
}: {
  reconnecting: boolean;
  onRetry: () => void;
  onClose: () => void;
}) {
  return <Modal backdropClassName="settings-backdrop" onClose={onClose} ariaLabel="设置">
    <section className="settings-dialog settings-unavailable">
      <header className="settings-dialog-header"><button className="settings-back" onClick={onClose} aria-label="返回"><ChevronLeft /></button><strong>设置</strong><h2>连接状态</h2><IconButton label="关闭设置" onClick={onClose}><X /></IconButton></header>
      <main className="settings-unavailable-main">
        <span className="settings-unavailable-icon"><Activity size={24} /></span>
        <div><span>Bobodan Settings</span><h2>设置暂时不可用</h2><p>学习页面仍可查看，但需要重新连接本地后端才能读取或修改设置。</p></div>
        <button className="primary-button" disabled={reconnecting} onClick={onRetry}>{reconnecting ? <><RefreshCw className="spin" size={15} />正在重连</> : <><RefreshCw size={15} />重新连接</>}</button>
      </main>
    </section>
  </Modal>;
}
