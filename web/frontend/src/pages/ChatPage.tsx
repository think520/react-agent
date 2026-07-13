import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, BookOpen, Brain, Command, FilePlus2, FolderOpen, Library, Paperclip, RotateCcw, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { AttributionBadges, BrandIllustration, ErrorNotice, IconButton, LoadingState } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { api, streamChat } from "../lib/api";
import type { ChatMessage, WikiArtifact, WikiFocusArtifact, WikiPlanArtifact, WikiResultArtifact } from "../types";

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

export function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const {
    refreshSessions,
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setDraft(localStorage.getItem(`bobodan:draft:${sessionId || "new"}`) || "");
    setError("");
    if (!sessionId) {
      setMessages([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    void api.session(sessionId)
      .then((session) => setMessages(session.messages))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

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
    setDraft("");
    setPaletteDismissed(true);
    setSending(true);
    setError("");
    setStatus("正在理解你的问题");
    setBrandState("thinking");
    setMessages((current) => [...current, { role: "user", content: message }, { role: "assistant", content: "", pending: true }]);
    let nextSessionId = sessionId;
    try {
      let profile: { learningGoal?: string; memoryEnabled?: boolean; webEnabled?: boolean } = {};
      try { profile = JSON.parse(localStorage.getItem("bobodan:learning-profile") || "{}"); }
      catch { profile = {}; }
      await streamChat(message, sessionId, selectedDocumentIds, profile, (streamEvent) => {
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
      });
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false } : item));
      await new Promise((resolve) => window.setTimeout(resolve, 600));
      setStatus("");
      await refreshSessions();
      if (nextSessionId) {
        void api.generateSessionTitle(nextSessionId).then(refreshSessions).catch(() => undefined);
      }
      if (!sessionId && nextSessionId) navigate(`/chat/${nextSessionId}`, { replace: true });
    } catch (reason) {
      const messageText = reason instanceof Error ? reason.message : "本轮回答失败，请重新发送。";
      setError(messageText);
      setStatus("");
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false, failed: true } : item));
    } finally {
      setSending(false);
    }
  }

  function latestArtifact(type: WikiArtifact["type"]): WikiArtifact | undefined {
    return messages.flatMap((message) => message.artifacts || []).filter((artifact) => artifact.type === type).at(-1);
  }

  async function refreshWikiSession(id: string) {
    const detail = await api.session(id);
    setMessages(detail.messages);
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
      await refreshWikiSession(result.chat_session_id);
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
      await refreshWikiSession(sessionId);
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
      await refreshWikiSession(sessionId);
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
      await refreshWikiSession(sessionId);
    } catch (reason) {
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
      await refreshWikiSession(sessionId);
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

  const activeProvider = settings?.providers.find((provider) => provider.name === settings.default_provider);
  const slashItems = useMemo<SlashItem[]>(() => [
    ...WEB_COMMANDS,
    ...(settings?.skills || []).map((skill) => ({
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

  function chooseSlashItem(item: SlashItem) {
    setDraft(item.value);
    setPaletteDismissed(true);
    setPaletteIndex(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function artifactSurface(artifact: WikiArtifact) {
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
      <div className="composer">
        <textarea
          ref={inputRef}
          rows={1}
          value={draft}
          disabled={sending || !libraryReady}
          placeholder="说点什么…"
          aria-label="消息"
          onChange={(event) => { setDraft(event.target.value); setPaletteDismissed(false); setPaletteIndex(0); }}
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
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="composer-toolbar">
          <IconButton label={documents.length ? "选择资料范围" : "前往资料库"} type="button" onClick={() => documents.length ? openContext() : navigate("/library")}><Paperclip /></IconButton>
          {selectedDocuments.length > 0 && <span className="composer-scope"><Library size={13} />{selectedDocuments.length} 份资料<button type="button" aria-label="清空资料范围" title="清空资料范围" onClick={clearDocumentScope}><X size={12} /></button></span>}
          <span className={`composer-model ${activeProvider?.configured ? "connected" : "offline"}`}><i />{settings?.default_provider || "AI 未连接"}</span>
          <span className="composer-hint">Enter 发送 · Shift Enter 换行</span>
          <button className="send-button" type="submit" disabled={!draft.trim() || sending || !libraryReady} aria-label="发送"><ArrowUp /></button>
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
              <div className="user-message" key={index}>{message.content}</div>
            ) : (
              <article className={`assistant-message ${message.failed ? "failed" : ""}`} key={index}>
                <div className="assistant-heading"><img src="/assets/brand/expressions/bobodan-expression-neutral.webp" alt="" /><span>Bobodan</span></div>
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
            {status && <div className="process-status" role="status">
              <BrandIllustration state={brandState} size={58} />
              <div><strong>Bobodan 正在处理</strong><span>{status}</span></div>
              <span className="process-lines" aria-hidden="true"><i /><i /><i /></span>
            </div>}
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
