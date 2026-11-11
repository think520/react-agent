import { FileText, MessageCircle } from "lucide-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import { citationTargets, linkCitations, type CitationTarget } from "../../lib/citations";
import { readerLocation } from "../../lib/documentLinks";
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
    <BlockErrorBoundary><div className="answer-prose"><AnswerMarkdown attribution={message.attribution} content={message.content || (message.pending ? "正在整理回答…" : message.failed ? "回答没有完成。" : "本轮没有生成可显示的内容。")} /></div></BlockErrorBoundary>
    {message.artifacts?.map((artifact) => <BlockErrorBoundary key={artifact.artifact_id}>{renderArtifact(artifact)}</BlockErrorBoundary>)}
    <AttributionBadges attribution={message.attribution} onOpenSources={onOpenSources} />
    <PersonalizationChip references={message.personalization} />
    {!message.pending && !message.failed && message.content && !message.artifacts?.some((artifact) => artifact.type === "practice_ready") && <AnswerActions onPreparePractice={() => onPreparePractice(index)} />}
    {message.failed && <AnswerFailure message={error || "AI 连接暂时不可用，请稍后重试。"} disabled={sending} onRetry={() => onRetry(index, true)} />}
    {message.stopped && <AnswerFailure message="回答已停止，只生成了部分内容。" disabled={sending} onRetry={() => onRetry(index)} />}
  </article>;
}

/** 正文 Markdown：把 [Sxxxxxx] 引用标签换成可点的序号，点了落到原文片段或网页快照。 */
function AnswerMarkdown({ content, attribution }: { content: string; attribution?: Attribution }) {
  const targets = citationTargets(content, attribution?.sources);
  return <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    urlTransform={(url, key) => (key === "href" && url.startsWith("cite:") ? url : defaultUrlTransform(url))}
    components={{
      a: ({ href, children }) => {
        if (href?.startsWith("cite:")) {
          const target = targets.get(href.slice(5));
          return target ? <CitationMark target={target} /> : <>{children}</>;
        }
        return <a href={href}>{children}</a>;
      },
    }}
  >{linkCitations(content, targets)}</ReactMarkdown>;
}

function CitationMark({ target }: { target: CitationTarget }) {
  const { source, index } = target;
  const location = source.heading || (source.page ? `第 ${source.page} 页` : source.slide ? `第 ${source.slide} 页` : "");
  const title = source.title + (location ? " · " + location : "");
  const label = `来源 ${index}：${title}`;
  const reader = source.source_type === "local" ? readerLocation(source) : null;
  if (reader) return <Link className="citation-mark" to={reader} title={title} aria-label={label}>{index}</Link>;
  if (source.url) return <a className="citation-mark" href={source.url} target="_blank" rel="noreferrer" title={title} aria-label={label}>{index}</a>;
  return <span className="citation-mark" title={title} aria-label={label}>{index}</span>;
}
