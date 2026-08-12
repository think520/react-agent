import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, BookOpen, Brain, Check, Command, FilePlus2, FileText, FolderOpen, Globe2, Library, MessageCircle, Paperclip, RotateCcw, Square, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { AttributionBadges, BrandIllustration, ErrorNotice, IconButton, LoadingState } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { ModelSelect } from "../components/ModelSelect";
import { KnowledgeContextCard } from "../components/artifacts/KnowledgeContextCard";
import { MemoryConfirmationCard } from "../components/artifacts/MemoryConfirmationCard";
import { PracticeReadyCard } from "../components/artifacts/PracticeReadyCard";
import { SettingsChangeCard } from "../components/artifacts/SettingsChangeCard";
import { WebCandidatesCard } from "../components/artifacts/WebCandidatesCard";
import { WebConsentCard } from "../components/artifacts/WebConsentCard";
import { WebEvidenceCard } from "../components/artifacts/WebEvidenceCard";
import { WikiFocusCard } from "../components/artifacts/WikiFocusCard";
import { WikiResultCard } from "../components/artifacts/WikiResultCard";
import { useChatStream, type ProcessBrandState } from "../hooks/useChatStream";
import { api, streamChat } from "../lib/api";
import { routeSlashCommand } from "../lib/commandRouter";
import { toErrorMessage } from "../lib/errors";
import { parseMentionDraft } from "../lib/mention";
import { looksLikeSettingsChange } from "../lib/settingsIntent";
import { useHandoffStore } from "../stores/handoffStore";
import { useUiStore } from "../stores/uiStore";
import type { ChatArtifact, ChatReference, KnowledgeContextArtifact, MemoryConfirmationArtifact, PersonalizationRef, PracticeReadyArtifact, RunSummaryArtifact, SettingsChangeArtifact, WebCandidatesArtifact, WebConsentArtifact, WebEvidenceArtifact, WikiFocusArtifact, WikiPlanArtifact, WikiResultArtifact } from "../types";

interface SlashItem {
  value: string;
  label: string;
  description: string;
  kind: "command" | "skill";
}

const WEB_COMMANDS: SlashItem[] = [
  { value: "/new", label: "/new", description: "开始新对话", kind: "command" },
  { value: "/library", label: "/library", description: "打开学习资料", kind: "command" },
  { value: "/wiki", label: "/wiki", description: "打开 Wiki 与维护工具", kind: "command" },
  { value: "/wiki plan ", label: "/wiki plan", description: "为当前资料生成 Wiki 整理计划", kind: "command" },
  { value: "/wiki update ", label: "/wiki update", description: "为当前资料拟定 Wiki 增量更新计划", kind: "command" },
  { value: "/wiki generate", label: "/wiki generate", description: "确认并执行当前 Wiki 计划", kind: "command" },
  { value: "/practice", label: "/practice", description: "开始一轮练习", kind: "command" },
  { value: "/review", label: "/review", description: "查看今日复习", kind: "command" },
  { value: "/kb search ", label: "/kb search", description: "只检索本地资料", kind: "command" },
  { value: "/web search ", label: "/web search", description: "确认后搜索公开网页候选", kind: "command" },
  { value: "/learning today", label: "/learning today", description: "整理今日学习任务", kind: "command" },
  { value: "/quiz generate ", label: "/quiz generate", description: "按主题生成 5 道题", kind: "command" },
];

function processTitle(state: ProcessBrandState) {
  if (state === "reading") return "正在查找资料";
  if (state === "writing") return "正在生成内容";
  if (state === "ready") return "本轮已经准备好";
  return "正在理解问题";
}

function BobodanProcess({ state, detail }: { state: ProcessBrandState; detail: string }) {
  return <div className={`bobodan-process ${state}`} role="status">
    <BrandIllustration key={state} state={state} size={52} />
    <div><strong>{processTitle(state)}</strong><small>{detail}</small><span className="bobodan-process-ink" aria-hidden="true"><i /><i /><i /></span></div>
  </div>;
}

function PersonalizationChip({ references }: { references?: PersonalizationRef[] }) {
  if (!references?.length) return null;
  return <details className="personalization-chip"><summary><Brain size={13} />个性化依据 <span>{references.length}</span></summary><div>{references.map((reference) => <section key={reference.id}><strong>{reference.title}</strong><p>{reference.content}</p><small>{reference.scope === "global" ? "全局" : "当前资料库"} · {new Date(reference.updated_at).toLocaleDateString("zh-CN")}</small></section>)}</div></details>;
}

function formatDuration(seconds: number) {
  if (seconds < 1) return `${Math.max(1, Math.round(seconds * 1000))}ms`;
  return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
}

const TOOL_LABELS: Record<string, string> = {
  rag_search: "资料检索",
  concept_map_query: "知识地图",
  concept_map_status: "知识地图状态",
  question_generate: "生成练习题",
  quiz_start: "准备练习",
  quiz_submit: "批改答案",
  learning_path: "学习路线",
  learning_progress: "学习进度",
  learning_review: "复习内容",
  request_memory_confirmation: "记忆确认",
  request_web_search: "联网确认",
  web_research: "网页检索",
};

function RunSummary({ artifact }: { artifact?: RunSummaryArtifact }) {
  if (!artifact) return null;
  const hitCount = artifact.operations.reduce((total, item) => total + (item.hit_count || 0), 0);
  const documentCount = artifact.operations.reduce((total, item) => total + (item.document_count || 0), 0);
  const relationCount = artifact.operations.reduce((total, item) => total + (item.relationship_count || 0), 0);
  const summary = artifact.operations.length
    ? [documentCount ? `${documentCount} 份资料` : "", hitCount ? `${hitCount} 个片段` : "", relationCount ? `${relationCount} 条关系` : ""].filter(Boolean).join(" · ") || `完成 ${artifact.operations.length} 项查询`
    : "直接回答";
  return <details className={`run-summary ${artifact.status}`}>
    <summary><Check size={14} /><strong>{artifact.status === "completed" ? "处理完成" : "处理未完成"}</strong><span>{summary}</span><small>{formatDuration(artifact.total_elapsed)}</small></summary>
    {artifact.operations.length > 0 && <div>{artifact.operations.map((operation, index) => <p key={`${operation.tool_name}:${index}`}>
      <span>{TOOL_LABELS[operation.tool_name] || "学习工具"}</span>
      {operation.query && <q>{operation.query}</q>}
      {operation.operation && <code>{operation.operation}</code>}
      {operation.tool_name === "rag_search" && operation.semantic_available === false && (
        <span className="retrieval-degraded">
          {operation.hit_count ? "当前仅使用关键词检索" : "关键词检索未命中，向量检索当前不可用"}
        </span>
      )}
      <small>{operation.status === "completed" ? "完成" : "失败"} · {formatDuration(operation.elapsed || 0)}</small>
    </p>)}</div>}
  </details>;
}

function initialDraft(sessionId: string | undefined, peekOnly = false) {
  const handoff = sessionId
    ? null
    : peekOnly
      ? useHandoffStore.getState().chatDraft
      : useHandoffStore.getState().consumeChatDraft();
  return handoff || localStorage.getItem(`bobodan:draft:${sessionId || "new"}`) || "";
}

export function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const {
    refreshSessions,
    refreshSettings,
    sessions,
    settings,
    documents,
    selectedDocumentIds,
    selectedDocuments,
    openContext,
    openConceptDetail,
    showKnowledgeContext,
    clearKnowledgeContext,
    showSourceContext,
    clearDocumentScope,
    activeLibrary,
    openLibrarySetup,
    startDocumentImport,
    documentImporting,
    libraryReady,
  } = useOutletContext<AppOutletContext>();
  // showKnowledgeContext changes identity when the viewport crosses the 768px
  // breakpoint (it closes over `desktop`). Keep the latest references in refs
  // (refreshed in an effect, since refs may not be written during render) so
  // the session-loading effect below does not re-run on window resize and
  // clobber an in-flight streaming response with a stale session snapshot.
  const showKnowledgeContextRef = useRef(showKnowledgeContext);
  const clearKnowledgeContextRef = useRef(clearKnowledgeContext);
  useEffect(() => {
    showKnowledgeContextRef.current = showKnowledgeContext;
    clearKnowledgeContextRef.current = clearKnowledgeContext;
  }, [showKnowledgeContext, clearKnowledgeContext]);
  const {
    messages,
    setMessages,
    status,
    setStatus,
    brandState,
    setBrandState,
    handleStreamEvent,
    settleLastMessage,
  } = useChatStream();
  const [draft, setDraft] = useState(() => initialDraft(sessionId, true));
  const [loading, setLoading] = useState(Boolean(sessionId));
  const [sending, setSending] = useState(false);
  const [practiceStarting, setPracticeStarting] = useState("");
  const [error, setError] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [paletteDismissed, setPaletteDismissed] = useState(false);
  const [wikiPlanLoading, setWikiPlanLoading] = useState(false);
  // P5G.4：`provider::model` 完整引用（模型级选择）
  const [selectedProvider, setSelectedProvider] = useState(() => useUiStore.getState().newSessionProvider || "");

  /** 把 provider 名（或 `provider::model`）补齐为完整引用。 */
  function resolveModelRef(ref: string): string {
    if (!ref) return "";
    const [provider, model] = ref.split("::");
    if (model) return ref;
    const found = settings?.providers.find((item) => item.name === provider);
    return found?.model ? `${provider}::${found.model}` : ref;
  }

  function sessionRef(session: { provider_name?: string | null; model_name?: string | null }): string {
    if (!session.provider_name) return "";
    return session.model_name ? `${session.provider_name}::${session.model_name}` : session.provider_name;
  }
  const [references, setReferences] = useState<ChatReference[]>([]);
  const [webOnce, setWebOnce] = useState(false);
  const strictDocumentScope = useUiStore((state) => state.strictDocumentScope);
  const toggleStrictDocumentScope = useUiStore((state) => state.toggleStrictDocumentScope);
  const [webSelections, setWebSelections] = useState<Record<string, string[]>>({});
  const [referenceDocuments, setReferenceDocuments] = useState(documents);
  const [mentionTab, setMentionTab] = useState<"document" | "session">("document");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionDismissed, setMentionDismissed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef(sessionId);
  const leaveChatRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setDraft(initialDraft(sessionId));
    setError("");
    useUiStore.getState().setSourceContext(null);
    if (!sessionId) {
      setMessages([]);
      setReferences([]);
      clearKnowledgeContextRef.current();
      setSelectedProvider(resolveModelRef(useUiStore.getState().newSessionProvider || settings?.default_provider || ""));
      setLoading(false);
      return;
    }
    setLoading(true);
    void api.session(sessionId)
      .then((session) => {
        if (cancelled) return;
        setMessages(session.messages);
        setReferences([]);
        setSelectedProvider(resolveModelRef(sessionRef(session) || settings?.default_provider || ""));
        const latestKnowledgeContext = session.messages
          .flatMap((message) => message.artifacts || [])
          .filter((artifact): artifact is KnowledgeContextArtifact => artifact.type === "knowledge_context")
          .at(-1);
        if (latestKnowledgeContext) showKnowledgeContextRef.current(latestKnowledgeContext.context);
        else clearKnowledgeContextRef.current();
      })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, settings?.default_provider, setMessages]);

  useEffect(() => {
    if (!selectedProvider && settings?.default_provider) setSelectedProvider(resolveModelRef(settings.default_provider));
  }, [selectedProvider, settings?.default_provider]);

  useEffect(() => {
    if (!activeLibrary) {
      setReferenceDocuments([]);
      return;
    }
    void api.documents("all").then(setReferenceDocuments).catch(() => setReferenceDocuments(documents));
  }, [activeLibrary, documents]);

  useEffect(() => {
    localStorage.setItem(`bobodan:draft:${sessionId || "new"}`, draft);
  }, [draft, sessionId]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const planningRunIds = useMemo(() => messages.flatMap((message) =>
    (message.artifacts || [])
      .filter((artifact): artifact is WikiPlanArtifact => artifact.type === "wiki_plan" && (artifact.status === "planning" || artifact.plan.status === "planning"))
      .map((artifact) => artifact.plan_id),
  ), [messages]);
  const planningRunKey = planningRunIds.join("|");

  useEffect(() => {
    if (!planningRunKey) return;
    const runIds = planningRunKey.split("|");
    let cancelled = false;
    const poll = async () => {
      for (const runId of runIds) {
        try {
          const run = await api.wikiRun(runId);
          if (cancelled) return;
          setMessages((current) => current.map((message) => ({
            ...message,
            artifacts: message.artifacts?.map((artifact) => artifact.type === "wiki_plan" && artifact.plan_id === runId
              ? { ...artifact, status: run.status, plan: { ...artifact.plan, ...run } }
              : artifact),
          })));
        } catch { /* the persisted artifact remains visible while the backend recovers */ }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1600);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [planningRunKey, setMessages]);

  useEffect(() => {
    const element = scrollRef.current;
    if (element && typeof element.scrollTo === "function") {
      element.scrollTo({ top: element.scrollHeight, behavior: sending ? "smooth" : "auto" });
    }
  }, [messages, status, sending]);

  async function send(event?: FormEvent, overrideMessage?: string, webResearchId?: string) {
    event?.preventDefault();
    const message = (overrideMessage ?? draft).trim();
    if (!message || sending) return;
    if (!libraryReady) return;
    if (!activeLibrary) {
      openLibrarySetup();
      return;
    }
    const route = webResearchId ? { kind: "none" as const } : routeSlashCommand(message, { webOnce });
    if (route.kind === "navigate") { setDraft(""); navigate(route.to); return; }
    if (route.kind === "wiki-generate") {
      setDraft("");
      const plan = latestArtifact("wiki_plan") as WikiPlanArtifact | undefined;
      if (plan?.status === "planned") await applyWikiPlan(plan);
      else setError("请先使用 /wiki plan 创建并审查一份 Wiki 计划。" );
      return;
    }
    if (route.kind === "wiki-focus") {
      setDraft("");
      await createWikiFocus(route.instruction, route.action);
      return;
    }
    if (route.kind === "practice-topic") {
      if (route.topic) useHandoffStore.getState().setPracticeTopic(route.topic);
      setDraft("");
      navigate("/practice");
      return;
    }
    if (route.kind === "web-search-empty") {
      setError("请在 /web search 后输入需要查找的内容。" );
      return;
    }
    if (route.kind === "web-search") {
      setDraft("");
      setWebOnce(false);
      await startWebSearch(route.query, undefined, true);
      return;
    }
    const pendingFocus = latestArtifact("wiki_focus") as WikiFocusArtifact | undefined;
    if (pendingFocus?.status === "awaiting_confirmation" && sessionId) {
      setDraft("");
      await reviseWikiFocus(pendingFocus, message);
      return;
    }
    if (looksLikeSettingsChange(message)) {
      setDraft("");
      setSending(true);
      setError("");
      try {
        const result = await api.createSettingsProposal(message, sessionId);
        if (!sessionId) navigate(`/chat/${result.chat_session_id}`, { replace: true });
        await refreshChatSession(result.chat_session_id);
        return;
      } catch (reason) {
        if (!(reason instanceof Error) || !("code" in reason) || (reason as Error & { code?: string }).code !== "settings_change_not_detected") {
          setError(toErrorMessage(reason, "无法创建设置变更确认。"));
          return;
        }
      } finally {
        setSending(false);
      }
    }
    setDraft("");
    setPaletteDismissed(true);
    setMentionDismissed(true);
    setSending(true);
    setError("");
    setStatus("正在理解你的问题");
    setBrandState("thinking");
    leaveChatRef.current = false;
    const outgoingReferences = [...references];
    setReferences([]);
    setMessages((current) => [...current, { role: "user", content: message, references: outgoingReferences }, { role: "assistant", content: "", pending: true }]);
    let nextSessionId = sessionId;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const profile = useUiStore.getState().learningProfile;
      const [sendProvider, sendModel] = (selectedProvider || settings?.default_provider || "").split("::");
      await streamChat(message, sessionId, selectedDocumentIds, {
        ...profile,
        memoryEnabled: settings?.preferences.memory.enabled ?? true,
        provider: sendProvider || undefined,
        model: sendModel || undefined,
        references: outgoingReferences,
        webResearchId,
        strictDocumentScope,
      }, (streamEvent) => handleStreamEvent(streamEvent, {
        onRunStarted: (chatSessionId) => {
          nextSessionId = chatSessionId;
          sessionIdRef.current = chatSessionId;
        },
        getSessionId: () => nextSessionId,
        onKnowledgeContext: showKnowledgeContext,
      }), controller.signal);
      settleLastMessage();
      await new Promise((resolve) => window.setTimeout(resolve, 600));
      setStatus("");
      await refreshSessions();
      if (nextSessionId) {
        void api.generateSessionTitle(nextSessionId).then(refreshSessions).catch(() => undefined);
      }
      if (!sessionId && nextSessionId && !leaveChatRef.current) navigate(`/chat/${nextSessionId}`, { replace: true });
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setStatus("");
        settleLastMessage(false, true);
        return;
      }
      setError(toErrorMessage(reason, "本轮回答失败，请重新发送。"));
      setStatus("");
      settleLastMessage(true);
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  }

  function latestArtifact<T extends ChatArtifact["type"]>(type: T): Extract<ChatArtifact, { type: T }> | undefined {
    return messages.flatMap((message) => message.artifacts || []).filter((artifact): artifact is Extract<ChatArtifact, { type: T }> => artifact.type === type).at(-1);
  }

  async function refreshChatSession(id: string) {
    const detail = await api.session(id);
    setMessages(detail.messages);
    setSelectedProvider(resolveModelRef(sessionRef(detail) || settings?.default_provider || ""));
    await refreshSessions();
  }

  async function startWebSearch(query: string, consentArtifactId?: string, appendUserMessage = false) {
    setSending(true);
    setError("");
    setStatus("正在搜索公开网页候选");
    setBrandState("reading");
    try {
      const result = await api.createWebSearch(query, sessionId, consentArtifactId, appendUserMessage);
      if (!sessionId) navigate(`/chat/${result.chat_session_id}`, { replace: true });
      await refreshChatSession(result.chat_session_id);
    } catch (reason) {
      setError(toErrorMessage(reason, "联网搜索暂时不可用。"));
    } finally {
      setStatus("");
      setSending(false);
    }
  }

  async function resolveWebConsent(artifact: WebConsentArtifact, action: "approve" | "reject") {
    if (!sessionId) return;
    if (action === "approve") {
      await startWebSearch(artifact.query, artifact.artifact_id);
      return;
    }
    setSending(true);
    setError("");
    try {
      await api.rejectWebConsent(artifact.artifact_id, sessionId);
      await refreshChatSession(sessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法取消本次联网请求。"));
    } finally {
      setSending(false);
    }
  }

  function toggleWebCandidate(artifact: WebCandidatesArtifact, candidateId: string) {
    setWebSelections((current) => {
      const selected = current[artifact.search_id] || [];
      if (selected.includes(candidateId)) {
        return { ...current, [artifact.search_id]: selected.filter((item) => item !== candidateId) };
      }
      if (selected.length >= 4) {
        setError("每次最多选择 4 个网页来源。" );
        return current;
      }
      return { ...current, [artifact.search_id]: [...selected, candidateId] };
    });
  }

  async function applyWebCandidates(artifact: WebCandidatesArtifact) {
    if (!sessionId) return;
    const selected = webSelections[artifact.search_id] || [];
    if (!selected.length) return;
    setSending(true);
    setError("");
    setStatus(`正在读取 ${selected.length} 个网页来源`);
    setBrandState("reading");
    try {
      const result = await api.selectWebSources(artifact.search_id, sessionId, selected);
      await refreshChatSession(sessionId);
      if (result.artifact.type === "web_evidence" && result.artifact.status !== "failed") {
        setSending(false);
        setStatus("");
        await send(undefined, "使用选中的网页来源继续回答。", result.artifact.research_id);
        return;
      }
    } catch (reason) {
      setError(toErrorMessage(reason, "选中的网页暂时无法读取。"));
    } finally {
      setStatus("");
      setSending(false);
    }
  }

  async function createWikiFocus(instruction: string, action: "generate" | "update" = "generate") {
    const carriedScope = useHandoffStore.getState().wikiScope || {};
    const documentIds = carriedScope.documentIds?.length ? carriedScope.documentIds : selectedDocumentIds;
    const wikiDocumentIds = carriedScope.wikiDocumentIds || [];
    const scopeMode = carriedScope.scopeMode || (wikiDocumentIds.length ? "selected_only" : "smart_library");
    setWikiPlanLoading(true);
    setError("");
    setStatus("正在阅读资料并提炼整理重点");
    setBrandState("reading");
    const command = `${action === "update" ? "/wiki update" : "/wiki plan"}${instruction ? ` ${instruction}` : ""}`;
    setMessages((current) => [...current, { role: "user", content: command }]);
    try {
      const result = await api.createWikiFocus({
        chat_session_id: sessionId,
        action,
        scope_mode: scopeMode,
        document_ids: documentIds,
        wiki_document_ids: wikiDocumentIds,
        course: carriedScope.course,
        topic: carriedScope.topic || instruction,
        instruction,
      });
      useHandoffStore.getState().clearWikiScope();
      if (!sessionId) navigate(`/chat/${result.chat_session_id}`, { replace: true });
      await refreshChatSession(result.chat_session_id);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法整理 Wiki 重点。"));
    } finally {
      setWikiPlanLoading(false);
      setStatus("");
    }
  }

  async function reviseWikiFocus(focus: WikiFocusArtifact, revision: string) {
    if (!sessionId) return;
    setWikiPlanLoading(true);
    setError("");
    setStatus("正在按你的补充调整重点");
    try {
      await api.reviseWikiFocus(focus.artifact_id, sessionId, revision);
      await refreshChatSession(sessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法调整 Wiki 重点。"));
    } finally {
      setWikiPlanLoading(false);
      setStatus("");
    }
  }

  async function confirmWikiFocus(focus: WikiFocusArtifact) {
    if (!sessionId) return;
    setWikiPlanLoading(true);
    setError("");
    setStatus("正在生成可审查的 Wiki 变更计划");
    try {
      await api.confirmWikiFocus(focus.artifact_id, sessionId);
      await refreshChatSession(sessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法生成 Wiki 计划。"));
    } finally {
      setWikiPlanLoading(false);
      setStatus("");
    }
  }

  async function applyWikiPlan(artifact: WikiPlanArtifact) {
    if (!sessionId) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      await api.applyChatWikiPlan(artifact.plan_id, sessionId);
      await refreshChatSession(sessionId);
    } catch (reason) {
      let stagedFailure = false;
      try {
        const refreshed = await api.wikiPlan(artifact.plan_id);
        stagedFailure = Boolean(refreshed.staging?.length);
        setMessages((current) => current.map((message) => ({
          ...message,
          artifacts: message.artifacts?.map((item) => item.type === "wiki_plan" && item.plan_id === artifact.plan_id
            ? { ...item, plan: refreshed }
            : item),
        })));
      } catch { /* keep the persisted chat artifact when refresh is unavailable */ }
      if (!stagedFailure) setError(toErrorMessage(reason, "Wiki 写入失败。"));
    } finally {
      setWikiPlanLoading(false);
    }
  }

  async function recoverWikiPlan(artifact: WikiPlanArtifact, strategy: "keep_existing" | "regenerate") {
    if (!sessionId) return;
    setWikiPlanLoading(true);
    setError("");
    setBrandState(strategy === "regenerate" ? "writing" : "reading");
    setStatus(strategy === "regenerate" ? "正在保留已有内容并重新规划" : "正在保留原页面并写入其余内容");
    try {
      await api.recoverChatWikiPlan(artifact.plan_id, sessionId, strategy);
      await refreshChatSession(sessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法继续处理这份 Wiki 计划。"));
    } finally {
      setWikiPlanLoading(false);
      setStatus("");
    }
  }

  async function cancelWikiRun(artifact: WikiPlanArtifact) {
    if (!sessionId) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      const result = await api.cancelChatWikiRun(artifact.plan_id, sessionId);
      setMessages((current) => current.map((message) => ({
        ...message,
        artifacts: message.artifacts?.map((item) => item.type === "wiki_plan" && item.plan_id === artifact.plan_id
          ? { ...item, status: result.run.status, plan: { ...item.plan, ...result.run } }
          : item),
      })));
    } catch (reason) {
      setError(toErrorMessage(reason, "无法取消这轮 Wiki 整理。"));
    } finally {
      setWikiPlanLoading(false);
    }
  }

  async function undoWikiPlan(artifact: WikiResultArtifact) {
    if (!sessionId || !artifact.checkpoint_id) return;
    setWikiPlanLoading(true);
    setError("");
    try {
      await api.restoreChatWikiCheckpoint(artifact.checkpoint_id, sessionId);
      await refreshChatSession(sessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法撤销本轮 Wiki 整理。"));
    } finally {
      setWikiPlanLoading(false);
    }
  }

  function applyPrompt(value: string) {
    setDraft(value);
    inputRef.current?.focus();
  }

  function preparePractice(index: number) {
    const topic = messages[index - 1]?.role === "user"
      ? messages[index - 1].content
      : messages[index].content.slice(0, 160);
    const handoff = useHandoffStore.getState();
    handoff.setPracticeTopic(topic);
    const isWebContinuation = messages[index - 1]?.role === "user" && messages[index - 1].content === "使用选中的网页来源继续回答。";
    const evidence = isWebContinuation
      ? messages.slice(0, index + 1).flatMap((message) => message.artifacts || []).filter((artifact): artifact is WebEvidenceArtifact => artifact.type === "web_evidence" && artifact.status !== "failed").at(-1)
      : undefined;
    handoff.setPracticeWebResearch(evidence ? evidence.research_id : null);
    navigate("/practice");
  }

  async function startPreparedPractice(artifact: PracticeReadyArtifact) {
    if (artifact.practice_session_id) {
      leaveChatRef.current = true;
      navigate(`/practice/${artifact.practice_session_id}`);
      return;
    }
    const activeSessionId = artifact.chat_session_id || sessionId || sessionIdRef.current;
    if (!activeSessionId) return;
    setPracticeStarting(artifact.artifact_id);
    setError("");
    leaveChatRef.current = true;
    try {
      const result = await api.startChatPractice(artifact.artifact_id, activeSessionId);
      void refreshChatSession(activeSessionId).catch(() => undefined);
      navigate(`/practice/${result.practice_session_id}`);
    } catch (reason) {
      leaveChatRef.current = false;
      if (!sessionId) navigate(`/chat/${activeSessionId}`, { replace: true });
      setError(toErrorMessage(reason, "暂时无法开始这轮练习。"));
    } finally {
      setPracticeStarting("");
    }
  }

  function retryMessage(index: number) {
    const previous = messages[index - 1];
    if (previous?.role === "user") void send(undefined, previous.content);
  }

  async function changeProvider(modelRef: string) {
    if (sending) return;
    const previous = selectedProvider;
    setSelectedProvider(modelRef);
    try {
      const [provider, model] = modelRef.split("::");
      if (sessionId) {
        await api.updateSessionProvider(sessionId, provider, model);
        await refreshSessions();
      } else {
        useUiStore.getState().setNewSessionProvider(modelRef);
      }
    } catch (reason) {
      setSelectedProvider(previous);
      setError(toErrorMessage(reason, "无法切换模型。"));
    }
  }

  async function changeAnswerDepth(value: "concise" | "standard" | "deep") {
    if (!settings || settings.preferences.assistant.answer_depth === value) return;
    try {
      await api.patchPreferences(settings.preferences.revision, { assistant: { answer_depth: value } });
      await refreshSettings();
    } catch (reason) {
      setError(toErrorMessage(reason, "回答深度没有保存成功。"));
    }
  }

  async function resolveSettingsChange(artifact: SettingsChangeArtifact, action: "apply" | "reject") {
    if (!sessionId) return;
    setSending(true);
    setError("");
    try {
      await api.resolveSettingsProposal(artifact.proposal_id, sessionId, action);
      await Promise.all([refreshChatSession(sessionId), refreshSettings()]);
    } catch (reason) {
      setError(toErrorMessage(reason, "设置变更没有处理成功。"));
    } finally {
      setSending(false);
    }
  }

  async function resolveMemoryProposal(artifact: MemoryConfirmationArtifact, action: "confirm" | "reject") {
    if (!sessionId) return;
    setSending(true);
    setError("");
    try {
      await api.resolveMemoryProposal(
        artifact.artifact_id,
        sessionId,
        action,
        action === "confirm" && artifact.requires_warning,
      );
      await refreshChatSession(sessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法更新这条记忆。"));
    } finally {
      setSending(false);
    }
  }

  function removeReference(reference: ChatReference) {
    setReferences((current) => current.filter((item) => !(item.type === reference.type && item.id === reference.id)));
  }

  function openReference(reference: ChatReference) {
    if (reference.type === "session") navigate(`/chat/${reference.id}`);
    else navigate(`/library?collection=${reference.collection || "material"}&document=${encodeURIComponent(reference.id)}`);
  }

  const activeProvider = settings?.providers.find((provider) => provider.name === (selectedProvider.split("::")[0] || selectedProvider));
  const slashItems = useMemo<SlashItem[]>(() => [
    ...WEB_COMMANDS,
    ...(settings?.skills || []).filter((skill) => skill.enabled).map((skill) => ({
      value: `/skill ${skill.name} `,
      label: `/skill ${skill.name}`,
      description: skill.description,
      kind: "skill" as const,
    })),
  ], [settings?.skills]);
  const slashQuery = draft.startsWith("/") ? draft.toLocaleLowerCase() : "";
  const filteredSlashItems = slashQuery
    ? slashItems.filter((item) => `${item.label} ${item.description}`.toLocaleLowerCase().includes(slashQuery.slice(1)))
    : [];
  const paletteOpen = !paletteDismissed && filteredSlashItems.length > 0;

  const mention = parseMentionDraft(draft);
  const rawMentionQuery = mention?.raw || "";
  const mentionQuery = mention?.query || "";
  const effectiveMentionTab = mention?.forcedTab || mentionTab;
  const mentionItems = effectiveMentionTab === "document"
    ? referenceDocuments.filter((document) => !mentionQuery || `${document.title} ${document.source}`.toLocaleLowerCase().includes(mentionQuery)).slice(0, 12).map((document) => ({
        type: "document" as const,
        id: document.document_id,
        title: document.title || document.source,
        collection: document.collection,
        subtitle: document.collection === "wiki" ? "AI 整理 Wiki" : document.course || document.kind || "本地资料",
      }))
    : sessions.filter((session) => session.chat_session_id !== sessionId && (!mentionQuery || session.name.toLocaleLowerCase().includes(mentionQuery))).slice(0, 12).map((session) => ({
        type: "session" as const,
        id: session.chat_session_id,
        title: session.name || "未命名会话",
        subtitle: new Date(session.last_active).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }),
      }));
  const mentionOpen = Boolean(mention) && !mentionDismissed && mentionItems.length > 0;

  function chooseMention(item: (typeof mentionItems)[number]) {
    if (item.type === "session" && references.filter((reference) => reference.type === "session").length >= 3) {
      setError("每条消息最多引用 3 个历史会话。" );
      return;
    }
    if (item.type === "document" && references.filter((reference) => reference.type === "document").length >= 8) {
      setError("每条消息最多引用 8 份资料。" );
      return;
    }
    setReferences((current) => current.some((reference) => reference.type === item.type && reference.id === item.id)
      ? current
      : [...current, { type: item.type, id: item.id, title: item.title, ...(item.type === "document" ? { collection: item.collection } : {}) }].slice(0, 8));
    setDraft((current) => current.replace(/@[^\s@]*$/, "").replace(/\s+$/, ""));
    setMentionDismissed(true);
    setMentionIndex(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function switchMentionTab(tab: "document" | "session") {
    setMentionTab(tab);
    setMentionIndex(0);
    if (rawMentionQuery === "资料" || rawMentionQuery === "会话") {
      setDraft((current) => current.replace(/@(?:资料|会话)$/, "@"));
    }
  }

  function chooseSlashItem(item: SlashItem) {
    setDraft(item.value);
    setPaletteDismissed(true);
    setPaletteIndex(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function artifactSurface(artifact: ChatArtifact) {
    switch (artifact.type) {
      case "knowledge_context":
        return <KnowledgeContextCard
          key={artifact.artifact_id}
          artifact={artifact}
          onShowContext={showKnowledgeContext}
          onOpenConcept={openConceptDetail}
          onOpenMap={(conceptId) => navigate("/knowledge-map", { state: { focusConceptId: conceptId } })}
        />;
      case "memory_confirmation":
        return <MemoryConfirmationCard key={artifact.artifact_id} artifact={artifact} busy={sending} onResolve={(item, action) => void resolveMemoryProposal(item, action)} />;
      case "settings_change":
        return <SettingsChangeCard key={artifact.artifact_id} artifact={artifact} busy={sending} onResolve={(item, action) => void resolveSettingsChange(item, action)} />;
      case "web_consent":
        return <WebConsentCard key={artifact.artifact_id} artifact={artifact} busy={sending} onResolve={(item, action) => void resolveWebConsent(item, action)} />;
      case "web_candidates":
        return <WebCandidatesCard
          key={artifact.artifact_id}
          artifact={artifact}
          selected={webSelections[artifact.search_id] || artifact.selected_candidate_ids || []}
          busy={sending}
          onToggle={toggleWebCandidate}
          onUse={(item) => void applyWebCandidates(item)}
        />;
      case "web_evidence":
        return <WebEvidenceCard key={artifact.artifact_id} artifact={artifact} />;
      case "practice_ready":
        return <PracticeReadyCard key={artifact.artifact_id} artifact={artifact} starting={practiceStarting === artifact.artifact_id} onStart={(item) => void startPreparedPractice(item)} />;
      case "wiki_focus":
        return <WikiFocusCard
          key={artifact.artifact_id}
          artifact={artifact}
          busy={wikiPlanLoading}
          onAdjust={() => { setDraft("请调整重点："); inputRef.current?.focus(); }}
          onConfirm={(item) => void confirmWikiFocus(item)}
        />;
      case "wiki_plan":
        return <WikiPlanCard
          key={artifact.artifact_id}
          plan={artifact.plan}
          busy={wikiPlanLoading}
          onApply={artifact.status === "planned" ? () => void applyWikiPlan(artifact) : undefined}
          onCancel={artifact.status === "planning" ? () => void cancelWikiRun(artifact) : undefined}
          onKeepExisting={artifact.status === "planned" && artifact.plan.staging?.length ? () => void recoverWikiPlan(artifact, "keep_existing") : undefined}
          onRegenerate={artifact.status === "planned" && artifact.plan.staging?.length ? () => void recoverWikiPlan(artifact, "regenerate") : undefined}
        />;
      case "wiki_result":
        return <WikiResultCard key={artifact.artifact_id} artifact={artifact} busy={wikiPlanLoading} onUndo={(item) => void undoWikiPlan(item)} />;
      default:
        return null;
    }
  }

  const composer = (
    <form className="composer-wrap" onSubmit={(event) => void send(event)}>
      {paletteOpen && <div className="slash-palette" role="listbox" aria-label="命令与技能">
        <div className="slash-palette-heading"><Command size={14} /><span>命令与技能</span><small>Enter 选择 · Esc 关闭</small></div>
        <div className="slash-palette-list">{filteredSlashItems.map((item, index) => (
          <button type="button" role="option" aria-selected={index === paletteIndex} className={index === paletteIndex ? "active" : ""} key={item.value} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseSlashItem(item)}>
            <span className="slash-item-icon">{item.kind === "skill" ? <Sparkles size={15} /> : <Command size={15} />}</span>
            <span><strong>{item.label}</strong><small>{item.description}</small></span>
            <i>{item.kind === "skill" ? "Skill" : "Command"}</i>
          </button>
        ))}</div>
      </div>}
      {mentionOpen && <div className="mention-palette" role="listbox" aria-label="引用资料或会话">
        <div className="mention-tabs" role="tablist"><button type="button" role="tab" aria-selected={effectiveMentionTab === "document"} className={effectiveMentionTab === "document" ? "active" : ""} onMouseDown={(event) => event.preventDefault()} onClick={() => switchMentionTab("document")}><FileText size={14} />资料</button><button type="button" role="tab" aria-selected={effectiveMentionTab === "session"} className={effectiveMentionTab === "session" ? "active" : ""} onMouseDown={(event) => event.preventDefault()} onClick={() => switchMentionTab("session")}><MessageCircle size={14} />会话</button><small>Tab 切换 · Enter 引用</small></div>
        <div className="mention-list">{mentionItems.map((item, index) => <button type="button" role="option" aria-selected={index === mentionIndex} className={index === mentionIndex ? "active" : ""} key={`${item.type}:${item.id}`} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseMention(item)}><span>{item.type === "document" ? <FileText size={15} /> : <MessageCircle size={15} />}</span><div><strong>{item.title}</strong><small>{item.subtitle}</small></div></button>)}</div>
      </div>}
      <div className="composer">
        {references.length > 0 && <div className="composer-references">{references.map((reference) => <span key={`${reference.type}:${reference.id}`}><button type="button" onClick={() => openReference(reference)}>{reference.type === "document" ? <FileText size={12} /> : <MessageCircle size={12} />}{reference.title}</button><button type="button" aria-label={`移除引用 ${reference.title}`} onClick={() => removeReference(reference)}><X size={12} /></button></span>)}</div>}
        <textarea
          ref={inputRef}
          rows={1}
          value={draft}
          disabled={sending || !libraryReady}
          placeholder="说点什么…"
          aria-label="消息"
          onChange={(event) => { setDraft(event.target.value); setPaletteDismissed(false); setMentionDismissed(false); setPaletteIndex(0); setMentionIndex(0); }}
          onKeyDown={(event) => {
            if (paletteOpen && event.key === "ArrowDown") {
              event.preventDefault();
              setPaletteIndex((current) => (current + 1) % filteredSlashItems.length);
              return;
            }
            if (paletteOpen && event.key === "ArrowUp") {
              event.preventDefault();
              setPaletteIndex((current) => (current - 1 + filteredSlashItems.length) % filteredSlashItems.length);
              return;
            }
            if (paletteOpen && (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey))) {
              event.preventDefault();
              chooseSlashItem(filteredSlashItems[Math.min(paletteIndex, filteredSlashItems.length - 1)]);
              return;
            }
            if (paletteOpen && event.key === "Escape") {
              event.preventDefault();
              setPaletteDismissed(true);
              return;
            }
            if (mentionOpen && event.key === "ArrowDown") {
              event.preventDefault();
              setMentionIndex((current) => (current + 1) % mentionItems.length);
              return;
            }
            if (mentionOpen && event.key === "ArrowUp") {
              event.preventDefault();
              setMentionIndex((current) => (current - 1 + mentionItems.length) % mentionItems.length);
              return;
            }
            if (mentionOpen && event.key === "Tab") {
              event.preventDefault();
              switchMentionTab(effectiveMentionTab === "document" ? "session" : "document");
              return;
            }
            if (mentionOpen && event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              chooseMention(mentionItems[Math.min(mentionIndex, mentionItems.length - 1)]);
              return;
            }
            if (mentionOpen && event.key === "Escape") {
              event.preventDefault();
              setMentionDismissed(true);
              return;
            }
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="composer-toolbar">
          <IconButton label={documents.length ? "选择资料范围" : "前往资料库"} type="button" onClick={() => documents.length ? openContext() : navigate("/library")}><Paperclip /></IconButton>
          <IconButton label={webOnce ? "取消本轮联网搜索" : "本轮搜索网页候选"} className={webOnce ? "web-on" : ""} type="button" disabled={sending} onClick={() => setWebOnce((value) => !value)}><Globe2 /></IconButton>
          {selectedDocuments.length > 0 && <span className="composer-scope"><Library size={13} />{selectedDocuments.length} 份优先资料<button className="scope-mode-toggle" type="button" title={strictDocumentScope ? "当前只检索选中资料，点击恢复全库检索" : "当前检索全库并优先这些资料，点击限制为仅选中"} onClick={toggleStrictDocumentScope}>{strictDocumentScope ? "仅这些" : "全库优先"}</button><button type="button" aria-label="清空优先资料" title="清空优先资料" onClick={clearDocumentScope}><X size={12} /></button></span>}
          {webOnce && <span className="composer-web-scope"><Globe2 size={13} />本轮联网</span>}
          <label className={`composer-select model ${activeProvider?.configured ? "connected" : "offline"}`} title="本会话使用的模型"><i /><ModelSelect providers={settings?.providers || []} label="当前模型" value={selectedProvider} onChange={(value) => void changeProvider(value)} className="composer-model-select" /></label>
          <label className="composer-select depth" title="回答深度"><select aria-label="回答深度" value={settings?.preferences.assistant.answer_depth || "standard"} disabled={sending || !settings} onChange={(event) => void changeAnswerDepth(event.target.value as "concise" | "standard" | "deep")}><option value="concise">简洁</option><option value="standard">标准</option><option value="deep">深入</option></select></label>
          <span className="composer-hint">Enter 发送 · Shift Enter 换行</span>
          {sending ? <button className="send-button stop" type="button" aria-label="停止生成" onClick={() => abortRef.current?.abort()}><Square /></button> : <button className="send-button" type="submit" disabled={!draft.trim() || !libraryReady} aria-label="发送"><ArrowUp /></button>}
        </div>
      </div>
    </form>
  );

  return (
    <section className={`chat-page ${!loading && !messages.length ? "is-empty" : ""}`}>
      <div className="chat-scroll" ref={scrollRef}>
        {loading ? <LoadingState label="正在找回这段对话…" /> : messages.length ? (
          <div className="conversation">
            {messages.map((message, index) => message.role === "user" ? (
              <div className="user-message-wrap" key={index}>
                <div className="user-message">{message.content}</div>
                {message.references?.length ? <div className="message-references">{message.references.map((reference) => <button type="button" key={`${reference.type}:${reference.id}`} onClick={() => openReference(reference)}>{reference.type === "document" ? <FileText size={12} /> : <MessageCircle size={12} />}<span>{reference.title}</span><small>{reference.type === "document" ? reference.collection === "wiki" ? "Wiki" : "资料" : "会话"}</small></button>)}</div> : null}
              </div>
            ) : (
              <article className={`assistant-message ${message.failed ? "failed" : ""}`} key={index}>
                <div className="assistant-heading"><img src="/assets/brand/expressions/bobodan-expression-neutral.webp" alt="" /><span>{settings?.preferences.assistant.display_name || "Bobodan"}</span></div>
                {message.pending && status && <BobodanProcess state={brandState} detail={status} />}
                {!message.pending && <RunSummary artifact={message.artifacts?.find((artifact): artifact is RunSummaryArtifact => artifact.type === "run_summary")} />}
                <div className="answer-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (message.pending ? "正在整理回答…" : message.failed ? "回答没有完成。" : "本轮没有生成可显示的内容。")}</ReactMarkdown></div>
                {message.artifacts?.map(artifactSurface)}
                <AttributionBadges attribution={message.attribution} onOpenSources={showSourceContext} />
                <PersonalizationChip references={message.personalization} />
                {!message.pending && !message.failed && message.content && !message.artifacts?.some((artifact) => artifact.type === "practice_ready") && <div className="answer-actions"><button className="quiet-button" onClick={() => preparePractice(index)}><BookOpen size={15} />生成 5 道练习</button></div>}
                {message.failed && <div className="answer-failure"><span>{error || "AI 连接暂时不可用，请稍后重试。"}</span><button className="quiet-button" disabled={sending} onClick={() => retryMessage(index)}><RotateCcw size={15} />重新发送本轮</button></div>}
                {message.stopped && <div className="answer-failure"><span>回答已停止，只生成了部分内容。</span><button className="quiet-button" disabled={sending} onClick={() => retryMessage(index)}><RotateCcw size={15} />重新发送本轮</button></div>}
              </article>
            ))}
            {status && !messages.at(-1)?.pending && <BobodanProcess state={brandState} detail={status} />}
          </div>
        ) : (
          <div className="welcome-view">
            <div className="welcome-identity">
              <BrandIllustration state="ready" size={112} alt="Bobodan" />
              <h2>今天想学点什么？</h2>
              <div className="welcome-context">
                <span><FolderOpen size={14} />{activeLibrary?.name || "尚未选择资料库"}</span>
                <span><Brain size={14} />记忆随学习沉淀</span>
              </div>
            </div>
            {error && <ErrorNotice message={error} />}
            {composer}
            {wikiPlanLoading && <BobodanProcess state="reading" detail={status || "正在生成 Wiki 计划"} />}
            <div className="starter-actions">
              <button onClick={() => applyPrompt("根据我的资料，帮我梳理今天最值得学习的三个知识点。")}>梳理学习重点</button>
              <button onClick={() => applyPrompt("请先用直觉解释，再给出严谨推导。")}>先讲直觉，再补证明</button>
              <button disabled={documentImporting} onClick={startDocumentImport}><FilePlus2 size={15} />{documentImporting ? "正在导入" : "导入资料"}</button>
              <button onClick={() => navigate("/practice")}><BookOpen size={15} />开始练习</button>
            </div>
          </div>
        )}
      </div>
      {messages.length > 0 && error && <ErrorNotice message={error} />}
      {messages.length > 0 && composer}
    </section>
  );
}
