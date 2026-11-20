import { FileText, MessageCircle } from "lucide-react";
import { memo, useMemo } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import { Link, useLocation } from "react-router-dom";
import remarkGfm from "remark-gfm";
import type { PluggableList } from "unified";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import { remarkCitations, type CitationTarget } from "../../lib/citations";
import { readerLocation } from "../../lib/documentLinks";
import { BobodanProcess, PersonalizationChip, RunSummary } from "../../pages/chat/chatPrimitives";
import { useUiStore } from "../../stores/uiStore";
import type { Attribution, ChatArtifact, ChatMessage, KnowledgeContextArtifact, RunSummaryArtifact } from "../../types";
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
  const images = (message.attachments || []).filter((item) => item.type === "image" && item.data_url);
  const files = (message.attachments || []).filter((item) => item.type === "file");
  return <div className="user-message-wrap">
    {images.length > 0 && (
      <div className="message-images">
        {images.map((item, idx) => (
          <a key={`${item.name}:${idx}`} href={item.data_url} target="_blank" rel="noreferrer" title={item.name}>
            <img src={item.data_url} alt={item.name} />
          </a>
        ))}
      </div>
    )}
    {message.content && <div className="user-message">{message.content}</div>}
    {(files.length > 0 || Boolean(message.references?.length)) && (
      <div className="message-references">
        {files.map((item, idx) => (
          <span className="message-file-chip" key={`${item.name}:${idx}`} title={item.truncated ? `${item.name}（已截取前段正文）` : item.name}>
            <FileText size={12} />
            <span>{item.name}</span>
            {item.char_count ? <small>{item.char_count >= 1000 ? `${(item.char_count / 1000).toFixed(1)}k 字` : `${item.char_count} 字`}</small> : null}
          </span>
        ))}
        {message.references?.map((reference) => <button type="button" key={reference.type + ":" + reference.id} onClick={() => onOpenReference(reference)}>{reference.type === "document" ? <FileText size={12} /> : <MessageCircle size={12} />}<span>{reference.title}</span><small>{reference.type === "document" ? reference.collection === "wiki" ? "Wiki" : "资料" : "会话"}</small></button>)}
      </div>
    )}
  </div>;
}

/** 合并单条消息内多次概念检索产生的重复 knowledge_context 卡片，并过滤空卡片。 */
export function normalizeMessageArtifacts(artifacts: ChatArtifact[] | undefined): ChatArtifact[] {
  if (!artifacts?.length) return [];
  const result: ChatArtifact[] = [];
  let mergedIndex = -1;
  let mergedContext: KnowledgeContextArtifact | null = null;
  const mergedRelationships: NonNullable<KnowledgeContextArtifact["context"]["relationships"]> = [];
  const seenConcepts = new Set<string>();
  const seenRels = new Set<string>();

  for (const artifact of artifacts) {
    if (artifact.type !== "knowledge_context") {
      result.push(artifact);
      continue;
    }
    const ctx = artifact.context;
    const concepts = ctx?.concepts || [];
    const relationships = ctx?.relationships || [];
    if (!concepts.length && !relationships.length && !ctx?.root) continue;

    if (!mergedContext) {
      mergedContext = {
        ...artifact,
        context: {
          ...ctx,
          concepts: [],
          relationships: mergedRelationships,
        },
      };
      mergedIndex = result.length;
      result.push(mergedContext);
    } else if (!mergedContext.context.root && ctx.root) {
      mergedContext.context.root = ctx.root;
    }

    for (const concept of concepts) {
      if (!seenConcepts.has(concept.concept_id)) {
        seenConcepts.add(concept.concept_id);
        mergedContext.context.concepts.push(concept);
      }
    }
    for (const relation of relationships) {
      const key = relation.rel_id || `${relation.from_id}|${relation.rel_type}|${relation.to_id}`;
      if (!seenRels.has(key)) {
        seenRels.add(key);
        mergedRelationships.push(relation);
      }
    }
  }

  if (mergedContext && mergedIndex >= 0) {
    const hasContent = mergedRelationships.length > 0 || mergedContext.context.concepts.length > 0;
    if (!hasContent) result.splice(mergedIndex, 1);
  }
  return result;
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
  const visibleArtifacts = useMemo(() => normalizeMessageArtifacts(message.artifacts), [message.artifacts]);
  return <article className={"assistant-message " + (message.failed ? "failed" : "")}>
    <div className="assistant-heading"><img src={message.failed ? "/assets/brand/expressions/bobodan-expression-curious.webp" : "/assets/brand/expressions/bobodan-expression-neutral.webp"} alt="" /><span>{assistantName}</span></div>
    {message.pending && status && <BobodanProcess state={brandState} detail={status} />}
    {!message.pending && <RunSummary artifact={message.artifacts?.find((artifact): artifact is RunSummaryArtifact => artifact.type === "run_summary")} />}
    {!message.pending && message.process?.length ? <ProcessFoldBlock steps={message.process} /> : null}
    <BlockErrorBoundary><div className="answer-prose"><AnswerMarkdown attribution={message.attribution} content={message.content || (message.pending ? "正在整理回答…" : message.failed ? "回答没有完成。" : "本轮没有生成可显示的内容。")} /></div></BlockErrorBoundary>
    {visibleArtifacts.map((artifact) => <BlockErrorBoundary key={artifact.artifact_id}>{renderArtifact(artifact)}</BlockErrorBoundary>)}
    <AttributionBadges attribution={message.attribution} onOpenSources={onOpenSources} />
    <PersonalizationChip references={message.personalization} />
    {!message.pending && !message.failed && message.content && !message.artifacts?.some((artifact) => artifact.type === "practice_ready") && <AnswerActions onPreparePractice={() => onPreparePractice(index)} />}
    {message.failed && <AnswerFailure message={error || "AI 连接暂时不可用，请稍后重试。"} disabled={sending} onRetry={() => onRetry(index, true)} />}
    {message.stopped && <AnswerFailure message="回答已停止，只生成了部分内容。" disabled={sending} onRetry={() => onRetry(index)} />}
  </article>;
}

/** 正文 Markdown：把 [Sxxxxxx] 引用标签换成可点的序号，点了落到原文片段或网页快照。 */
const answerUrlTransform = (url: string, key: string) => (key === "href" && url.startsWith("cite:") ? url : defaultUrlTransform(url));

const AnswerMarkdown = memo(function AnswerMarkdown({ content, attribution }: { content: string; attribution?: Attribution }) {
  const targets = useMemo(() => new Map<string, CitationTarget>(), []);
  const remarkPlugins = useMemo<PluggableList>(() => [
    remarkGfm,
    [remarkCitations, { sources: attribution?.sources, targets }],
  ], [attribution?.sources, targets]);
  const components = useMemo<Components>(() => ({
    a: ({ href, children }) => {
      if (href?.startsWith("cite:")) {
        const target = targets.get(href.slice(5));
        return target ? <CitationMark target={target} /> : <>{children}</>;
      }
      return <a href={href}>{children}</a>;
    },
  }), [targets]);
  return <ReactMarkdown remarkPlugins={remarkPlugins} urlTransform={answerUrlTransform} components={components}>
    {content}
  </ReactMarkdown>;
});

function CitationMark({ target }: { target: CitationTarget }) {
  const routerLocation = useLocation();
  const lastChatSessionTitle = useUiStore((state) => state.lastChatSessionTitle);
  const { source, index } = target;
  const location = source.heading || (source.page ? `第 ${source.page} 页` : source.slide ? `第 ${source.slide} 页` : "");
  const title = source.title + (location ? " · " + location : "");
  const label = `来源 ${index}：${title}`;
  const reader = source.source_type === "local" ? readerLocation(source) : null;
  const returnState = routerLocation.pathname.startsWith("/chat/")
    ? {
        returnTo: routerLocation.pathname + routerLocation.search,
        returnLabel: lastChatSessionTitle ? `返回对话 · ${lastChatSessionTitle}` : "返回刚才的对话",
      }
    : undefined;
  if (reader) return <Link className="citation-mark" to={reader} state={returnState} title={title} aria-label={label}>{index}</Link>;
  if (source.url) return <a className="citation-mark" href={source.url} target="_blank" rel="noreferrer" title={title} aria-label={label}>{index}</a>;
  return <span className="citation-mark" title={title} aria-label={label}>{index}</span>;
}
