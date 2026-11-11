import { memo, useCallback, useLayoutEffect, useRef } from "react";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import { BobodanProcess } from "../../pages/chat/chatPrimitives";
import type { Attribution, ChatArtifact, ChatMessage } from "../../types";
import { AssistantMessage, UserMessage } from "./ChatMessage";

type Reference = NonNullable<ChatMessage["references"]>[number];

/**
 * 事件回调稳定化：ChatPage 每次渲染都会给出新的函数，这里用 ref 转一道（只用于事件里调用的回调），
 * 让下面的 memo 消息只在**自己的数据**变化时重渲染（2026-11-11 审查：流式输出时
 * 每 33ms 一次刷新，以前会把所有历史消息的 Markdown 从头解析一遍）。
 */
function useStable<A extends unknown[], R>(fn: (...args: A) => R): (...args: A) => R {
  const ref = useRef(fn);
  // 在提交阶段更新（渲染期写 ref 违反 react-hooks/refs）；回调只会在事件里被调用，届时已是最新。
  useLayoutEffect(() => { ref.current = fn; });
  return useCallback((...args: A) => ref.current(...args), []);
}

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

/** Chat 的 Transcript 层（W-F7）：消息列表 + 截断提示 + 收尾状态。 */
export function ChatTranscript({ messages, status, brandState, assistantName, sending, error, truncated, onContinue, onPreparePractice, onRetry, renderArtifact, onOpenReference, onOpenSources }: {
  messages: ChatMessage[];
  status: string | null;
  brandState: ProcessBrandState;
  assistantName: string;
  sending: boolean;
  error: string;
  truncated: { continuing: boolean } | null;
  onContinue: () => void;
  onPreparePractice: (index: number) => void;
  onRetry: (index: number, retryFailed?: boolean) => void;
  renderArtifact: (artifact: ChatArtifact) => React.ReactNode;
  onOpenReference: (reference: Reference) => void;
  onOpenSources: (attribution: Attribution) => void;
}) {
  const preparePractice = useStable(onPreparePractice);
  const retry = useStable(onRetry);
  const openReference = useStable(onOpenReference);
  const openSources = useStable(onOpenSources);
  const lastIndex = messages.length - 1;

  return <div className="conversation">
    {messages.map((message, index) => {
      const isLast = index === lastIndex;
      return message.role === "user"
        ? <MemoUserMessage key={index} message={message} onOpenReference={openReference} />
        : <MemoAssistantMessage
            key={index}
            message={message}
            index={index}
            assistantName={assistantName}
            // 过程状态只属于正在生成的那一条；给历史消息传固定值，memo 才不会被流式状态打穿。
            status={isLast ? status : null}
            brandState={isLast ? brandState : "ready"}
            sending={sending}
            error={isLast || message.failed ? error : ""}
            onPreparePractice={preparePractice}
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
  </div>;
}
