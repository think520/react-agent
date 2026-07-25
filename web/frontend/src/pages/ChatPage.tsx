import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, BookOpen, Brain, Check, Command, ExternalLink, FilePlus2, FileText, FolderOpen, Globe2, Library, MessageCircle, Paperclip, RotateCcw, Square, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { AttributionBadges, BrandIllustration, ErrorNotice, IconButton, LoadingState } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { api, streamChat } from "../lib/api";
import type { ChatArtifact, ChatMessage, ChatReference, MemoryConfirmationArtifact, PersonalizationRef, PracticeReadyArtifact, SettingsChangeArtifact, WebCandidatesArtifact, WebConsentArtifact, WebEvidenceArtifact, WikiFocusArtifact, WikiPlanArtifact, WikiResultArtifact } from "../types";

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

const SETTINGS_PHRASES = [
  "回答短一点", "简短一点", "回答简洁", "少说一点", "回答详细", "讲深入", "更深入", "详细一点",
  "标准回答", "恢复标准", "正常详细", "引导我", "苏格拉底", "多提问", "直接讲解", "讲解式",
  "直接告诉我", "陪我练", "陪练", "多练习", "反馈直接", "直接批评", "严格一点", "反馈温和",
  "温和一点", "别太直接", "关闭记忆", "不要记忆", "停用记忆", "开启记忆", "打开记忆", "启用记忆",
];

function looksLikeSettingsChange(message: string) {
  const text = message.replace(/\s+/g, "").toLocaleLowerCase();
  return SETTINGS_PHRASES.some((phrase) => text.includes(phrase));
}

type ProcessBrandState = "thinking" | "reading" | "writing" | "ready";

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

function displaySettingValue(value: unknown) {
  if (value === true) return "开启";
  if (value === false) return "关闭";
  const labels: Record<string, string> = {
    concise: "简洁", standard: "标准", deep: "深入",
    guided: "引导式", explanatory: "讲解式", practice: "陪练式",
    gentle: "温和", direct: "直接",
  };
  return labels[String(value)] || String(value);
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
    clearDocumentScope,
    activeLibrary,
    openLibrarySetup,
    startDocumentImport,
    documentImporting,
    libraryReady,
  } = useOutletContext<AppOutletContext>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState(() => localStorage.getItem(`bobodan:draft:${sessionId || "new"}`) || "");
  const [loading, setLoading] = useState(Boolean(sessionId));
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState("");
  const [brandState, setBrandState] = useState<ProcessBrandState>("thinking");
  const [practiceStarting, setPracticeStarting] = useState("");
  const [error, setError] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [paletteDismissed, setPaletteDismissed] = useState(false);
  const [wikiPlanLoading, setWikiPlanLoading] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState(() => localStorage.getItem("bobodan:provider:new") || "");
  const [references, setReferences] = useState<ChatReference[]>([]);
  const [webOnce, setWebOnce] = useState(false);
  const [strictDocumentScope, setStrictDocumentScope] = useState(
    () => localStorage.getItem("bobodan:scope:strict") === "true",
  );
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
    setDraft(localStorage.getItem(`bobodan:draft:${sessionId || "new"}`) || "");
    setError("");
    if (!sessionId) {
      setMessages([]);
      setReferences([]);
      setSelectedProvider(localStorage.getItem("bobodan:provider:new") || settings?.default_provider || "");
      setLoading(false);
      return;
    }
    setLoading(true);
    void api.session(sessionId)
      .then((session) => {
        setMessages(session.messages);
        setReferences([]);
        setSelectedProvider(session.provider_name || settings?.default_provider || "");
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [sessionId, settings?.default_provider]);

  useEffect(() => {
    if (!selectedProvider && settings?.default_provider) setSelectedProvider(settings.default_provider);
  }, [selectedProvider, settings?.default_provider]);

  useEffect(() => {
    if (!activeLibrary) {
      setReferenceDocuments([]);
      return;
    }
    void api.documents("all").then(setReferenceDocuments).catch(() => setReferenceDocuments(documents));
  }, [activeLibrary?.library_id, documents]);

  useEffect(() => {
    localStorage.setItem(`bobodan:draft:${sessionId || "new"}`, draft);
  }, [draft, sessionId]);

  useEffect(() => {
    localStorage.setItem("bobodan:scope:strict", String(strictDocumentScope));
  }, [strictDocumentScope]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const planningRunIds = useMemo(() => messages.flatMap((message) =>
    (message.artifacts || [])
      .filter((artifact): artifact is WikiPlanArtifact => artifact.type === "wiki_plan" && (artifact.status === "planning" || artifact.plan.status === "planning"))
      .map((artifact) => artifact.plan_id),
  ), [messages]);

  useEffect(() => {
    if (!planningRunIds.length) return;
    let cancelled = false;
    const poll = async () => {
      for (const runId of planningRunIds) {
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
  }, [planningRunIds.join("|")]);

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
    if (message === "/new") { setDraft(""); navigate("/chat"); return; }
    if (message === "/library") { setDraft(""); navigate("/library"); return; }
    if (message === "/wiki") { setDraft(""); navigate("/library?collection=wiki"); return; }
    if (message === "/wiki generate") {
      setDraft("");
      const plan = latestArtifact("wiki_plan") as WikiPlanArtifact | undefined;
      if (plan?.status === "planned") await applyWikiPlan(plan);
      else setError("请先使用 /wiki plan 创建并审查一份 Wiki 计划。" );
      return;
    }
    if (message === "/wiki plan" || message.startsWith("/wiki plan ")) {
      setDraft("");
      await createWikiFocus(message.slice("/wiki plan".length).trim());
      return;
    }
    if (message === "/wiki update" || message.startsWith("/wiki update ")) {
      setDraft("");
      await createWikiFocus(message.slice("/wiki update".length).trim(), "update");
      return;
    }
    if (message === "/practice") { setDraft(""); navigate("/practice"); return; }
    if (message === "/review") { setDraft(""); navigate("/review"); return; }
    if (message.startsWith("/quiz generate ")) {
      const topic = message.slice("/quiz generate ".length).trim();
      if (topic) localStorage.setItem("bobodan:practice-topic", topic);
      setDraft("");
      navigate("/practice");
      return;
    }
    if (!webResearchId && (webOnce || message === "/web search" || message.startsWith("/web search "))) {
      const query = message.startsWith("/web search") ? message.slice("/web search".length).trim() : message;
      if (!query) {
        setError("请在 /web search 后输入需要查找的内容。" );
        return;
      }
      setDraft("");
      setWebOnce(false);
      await startWebSearch(query, undefined, true);
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
          setError(reason instanceof Error ? reason.message : "无法创建设置变更确认。" );
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
      let profile: { learningGoal?: string; webEnabled?: boolean } = {};
      try { profile = JSON.parse(localStorage.getItem("bobodan:learning-profile") || "{}"); }
      catch { profile = {}; }
      await streamChat(message, sessionId, selectedDocumentIds, {
        ...profile,
        memoryEnabled: settings?.preferences.memory.enabled ?? true,
        provider: selectedProvider || settings?.default_provider,
        references: outgoingReferences,
        webResearchId,
        strictDocumentScope,
      }, (streamEvent) => {
        if (streamEvent.event === "run_started") {
          nextSessionId = streamEvent.data.chat_session_id;
          sessionIdRef.current = streamEvent.data.chat_session_id;
        }
        if (streamEvent.event === "status") {
          setStatus(streamEvent.data.message);
          if (["rag_search", "web_research"].includes(streamEvent.data.tool_name || "") || /资料|检索|查找|读取|网页/.test(streamEvent.data.message)) setBrandState("reading");
          else if (["question_generate", "quiz_start"].includes(streamEvent.data.tool_name || "") || /题目|练习|生成/.test(streamEvent.data.message)) setBrandState("writing");
          setMessages((current) => current.map((item, index) => index === current.length - 1
            ? {
                ...item,
                process: [...(item.process || []), {
                  phase: streamEvent.data.phase,
                  message: streamEvent.data.message,
                  toolName: streamEvent.data.tool_name,
                  elapsed: streamEvent.data.elapsed,
                }],
              }
            : item));
        }
        if (streamEvent.event === "message_delta") {
          setStatus("正在组织回答");
          setBrandState("writing");
          setMessages((current) => current.map((item, index) => index === current.length - 1
            ? { ...item, content: item.content + streamEvent.data.content }
            : item));
        }
        if (streamEvent.event === "citation") {
          setStatus("已找到相关资料，正在整理");
          setBrandState("reading");
          setMessages((current) => current.map((item, index) => index === current.length - 1
            ? { ...item, attribution: streamEvent.data.attribution }
            : item));
        }
        if (streamEvent.event === "personalization") {
          setMessages((current) => current.map((item, index) => index === current.length - 1
            ? { ...item, personalization: streamEvent.data.references }
            : item));
        }
        if (streamEvent.event === "chat_artifact") {
          const artifact = streamEvent.data.artifact.type === "practice_ready"
            ? { ...streamEvent.data.artifact, chat_session_id: nextSessionId }
            : streamEvent.data.artifact;
          setMessages((current) => current.map((item, index) => index === current.length - 1
            ? { ...item, artifacts: [...(item.artifacts || []), artifact] }
            : item));
        }
        if (streamEvent.event === "run_failed") throw new Error(streamEvent.data.error.message);
        if (streamEvent.event === "run_completed") { setBrandState("ready"); setStatus("回答已经整理完成"); }
      }, controller.signal);
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false } : item));
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
        setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false } : item));
        return;
      }
      const messageText = reason instanceof Error ? reason.message : "本轮回答失败，请重新发送。";
      setError(messageText);
      setStatus("");
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false, failed: true } : item));
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
    setSelectedProvider(detail.provider_name || settings?.default_provider || "");
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
      setError(reason instanceof Error ? reason.message : "联网搜索暂时不可用。" );
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
      setError(reason instanceof Error ? reason.message : "无法取消本次联网请求。" );
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

  async function useWebCandidates(artifact: WebCandidatesArtifact) {
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
      setError(reason instanceof Error ? reason.message : "选中的网页暂时无法读取。" );
    } finally {
      setStatus("");
      setSending(false);
    }
  }

  async function createWikiFocus(instruction: string, action: "generate" | "update" = "generate") {
    let carriedScope: {
      scopeMode?: "uncovered" | "smart_library" | "selected_only" | "course";
      documentIds?: string[];
      wikiDocumentIds?: string[];
      course?: string | null;
      topic?: string;
    } = {};
    try { carriedScope = JSON.parse(localStorage.getItem("bobodan:wiki-scope") || "{}"); }
    catch { carriedScope = {}; }
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
      localStorage.removeItem("bobodan:wiki-scope");
      if (!sessionId) navigate(`/chat/${result.chat_session_id}`, { replace: true });
      await refreshChatSession(result.chat_session_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法整理 Wiki 重点。" );
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
      setError(reason instanceof Error ? reason.message : "无法调整 Wiki 重点。" );
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
      setError(reason instanceof Error ? reason.message : "无法生成 Wiki 计划。" );
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
      if (!stagedFailure) setError(reason instanceof Error ? reason.message : "Wiki 写入失败。" );
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
      setError(reason instanceof Error ? reason.message : "无法继续处理这份 Wiki 计划。" );
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
      setError(reason instanceof Error ? reason.message : "无法取消这轮 Wiki 整理。" );
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
      setError(reason instanceof Error ? reason.message : "无法撤销本轮 Wiki 整理。" );
    } finally {
      setWikiPlanLoading(false);
    }
  }

  function usePrompt(value: string) {
    setDraft(value);
    inputRef.current?.focus();
  }

  function preparePractice(index: number) {
    const topic = messages[index - 1]?.role === "user"
      ? messages[index - 1].content
      : messages[index].content.slice(0, 160);
    localStorage.setItem("bobodan:practice-topic", topic);
    const isWebContinuation = messages[index - 1]?.role === "user" && messages[index - 1].content === "使用选中的网页来源继续回答。";
    const evidence = isWebContinuation
      ? messages.slice(0, index + 1).flatMap((message) => message.artifacts || []).filter((artifact): artifact is WebEvidenceArtifact => artifact.type === "web_evidence" && artifact.status !== "failed").at(-1)
      : undefined;
    if (evidence) localStorage.setItem("bobodan:practice-web-research", evidence.research_id);
    else localStorage.removeItem("bobodan:practice-web-research");
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
      setError(reason instanceof Error ? reason.message : "暂时无法开始这轮练习。" );
    } finally {
      setPracticeStarting("");
    }
  }

  function retryMessage(index: number) {
    const previous = messages[index - 1];
    if (previous?.role === "user") void send(undefined, previous.content);
  }

  async function changeProvider(provider: string) {
    if (sending) return;
    const previous = selectedProvider;
    setSelectedProvider(provider);
    try {
      if (sessionId) {
        await api.updateSessionProvider(sessionId, provider);
        await refreshSessions();
      } else {
        localStorage.setItem("bobodan:provider:new", provider);
      }
    } catch (reason) {
      setSelectedProvider(previous);
      setError(reason instanceof Error ? reason.message : "无法切换模型。" );
    }
  }

  async function changeAnswerDepth(value: "concise" | "standard" | "deep") {
    if (!settings || settings.preferences.assistant.answer_depth === value) return;
    try {
      await api.patchPreferences(settings.preferences.revision, { assistant: { answer_depth: value } });
      await refreshSettings();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回答深度没有保存成功。" );
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
      setError(reason instanceof Error ? reason.message : "设置变更没有处理成功。" );
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
      setError(reason instanceof Error ? reason.message : "无法更新这条记忆。" );
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

  const activeProvider = settings?.providers.find((provider) => provider.name === selectedProvider);
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

  const mentionMatch = draft.match(/(?:^|\s)@([^\s@]*)$/);
  const rawMentionQuery = mentionMatch?.[1] || "";
  const mentionQuery = rawMentionQuery === "资料" || rawMentionQuery === "会话" ? "" : rawMentionQuery.toLocaleLowerCase();
  const effectiveMentionTab = rawMentionQuery === "会话" ? "session" : rawMentionQuery === "资料" ? "document" : mentionTab;
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
  const mentionOpen = Boolean(mentionMatch) && !mentionDismissed && mentionItems.length > 0 && !draft.startsWith("/");

  function chooseMention(item: (typeof mentionItems)[number]) {
    if (item.type === "session" && references.filter((reference) => reference.type === "session").length >= 3) {
      setError("每条消息最多引用 3 个历史会话。" );
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
    if (artifact.type === "memory_confirmation") {
      return <section className={`memory-confirmation-card ${artifact.status}`} key={artifact.artifact_id}>
        <header><span><Brain size={15} />个人知识</span><strong>{artifact.status === "pending" ? "确认后才会长期记住" : artifact.status === "confirmed" ? "已经记住" : "没有保存"}</strong></header>
        <div className="memory-confirmation-content"><small>{artifact.scope === "global" ? "所有资料库" : "当前资料库"} · {artifact.kind}</small><h4>{artifact.title}</h4>{artifact.before && <del>{artifact.before.content}</del>}<p>{artifact.content}</p></div>
        {artifact.requires_warning && artifact.status === "pending" && <div className="memory-sensitive-warning">这可能涉及健康、身份或其他敏感信息。确认后只保存在本地，你可以随时编辑或删除。</div>}
        {artifact.status === "pending" && <footer><button className="quiet-button" disabled={sending} onClick={() => void resolveMemoryProposal(artifact, "reject")}>不保存</button><button className="primary-button" disabled={sending} onClick={() => void resolveMemoryProposal(artifact, "confirm")}><Check size={15} />{artifact.requires_warning ? "了解并记住" : "确认记住"}</button></footer>}
      </section>;
    }
    if (artifact.type === "settings_change") {
      return <section className={`settings-change-card ${artifact.status}`} key={artifact.artifact_id}>
        <header><span>设置变更</span><strong>{artifact.status === "pending" ? "确认后才会生效" : artifact.status === "applied" ? "设置已更新" : "已取消修改"}</strong></header>
        <div className="settings-change-list">{artifact.changes.map((change) => <div key={change.key}><span>{change.label}</span><del>{displaySettingValue(change.before)}</del><i>→</i><strong>{displaySettingValue(change.after)}</strong></div>)}</div>
        {artifact.status === "pending" && <footer><button className="quiet-button" disabled={sending} onClick={() => void resolveSettingsChange(artifact, "reject")}>取消</button><button className="primary-button" disabled={sending} onClick={() => void resolveSettingsChange(artifact, "apply")}><Check size={15} />确认修改</button></footer>}
      </section>;
    }
    if (artifact.type === "web_consent") {
      return <section className={`web-consent-card ${artifact.status}`} key={artifact.artifact_id}>
        <header><span><Globe2 size={15} />联网资料</span><strong>{artifact.status === "pending" ? "本地证据暂时不足" : artifact.status === "approved" ? "已同意联网查找" : "已继续使用本地资料"}</strong></header>
        <p>{artifact.reason}</p><blockquote>{artifact.query}</blockquote>
        {artifact.status === "pending" && <footer><button className="quiet-button" disabled={sending} onClick={() => void resolveWebConsent(artifact, "reject")}>只用本地资料</button><button className="primary-button" disabled={sending} onClick={() => void resolveWebConsent(artifact, "approve")}><Globe2 size={15} />联网查找</button></footer>}
      </section>;
    }
    if (artifact.type === "web_candidates") {
      const selected = webSelections[artifact.search_id] || artifact.selected_candidate_ids || [];
      const selectable = artifact.status === "ready" || artifact.status === "partial" || (artifact.status === "failed" && artifact.candidates.length > 0);
      const qualityLabels = { official: "官方/教育", reference: "参考资料", community: "社区内容", unknown: "普通网页" };
      return <section className={`web-candidates-card ${artifact.status}`} key={artifact.artifact_id}>
        <header><span><Globe2 size={15} />网页候选</span><strong>{artifact.status === "failed" ? "没有找到可用来源" : artifact.status === "fetching" ? "正在读取来源" : artifact.status === "used" ? "已选择来源" : `找到 ${artifact.candidates.length} 个候选`}</strong></header>
        <p>搜索摘要只用于选择，勾选后才会读取网页正文。最多选择 4 个。</p>
        {artifact.candidates.length > 0 && <div className="web-candidate-list">{artifact.candidates.map((candidate) => <label className={selected.includes(candidate.candidate_id) ? "selected" : ""} key={candidate.candidate_id}><input type="checkbox" checked={selected.includes(candidate.candidate_id)} disabled={!selectable || sending} onChange={() => toggleWebCandidate(artifact, candidate.candidate_id)} /><span><strong>{candidate.title}</strong><small>{candidate.domain} · {qualityLabels[candidate.quality_hint]}</small><p>{candidate.snippet}</p></span><a href={candidate.url} target="_blank" rel="noreferrer" aria-label={`打开 ${candidate.title}`} onClick={(event) => event.stopPropagation()}><ExternalLink size={14} /></a></label>)}</div>}
        {selectable && <footer><small>{selected.length ? `已选择 ${selected.length} 个来源` : artifact.status === "ready" ? "尚未选择来源" : "可以重新选择来源并重试"}</small><button className="primary-button" disabled={!selected.length || sending} onClick={() => void useWebCandidates(artifact)}><BookOpen size={15} />{artifact.status === "ready" ? "使用选中来源" : "重新读取来源"}</button></footer>}
      </section>;
    }
    if (artifact.type === "web_evidence") {
      return <section className={`web-evidence-card ${artifact.status}`} key={artifact.artifact_id}>
        <header><span><BookOpen size={15} />网页证据</span><strong>{artifact.status === "failed" ? "来源读取失败" : artifact.status === "partial" ? "部分来源可用" : "证据快照已保存"}</strong></header>
        {artifact.sources.length ? <div>{artifact.sources.map((source) => <a href={source.url || "#"} target="_blank" rel="noreferrer" key={source.source_id}><span><strong>{source.title}</strong><small>{source.domain} · {source.reader === "jina" ? "Jina Reader 后备" : "直接读取"} · {source.accessed_at ? new Date(source.accessed_at).toLocaleString("zh-CN") : ""}</small></span><ExternalLink size={14} /></a>)}</div> : <p>这些网页没有返回可核实的正文，未用于回答。</p>}
      </section>;
    }
    if (artifact.type === "practice_ready") {
      return <section className={`practice-ready-card ${artifact.status}`} key={artifact.artifact_id}>
        <BrandIllustration state="ready" size={56} />
        <div><header><span>练习已就绪</span><strong>{artifact.count} 道题已经准备好</strong></header><p>{artifact.topic}</p><AttributionBadges attribution={artifact.attribution} /></div>
        <button className="primary-button" disabled={practiceStarting === artifact.artifact_id} onClick={() => void startPreparedPractice(artifact)}><BookOpen size={15} />{artifact.status === "started" ? "继续练习" : practiceStarting === artifact.artifact_id ? "正在打开" : "开始练习"}</button>
      </section>;
    }
    if (artifact.type === "wiki_focus") {
      return <section className="wiki-focus-card" key={artifact.artifact_id}>
        <header><span>Wiki Focus</span><strong>先确认整理重点</strong></header>
        <p>资料范围：{artifact.scope.documents.join("、")}</p>
        {artifact.instruction && <blockquote>{artifact.instruction}</blockquote>}
        {artifact.status === "awaiting_confirmation" && <footer>
          <button className="quiet-button" onClick={() => { setDraft("请调整重点："); inputRef.current?.focus(); }}>调整重点</button>
          <button className="primary-button" disabled={wikiPlanLoading} onClick={() => void confirmWikiFocus(artifact)}>按此重点继续</button>
        </footer>}
        {artifact.status === "confirmed" && <small>重点已确认，计划已生成。</small>}
      </section>;
    }
    if (artifact.type === "wiki_plan") {
      return <WikiPlanCard
        key={artifact.artifact_id}
        plan={artifact.plan}
        busy={wikiPlanLoading}
        onApply={artifact.status === "planned" ? () => void applyWikiPlan(artifact) : undefined}
        onCancel={artifact.status === "planning" ? () => void cancelWikiRun(artifact) : undefined}
        onKeepExisting={artifact.status === "planned" && artifact.plan.staging?.length ? () => void recoverWikiPlan(artifact, "keep_existing") : undefined}
        onRegenerate={artifact.status === "planned" && artifact.plan.staging?.length ? () => void recoverWikiPlan(artifact, "regenerate") : undefined}
      />;
    }
    if (artifact.type === "wiki_result") return <section className={`wiki-result-card ${artifact.status}`} key={artifact.artifact_id}>
      <header><span>Wiki Result</span><strong>{artifact.status === "restored" ? "已恢复检查点" : "Wiki 已写入"}</strong></header>
      {artifact.kept_existing?.length ? <p>已保留“{artifact.kept_existing.join("、")}”的原页面，并写入其余 {artifact.written?.length || 0} 个页面。</p> : artifact.written?.length ? <p>本轮写入 {artifact.written.length} 个页面。</p> : <p>{artifact.status === "restored" ? "本轮变更已经撤销。" : "已保存变更和检查点。"}</p>}
      {artifact.status === "applied" && artifact.checkpoint_id && <footer><button className="quiet-button" disabled={wikiPlanLoading} onClick={() => void undoWikiPlan(artifact)}>撤销本轮写入</button></footer>}
    </section>;
    return null;
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
          {selectedDocuments.length > 0 && <span className="composer-scope"><Library size={13} />{selectedDocuments.length} 份优先资料<button className="scope-mode-toggle" type="button" title={strictDocumentScope ? "当前只检索选中资料，点击恢复全库检索" : "当前检索全库并优先这些资料，点击限制为仅选中"} onClick={() => setStrictDocumentScope((value) => !value)}>{strictDocumentScope ? "仅这些" : "全库优先"}</button><button type="button" aria-label="清空优先资料" title="清空优先资料" onClick={clearDocumentScope}><X size={12} /></button></span>}
          {webOnce && <span className="composer-web-scope"><Globe2 size={13} />本轮联网</span>}
          <label className={`composer-select model ${activeProvider?.configured ? "connected" : "offline"}`} title="本会话使用的模型"><i /><select aria-label="当前模型" value={selectedProvider} disabled={sending} onChange={(event) => void changeProvider(event.target.value)}>{settings?.providers.map((provider) => <option key={provider.name} value={provider.name} disabled={!provider.configured}>{provider.name}{provider.configured ? "" : "（不可用）"}</option>)}</select></label>
          <label className="composer-select depth" title="回答深度"><select aria-label="回答深度" value={settings?.preferences.assistant.answer_depth || "standard"} disabled={sending || !settings} onChange={(event) => void changeAnswerDepth(event.target.value as "concise" | "standard" | "deep")}><option value="concise">简洁</option><option value="standard">标准</option><option value="deep">深入</option></select></label>
          <span className="composer-hint">Enter 发送 · Shift Enter 换行</span>
          {sending && abortRef.current ? <button className="send-button stop" type="button" aria-label="停止生成" onClick={() => abortRef.current?.abort()}><Square /></button> : <button className="send-button" type="submit" disabled={!draft.trim() || sending || !libraryReady} aria-label="发送"><ArrowUp /></button>}
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
                <div className="answer-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (message.pending ? "正在整理回答…" : message.failed ? "回答没有完成。" : "本轮没有生成可显示的内容。")}</ReactMarkdown></div>
                {message.artifacts?.map(artifactSurface)}
                <AttributionBadges attribution={message.attribution} />
                <PersonalizationChip references={message.personalization} />
                {!message.pending && message.process?.length ? <details className="process-disclosure">
                  <summary>查看处理过程</summary>
                  <div>{message.process.map((item, processIndex) => <p key={processIndex}><span>{item.phase === "failed" ? "未完成" : item.phase === "completed" ? "完成" : "进行中"}</span>{item.message}{typeof item.elapsed === "number" ? <small>{item.elapsed.toFixed(1)}s</small> : null}</p>)}</div>
                </details> : null}
                {!message.pending && !message.failed && message.content && !message.artifacts?.some((artifact) => artifact.type === "practice_ready") && <div className="answer-actions"><button className="quiet-button" onClick={() => preparePractice(index)}><BookOpen size={15} />生成 5 道练习</button></div>}
                {message.failed && <div className="answer-failure"><span>{error || "AI 连接暂时不可用，请稍后重试。"}</span><button className="quiet-button" disabled={sending} onClick={() => retryMessage(index)}><RotateCcw size={15} />重新发送本轮</button></div>}
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
              <button onClick={() => usePrompt("根据我的资料，帮我梳理今天最值得学习的三个知识点。")}>梳理学习重点</button>
              <button onClick={() => usePrompt("请先用直觉解释，再给出严谨推导。")}>先讲直觉，再补证明</button>
              <button disabled={documentImporting} onClick={startDocumentImport}><FilePlus2 size={15} />{documentImporting ? "正在导入" : "导入资料"}</button>
              <button onClick={() => navigate("/practice")}><BookOpen size={15} />开始练习</button>
            </div>
          </div>
        )}
      </div>
      {messages.length > 0 && composer}
    </section>
  );
}
