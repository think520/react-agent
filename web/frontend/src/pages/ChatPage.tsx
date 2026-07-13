import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, BookOpen, Brain, Check, Command, FilePlus2, FileText, FolderOpen, Library, MessageCircle, Paperclip, RotateCcw, Square, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { AttributionBadges, BrandIllustration, ErrorNotice, IconButton, LoadingState } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { api, streamChat } from "../lib/api";
import type { ChatArtifact, ChatMessage, ChatReference, SettingsChangeArtifact, WikiFocusArtifact, WikiPlanArtifact, WikiResultArtifact } from "../types";

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
  const [brandState, setBrandState] = useState<"thinking" | "reading" | "writing">("thinking");
  const [error, setError] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [paletteDismissed, setPaletteDismissed] = useState(false);
  const [wikiPlanLoading, setWikiPlanLoading] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState(() => localStorage.getItem("bobodan:provider:new") || "");
  const [references, setReferences] = useState<ChatReference[]>([]);
  const [referenceDocuments, setReferenceDocuments] = useState(documents);
  const [mentionTab, setMentionTab] = useState<"document" | "session">("document");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionDismissed, setMentionDismissed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

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
    const element = scrollRef.current;
    if (element && typeof element.scrollTo === "function") {
      element.scrollTo({ top: element.scrollHeight, behavior: sending ? "smooth" : "auto" });
    }
  }, [messages, status, sending]);

  async function send(event?: FormEvent, overrideMessage?: string) {
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
      }, (streamEvent) => {
        if (streamEvent.event === "run_started") nextSessionId = streamEvent.data.chat_session_id;
        if (streamEvent.event === "status") {
          setStatus(streamEvent.data.message);
          if (/资料|检索|查找|读取/.test(streamEvent.data.message)) setBrandState("reading");
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
        if (streamEvent.event === "run_failed") throw new Error(streamEvent.data.error.message);
        if (streamEvent.event === "run_completed") setStatus("回答已经整理完成");
      }, controller.signal);
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false } : item));
      await new Promise((resolve) => window.setTimeout(resolve, 600));
      setStatus("");
      await refreshSessions();
      if (nextSessionId) {
        void api.generateSessionTitle(nextSessionId).then(refreshSessions).catch(() => undefined);
      }
      if (!sessionId && nextSessionId) navigate(`/chat/${nextSessionId}`, { replace: true });
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

  async function createWikiFocus(instruction: string, action: "generate" | "update" = "generate") {
    let carriedScope: { documentIds?: string[]; wikiDocumentIds?: string[]; course?: string | null } = {};
    try { carriedScope = JSON.parse(localStorage.getItem("bobodan:wiki-scope") || "{}"); }
    catch { carriedScope = {}; }
    const documentIds = carriedScope.documentIds?.length ? carriedScope.documentIds : selectedDocumentIds;
    const wikiDocumentIds = carriedScope.wikiDocumentIds || [];
    if (!documentIds.length && !wikiDocumentIds.length && !carriedScope.course) {
      setError("请先从资料库选择至少一份学习资料，再开始 Wiki 整理。" );
      return;
    }
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
        document_ids: documentIds,
        wiki_document_ids: wikiDocumentIds,
        course: carriedScope.course,
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
      try {
        const refreshed = await api.wikiPlan(artifact.plan_id);
        setMessages((current) => current.map((message) => ({
          ...message,
          artifacts: message.artifacts?.map((item) => item.type === "wiki_plan" && item.plan_id === artifact.plan_id
            ? { ...item, plan: refreshed }
            : item),
        })));
      } catch { /* keep the persisted chat artifact when refresh is unavailable */ }
      setError(reason instanceof Error ? reason.message : "Wiki 写入失败。" );
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
    navigate("/practice");
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
    if (artifact.type === "settings_change") {
      return <section className={`settings-change-card ${artifact.status}`} key={artifact.artifact_id}>
        <header><span>设置变更</span><strong>{artifact.status === "pending" ? "确认后才会生效" : artifact.status === "applied" ? "设置已更新" : "已取消修改"}</strong></header>
        <div className="settings-change-list">{artifact.changes.map((change) => <div key={change.key}><span>{change.label}</span><del>{displaySettingValue(change.before)}</del><i>→</i><strong>{displaySettingValue(change.after)}</strong></div>)}</div>
        {artifact.status === "pending" && <footer><button className="quiet-button" disabled={sending} onClick={() => void resolveSettingsChange(artifact, "reject")}>取消</button><button className="primary-button" disabled={sending} onClick={() => void resolveSettingsChange(artifact, "apply")}><Check size={15} />确认修改</button></footer>}
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
      />;
    }
    return <section className={`wiki-result-card ${artifact.status}`} key={artifact.artifact_id}>
      <header><span>Wiki Result</span><strong>{artifact.status === "restored" ? "已恢复检查点" : "Wiki 已写入"}</strong></header>
      {artifact.written?.length ? <p>本轮写入 {artifact.written.length} 个页面。</p> : <p>{artifact.status === "restored" ? "本轮变更已经撤销。" : "已保存变更和检查点。"}</p>}
      {artifact.status === "applied" && artifact.checkpoint_id && <footer><button className="quiet-button" disabled={wikiPlanLoading} onClick={() => void undoWikiPlan(artifact)}>撤销本轮写入</button></footer>}
    </section>;
  }

  const composer = (
    <form className="composer-wrap" onSubmit={(event) => void send(event)}>
      {status && <div className="composer-status" role="status"><span className="composer-status-mark"><Sparkles size={14} /></span><div><strong>{brandState === "reading" ? "正在查找资料" : brandState === "writing" ? "正在生成回答" : "正在理解问题"}</strong><small>{status}</small></div></div>}
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
          {selectedDocuments.length > 0 && <span className="composer-scope"><Library size={13} />{selectedDocuments.length} 份资料<button type="button" aria-label="清空资料范围" title="清空资料范围" onClick={clearDocumentScope}><X size={12} /></button></span>}
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
                <div className="answer-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (message.pending ? "正在整理回答…" : message.failed ? "回答没有完成。" : "本轮没有生成可显示的内容。")}</ReactMarkdown></div>
                {message.artifacts?.map(artifactSurface)}
                <AttributionBadges attribution={message.attribution} />
                {!message.pending && message.process?.length ? <details className="process-disclosure">
                  <summary>查看处理过程</summary>
                  <div>{message.process.map((item, processIndex) => <p key={processIndex}><span>{item.phase === "failed" ? "未完成" : item.phase === "completed" ? "完成" : "进行中"}</span>{item.message}{typeof item.elapsed === "number" ? <small>{item.elapsed.toFixed(1)}s</small> : null}</p>)}</div>
                </details> : null}
                {!message.pending && !message.failed && message.content && <div className="answer-actions"><button className="quiet-button" onClick={() => preparePractice(index)}><BookOpen size={15} />生成 5 道练习</button></div>}
                {message.failed && <div className="answer-failure"><span>{error || "AI 连接暂时不可用，请稍后重试。"}</span><button className="quiet-button" disabled={sending} onClick={() => retryMessage(index)}><RotateCcw size={15} />重新发送本轮</button></div>}
              </article>
            ))}
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
            {wikiPlanLoading && <div className="process-status" role="status">
              <BrandIllustration state="reading" size={58} />
              <div><strong>Bobodan 正在整理</strong><span>{status || "正在生成 Wiki 计划"}</span></div>
              <span className="process-lines" aria-hidden="true"><i /><i /><i /></span>
            </div>}
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
