import { BookmarkPlus, BookOpen, MessageSquareText, Sparkles } from "lucide-react";
import { memo, useMemo, useRef } from "react";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import { useStableCallback as useStable } from "../../hooks/useStableCallback";
import { useTextSelection } from "../../hooks/useTextSelection";
import { BobodanProcess } from "../../pages/chat/chatPrimitives";
import type { Attribution, ChatArtifact, ChatMessage } from "../../types";
import { SelectionActionBar, type SelectionToolbarAction } from "../SelectionActionBar";
import { AssistantMessage, UserMessage } from "./ChatMessage";

type Reference = NonNullable<ChatMessage["references"]>[number];

type AssistantProps = Parameters<typeof AssistantMessage>[0];

const MemoUserMessage = memo(UserMessage);
// renderArtifact 在**渲染期**调用、闭包里带着页面状态（如 busy），不能走 ref 稳定化（会读到上一帧的状态）。
// 所以它照常每次变化，只让「真的有卡片」的消息跟着重渲染；纯文本消息忽略它。
const MemoAssistantMessage = memo(AssistantMessage, (prev: AssistantProps, next: AssistantProps) => {
  for (const key of Object.keys(next) as (keyof AssistantProps)[]) {
    if (key === "renderArtifact" && !next.message.artifacts?.length) continue;
    if (!Object.is(prev[key], next[key])) return false;
  }
  return true;
});

/** Chat 的 Transcript 层（W-F7）：消息列表 + 截断提示 + 回答划词操作 + 收尾状态。 */
export function ChatTranscript({
  messages,
  status,
  brandState,
  assistantName,
  sending,
  error,
  truncated,
  onContinue,
  onPreparePractice,
  onFollowUp,
  onSelectionExplain,
  onSelectionQuote,
  onSelectionPractice,
  onSelectionSaveNote,
  onRetry,
  renderArtifact,
  onOpenReference,
  onOpenSources,
}: {
  messages: ChatMessage[];
  status: string | null;
  brandState: ProcessBrandState;
  assistantName: string;
  sending: boolean;
  error: string;
  truncated: { continuing: boolean } | null;
  onContinue: () => void;
  onPreparePractice: (index: number) => void;
  onFollowUp?: (prompt: string) => void;
  onSelectionExplain?: (quote: string) => void;
  onSelectionQuote?: (quote: string) => void;
  onSelectionPractice?: (quote: string) => void;
  onSelectionSaveNote?: (quote: string) => void;
  onRetry: (index: number, retryFailed?: boolean) => void;
  renderArtifact: (artifact: ChatArtifact) => React.ReactNode;
  onOpenReference: (reference: Reference) => void;
  onOpenSources: (attribution: Attribution) => void;
}) {
  const preparePractice = useStable(onPreparePractice);
  const followUpStable = useStable((prompt: string) => {
    onFollowUp?.(prompt);
  });
  const retry = useStable(onRetry);
  const openReference = useStable(onOpenReference);
  const openSources = useStable(onOpenSources);
  const containerRef = useRef<HTMLDivElement>(null);
  const hasSelectionHandlers = Boolean(
    onSelectionExplain || onSelectionQuote || onSelectionPractice || onSelectionSaveNote,
  );
  const { selection, clearSelection, captureNow } = useTextSelection(containerRef, {
    enabled: !sending && hasSelectionHandlers,
    matchSelector: '[data-selectable-answer="true"]',
  });

  const selectionActions = useMemo<SelectionToolbarAction[]>(() => {
    const quote = selection.quote;
    if (!quote) return [];
    const actions: SelectionToolbarAction[] = [];
    if (onSelectionExplain) {
      actions.push({
        id: "explain",
        label: "解释这段",
        icon: <Sparkles size={13} />,
        primary: true,
        onClick: () => {
          onSelectionExplain(quote);
          clearSelection();
        },
      });
    }
    if (onSelectionQuote) {
      actions.push({
        id: "quote",
        label: "引用追问",
        icon: <MessageSquareText size={13} />,
        onClick: () => {
          onSelectionQuote(quote);
          clearSelection();
        },
      });
    }
    if (onSelectionPractice) {
      actions.push({
        id: "practice",
        label: "基于此出题",
        icon: <BookOpen size={13} />,
        onClick: () => {
          onSelectionPractice(quote);
          clearSelection();
        },
      });
    }
    if (onSelectionSaveNote) {
      actions.push({
        id: "save-note",
        label: "存为知识",
        icon: <BookmarkPlus size={13} />,
        onClick: () => {
          onSelectionSaveNote(quote);
          clearSelection();
        },
      });
    }
    return actions;
  }, [clearSelection, onSelectionExplain, onSelectionPractice, onSelectionQuote, onSelectionSaveNote, selection.quote]);

  const lastIndex = messages.length - 1;
  const stableFollowUpProp = onFollowUp ? followUpStable : undefined;

  return (
    <div className="conversation" ref={containerRef} onMouseUp={captureNow}>
      {messages.map((message, index) => {
        const isLast = index === lastIndex;
        return message.role === "user"
          ? <MemoUserMessage key={index} message={message} onOpenReference={openReference} />
          : <MemoAssistantMessage
              key={index}
              message={message}
              index={index}
              isLatest={isLast}
              assistantName={assistantName}
              // 过程状态只属于正在生成的那一条；给历史消息传固定值，memo 才不会被流式状态打穿。
              status={isLast ? status : null}
              brandState={isLast ? brandState : "ready"}
              sending={sending}
              error={isLast || message.failed ? error : ""}
              onPreparePractice={preparePractice}
              onFollowUp={stableFollowUpProp}
              onRetry={retry}
              renderArtifact={renderArtifact}
              onOpenSources={openSources}
            />;
      })}
      {truncated && !truncated.continuing && (
        <div className="answer-truncated" role="status">
          <span>这次回答被输出长度上限截断了，没有写完。</span>
          <button className="quiet-button" disabled={sending} onClick={onContinue}>接着写</button>
        </div>
      )}
      {status && !messages.at(-1)?.pending && <BobodanProcess state={brandState} detail={status} />}
      {selection.quote && selectionActions.length > 0 && (
        <SelectionActionBar
          quote={selection.quote}
          anchor={selection.anchor}
          actions={selectionActions}
          onClose={clearSelection}
        />
      )}
    </div>
  );
}
