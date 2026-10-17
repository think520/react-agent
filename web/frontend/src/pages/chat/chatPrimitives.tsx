/**
 * Chat 页的纯展示原语与工具函数（2026-10-17 M2 拆分：从 ChatPage.tsx 抽出第 38–147 行，行为不变）。
 * 这里不放状态：只接收 props，或做不依赖 React 的格式转换。
 */
import {} from "../../lib/documentLinks";
import { Fragment } from "react";
import { Brain, Check } from "lucide-react";
import {} from "react-router-dom";

import type {} from "../../components/AppShell";
import { BrandIllustration } from "../../components/common";
import {} from "../../components/WikiPlanCard";
import {} from "../../components/ModelSelect";
import {} from "../../components/DropdownSelect";
import {} from "../../components/artifacts/AskUserCard";
import { RetrievalDegradedNotice } from "../../components/RetrievalDegradedNotice";
import {} from "../../components/artifacts/KnowledgeContextCard";
import {} from "../../components/artifacts/MemoryConfirmationCard";
import {} from "../../components/artifacts/PracticeReadyCard";
import {} from "../../components/artifacts/SettingsChangeCard";
import {} from "../../components/artifacts/WebCandidatesCard";
import {} from "../../components/artifacts/WebConsentCard";
import {} from "../../components/artifacts/WebEvidenceCard";
import {} from "../../components/artifacts/WikiFocusCard";
import {} from "../../components/artifacts/WikiResultCard";
import {} from "../../components/ProcessFoldBlock";
import { type ProcessBrandState } from "../../hooks/useChatStream";
import {} from "../../hooks/useStickyBottomScroll";
import {} from "../../ui";
import {} from "../../lib/api";
import {} from "../../lib/commandRouter";
import {} from "../../lib/errors";
import {} from "../../lib/mention";
import {} from "../../lib/settingsIntent";
import { useHandoffStore } from "../../stores/handoffStore";
import {} from "../../stores/noticeStore";
import {} from "../../stores/uiStore";
import type { PersonalizationRef, RunSummaryArtifact } from "../../types";


export interface SlashItem {
  value: string;
  label: string;
  description: string;
  kind: "command" | "skill";
}

export const WEB_COMMANDS: SlashItem[] = [
  { value: "/new", label: "/new", description: "开始新对话", kind: "command" },
  { value: "/library", label: "/library", description: "打开学习资料", kind: "command" },
  { value: "/wiki", label: "/wiki", description: "打开 Wiki 与维护工具", kind: "command" },
  { value: "/wiki plan ", label: "/wiki plan", description: "为当前资料生成 Wiki 整理计划", kind: "command" },
  { value: "/wiki update ", label: "/wiki update", description: "为当前资料拟定 Wiki 增量更新计划", kind: "command" },
  { value: "/wiki generate", label: "/wiki generate", description: "确认并执行当前 Wiki 计划", kind: "command" },
  { value: "/practice", label: "/practice", description: "开始一轮练习", kind: "command" },
  { value: "/review", label: "/review", description: "查看今日复习", kind: "command" },
  { value: "/kb search ", label: "/kb search", description: "只检索本地资料", kind: "command" },
  { value: "/web search ", label: "/web search", description: "确认后搜索公开网页候选", kind: "command" },
  { value: "/learning today", label: "/learning today", description: "整理今日学习任务", kind: "command" },
  { value: "/quiz generate ", label: "/quiz generate", description: "按主题生成 5 道题", kind: "command" },
];

function processTitle(state: ProcessBrandState) {
  if (state === "reading") return "正在查找资料";
  if (state === "writing") return "正在生成内容";
  if (state === "ready") return "本轮已经准备好";
  return "正在理解问题";
}

// State art swaps must not flash empty; warm every phase image once so the
// 160ms opacity transition is the only visible change between phases.
for (const state of ["thinking", "reading", "writing", "ready"] as const) {
  const img = new Image();
  img.src = `/assets/brand/states/bobodan-state-${state}.webp`;
}

export function BobodanProcess({ state, detail }: { state: ProcessBrandState; detail: string }) {
  return <div className={`bobodan-process ${state}`} role="status">
    <BrandIllustration state={state} size={52} />
    <div><strong>{processTitle(state)}</strong><small>{detail}</small><span className="bobodan-process-ink" aria-hidden="true"><i /><i /><i /></span></div>
  </div>;
}

export function PersonalizationChip({ references }: { references?: PersonalizationRef[] }) {
  if (!references?.length) return null;
  return <details className="personalization-chip"><summary><Brain size={13} />个性化依据 <span>{references.length}</span></summary><div>{references.map((reference) => <section key={reference.id}><strong>{reference.title}</strong><p>{reference.content}</p><small>{reference.scope === "global" ? "全局" : "当前资料库"} · {new Date(reference.updated_at).toLocaleDateString("zh-CN")}</small></section>)}</div></details>;
}

function formatDuration(seconds: number) {
  if (seconds < 1) return `${Math.max(1, Math.round(seconds * 1000))}ms`;
  return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
}

const TOOL_LABELS: Record<string, string> = {
  rag_search: "资料检索",
  concept_map_query: "知识地图",
  concept_map_status: "知识地图状态",
  question_generate: "生成练习题",
  quiz_start: "准备练习",
  quiz_submit: "批改答案",
  learning_path: "学习路线",
  learning_progress: "学习进度",
  learning_review: "复习内容",
  request_memory_confirmation: "记忆确认",
  request_web_search: "联网确认",
  web_research: "网页检索",
};

export function RunSummary({ artifact }: { artifact?: RunSummaryArtifact }) {
  if (!artifact) return null;
  const hitCount = artifact.operations.reduce((total, item) => total + (item.hit_count || 0), 0);
  const documentCount = artifact.operations.reduce((total, item) => total + (item.document_count || 0), 0);
  const relationCount = artifact.operations.reduce((total, item) => total + (item.relationship_count || 0), 0);
  const summary = artifact.operations.length
    ? [documentCount ? `${documentCount} 份资料` : "", hitCount ? `${hitCount} 个片段` : "", relationCount ? `${relationCount} 条关系` : ""].filter(Boolean).join(" · ") || `完成 ${artifact.operations.length} 项查询`
    : "直接回答";
  return <details className={`run-summary ${artifact.status}`}>
    <summary><Check size={14} /><strong>{artifact.status === "completed" ? "处理完成" : "处理未完成"}</strong><span>{summary}</span><small>{formatDuration(artifact.total_elapsed)}</small></summary>
    {artifact.operations.length > 0 && <div>{artifact.operations.map((operation, index) => <Fragment key={`${operation.tool_name}:${index}`}><p>
      <span>{TOOL_LABELS[operation.tool_name] || "学习工具"}</span>
      {operation.query && <q>{operation.query}</q>}
      {operation.operation && <code>{operation.operation}</code>}

      {/* P1-22: non-text material cannot be grepped, so an empty result must not
          read as “the material does not say it”. */}
      {operation.tool_name === "rag_search" && !!operation.grep_unreadable && (
        <span className="retrieval-degraded">
          {operation.grep_unreadable_sources?.length
            ? `${operation.grep_unreadable_sources[0]} 等 ${operation.grep_unreadable} 份非文本资料无法原文定位`
            : `${operation.grep_unreadable} 份非文本资料无法原文定位`}
        </span>
      )}
      <small>{operation.status === "completed" ? "完成" : "失败"} · {formatDuration(operation.elapsed || 0)}</small>
    </p>
      {/* W2 降级可见性：说清"为什么是纯文本检索 + 下一步"（<details> 不能嵌在 <p> 里）。 */}
      {operation.tool_name === "rag_search" && operation.semantic_available === false && (
        <RetrievalDegradedNotice reason={operation.semantic_reason} hitCount={operation.hit_count} />
      )}
    </Fragment>)}</div>}
  </details>;
}

export function initialDraft(sessionId: string | undefined, peekOnly = false) {
  const handoff = sessionId
    ? null
    : peekOnly
      ? useHandoffStore.getState().chatDraft
      : useHandoffStore.getState().consumeChatDraft();
  return handoff || localStorage.getItem(`bobodan:draft:${sessionId || "new"}`) || "";
}
