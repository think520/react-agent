import { useState, type ButtonHTMLAttributes, type ReactNode, type SyntheticEvent } from "react";
import { ExternalLink, FileText, LoaderCircle, SearchX } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import type { Attribution, SourceRef } from "../types";

export function IconButton({ label, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <button className={`icon-button ${className}`} aria-label={label} title={label} {...props} />;
}

export function LoadingState({ label = "正在整理…" }: { label?: string }) {
  return (
    <div className="state-line" role="status">
      <LoaderCircle className="spin" size={17} />
      <span>{label}</span>
    </div>
  );
}

export type BrandState = "ready" | "thinking" | "reading" | "writing" | "listening" | "resting";

export function BrandIllustration({ state, size = 72, alt = "" }: { state: BrandState; size?: number; alt?: string }) {
  return <img className="brand-illustration" src={`/assets/brand/states/bobodan-state-${state}.webp`} width={size} height={size} alt={alt} />;
}

export function ErrorNotice({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="error-notice" role="alert">
      <img className="brand-expression" src="/assets/brand/expressions/bobodan-expression-curious.webp" width="38" height="38" alt="" />
      <div><strong>没有顺利完成</strong><p>{message}</p></div>
      {action}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  compact = false,
  state,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  compact?: boolean;
  state?: BrandState;
}) {
  return (
    <div className={`empty-state ${compact ? "compact" : ""}`}>
      {state ? <BrandIllustration state={state} size={compact ? 62 : 92} /> : <SearchX size={22} />}
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}

const attributionLabels = {
  local: "本地资料",
  local_extension: "本地扩展",
  web: "网页来源",
  ai: "AI 补充",
  unverified: "待核实",
};

interface WebSourceDetail {
  final_url: string;
  title: string;
  domain: string;
  excerpt: string;
  accessed_at: string;
  reader: "direct" | "jina";
}

function WebSourceBadge({ source, label }: { source: SourceRef; label: string }) {
  const [detail, setDetail] = useState<WebSourceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const metadata = [
    source.domain,
    source.accessed_at ? new Date(source.accessed_at).toLocaleString("zh-CN") : "",
    source.reader === "jina" ? "Jina Reader 后备" : source.reader === "direct" ? "直接读取" : "",
  ].filter(Boolean).join(" · ");

  async function loadDetail(event: SyntheticEvent<HTMLDetailsElement>) {
    if (!event.currentTarget.open || detail || loading || !source.snapshot_id) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.webSource(source.snapshot_id);
      setDetail(result.source as unknown as WebSourceDetail);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "暂时无法读取证据快照。" );
    } finally {
      setLoading(false);
    }
  }

  return <details className="web-source-detail" onToggle={(event) => void loadDetail(event)}>
    <summary className="source-chip web" title={metadata}>
      <ExternalLink size={14} /><span>{label} · {source.title}</span>
    </summary>
    <section>
      <header><strong>{detail?.title || source.title}</strong><small>{metadata}</small></header>
      {loading ? <p>正在读取当时保存的引用片段…</p> : error ? <p>{error}</p> : <blockquote>{detail?.excerpt || "暂无可显示的引用片段。"}</blockquote>}
      {(detail?.final_url || source.url) && <a href={detail?.final_url || source.url || "#"} target="_blank" rel="noreferrer">打开原网页<ExternalLink size={13} /></a>}
    </section>
  </details>;
}

export function AttributionBadges({ attribution }: { attribution?: Attribution }) {
  if (!attribution) return null;
  const sources = attribution.sources.slice(0, 2);
  return (
    <div className="source-row" aria-label="回答来源">
      {sources.length ? sources.map((source) => {
        const location = source.heading || (source.page ? `第 ${source.page} 页` : source.slide ? `第 ${source.slide} 页` : "");
        const sourceLabel = source.wiki_type === "note" ? "个人笔记" : source.collection === "wiki" ? "Wiki" : attributionLabels[attribution.kind];
        const sourceDetail = location;
        const content = <>{source.source_type === "web" ? <ExternalLink size={14} /> : <FileText size={14} />}<span>{sourceLabel} · {source.title}</span>{location && <small>{location}</small>}</>;
        if (source.source_type === "web" && source.snapshot_id) return <WebSourceBadge source={source} label={sourceLabel} key={source.source_id} />;
        if (source.url) return <a className={`source-chip ${attribution.kind}`} href={source.url} target="_blank" rel="noreferrer" title={sourceDetail} key={source.source_id}>{content}</a>;
        if (source.document_id) {
          const target = `/library?collection=${source.collection === "wiki" ? "wiki" : "material"}&document=${encodeURIComponent(source.document_id)}${source.chunk_id ? `&chunk=${encodeURIComponent(source.chunk_id)}` : ""}`;
          return <Link className={`source-chip ${attribution.kind}`} title={`打开资料${location ? ` · ${location}` : ""}`} to={target} key={source.source_id}>{content}</Link>;
        }
        return <span className={`source-chip ${attribution.kind}`} title={location} key={source.source_id}>{content}</span>;
      }) : <span className={`source-chip ${attribution.kind}`}>{attributionLabels[attribution.kind]}</span>}
      {attribution.sources.length > 2 && <span className="source-more">+{attribution.sources.length - 2}</span>}
    </div>
  );
}

export function formatRelativeDate(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export function formatSessionTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export function textValue(record: Record<string, unknown>, keys: string[], fallback: string) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return fallback;
}
