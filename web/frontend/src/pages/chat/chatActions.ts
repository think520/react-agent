/**
 * Chat 页的动作层（2026-10-17 M2 store-lift 第 2 步）。
 *
 * 借 openhanako「actions 无闭包」的思路，但把依赖折叠成**一个 ctx 对象**：处理器本体原样搬出组件，
 * 只把原来闭包捕获的值改成 ctx 字段；组件每帧 «createChatActions(ctx)» 一次并解构，调用点一字未改。
 */
import type { FormEvent } from "react";

import { api, streamChat } from "../../lib/api";
import { routeSlashCommand } from "../../lib/commandRouter";
import { toErrorMessage } from "../../lib/errors";
import { readerLocation } from "../../lib/documentLinks";
import { looksLikeSettingsChange } from "../../lib/settingsIntent";
import { notifyError } from "../../stores/noticeStore";
import { useUiStore } from "../../stores/uiStore";
import { useHandoffStore } from "../../stores/handoffStore";
import { setSending, setWebOnce, setPaletteDismissed, setMentionDismissed, setReferences, setInlineError, setWebSelections, setWikiPlanLoading, setPracticeStarting } from "../../stores/chatStore";
import type { ChatStreamEvent } from "../../lib/api";
import type { NavigateFunction } from "react-router-dom";
import type {
  AskUserArtifact, ChatArtifact, ChatMessage, ChatReference, DocumentSummary, LibrarySummary,
  MemoryConfirmationArtifact, PracticeReadyArtifact, SettingsChangeArtifact, SettingsSummary,
  WebCandidatesArtifact, WebConsentArtifact, WebEvidenceArtifact, WikiFocusArtifact, WikiPlanArtifact,
  WikiResultArtifact,
} from "../../types";
import type { ProcessBrandState, StreamEventHandlers } from "../../hooks/useChatStream";
import type { AppOutletContext } from "../../components/shell/types";

export interface ChatActionContext {
  messages: ChatMessage[];
  setMessages: (next: ChatMessage[] | ((current: ChatMessage[]) => ChatMessage[])) => void;
  status: string;
  setStatus: (status: string) => void;
  brandState: ProcessBrandState;
  setBrandState: (state: ProcessBrandState) => void;
  handleStreamEvent: (event: ChatStreamEvent, handlers?: StreamEventHandlers) => void;
  settleLastMessage: (failed?: boolean, stopped?: boolean) => void;
  truncated: { continuing: boolean } | null;
  clearTruncated: () => void;
  settings: SettingsSummary | null;
  sessionId: string | undefined;
  navigate: NavigateFunction;
  documents: DocumentSummary[];
  selectedDocumentIds: string[];
  referenceDocuments: DocumentSummary[];
  inputRef: { current: HTMLTextAreaElement | null };
  abortRef: { current: AbortController | null };
  streamIdRef: { current: string | null };
  sessionIdRef: { current: string | undefined };
  leaveChatRef: { current: boolean };
  startDocumentImport: AppOutletContext["startDocumentImport"];
  documentImporting: boolean;
  openLibrarySetup: AppOutletContext["openLibrarySetup"];
  clearDocumentScope: AppOutletContext["clearDocumentScope"];
  selectedDocuments: DocumentSummary[];
  resolveModelRef: (ref: string) => string;
  sessionRef: (session: { provider_name?: string | null; model_name?: string | null }) => string;
  setSelectedProvider: (next: string | ((current: string) => string)) => void;
  setDraft: (next: string | ((current: string) => string)) => void;
  draft: string;
  sending: boolean;
  webOnce: boolean;
  libraryReady: boolean;
  activeLibrary: LibrarySummary | null;
  pinToBottom: () => void;
  references: ChatReference[];
  webSelections: Record<string, string[]>;
  refreshSessions: AppOutletContext["refreshSessions"];
  refreshSettings: AppOutletContext["refreshSettings"];
  receiveKnowledgeContext: AppOutletContext["receiveKnowledgeContext"];
  selectedProvider: string;
  strictDocumentScope: boolean;
}

export function createChatActions(ctx: ChatActionContext) {
  const {
    messages,
    setMessages,
    setStatus,
    setBrandState,
    handleStreamEvent,
    settleLastMessage,
    settings,
    sessionId,
    navigate,
    selectedDocumentIds,
    inputRef,
    abortRef,
    streamIdRef,
    sessionIdRef,
    leaveChatRef,
    openLibrarySetup,
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
  } = ctx;

  /** 与组件内一致：页面错误统一走通知中心（E1）。 */
  const setError = notifyError;

  async function send(
    event?: FormEvent,
    overrideMessage?: string,
    webResearchId?: string,
    retryFailed = false,
  ) {
    event?.preventDefault();
    const message = (overrideMessage ?? draft).trim();
    if (!message || sending) return;
    if (!libraryReady) return;
    if (!activeLibrary) {
      openLibrarySetup();
      return;
    }
    // W3 F7：只有**用户发消息**才无条件回到底部 —— 助手流式输出不会把视图拽回去，
    // 而用户自己滚到上面之后再发一条，应该回到最新消息。
    pinToBottom();
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
    // F05（2026-09-28 审查）：上一轮失败时，服务端其实**已经分配了会话**（run_started 里回过
    // chat_session_id），只是路由还没跳过去。重试必须沿用它 —— 否则又开一个新会话，
    // 用户刚才那一轮的历史就再也接不上了。
    const targetSessionId = sessionId || sessionIdRef.current || undefined;
    let nextSessionId = targetSessionId;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const profile = useUiStore.getState().learningProfile;
      const [sendProvider, sendModel] = (selectedProvider || settings?.default_provider || "").split("::");
      await streamChat(message, targetSessionId, selectedDocumentIds, {
        ...profile,
        memoryEnabled: settings?.preferences.memory.enabled ?? true,
        provider: sendProvider || undefined,
        model: sendModel || undefined,
        references: outgoingReferences,
        webResearchId,
        strictDocumentScope,
        retryFailed,
        onStreamId: (id) => { streamIdRef.current = id; },
      }, (streamEvent) => handleStreamEvent(streamEvent, {
        onRunStarted: (chatSessionId) => {
          nextSessionId = chatSessionId;
          sessionIdRef.current = chatSessionId;
        },
        getSessionId: () => nextSessionId,
        onKnowledgeContext: receiveKnowledgeContext,
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
      setInlineError(toErrorMessage(reason, "本轮回答失败，请重新发送。"));
      setStatus("");
      settleLastMessage(true);
    } finally {
      abortRef.current = null;
      streamIdRef.current = null;
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

  function retryMessage(index: number, retryFailed = false) {
    const previous = messages[index - 1];
    // 只有**失败**的那一轮才声明 retry_failed（后端据此清掉失败尾部，避免同一句 user turn
    // 存两遍）。「回答已停止」的那一轮没有失败标记，声明了只会让后端多做一次无用的查找。
    if (previous?.role === "user") void send(undefined, previous.content, undefined, retryFailed);
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

  async function sendResume(interactionId: string) {
    // 同 skipInteraction：卡片可能在会话 state 落定前就被操作。
    const activeSessionId = sessionId || sessionIdRef.current || "";
    if (!activeSessionId) return;
    const controller = new AbortController();
    abortRef.current = controller;
    streamIdRef.current = null;
    // Decision B: the continuation is a new assistant message, not a user
    // bubble -- the answers are carried as the paused tool call's result.
    setMessages((current) => [...current, { role: "assistant", content: "", pending: true }]);
    try {
      const profile = useUiStore.getState().learningProfile;
      const [sendProvider, sendModel] = (selectedProvider || settings?.default_provider || "").split("::");
      await streamChat("", activeSessionId, selectedDocumentIds, {
        ...profile,
        memoryEnabled: settings?.preferences.memory.enabled ?? true,
        provider: sendProvider || undefined,
        model: sendModel || undefined,
        references: [],
        strictDocumentScope,
        resumeInteractionId: interactionId,
        onStreamId: (id) => { streamIdRef.current = id; },
      }, (streamEvent) => handleStreamEvent(streamEvent, {
        getSessionId: () => activeSessionId,
      }), controller.signal);
      settleLastMessage();
      setStatus("");
      await refreshChatSession(activeSessionId);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setStatus("");
        settleLastMessage(false, true);
        return;
      }
      setInlineError(toErrorMessage(reason, "继续回答失败，请重新发送。"));
      settleLastMessage(true);
    } finally {
      abortRef.current = null;
      streamIdRef.current = null;
      setSending(false);
    }
  }

  async function skipInteraction(artifact: AskUserArtifact) {
    // 卡片在流中途就会渲染，那时 sessionId 的 **state** 还没落定（只有 ref）——
    // 这里必须兜底，否则点「跳过」会静默什么都不做。
    const activeSessionId = sessionId || sessionIdRef.current || "";
    if (!activeSessionId) return;
    try {
      await api.skipInteraction(artifact.artifact_id, activeSessionId);
    } catch (reason) {
      setError(toErrorMessage(reason, "跳过没有成功。"));
      return;
    }
    // W1 E4：跳过同样要**唤醒暂停的那一轮** —— 否则用户被晾在这里。
    await sendResume(artifact.artifact_id);
  }

  async function resolveInteraction(artifact: AskUserArtifact, answers: Array<{ id: string; answer: string }>) {
    // 同上：回答也可能发生在会话 state 落定之前。
    const activeSessionId = sessionId || sessionIdRef.current || "";
    if (!activeSessionId) return;
    try {
      await api.answerInteraction(artifact.artifact_id, activeSessionId, answers);
    } catch (reason) {
      setError(toErrorMessage(reason, "回答没有保存成功。"));
      return;
    }
    // E4: the paused turn continues with these answers as its tool result.
    await sendResume(artifact.artifact_id);
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
    else navigate(readerLocation({ document_id: reference.id, collection: reference.collection }) || "/library");
  }


  return {
    latestArtifact,
    refreshChatSession,
    startWebSearch,
    resolveWebConsent,
    toggleWebCandidate,
    applyWebCandidates,
    createWikiFocus,
    reviseWikiFocus,
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
    sendResume,
    skipInteraction,
    resolveInteraction,
    resolveMemoryProposal,
    removeReference,
    openReference,
    send,
  };
}
