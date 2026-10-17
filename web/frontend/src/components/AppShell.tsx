import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, Keyboard, Menu, PanelLeft, PanelRight, Plus, Settings } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, setActiveLibraryId } from "../lib/api";
import { clearImportReport, emptyDocumentImport } from "../lib/importState";
import type { DocumentImportState } from "../lib/importState";
import { errorCodeOf } from "../lib/errorHints";
import { useImportRun } from "../hooks/useImportRun";
import { toErrorMessage } from "../lib/errors";
import { describeDocumentImport } from "../lib/importSummary";
import { notifyError } from "../stores/noticeStore";
import { useUiStore } from "../stores/uiStore";
import type { Attribution, ChatSessionSummary, DocumentSummary, KnowledgeContext, LibraryMigrationPreview, LibrarySummary, ReviewQueue, SettingsSummary } from "../types";
import { IconButton } from "./common";
import { OnboardingDialog } from "./OnboardingDialog";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { LibrarySetupDialog } from "./LibrarySetupDialog";
import { SettingsDialog, SettingsUnavailableDialog } from "./SettingsDialog";
import { SessionRail } from "./SessionRail";
import { NoticeCenter } from "./NoticeCenter";
import { navItems, pageMeta } from "./shell/nav";
import { ContextPanel } from "./shell/ContextPanel";

import type { AppOutletContext } from "./shell/types";
import { resolveTheme, systemPrefersDark, watchSystemTheme } from "../lib/theme";
export type { AppOutletContext, LibrarySetupOptions } from "./shell/types";

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const section = location.pathname.split("/")[1] || "chat";
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [settings, setSettings] = useState<SettingsSummary | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);
  const [review, setReview] = useState<ReviewQueue | null>(null);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const previewTimer = useRef<number | null>(null);
  const importRun = useImportRun();
  const [documentImport, setDocumentImport] = useState<DocumentImportState>(emptyDocumentImport);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [libraries, setLibraries] = useState<LibrarySummary[]>([]);
  const [activeLibrary, setActiveLibrary] = useState<LibrarySummary | null>(null);
  const documentImportInput = useRef<HTMLInputElement>(null);
  const pendingDocumentFiles = useRef<File[]>([]);
  const pendingDuplicateFiles = useRef<File[]>([]);
  // E8：留下这次"需要处理"的文件对象，才能提供真正的重试（而不是假按钮）。
  const pendingRetryFiles = useRef<File[]>([]);
  const [backendState, setBackendState] = useState<"connected" | "disconnected" | "reconnecting">("connected");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);

  // Cross-cutting UI state lives in the store (persisted keys included).
  const selectedDocumentIds = useUiStore((state) => state.documentScope);
  const toggleDocumentScope = useUiStore((state) => state.toggleDocumentScope);
  const setDocumentScope = useUiStore((state) => state.setDocumentScope);
  const clearDocumentScope = useUiStore((state) => state.clearDocumentScope);
  const pruneDocumentScope = useUiStore((state) => state.pruneDocumentScope);
  const leftSavedOpen = useUiStore((state) => state.leftSidebarOpen);
  const rightSavedOpen = useUiStore((state) => state.rightSidebarOpen);
  const setPanelOpen = useUiStore((state) => state.setPanelOpen);
  const sidebarOpen = useUiStore((state) => state.mobileSidebarOpen);
  const setSidebarOpen = useUiStore((state) => state.setMobileSidebarOpen);
  const contextOpen = useUiStore((state) => state.mobileContextOpen);
  const setContextOpen = useUiStore((state) => state.setMobileContextOpen);
  const leftPreview = useUiStore((state) => state.leftPreview);
  const rightPreview = useUiStore((state) => state.rightPreview);
  const setPreview = useUiStore((state) => state.setPreview);
  const togglePreview = useUiStore((state) => state.togglePreview);
  const setLearningProfile = useUiStore((state) => state.setLearningProfile);
  const onboardingOpen = useUiStore((state) => state.onboardingOpen);
  const setOnboardingOpen = useUiStore((state) => state.setOnboardingOpen);
  const librarySetup = useUiStore((state) => state.librarySetup);
  const openLibrarySetup = useUiStore((state) => state.openLibrarySetup);
  const closeLibrarySetup = useUiStore((state) => state.closeLibrarySetup);
  const conceptDetailId = useUiStore((state) => state.conceptDetailId);
  const setConceptDetailId = useUiStore((state) => state.setConceptDetailId);
  const knowledgeContext = useUiStore((state) => state.knowledgeContext);
  const setKnowledgeContext = useUiStore((state) => state.setKnowledgeContext);
  const sourceContext = useUiStore((state) => state.sourceContext);
  const setSourceContext = useUiStore((state) => state.setSourceContext);

  const settingsSection = searchParams.get("settings");
  const activeLibraryId = activeLibrary?.library_id || null;

  useEffect(() => {
    if (section !== "knowledge-map") setConceptDetailId(null);
  }, [section, setConceptDetailId]);

  const refreshSettings = useCallback(async () => {
    try {
      const result = await api.settings();
      setSettings(result);
      return result;
    } catch {
      return null;
    }
  }, []);

  const reconnectBackend = useCallback(async () => {
    setBackendState("reconnecting");
    try {
      await api.health();
      setBackendState("connected");
      setReconnectAttempt(0);
      await refreshSettings();
    } catch {
      setBackendState("disconnected");
    }
  }, [refreshSettings]);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.sessions());
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const loadScopedData = useCallback(async () => {
    await Promise.all([
      refreshSessions(),
      api.documents("material").then(setDocuments).catch(() => setDocuments([])),
      api.reviewQueue().then(setReview).catch(() => setReview(null)),
    ]);
  }, [refreshSessions]);

  const uploadDocuments = useCallback(async (files: File[], duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing") => {
    setDocumentImport((current) => ({ ...current, importing: true, notice: "", error: "", duplicateCount: duplicateStrategy === "save_copy" ? 0 : current.duplicateCount }));
    try {
      // E8：导入走**运行态**（可轮询进度、可取消），不再是黑盒的一次性 POST。
      const result = await importRun.start(files, duplicateStrategy);
      if (!result) throw new Error("导入没有返回结果。");
      const duplicates = result.duplicates || [];
      if (duplicateStrategy === "keep_existing") {
        const duplicateNames = new Set(duplicates.map((item) => item.filename));
        pendingDuplicateFiles.current = files.filter((file) => duplicateNames.has(file.name));
      } else {
        pendingDuplicateFiles.current = [];
      }
      const batch = result.results || [];
      // E8：留下"需要处理"的那几份文件对象，重试按钮才有真东西可重发。
      const problematic = new Set(
        batch
          .filter((item) => item.status === "rejected" || item.status === "cancelled"
            || (item.status === "imported" && !item.searchable))
          .map((item) => item.filename),
      );
      pendingRetryFiles.current = files.filter((file) => problematic.has(file.name));
      setDocumentImport((current) => ({
        ...current,
        notice: describeDocumentImport(result),
        duplicateCount: duplicates.length,
        results: batch,
        version: current.version + 1,
      }));
      await loadScopedData();
    } catch (reason) {
      setDocumentImport((current) => ({
        ...current,
        error: toErrorMessage(reason, "资料导入失败。"),
        // W1 E1：把 code 一起留下，界面才能说"下一步"（换格式 / 去设置 / 稍后重试）。
        errorCode: errorCodeOf(reason),
      }));
    } finally {
      setDocumentImport((current) => ({ ...current, importing: false }));
      navigate("/library");
    }
  }, [importRun, loadScopedData, navigate]);

  const importDroppedFiles = useCallback((files: File[]) => {
    if (!files.length) return;
    if (!activeLibrary) {
      pendingDocumentFiles.current = files;
      openLibrarySetup({ initialMode: "create", importCount: files.length });
      return;
    }
    void uploadDocuments(files);
  }, [activeLibrary, openLibrarySetup, uploadDocuments]);

  /** E8：重试这次"需要处理"的那几份（复用导入通道：字节已在库里的会走补索引路径）。 */
  const retryFailedImports = useCallback(() => {
    const files = pendingRetryFiles.current;
    pendingRetryFiles.current = [];
    if (files.length) void uploadDocuments(files);
  }, [uploadDocuments]);

  const dismissImportReport = useCallback(() => {
    pendingRetryFiles.current = [];
    setDocumentImport((current) => ({ ...current, results: null }));
  }, []);

  const importDuplicatesAsCopies = useCallback(() => {
    const files = pendingDuplicateFiles.current;
    pendingDuplicateFiles.current = [];
    if (files.length) void uploadDocuments(files, "save_copy");
  }, [uploadDocuments]);

  function cancelLibrarySetup() {
    if (librarySetup?.importCount) pendingDocumentFiles.current = [];
    closeLibrarySetup();
  }

  function startDocumentImport() {
    pendingDuplicateFiles.current = [];
    setDocumentImport((current) => ({ ...current, notice: "", error: "", duplicateCount: 0 }));
    documentImportInput.current?.click();
  }

  async function selectDocumentsForImport(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    if (!activeLibrary) {
      pendingDocumentFiles.current = files;
      openLibrarySetup({ initialMode: "create", importCount: files.length });
      return;
    }
    await uploadDocuments(files);
  }

  useEffect(() => {
    void Promise.all([refreshSettings(), api.libraries()])
      .then(async ([, registry]) => {
        setLibraries(registry.libraries);
        const remembered = localStorage.getItem("bobodan:library:active");
        const selected = registry.libraries.find((item) => item.library_id === remembered && item.available)
          || registry.libraries.find((item) => item.library_id === registry.active_library_id && item.available)
          || registry.libraries.find((item) => item.available)
          || null;
        setActiveLibraryId(selected?.library_id || null);
        setActiveLibrary(selected);
        if (selected) await loadScopedData();
        else {
          setSessions([]);
          setDocuments([]);
          setReview(null);
          setLoadingSessions(false);
        }
      })
      .catch(() => setLoadingSessions(false))
      .finally(() => setInitialDataLoaded(true));
  }, [loadScopedData, refreshSettings]);

  useEffect(() => {
    if (!settings) return;
    const appearance = settings.preferences.appearance;
    const root = document.documentElement;
    root.dataset.readingFont = appearance.reading_font;
    root.dataset.paperTexture = appearance.paper_texture ? "on" : "off";
    root.dataset.sessionDensity = appearance.session_density;
    root.dataset.motion = appearance.motion;
    root.dataset.theme = resolveTheme(appearance.theme ?? "system", systemPrefersDark());
    root.dataset.contrast = appearance.contrast === "high" ? "high" : "normal";
    root.style.setProperty("--body-font-size", `${appearance.body_font_size}px`);
    root.style.setProperty("--content-width", `${appearance.content_width}px`);
  }, [settings]);

  // 主题 = 跟随系统时，系统切换要实时反映（W-F6）。
  useEffect(() => {
    if (!settings) return;
    if ((settings.preferences.appearance.theme ?? "system") !== "system") return;
    return watchSystemTheme((prefersDark) => {
      document.documentElement.dataset.theme = prefersDark ? "dark" : "light";
    });
  }, [settings]);

  useEffect(() => {
    if (!settings || localStorage.getItem("bobodan:preferences:migrated") === "1") return;
    const legacy = useUiStore.getState().learningProfile;
    const patch: Record<string, unknown> = {};
    if ((legacy.displayName && !settings.preferences.user.display_name) || (legacy.learningGoal && !settings.preferences.user.long_term_goal)) {
      patch.user = {
        ...(legacy.displayName ? { display_name: legacy.displayName } : {}),
        ...(legacy.learningGoal ? { long_term_goal: legacy.learningGoal } : {}),
      };
    }
    if (typeof legacy.memoryEnabled === "boolean" && settings.preferences.memory.enabled !== legacy.memoryEnabled) {
      patch.memory = { enabled: legacy.memoryEnabled };
    }
    if (!Object.keys(patch).length) {
      localStorage.setItem("bobodan:preferences:migrated", "1");
      return;
    }
    void api.patchPreferences(settings.preferences.revision, patch)
      .then(() => refreshSettings())
      .then(() => localStorage.setItem("bobodan:preferences:migrated", "1"))
      .catch(() => undefined);
  }, [refreshSettings, settings]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const delays = [2000, 5000, 10000, 30000];
    const check = async (attempt = 0) => {
      try {
        await api.health();
        if (!cancelled) {
          setBackendState("connected");
          setReconnectAttempt(0);
        }
      } catch {
        if (cancelled) return;
        setBackendState("disconnected");
        setReconnectAttempt(attempt + 1);
        timer = window.setTimeout(() => {
          setBackendState("reconnecting");
          void check(attempt + 1);
        }, delays[Math.min(attempt, delays.length - 1)]);
      }
    };
    void check();
    const interval = window.setInterval(() => void api.health().catch(() => void check()), 30000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  // Ctrl/Cmd+N — the shortcut the 新对话 button advertises.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        setShortcutsOpen(false);
        navigate("/chat");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  function openSettings(section = "assistant") {
    const next = new URLSearchParams(searchParams);
    next.set("settings", section);
    setSearchParams(next, { replace: true });
  }

  function closeSettings() {
    const next = new URLSearchParams(searchParams);
    next.delete("settings");
    setSearchParams(next, { replace: true });
    requestAnimationFrame(() => settingsButtonRef.current?.focus());
  }

  useEffect(() => {
    if (!activeLibraryId || !pendingDocumentFiles.current.length) return;
    const files = pendingDocumentFiles.current;
    pendingDocumentFiles.current = [];
    void uploadDocuments(files);
  }, [activeLibraryId, uploadDocuments]);

  useEffect(() => {
    if (!initialDataLoaded || !activeLibrary || localStorage.getItem("bobodan:onboarding:v1") === "complete") return;
    if (sessions.length || documents.length) {
      localStorage.setItem("bobodan:onboarding:v1", "complete");
      return;
    }
    setOnboardingOpen(true);
  }, [activeLibrary, documents.length, initialDataLoaded, sessions.length, setOnboardingOpen]);

  async function createLibrary(name: string, parentPath: string) {
    const library = await api.createLibrary(name, parentPath);
    setActiveLibraryId(library.library_id);
    setActiveLibrary(library);
    const registry = await api.libraries();
    setLibraries(registry.libraries);
    await loadScopedData();
    return library;
  }

  async function openExistingLibrary(path: string) {
    const library = await api.openLibrary(path);
    setActiveLibraryId(library.library_id);
    setActiveLibrary(library);
    const registry = await api.libraries();
    setLibraries(registry.libraries);
    await loadScopedData();
  }

  async function previewLibraryMigration(path: string): Promise<LibraryMigrationPreview> {
    return api.previewLibraryMigration(path);
  }

  async function migrateLibrary(name: string, path: string) {
    const result = await api.migrateLibrary(path, name);
    setActiveLibraryId(result.library.library_id);
    setActiveLibrary(result.library);
    clearDocumentScope();
    const registry = await api.libraries();
    setLibraries(registry.libraries);
    navigate("/library");
    await loadScopedData();
  }

  async function switchLibrary(libraryId: string) {
    if (libraryId === activeLibrary?.library_id) return;
    // W1 E1：导入报告、通知与"可重试文件"都属于**上一个**资料库 —— 不清就会串库
    // （上一库的失败清单还挂着，点「重试这 N 份」会导进新库）。
    setDocumentImport(clearImportReport);
    pendingRetryFiles.current = [];
    setConceptDetailId(null);
    setKnowledgeContext(null);
    setSourceContext(null);
    const library = await api.activateLibrary(libraryId);
    setActiveLibraryId(library.library_id);
    setActiveLibrary(library);
    clearDocumentScope();
    navigate("/chat");
    await loadScopedData();
  }

  useEffect(() => {
    if (!initialDataLoaded || documents.length === 0) return;
    pruneDocumentScope(documents.map((document) => document.document_id));
  }, [documents, initialDataLoaded, pruneDocumentScope]);

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
    setContextOpen(false);
  }, [location.pathname, setContextOpen, setSidebarOpen]);

  const activeSession = useMemo(
    () => sessions.find((session) => session.chat_session_id === params.sessionId),
    [params.sessionId, sessions],
  );
  const meta = pageMeta[section] || pageMeta.chat;
  const title = activeSession?.name || meta[1];

  const desktop = viewportWidth >= 768;
  const rightAutoCollapsed = viewportWidth < 1288;
  const leftAutoCollapsed = viewportWidth < 972;
  const leftOpen = leftSavedOpen && !leftAutoCollapsed;
  const rightOpen = rightSavedOpen && !rightAutoCollapsed;

  const openRightPanel = useCallback(() => {
    if (!desktop) {
      setContextOpen(true);
    } else if (rightAutoCollapsed) {
      setPreview("right", true);
    } else {
      setPanelOpen("right", true);
    }
  }, [desktop, rightAutoCollapsed, setContextOpen, setPanelOpen, setPreview]);

  function openConceptDetail(conceptId: string) {
    setConceptDetailId(conceptId);
    openRightPanel();
  }

  const showKnowledgeContext = useCallback((context: KnowledgeContext) => {
    setKnowledgeContext(context);
    openRightPanel();
  }, [openRightPanel, setKnowledgeContext]);

  // 流式/恢复时只记录上下文，不自动打开面板（P5G 体验整改：卡片不自动弹面板）
  const receiveKnowledgeContext = useCallback((context: KnowledgeContext) => {
    setKnowledgeContext(context);
  }, [setKnowledgeContext]);

  const clearKnowledgeContext = useCallback(() => setKnowledgeContext(null), [setKnowledgeContext]);

  function showSourceContext(attribution: Attribution) {
    setSourceContext(attribution);
    setConceptDetailId(null);
    openRightPanel();
  }

  function schedulePreview(side: "left" | "right", open: boolean) {
    if (!desktop) return;
    if (previewTimer.current !== null) window.clearTimeout(previewTimer.current);
    previewTimer.current = window.setTimeout(() => setPreview(side, open), 200);
  }

  function togglePanel(side: "left" | "right") {
    const autoCollapsed = side === "left" ? leftAutoCollapsed : rightAutoCollapsed;
    if (autoCollapsed) {
      togglePreview(side);
      return;
    }
    setPanelOpen(side, !(side === "left" ? leftSavedOpen : rightSavedOpen));
  }

  const selectedDocuments = useMemo(
    () => documents.filter((document) => selectedDocumentIds.includes(document.document_id)),
    [documents, selectedDocumentIds],
  );

  const contextPanelView = {
    contextOpen,
    conceptDetailId,
    desktop,
    rightAutoCollapsed,
    setPreview,
    setContextOpen,
    setConceptDetailId,
    openConceptDetail,
    documents,
    review,
    selectedDocumentIds,
    toggleDocumentScope,
    knowledgeContext,
    sourceContext,
    openMapForConcept: (conceptId: string) => navigate("/knowledge-map", { state: { focusConceptId: conceptId } }),
  };

  return (
    <div className={`app-shell ${leftOpen ? "" : "left-collapsed"} ${rightOpen ? "" : "right-collapsed"} ${leftPreview ? "left-preview" : ""} ${rightPreview ? "right-preview" : ""}`}>
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`} aria-label="主导航" onMouseEnter={() => schedulePreview("left", true)} onMouseLeave={() => schedulePreview("left", false)}>
        <div className="brand-row">
          <img
            src="/assets/brand/avatar/bobodan-avatar-64.png"
            srcSet="/assets/brand/avatar/bobodan-avatar-64.png 1x, /assets/brand/avatar/bobodan-avatar-128.png 2x"
            width="36"
            height="36"
            alt=""
          />
          <div><strong>Bobodan</strong><span>Local learning companion</span></div>
          <IconButton label="收起导航" className="mobile-only" onClick={() => setSidebarOpen(false)}><ChevronLeft /></IconButton>
        </div>
        <button className="new-chat-button" onClick={() => navigate("/chat")}><span><Plus size={17} />新对话</span><kbd>Ctrl N</kbd></button>
        <nav className="primary-nav">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink to={to} key={to} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
              <Icon size={18} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <SessionRail
          sessions={sessions}
          loading={loadingSessions}
          activeSessionId={params.sessionId}
          refreshSessions={refreshSessions}
        />
        <div className="profile-row">
          <span className="profile-avatar">库</span>
          <span><strong>{activeLibrary?.name || "尚未选择资料库"}</strong><small>{settings?.default_provider || "等待连接 AI"}</small></span>
          <button ref={settingsButtonRef} className="icon-button" aria-label="打开设置" title="打开设置" onClick={() => openSettings()}><Settings size={17} /></button>
        </div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <IconButton label="打开导航" className="menu-button" onClick={() => setSidebarOpen(true)}><Menu /></IconButton>
          <IconButton label={leftOpen ? "收起左栏" : "展开左栏"} className="panel-toggle desktop-panel-toggle" onClick={() => togglePanel("left")}><PanelLeft /></IconButton>
          <div className="topbar-title"><span>{meta[0]}</span><h1>{title}</h1></div>
          <IconButton label="键盘快捷键" onClick={() => setShortcutsOpen(true)}><Keyboard size={17} /></IconButton>
          <IconButton label={rightOpen ? "收起右栏" : "展开右栏"} className="panel-toggle desktop-panel-toggle" onClick={() => togglePanel("right")}><PanelRight /></IconButton>
          <IconButton label="学习上下文" className="context-button" onClick={() => setContextOpen(true)}><PanelRight /></IconButton>
        </header>
        <Outlet context={{
          sessions,
          settings,
          refreshSettings,
          refreshSessions,
          openContext: openRightPanel,
          conceptDetailId,
          openConceptDetail,
          closeConceptDetail: () => setConceptDetailId(null),
          showKnowledgeContext,
          receiveKnowledgeContext,
          clearKnowledgeContext,
          showSourceContext,
          documents,
          selectedDocumentIds,
          selectedDocuments,
          toggleDocumentScope,
          setDocumentScope,
          clearDocumentScope,
          libraries,
          activeLibrary,
          openLibrarySetup,
          createLibrary,
          switchLibrary,
          startDocumentImport,
          documentImporting: documentImport.importing || importRun.running,
    documentImportProgress: importRun.progress,
    documentImportErrorCode: documentImport.errorCode,
    cancelDocumentImport: () => void importRun.cancel(),
          documentImportNotice: documentImport.notice,
          documentImportError: documentImport.error,
          documentImportDuplicateCount: documentImport.duplicateCount,
          importDuplicatesAsCopies,
          documentImportVersion: documentImport.version,
          importDroppedFiles,
          documentImportResults: documentImport.results,
          documentImportCanRetry: pendingRetryFiles.current.length > 0,
          retryFailedImports,
          dismissImportReport,
          libraryReady: initialDataLoaded,
        } satisfies AppOutletContext} />
      </main>
      <ContextPanel view={contextPanelView} />
      {!leftOpen && <div className="panel-hover-edge left" onMouseEnter={() => schedulePreview("left", true)} onMouseLeave={() => schedulePreview("left", false)} />}

      <nav className="mobile-nav" aria-label="移动端主导航">
        {navItems.map(({ to, label, icon: Icon }) => <NavLink to={to} key={to} className={({ isActive }) => isActive ? "active" : ""}><Icon /><span>{label}</span></NavLink>)}
      </nav>
      {(sidebarOpen || contextOpen) && <button className="scrim" aria-label="关闭浮层" onClick={() => { setSidebarOpen(false); setContextOpen(false); }} />}
      {onboardingOpen && <OnboardingDialog
        settings={settings}
        documents={documents}
        selectedDocumentIds={selectedDocumentIds}
        onToggleDocument={toggleDocumentScope}
        onComplete={(profile) => {
          localStorage.setItem("bobodan:onboarding:v1", "complete");
          setLearningProfile(profile);
          if (settings) {
            void api.patchPreferences(settings.preferences.revision, {
              user: { display_name: profile.displayName, long_term_goal: profile.learningGoal },
              memory: { enabled: profile.memoryEnabled },
              search: { permission: profile.webEnabled ? "auto" : "ask" },
            }).then(() => refreshSettings()).catch((reason: Error) => notifyError(toErrorMessage(reason, "首次配置没有保存成功，请到设置里检查。")));
          }
          setOnboardingOpen(false);
        }}
      />}
      {librarySetup && <LibrarySetupDialog
        onClose={cancelLibrarySetup}
        onComplete={closeLibrarySetup}
        onCreate={async (name, parentPath) => { await createLibrary(name, parentPath); }}
        onOpen={openExistingLibrary}
        onPreviewMigration={previewLibraryMigration}
        onMigrate={migrateLibrary}
        initialMode={librarySetup.initialMode}
        importCount={librarySetup.importCount}
      />}
      <input ref={documentImportInput} className="visually-hidden" type="file" multiple accept=".md,.txt,.pdf,.docx,.pptx" onChange={(event) => void selectDocumentsForImport(event)} />
      {backendState !== "connected" && <div className={`connection-bar ${backendState}`} role="status">
        <span>{backendState === "reconnecting" ? "正在重新连接 Bobodan…" : `Bobodan 后端已断开${reconnectAttempt ? `，已重试 ${reconnectAttempt} 次` : ""}`}</span>
        <button type="button" onClick={() => void reconnectBackend()}>重新连接</button>
      </div>}
      {settingsSection && settings && <SettingsDialog
        settings={settings}
        activeLibrary={activeLibrary}
        section={settingsSection}
        onSectionChange={(nextSection) => openSettings(nextSection)}
        onClose={closeSettings}
        onSettingsChange={setSettings}
      />}
      {settingsSection && initialDataLoaded && !settings && <SettingsUnavailableDialog
        reconnecting={backendState === "reconnecting"}
        onRetry={() => void reconnectBackend()}
        onClose={closeSettings}
      />}
      {shortcutsOpen && <ShortcutsDialog onClose={() => setShortcutsOpen(false)} />}
      <NoticeCenter />
    </div>
  );
}
