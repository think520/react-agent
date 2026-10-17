import { FileText, MessageCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import { BobodanProcess, PersonalizationChip, RunSummary } from "../../pages/chat/chatPrimitives";
import type { Attribution, ChatArtifact, ChatMessage, RunSummaryArtifact } from "../../types";
import { BlockErrorBoundary } from "../../ui";
import { AttributionBadges } from "../common";
import { ProcessFoldBlock } from "../ProcessFoldBlock";
import { AnswerActions, AnswerFailure } from "./ChatActions";

type ChatReference = NonNullable<ChatMessage["references"]>[number];

/** Chat 的 Message 层（W-F7）：一条消息怎么渲染，只决定这里。 */
export function UserMessage({ message, onOpenReference }: {
  message: ChatMessage;
  onOpenReference: (reference: ChatReference) => void;
}) {
  return <div className="user-message-wrap">
    <div className="user-message">{message.content}</div>
    {message.references?.length ? <div className="message-references">{message.references.map((reference) => <button type="button" key={reference.type + ":" + reference.id} onClick={() => onOpenReference(reference)}>{reference.type === "document" ? <FileText size={12} /> : <MessageCircle size={12} />}<span>{reference.title}</span><small>{reference.type === "document" ? reference.collection === "wiki" ? "Wiki" : "资料" : "会话"}</small></button>)}</div> : null}
  </div>;
}

export function AssistantMessage({ message, index, assistantName, status, brandState, sending, error, onPreparePractice, onRetry, renderArtifact, onOpenSources }: {
  message: ChatMessage;
  index: number;
  assistantName: string;
  status: string | null;
  brandState: ProcessBrandState;
  sending: boolean;
  error: string;
  onPreparePractice: (index: number) => void;
  onRetry: (index: number, retryFailed?: boolean) => void;
  renderArtifact: (artifact: ChatArtifact) => React.ReactNode;
  onOpenSources: (attribution: Attribution) => void;
}) {
  return <article className={"assistant-message " + (message.failed ? "failed" : "")}>
    <div className="assistant-heading"><img src={message.failed ? "/assets/brand/expressions/bobodan-expression-curious.webp" : "/assets/brand/expressions/bobodan-expression-neutral.webp"} alt="" /><span>{assistantName}</span></div>
    {message.pending && status && <BobodanProcess state={brandState} detail={status} />}
    {!message.pending && <RunSummary artifact={message.artifacts?.find((artifact): artifact is RunSummaryArtifact => artifact.type === "run_summary")} />}
    {!message.pending && message.process?.length ? <ProcessFoldBlock steps={message.process} /> : null}
    <BlockErrorBoundary><div className="answer-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (message.pending ? "正在整理回答…" : message.failed ? "回答没有完成。" : "本轮没有生成可显示的内容。")}</ReactMarkdown></div></BlockErrorBoundary>
    {message.artifacts?.map((artifact) => <BlockErrorBoundary key={artifact.artifact_id}>{renderArtifact(artifact)}</BlockErrorBoundary>)}
    <AttributionBadges attribution={message.attribution} onOpenSources={onOpenSources} />
    <PersonalizationChip references={message.personalization} />
    {!message.pending && !message.failed && message.content && !message.artifacts?.some((artifact) => artifact.type === "practice_ready") && <AnswerActions onPreparePractice={() => onPreparePractice(index)} />}
    {message.failed && <AnswerFailure message={error || "AI 连接暂时不可用，请稍后重试。"} disabled={sending} onRetry={() => onRetry(index, true)} />}
    {message.stopped && <AnswerFailure message="回答已停止，只生成了部分内容。" disabled={sending} onRetry={() => onRetry(index)} />}
  </article>;
}
