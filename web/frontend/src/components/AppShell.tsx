import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  ChevronLeft,
  FileText,
  Library,
  Map,
  Menu,
  MessageCircle,
  NotebookPen,
  PanelLeft,
  PanelRight,
  PenLine,
  Plus,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, setActiveLibraryId } from "../lib/api";
import { toErrorMessage } from "../lib/errors";
import { useUiStore } from "../stores/uiStore";
import type { Attribution, ChatSessionSummary, DocumentSummary, KnowledgeContext, LibraryMigrationPreview, LibrarySummary, ReviewQueue, SettingsSummary } from "../types";
import { groupAttributionSources, IconButton, textValue } from "./common";
import { OnboardingDialog } from "./OnboardingDialog";
import { LibrarySetupDialog, type LibrarySetupMode } from "./LibrarySetupDialog";
import { SettingsDialog, SettingsUnavailableDialog } from "./SettingsDialog";
import { ConceptSidebar } from "./ConceptSidebar";
import { SessionRail } from "./SessionRail";

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
  conceptDetailId: string | null;
  openConceptDetail: (conceptId: string) => void;
  closeConceptDetail: () => void;
  showKnowledgeContext: (context: KnowledgeContext) => void;
  receiveKnowledgeContext: (context: KnowledgeContext) => void;
  clearKnowledgeContext: () => void;
  showSourceContext: (attribution: Attribution) => void;
  documents: DocumentSummary[];
  selectedDocumentIds: string[];
  selectedDocuments: DocumentSummary[];
  toggleDocumentScope: (documentId: string) => void;
  setDocumentScope: (documentIds: string[]) => void;
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
  { to: "/knowledge-map", label: "知识地图", icon: Map },
  { to: "/notes", label: "笔记", icon: NotebookPen },
  { to: "/library", label: "资料库", icon: Library },
];

const pageMeta: Record<string, [string, string]> = {
  chat: ["学习对话", "今天想学什么？"],
  practice: ["主动练习", "用题目检验理解"],
  review: ["今日复习", "把薄弱点慢慢练熟"],
  library: ["本地资料", "你的学习材料"],
  "knowledge-map": ["知识地图", "概念关系一览"],
};

function LearningContext({
  documents,
  review,
  selectedDocumentIds,
  toggleDocumentScope,
  knowledgeContext,
  sourceContext,
  onOpenConcept,
  onOpenMap,
}: {
  documents: DocumentSummary[];
  review: ReviewQueue | null;
  selectedDocumentIds: string[];
  toggleDocumentScope: (documentId: string) => void;
  knowledgeContext: KnowledgeContext | null;
  sourceContext: Attribution | null;
  onOpenConcept: (conceptId: string) => void;
  onOpenMap: (conceptId: string) => void;
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
        {sourceContext && <section className="context-section response-sources">
          <div className="context-heading"><FileText size={16} />本轮回答来源</div>
          <div className="context-source-list">
            {groupAttributionSources(sourceContext.sources).map((group) => {
              return <details className="context-source-group" key={group.key}>
                <summary><strong>{group.title}</strong><small>命中 {group.sources.length} 处</small></summary>
                <div>{group.sources.map((source, index) => <section key={source.source_id || index}>
                  <small>{source.heading || (source.page ? `第 ${source.page} 页` : source.slide ? `第 ${source.slide} 页` : "原文片段")}</small>
                  {source.excerpt && <p>{source.excerpt}</p>}
                  {source.document_id && <NavLink className="text-link" to={`/library?collection=${source.collection === "wiki" ? "wiki" : "material"}&document=${encodeURIComponent(source.document_id)}${source.chunk_id ? `&chunk=${encodeURIComponent(source.chunk_id)}` : ""}`}>打开原文</NavLink>}
                </section>)}</div>
              </details>;
            })}
            {!sourceContext.sources.length && <p className="context-empty">资料库中没有找到直接依据。</p>}
          </div>
        </section>}
        {knowledgeContext && <section className="context-section related-knowledge">
          <div className="context-heading"><Map size={16} />相关知识</div>
          <div className="context-relation-list">
            {(knowledgeContext.relationships || []).slice(0, 6).map((relation) => <div className="context-relation" key={relation.rel_id}>
              <button type="button" onClick={() => onOpenConcept(relation.from_id)}>{relation.from_name}</button>
              <span>{relation.rel_type}</span>
              <button type="button" onClick={() => onOpenConcept(relation.to_id)}>{relation.to_name}</button>
              {relation.evidence_status !== "valid" && <small>{relation.evidence_status === "stale" ? "来源已变化" : "暂无原文证据"}</small>}
            </div>)}
            {!(knowledgeContext.relationships || []).length && knowledgeContext.concepts.slice(0, 6).map((concept) => <button className="context-concept" type="button" key={concept.concept_id} onClick={() => onOpenConcept(concept.concept_id)}>{concept.name}</button>)}
          </div>
          {knowledgeContext.concepts[0] && <button className="text-link" type="button" onClick={() => onOpenMap(knowledgeContext.root?.concept_id || knowledgeContext.concepts[0].concept_id)}>在知识地图查看</button>}
        </section>}
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
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const previewTimer = useRef<number | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [libraries, setLibraries] = useState<LibrarySummary[]>([]);
  const [activeLibrary, setActiveLibrary] = useState<LibrarySummary | null>(null);
  const documentImportInput = useRef<HTMLInputElement>(null);
  const pendingDocumentFiles = useRef<File[]>([]);
  const [documentImport, setDocumentImport] = useState({ importing: false, notice: "", error: "", version: 0 });
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

  const uploadDocuments = useCallback(async (files: File[]) => {
    setDocumentImport((current) => ({ ...current, importing: true, notice: "", error: "" }));
    try {
      const result = await api.importDocuments(files);
      const rejected = result.rejected.length ? `，${result.rejected.length} 份未能导入` : "";
      setDocumentImport((current) => ({
        ...current,
        notice: `已导入 ${result.imported.length} 份资料并建立索引${rejected}。`,
        version: current.version + 1,
      }));
      await loadScopedData();
    } catch (reason) {
      setDocumentImport((current) => ({ ...current, error: toErrorMessage(reason, "资料导入失败。") }));
    } finally {
      setDocumentImport((current) => ({ ...current, importing: false }));
      navigate("/library");
    }
  }, [loadScopedData, navigate]);

  function cancelLibrarySetup() {
    if (librarySetup?.importCount) pendingDocumentFiles.current = [];
    closeLibrarySetup();
  }

  function startDocumentImport() {
    setDocumentImport((current) => ({ ...current, notice: "", error: "" }));
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
    setDocumentImport((current) => ({ ...current, notice: "", error: "" }));
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

  function openConceptDetail(conceptId: string) {
    setConceptDetailId(conceptId);
    if (desktop) setPanelOpen("right", true);
    else setContextOpen(true);
  }

  const showKnowledgeContext = useCallback((context: KnowledgeContext) => {
    setKnowledgeContext(context);
    if (desktop) setPanelOpen("right", true);
    else setContextOpen(true);
  }, [desktop, setContextOpen, setKnowledgeContext, setPanelOpen]);

  // 流式/恢复时只记录上下文，不自动打开面板（P5G 体验整改：卡片不自动弹面板）
  const receiveKnowledgeContext = useCallback((context: KnowledgeContext) => {
    setKnowledgeContext(context);
  }, [setKnowledgeContext]);

  const clearKnowledgeContext = useCallback(() => setKnowledgeContext(null), [setKnowledgeContext]);

  function showSourceContext(attribution: Attribution) {
    setSourceContext(attribution);
    setConceptDetailId(null);
    if (desktop) setPanelOpen("right", true);
    else setContextOpen(true);
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
          <IconButton label={rightOpen ? "收起右栏" : "展开右栏"} className="panel-toggle desktop-panel-toggle" onClick={() => togglePanel("right")}><PanelRight /></IconButton>
          <IconButton label="学习上下文" className="context-button" onClick={() => setContextOpen(true)}><PanelRight /></IconButton>
        </header>
        <Outlet context={{
          sessions,
          settings,
          refreshSettings,
          refreshSessions,
          openContext: () => desktop ? setPanelOpen("right", true) : setContextOpen(true),
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
          documentImporting: documentImport.importing,
          documentImportNotice: documentImport.notice,
          documentImportError: documentImport.error,
          documentImportVersion: documentImport.version,
          libraryReady: initialDataLoaded,
        } satisfies AppOutletContext} />
      </main>

      <aside className={`context-panel ${contextOpen ? "open" : ""}`} aria-label="学习上下文" onMouseEnter={() => schedulePreview("right", true)} onMouseLeave={() => schedulePreview("right", false)}>
        <div className="context-header">
          <strong>{conceptDetailId ? "概念详情" : "学习书桌"}</strong>
          <IconButton
            label={conceptDetailId ? "返回学习书桌" : "关闭上下文"}
            onClick={() => conceptDetailId ? setConceptDetailId(null) : setContextOpen(false)}
          ><X /></IconButton>
        </div>
        {conceptDetailId ? (
          <ConceptSidebar
            embedded
            conceptId={conceptDetailId}
            onClose={() => setConceptDetailId(null)}
            onNavigateConcept={openConceptDetail}
          />
        ) : (
          <LearningContext
            documents={documents}
            review={review}
            selectedDocumentIds={selectedDocumentIds}
            toggleDocumentScope={toggleDocumentScope}
            knowledgeContext={knowledgeContext}
            sourceContext={sourceContext}
            onOpenConcept={openConceptDetail}
            onOpenMap={(conceptId) => navigate("/knowledge-map", { state: { focusConceptId: conceptId } })}
          />
        )}
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
          setLearningProfile(profile);
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
