import type { ProcessBrandState } from "../../hooks/useChatStream";
import { BobodanProcess } from "../../pages/chat/chatPrimitives";
import type { Attribution, ChatArtifact, ChatMessage } from "../../types";
import { AssistantMessage, UserMessage } from "./ChatMessage";

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
  onOpenReference: (reference: NonNullable<ChatMessage["references"]>[number]) => void;
  onOpenSources: (attribution: Attribution) => void;
}) {
  return <div className="conversation">
    {messages.map((message, index) => message.role === "user"
      ? <UserMessage key={index} message={message} onOpenReference={onOpenReference} />
      : <AssistantMessage
          key={index}
          message={message}
          index={index}
          assistantName={assistantName}
          status={status}
          brandState={brandState}
          sending={sending}
          error={error}
          onPreparePractice={onPreparePractice}
          onRetry={onRetry}
          renderArtifact={renderArtifact}
          onOpenSources={onOpenSources}
        />)}
    {truncated && !truncated.continuing && (
      <div className="answer-truncated" role="status">
        <span>这次回答被输出长度上限截断了，没有写完。</span>
        <button className="quiet-button" disabled={sending} onClick={onContinue}>接着写</button>
      </div>
    )}
    {status && !messages.at(-1)?.pending && <BobodanProcess state={brandState} detail={status} />}
  </div>;
}
