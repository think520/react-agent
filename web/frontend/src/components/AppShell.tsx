import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  ChevronLeft,
  FileText,
  Library,
  Menu,
  MessageCircle,
  MoreHorizontal,
  PanelLeft,
  PanelRight,
  PenLine,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, setActiveLibraryId } from "../lib/api";
import type { ChatSessionSummary, DocumentSummary, LibraryMigrationPreview, LibrarySummary, ReviewQueue, SettingsSummary } from "../types";
import { formatSessionTime, IconButton, LoadingState, textValue } from "./common";
import { OnboardingDialog } from "./OnboardingDialog";
import { LibrarySetupDialog, type LibrarySetupMode } from "./LibrarySetupDialog";
import { SettingsDialog, SettingsUnavailableDialog } from "./SettingsDialog";

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
  documents: DocumentSummary[];
  selectedDocumentIds: string[];
  selectedDocuments: DocumentSummary[];
  toggleDocumentScope: (documentId: string) => void;
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
  documentImportVersion: number;
  libraryReady: boolean;
}

const navItems = [
  { to: "/chat", label: "对话", icon: MessageCircle },
  { to: "/practice", label: "练习", icon: PenLine },
  { to: "/review", label: "复习", icon: BookOpen },
  { to: "/library", label: "资料库", icon: Library },
];

const pageMeta: Record<string, [string, string]> = {
  chat: ["学习对话", "今天想学什么？"],
  practice: ["主动练习", "用题目检验理解"],
  review: ["今日复习", "把薄弱点慢慢练熟"],
  library: ["本地资料", "你的学习材料"],
};

function LearningContext({
  documents,
  review,
  selectedDocumentIds,
  toggleDocumentScope,
}: {
  documents: DocumentSummary[];
  review: ReviewQueue | null;
  selectedDocumentIds: string[];
  toggleDocumentScope: (documentId: string) => void;
}) {
  const [tab, setTab] = useState<"sources" | "learning">("sources");
  const due = review?.due_concepts.length || 0;
  const weak = review?.weaknesses.length || 0;
  return (
    <div className="context-content">
      <div className="context-tabs" role="tablist" aria-label="学习书桌视图">
        <button className={tab === "sources" ? "active" : ""} role="tab" aria-selected={tab === "sources"} onClick={() => setTab("sources")}>资料</button>
        <button className={tab === "learning" ? "active" : ""} role="tab" aria-selected={tab === "learning"} onClick={() => setTab("learning")}>学习</button>
      </div>
      {tab === "sources" ? <>
        <section className="context-section">
          <div className="context-heading"><Sparkles size={16} />回答边界</div>
          <p className="context-copy">优先使用本地资料；网页来源、AI 补充和待核实内容会分别标注。</p>
        </section>
        <section className="context-section">
          <div className="context-heading"><Library size={16} />当前资料范围</div>
          {documents.length ? <div className="context-list">{documents.slice(0, 5).map((document) => (
            <button className={`context-document scope-document ${selectedDocumentIds.includes(document.document_id) ? "selected" : ""}`} key={document.document_id} onClick={() => toggleDocumentScope(document.document_id)}>
              <span className="document-icon"><FileText size={15} /></span>
              <span><strong>{document.title || document.source}</strong><small>{document.course || document.kind || "本地资料"}</small></span>
              <i aria-hidden="true" />
            </button>
          ))}</div> : <div className="context-empty-action"><p className="context-empty">还没有导入资料。</p><NavLink to="/library" className="text-link">导入第一份资料</NavLink></div>}
          {documents.length > 5 && <NavLink to="/library" className="text-link context-library-link">在资料库中选择更多</NavLink>}
        </section>
      </> : <>
        <section className="context-section">
          <div className="context-heading"><BookOpen size={16} />学习回流</div>
          <div className="context-metrics">
            <div><strong>{due}</strong><span>到期概念</span></div>
            <div><strong>{weak}</strong><span>薄弱点</span></div>
          </div>
          <NavLink to="/review" className="text-link">查看今日复习</NavLink>
        </section>
        <section className="context-section">
          <div className="context-heading"><PenLine size={16} />接下来</div>
          <div className="context-next-list">
            {(review?.due_concepts || []).slice(0, 3).map((item, index) => <div key={index}><span>{index + 1}</span><strong>{textValue(item, ["concept", "title", "name"], "待复习知识点")}</strong></div>)}
            {!due && <p className="context-empty">今天没有到期内容，可以开始一轮新练习。</p>}
          </div>
        </section>
      </>}
    </div>
  );
}

function sessionGroup(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "更早";
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayDiff = Math.round((startToday.getTime() - startDate.getTime()) / 86_400_000);
  if (dayDiff === 0) return "今天";
  if (dayDiff === 1) return "昨天";
  const weekday = startToday.getDay() || 7;
  const startWeek = new Date(startToday);
  startWeek.setDate(startToday.getDate() - weekday + 1);
  if (startDate >= startWeek) return "本周";
  return "更早";
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const section = location.pathname.split("/")[1] || "chat";
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [settings, setSettings] = useState<SettingsSummary | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("bobodan:scope:documents") || "[]"); }
    catch { return []; }
  });
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);
  const [review, setReview] = useState<ReviewQueue | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [leftSavedOpen, setLeftSavedOpen] = useState(() => localStorage.getItem("bobodan:sidebar:left") !== "false");
  const [rightSavedOpen, setRightSavedOpen] = useState(() => localStorage.getItem("bobodan:sidebar:right") !== "false");
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [leftPreview, setLeftPreview] = useState(false);
  const [rightPreview, setRightPreview] = useState(false);
  const previewTimer = useRef<number | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionQuery, setSessionQuery] = useState("");
  const [libraries, setLibraries] = useState<LibrarySummary[]>([]);
  const [activeLibrary, setActiveLibrary] = useState<LibrarySummary | null>(null);
  const [librarySetupOpen, setLibrarySetupOpen] = useState(false);
  const [librarySetupOptions, setLibrarySetupOptions] = useState<LibrarySetupOptions>({});
  const documentImportInput = useRef<HTMLInputElement>(null);
  const pendingDocumentFiles = useRef<File[]>([]);
  const [documentImporting, setDocumentImporting] = useState(false);
  const [documentImportNotice, setDocumentImportNotice] = useState("");
  const [documentImportError, setDocumentImportError] = useState("");
  const [documentImportVersion, setDocumentImportVersion] = useState(0);
  const [backendState, setBackendState] = useState<"connected" | "disconnected" | "reconnecting">("connected");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);

  const settingsSection = searchParams.get("settings");

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

  const uploadDocuments = useCallback(async (files: File[]) => {
    setDocumentImporting(true);
    setDocumentImportNotice("");
    setDocumentImportError("");
    try {
      const result = await api.importDocuments(files);
      const rejected = result.rejected.length ? `，${result.rejected.length} 份未能导入` : "";
      setDocumentImportNotice(`已导入 ${result.imported.length} 份资料并建立索引${rejected}。`);
      setDocumentImportVersion((current) => current + 1);
      await loadScopedData();
    } catch (reason) {
      setDocumentImportError(reason instanceof Error ? reason.message : "资料导入失败。");
    } finally {
      setDocumentImporting(false);
      navigate("/library");
    }
  }, [loadScopedData, navigate]);

  function openLibrarySetup(options: LibrarySetupOptions = {}) {
    setLibrarySetupOptions(options);
    setLibrarySetupOpen(true);
  }

  function cancelLibrarySetup() {
    if (librarySetupOptions.importCount) pendingDocumentFiles.current = [];
    setLibrarySetupOpen(false);
    setLibrarySetupOptions({});
  }

  function completeLibrarySetup() {
    setLibrarySetupOpen(false);
    setLibrarySetupOptions({});
  }

  function startDocumentImport() {
    setDocumentImportNotice("");
    setDocumentImportError("");
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
    root.style.setProperty("--body-font-size", `${appearance.body_font_size}px`);
    root.style.setProperty("--content-width", `${appearance.content_width}px`);
  }, [settings]);

  useEffect(() => {
    if (!settings || localStorage.getItem("bobodan:preferences:migrated") === "1") return;
    let legacy: { displayName?: string; learningGoal?: string; memoryEnabled?: boolean } = {};
    try { legacy = JSON.parse(localStorage.getItem("bobodan:learning-profile") || "{}"); }
    catch { legacy = {}; }
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
    if (!activeLibrary || !pendingDocumentFiles.current.length) return;
    const files = pendingDocumentFiles.current;
    pendingDocumentFiles.current = [];
    void uploadDocuments(files);
  }, [activeLibrary?.library_id, uploadDocuments]);

  useEffect(() => {
    localStorage.setItem("bobodan:scope:documents", JSON.stringify(selectedDocumentIds));
  }, [selectedDocumentIds]);

  useEffect(() => {
    if (!initialDataLoaded || !activeLibrary || localStorage.getItem("bobodan:onboarding:v1") === "complete") return;
    if (sessions.length || documents.length) {
      localStorage.setItem("bobodan:onboarding:v1", "complete");
      return;
    }
    setOnboardingOpen(true);
  }, [activeLibrary, documents.length, initialDataLoaded, sessions.length]);

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
    setSelectedDocumentIds([]);
    const registry = await api.libraries();
    setLibraries(registry.libraries);
    navigate("/library");
    await loadScopedData();
  }

  async function switchLibrary(libraryId: string) {
    if (libraryId === activeLibrary?.library_id) return;
    setDocumentImportNotice("");
    setDocumentImportError("");
    const library = await api.activateLibrary(libraryId);
    setActiveLibraryId(library.library_id);
    setActiveLibrary(library);
    setSelectedDocumentIds([]);
    navigate("/chat");
    await loadScopedData();
  }

  useEffect(() => {
    if (!initialDataLoaded || documents.length === 0) return;
    const valid = new Set(documents.map((document) => document.document_id));
    setSelectedDocumentIds((current) => current.filter((id) => valid.has(id)));
  }, [documents, initialDataLoaded]);

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
    setContextOpen(false);
  }, [location.pathname]);

  const activeSession = useMemo(
    () => sessions.find((session) => session.chat_session_id === params.sessionId),
    [params.sessionId, sessions],
  );
  const meta = pageMeta[section] || pageMeta.chat;
  const title = activeSession?.name || meta[1];
  const groupedSessions = useMemo(() => {
    const query = sessionQuery.trim().toLocaleLowerCase();
    const filtered = sessions.filter((session) => !query || (session.name || "未命名会话").toLocaleLowerCase().includes(query));
    return ["今天", "昨天", "本周", "更早"].map((label) => ({
      label,
      sessions: filtered.filter((session) => sessionGroup(session.last_active) === label),
    })).filter((group) => group.sessions.length);
  }, [sessionQuery, sessions]);

  const desktop = viewportWidth >= 768;
  const rightAutoCollapsed = viewportWidth < 1288;
  const leftAutoCollapsed = viewportWidth < 972;
  const leftOpen = leftSavedOpen && !leftAutoCollapsed;
  const rightOpen = rightSavedOpen && !rightAutoCollapsed;

  function persistPanel(side: "left" | "right", open: boolean) {
    localStorage.setItem(`bobodan:sidebar:${side}`, String(open));
    if (side === "left") setLeftSavedOpen(open);
    else setRightSavedOpen(open);
  }

  function schedulePreview(side: "left" | "right", open: boolean) {
    if (!desktop) return;
    if (previewTimer.current !== null) window.clearTimeout(previewTimer.current);
    previewTimer.current = window.setTimeout(() => {
      if (side === "left") setLeftPreview(open);
      else setRightPreview(open);
    }, 200);
  }

  function togglePanel(side: "left" | "right") {
    const autoCollapsed = side === "left" ? leftAutoCollapsed : rightAutoCollapsed;
    if (autoCollapsed) {
      if (side === "left") setLeftPreview((value) => !value);
      else setRightPreview((value) => !value);
      return;
    }
    persistPanel(side, !(side === "left" ? leftSavedOpen : rightSavedOpen));
  }

  function toggleDocumentScope(documentId: string) {
    setSelectedDocumentIds((current) => current.includes(documentId)
      ? current.filter((id) => id !== documentId)
      : [...current, documentId]);
  }

  const selectedDocuments = useMemo(
    () => documents.filter((document) => selectedDocumentIds.includes(document.document_id)),
    [documents, selectedDocumentIds],
  );

  async function saveRename(id: string) {
    const name = editingName.trim();
    if (!name) return;
    await api.renameSession(id, name);
    setEditingId(null);
    await refreshSessions();
  }

  async function removeSession(session: ChatSessionSummary) {
    if (!window.confirm(`删除会话「${session.name || "未命名会话"}」？此操作无法撤销。`)) return;
    await api.deleteSession(session.chat_session_id);
    if (params.sessionId === session.chat_session_id) navigate("/chat");
    await refreshSessions();
  }

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
        <div className="session-section">
          <div className="section-label"><span>最近对话</span><IconButton label="刷新会话" onClick={() => void refreshSessions()}><RefreshCw size={15} /></IconButton></div>
          <label className="session-search"><Search size={14} /><input value={sessionQuery} onChange={(event) => setSessionQuery(event.target.value)} placeholder="搜索对话" aria-label="搜索对话" /></label>
          {loadingSessions ? <LoadingState label="正在找回会话…" /> : groupedSessions.length ? (
            <div className="session-list">{groupedSessions.map((group) => <section className="session-group" key={group.label}><div className="session-group-label">{group.label}</div>{group.sessions.map((session) => (
              <div className={`session-row ${params.sessionId === session.chat_session_id ? "active" : ""}`} key={session.chat_session_id}>
                {editingId === session.chat_session_id ? (
                  <form onSubmit={(event) => { event.preventDefault(); void saveRename(session.chat_session_id); }}>
                    <input autoFocus value={editingName} maxLength={120} onChange={(event) => setEditingName(event.target.value)} onBlur={() => void saveRename(session.chat_session_id)} />
                  </form>
                ) : (
                  <button className="session-main" onClick={() => navigate(`/chat/${session.chat_session_id}`)}>
                    <span>{session.name || "未命名会话"}</span><small>{formatSessionTime(session.last_active)}</small>
                  </button>
                )}
                <div className="session-actions">
                  <IconButton label="重命名" onClick={() => { setEditingId(session.chat_session_id); setEditingName(session.name || ""); }}><MoreHorizontal size={15} /></IconButton>
                  <IconButton label="删除会话" onClick={() => void removeSession(session)}><Trash2 size={14} /></IconButton>
                </div>
              </div>
            ))}</section>)}</div>
          ) : <p className="sidebar-empty">{sessionQuery ? "没有找到匹配的对话。" : "你的学习对话会保存在这里。"}</p>}
        </div>
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
          <IconButton label={rightOpen ? "收起右栏" : "展开右栏"} className="panel-toggle desktop-panel-toggle" onClick={() => togglePanel("right")}><PanelRight /></IconButton>
          <IconButton label="学习上下文" className="context-button" onClick={() => setContextOpen(true)}><PanelRight /></IconButton>
        </header>
        <Outlet context={{
          sessions,
          settings,
          refreshSettings,
          refreshSessions,
          openContext: () => desktop ? persistPanel("right", true) : setContextOpen(true),
          documents,
          selectedDocumentIds,
          selectedDocuments,
          toggleDocumentScope,
          clearDocumentScope: () => setSelectedDocumentIds([]),
          libraries,
          activeLibrary,
          openLibrarySetup,
          createLibrary,
          switchLibrary,
          startDocumentImport,
          documentImporting,
          documentImportNotice,
          documentImportError,
          documentImportVersion,
          libraryReady: initialDataLoaded,
        } satisfies AppOutletContext} />
      </main>

      <aside className={`context-panel ${contextOpen ? "open" : ""}`} aria-label="学习上下文" onMouseEnter={() => schedulePreview("right", true)} onMouseLeave={() => schedulePreview("right", false)}>
        <div className="context-header"><strong>学习书桌</strong><IconButton label="关闭上下文" onClick={() => setContextOpen(false)}><X /></IconButton></div>
        <LearningContext documents={documents} review={review} selectedDocumentIds={selectedDocumentIds} toggleDocumentScope={toggleDocumentScope} />
      </aside>

      {!leftOpen && <div className="panel-hover-edge left" onMouseEnter={() => schedulePreview("left", true)} onMouseLeave={() => schedulePreview("left", false)} />}
      {!rightOpen && <div className="panel-hover-edge right" onMouseEnter={() => schedulePreview("right", true)} onMouseLeave={() => schedulePreview("right", false)} />}

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
          localStorage.setItem("bobodan:learning-profile", JSON.stringify(profile));
          if (settings) {
            void api.patchPreferences(settings.preferences.revision, {
              user: { display_name: profile.displayName, long_term_goal: profile.learningGoal },
              memory: { enabled: profile.memoryEnabled },
              search: { permission: profile.webEnabled ? "auto" : "ask" },
            }).then(() => refreshSettings()).catch(() => undefined);
          }
          setOnboardingOpen(false);
        }}
      />}
      {librarySetupOpen && <LibrarySetupDialog
        onClose={cancelLibrarySetup}
        onComplete={completeLibrarySetup}
        onCreate={async (name, parentPath) => { await createLibrary(name, parentPath); }}
        onOpen={openExistingLibrary}
        onPreviewMigration={previewLibraryMigration}
        onMigrate={migrateLibrary}
        initialMode={librarySetupOptions.initialMode}
        importCount={librarySetupOptions.importCount}
      />}
      <input ref={documentImportInput} className="visually-hidden" type="file" multiple accept=".md,.pdf,.docx,.pptx" onChange={(event) => void selectDocumentsForImport(event)} />
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
    </div>
  );
}
