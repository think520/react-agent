import { AlertTriangle, Check, FilePlus2, GitMerge, MinusCircle, RefreshCw, Undo2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { WikiChangeKind, WikiPlan } from "../types";
import { IconButton } from "./common";

const changeMeta: Record<WikiChangeKind, { label: string; icon: typeof FilePlus2 }> = {
  add: { label: "新增", icon: FilePlus2 },
  update: { label: "更新", icon: RefreshCw },
  merge: { label: "合并", icon: GitMerge },
  conflict: { label: "冲突", icon: AlertTriangle },
  skip: { label: "跳过", icon: MinusCircle },
};

const pageTypeLabels: Record<WikiPlan["changes"][number]["page_type"], string> = {
  wiki_source: "资料摘要",
  wiki_entity: "实体页",
  wiki_concept: "概念页",
  wiki_analysis: "综合分析",
  wiki_question: "问题与发现",
};

export function WikiPlanCard({
  plan,
  busy = false,
  onApply,
  onClose,
  onUndo,
}: {
  plan: WikiPlan;
  busy?: boolean;
  onApply?: () => void;
  onClose?: () => void;
  onUndo?: () => void;
}) {
  const applicable = plan.summary.add + plan.summary.update + plan.summary.merge;
  return (
    <section className={`wiki-plan-card ${plan.status}`} aria-label="Wiki 整理计划">
      <header className="wiki-plan-header">
        <div>
          <span>{plan.status === "applied" ? "Wiki Updated" : "Wiki Plan"}</span>
          <h3>{plan.status === "applied" ? "Wiki 已按计划更新" : "先审查这份整理计划"}</h3>
          <p>{plan.scope.documents.join("、") || "当前学习资料"}</p>
        </div>
        {onClose && <IconButton label="关闭 Wiki 计划" onClick={onClose}><X size={17} /></IconButton>}
      </header>

      <div className="wiki-plan-summary">
        {(Object.keys(changeMeta) as WikiChangeKind[]).map((kind) => {
          const Icon = changeMeta[kind].icon;
          return <span className={kind} key={kind}><Icon size={14} /><strong>{plan.summary[kind]}</strong>{changeMeta[kind].label}</span>;
        })}
      </div>

      {plan.summary.conflict > 0 && (
        <div className="wiki-plan-warning"><AlertTriangle size={16} />同名用户页面不会被覆盖，冲突项会保留原样。</div>
      )}
      {(plan.staging?.length || 0) > 0 && (
        <div className="wiki-plan-warning"><AlertTriangle size={16} />有 {plan.staging!.length} 个页面未通过写入校验，已放入隔离区。请查看错误并重新生成计划。</div>
      )}

      <div className="wiki-plan-changes">
        {plan.changes.map((change) => {
          const Icon = changeMeta[change.kind].icon;
          return (
            <details className={`wiki-plan-change ${change.kind}`} key={change.change_id}>
              <summary>
                <span className="wiki-change-icon"><Icon size={15} /></span>
                <span><strong>{change.title}</strong><small>{pageTypeLabels[change.page_type]} · {change.source_count} 个原文位置</small></span>
                <i>{changeMeta[change.kind].label}</i>
              </summary>
              <div className="wiki-change-preview">
                {change.summary && <p className="wiki-change-summary">{change.summary}</p>}
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{change.content}</ReactMarkdown>
              </div>
            </details>
          );
        })}
      </div>

      <footer className="wiki-plan-actions">
        <span>{plan.status === "planned" ? `确认后写入 ${applicable} 个页面` : `已写入 ${plan.written?.length || applicable} 个页面`}</span>
        <div>
          {plan.status === "applied" && onUndo && <button className="quiet-button" disabled={busy} onClick={onUndo}><Undo2 size={15} />撤销本轮</button>}
          {plan.status === "planned" && onApply && <button className="primary-button" disabled={busy || applicable === 0 || Boolean(plan.staging?.length)} onClick={onApply}><Check size={16} />{busy ? "正在写入" : "确认并生成"}</button>}
        </div>
      </footer>
    </section>
  );
}
