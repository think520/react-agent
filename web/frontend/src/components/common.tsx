import type { ButtonHTMLAttributes, ReactNode } from "react";
import { FileText, LoaderCircle, SearchX } from "lucide-react";
import { Link } from "react-router-dom";

import type { Attribution } from "../types";

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

export function AttributionBadges({ attribution }: { attribution?: Attribution }) {
  if (!attribution) return null;
  const sources = attribution.sources.slice(0, 2);
  return (
    <div className="source-row" aria-label="回答来源">
      {sources.length ? sources.map((source) => {
        const location = source.heading || (source.page ? `第 ${source.page} 页` : source.slide ? `第 ${source.slide} 页` : "");
        const sourceLabel = source.collection === "wiki" ? "Wiki" : attributionLabels[attribution.kind];
        const content = <><FileText size={14} /><span>{sourceLabel} · {source.title}</span>{location && <small>{location}</small>}</>;
        if (source.url) return <a className={`source-chip ${attribution.kind}`} href={source.url} target="_blank" rel="noreferrer" key={source.source_id}>{content}</a>;
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
