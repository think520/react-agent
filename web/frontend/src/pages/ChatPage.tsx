import {} from "../lib/documentLinks";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Command, FileText, Globe2, Library, MessageCircle, Paperclip, Square, Sparkles, X } from "lucide-react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import { createChatActions } from "./chat/chatActions";

import type { AppOutletContext } from "../components/AppShell";
import { IconButton, LoadingState } from "../components/common";
import { WikiPlanCard } from "../components/WikiPlanCard";
import { ModelSelect } from "../components/ModelSelect";
import { DropdownSelect } from "../components/DropdownSelect";
import { AskUserCard } from "../components/artifacts/AskUserCard";
import {} from "../components/RetrievalDegradedNotice";
import { KnowledgeContextCard } from "../components/artifacts/KnowledgeContextCard";
import { MemoryConfirmationCard } from "../components/artifacts/MemoryConfirmationCard";
import { PracticeReadyCard } from "../components/artifacts/PracticeReadyCard";
import { SettingsChangeCard } from "../components/artifacts/SettingsChangeCard";
import { WebCandidatesCard } from "../components/artifacts/WebCandidatesCard";
import { WebConsentCard } from "../components/artifacts/WebConsentCard";
import { WebEvidenceCard } from "../components/artifacts/WebEvidenceCard";
import { WikiFocusCard } from "../components/artifacts/WikiFocusCard";
import { WikiResultCard } from "../components/artifacts/WikiResultCard";
import {} from "../components/ProcessFoldBlock";
import { useChatStream } from "../hooks/useChatStream";
import { useStickyBottomScroll } from "../hooks/useStickyBottomScroll";
import {} from "../ui";
import { api } from "../lib/api";
import {} from "../lib/commandRouter";
import {} from "../lib/errors";
import { parseMentionDraft } from "../lib/mention";
import {} from "../lib/settingsIntent";
import {} from "../stores/handoffStore";
import {
  setMentionDismissed, setMentionIndex, setMentionTab, setPaletteDismissed, setPaletteIndex,
  setReferences, setWebOnce, setInlineError, useChatUiStore,
} from "../stores/chatStore";
import { notifyError } from "../stores/noticeStore";
import { useUiStore } from "../stores/uiStore";
import type { ChatArtifact, KnowledgeContextArtifact, WikiPlanArtifact } from "../types";

import { initialDraft } from "./chat/chatPrimitives";
import { ChatTranscript } from "../components/chat/ChatTranscript";
import { ChatWelcome } from "../components/chat/ChatWelcome";
import type { SlashItem } from "./chat/chatPrimitives";
import { WEB_COMMANDS } from "./chat/chatPrimitives";
import { useCompositionGuard, isImeKeyEvent } from "../lib/ime";

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
    receiveKnowledgeContext,
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
  const receiveKnowledgeContextRef = useRef(receiveKnowledgeContext);
  const clearKnowledgeContextRef = useRef(clearKnowledgeContext);
  const settingsRef = useRef(settings);
  useEffect(() => {
    showKnowledgeContextRef.current = showKnowledgeContext;
    receiveKnowledgeContextRef.current = receiveKnowledgeContext;
    clearKnowledgeContextRef.current = clearKnowledgeContext;
  }, [showKnowledgeContext, receiveKnowledgeContext, clearKnowledgeContext]);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);
  const {
    messages,
    setMessages,
    status,
    setStatus,
    brandState,
    setBrandState,
    handleStreamEvent,
    settleLastMessage,
    truncated,
    clearTruncated,
  } = useChatStream();
  const ime = useCompositionGuard();
  const [draft, setDraft] = useState(() => initialDraft(sessionId, true));
  const [loading, setLoading] = useState(Boolean(sessionId));
  const sending = useChatUiStore((state) => state.sending);
  const practiceStarting = useChatUiStore((state) => state.practiceStarting);
  const error = useChatUiStore((state) => state.inlineError);
  // E1: operation failures are reported to the app-level surface so they stay
  // visible even when the card, dialog or panel that triggered them is gone.
  // `error` (above) keeps only page-level failures: session load and stream fail.
  const setError = (message: string) => notifyError(message);
  const paletteIndex = useChatUiStore((state) => state.paletteIndex);
  const paletteDismissed = useChatUiStore((state) => state.paletteDismissed);
  const wikiPlanLoading = useChatUiStore((state) => state.wikiPlanLoading);
  // P5G.4：`provider::model` 完整引用（模型级选择）
  const [selectedProvider, setSelectedProvider] = useState(() => useUiStore.getState().newSessionProvider || "");

  /** 把 provider 名（或 `provider::model`）补齐为完整引用。 */
  const resolveModelRef = useCallback((ref: string): string => {
    if (!ref) return "";
    const [provider, model] = ref.split("::");
    if (model) return ref;
    const found = settingsRef.current?.providers.find((item) => item.name === provider);
    return found?.model ? `${provider}::${found.model}` : ref;
  }, []);

  function sessionRef(session: { provider_name?: string | null; model_name?: string | null }): string {
    if (!session.provider_name) return "";
    return session.model_name ? `${session.provider_name}::${session.model_name}` : session.provider_name;
  }
  const references = useChatUiStore((state) => state.references);
  const webOnce = useChatUiStore((state) => state.webOnce);
  const strictDocumentScope = useUiStore((state) => state.strictDocumentScope);
  const toggleStrictDocumentScope = useUiStore((state) => state.toggleStrictDocumentScope);
  const webSelections = useChatUiStore((state) => state.webSelections);
  const [referenceDocuments, setReferenceDocuments] = useState(documents);
  const mentionTab = useChatUiStore((state) => state.mentionTab);
  const mentionIndex = useChatUiStore((state) => state.mentionIndex);
  const mentionDismissed = useChatUiStore((state) => state.mentionDismissed);
  const { ref: scrollRef, pinToBottom } = useStickyBottomScroll<HTMLDivElement>([messages, status]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // P0-1: the run lives on the server now, so stopping it needs its stream id.
  const streamIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef(sessionId);
  const leaveChatRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const defaultProvider = settingsRef.current?.default_provider || "";
    setDraft(initialDraft(sessionId));
    setError("");
    useUiStore.getState().setSourceContext(null);
    if (!sessionId) {
      setMessages([]);
      setReferences([]);
      clearKnowledgeContextRef.current();
      setSelectedProvider(resolveModelRef(useUiStore.getState().newSessionProvider || defaultProvider));
      setLoading(false);
      return;
    }
    setLoading(true);
    void api.session(sessionId)
      .then((session) => {
        if (cancelled) return;
        setMessages(session.messages);
        setReferences([]);
        setSelectedProvider(resolveModelRef(sessionRef(session) || defaultProvider));
        const latestKnowledgeContext = session.messages
          .flatMap((message) => message.artifacts || [])
          .filter((artifact): artifact is KnowledgeContextArtifact => artifact.type === "knowledge_context")
          .at(-1);
        if (latestKnowledgeContext) receiveKnowledgeContextRef.current(latestKnowledgeContext.context);
        else clearKnowledgeContextRef.current();
      })
      .catch((reason: Error) => { if (!cancelled) setInlineError(reason.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, setMessages, resolveModelRef]);

  useEffect(() => {
    const resolved = resolveModelRef(selectedProvider || settings?.default_provider || "");
    if (resolved && resolved !== selectedProvider) setSelectedProvider(resolved);
  }, [selectedProvider, settings, resolveModelRef]);

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

  const {
    resolveWebConsent,
    toggleWebCandidate,
    applyWebCandidates,
    confirmWikiFocus,
    applyWikiPlan,
    recoverWikiPlan,
    cancelWikiRun,
    undoWikiPlan,
    applyPrompt,
    preparePractice,
    startPreparedPractice,
    retryMessage,
    changeProvider,
    changeAnswerDepth,
    resolveSettingsChange,
    skipInteraction,
    resolveInteraction,
    resolveMemoryProposal,
    removeReference,
    openReference,
    send,
  // 误报：这里只是把 ref 对象转交给纯工厂（函数体内才读 .current），render 期并不访问 ref。
  // eslint-disable-next-line react-hooks/refs -- factory only stores the refs; .current is read inside handlers
  } = createChatActions({
    messages,
    setMessages,
    status,
    setStatus,
    brandState,
    setBrandState,
    handleStreamEvent,
    settleLastMessage,
    truncated,
    clearTruncated,
    settings,
    sessionId,
    navigate,
    documents,
    selectedDocumentIds,
    referenceDocuments,
    inputRef,
    abortRef,
    streamIdRef,
    sessionIdRef,
    leaveChatRef,
    startDocumentImport,
    documentImporting,
    openLibrarySetup,
    clearDocumentScope,
    selectedDocuments,
    resolveModelRef,
    sessionRef,
    setSelectedProvider,
    setDraft,
    draft,
    sending,
    webOnce,
    libraryReady,
    activeLibrary,
    pinToBottom,
    references,
    webSelections,
    refreshSessions,
    refreshSettings,
    receiveKnowledgeContext,
    selectedProvider,
    strictDocumentScope,
  });

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
      case "ask_user":
        return <AskUserCard
          key={artifact.artifact_id}
          artifact={artifact}
          busy={sending}
          onAnswer={(item, answers) => void resolveInteraction(item, answers)}
          onSkip={(item) => void skipInteraction(item)}
        />;
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
        <div className="mention-list">{mentionItems.map((item, index) => {
          const alreadySelected = references.some((reference) => reference.type === item.type && reference.id === item.id);
          return <button
            type="button"
            role="option"
            aria-selected={index === mentionIndex}
            key={`${item.type}:${item.id}`}
            className={[index === mentionIndex ? "active" : "", alreadySelected ? "selected" : ""].filter(Boolean).join(" ") || undefined}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => chooseMention(item)}
          >
            <span>{item.type === "document" ? <FileText size={15} /> : <MessageCircle size={15} />}</span>
            <div><strong>{item.title}</strong><small>{item.subtitle}</small></div>
            {alreadySelected && <i className="mention-selected">已引用</i>}
          </button>;
        })}</div>
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
      {...ime.compositionProps}
          onChange={(event) => { setDraft(event.target.value); setPaletteDismissed(false); setMentionDismissed(false); setPaletteIndex(0); setMentionIndex(0); }}
          onKeyDown={(event) => {
          if (ime.isComposing(event) || isImeKeyEvent(event)) return;
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
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !ime.isComposing(event)) {
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
          <label className={`composer-select model ${activeProvider?.configured ? "connected" : "offline"}`} title="本会话使用的模型"><i /><ModelSelect providers={settings?.providers || []} label="当前模型" value={selectedProvider} onChange={(value) => void changeProvider(value)} /></label>
          <label className="composer-select depth" title="回答深度"><DropdownSelect ariaLabel="回答深度" value={settings?.preferences.assistant.answer_depth || "standard"} disabled={sending || !settings} onChange={(value) => void changeAnswerDepth(value as "concise" | "standard" | "deep")} options={[{ value: "concise", label: "简洁" }, { value: "standard", label: "标准" }, { value: "deep", label: "深入" }]} /></label>
          <span className="composer-hint">Enter 发送 · Shift Enter 换行</span>
          {sending ? <button className="send-button stop" type="button" aria-label="停止生成" onClick={() => { const id = streamIdRef.current; abortRef.current?.abort(); if (id) void api.cancelRun(id).catch(() => undefined); }}><Square /></button> : <button className="send-button" type="submit" disabled={!draft.trim() || !libraryReady} aria-label="发送"><ArrowUp /></button>}
        </div>
      </div>
    </form>
  );

  return (
    <section className={"chat-page " + (!loading && !messages.length ? "is-empty" : "")}>
      <div className="chat-scroll" ref={scrollRef}>
        {loading ? <LoadingState label="正在找回这段对话…" /> : messages.length ? (
          <ChatTranscript
            messages={messages}
            status={status}
            brandState={brandState}
            assistantName={settings?.preferences.assistant.display_name || "Bobodan"}
            sending={sending}
            error={error || ""}
            truncated={truncated}
            onContinue={() => { clearTruncated(); void send(undefined, "请从中断处继续写，不要重复已经写过的内容。"); }}
            onPreparePractice={preparePractice}
            onRetry={retryMessage}
            renderArtifact={artifactSurface}
            onOpenReference={openReference}
            onOpenSources={showSourceContext}
          />
        ) : (
          <ChatWelcome
            libraryName={activeLibrary?.name || ""}
            error={error || ""}
            composer={composer}
            wikiPlanLoading={wikiPlanLoading}
            status={status}
            brandState={brandState}
            documentImporting={documentImporting}
            onApplyPrompt={applyPrompt}
            onImport={startDocumentImport}
            onOpenPractice={() => navigate("/practice")}
          />
        )}
      </div>
      {messages.length > 0 && composer}
    </section>
  );
}
