import { AlertTriangle, Check, FilePlus2, GitMerge, MinusCircle, RefreshCw, ShieldCheck, Undo2, X } from "lucide-react";
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

function validationMessage(error: string) {
  const messages: Record<string, string> = {
    "incoming body is unexpectedly shorter than the existing page": "新草稿比现有页面短，直接覆盖可能丢失已经整理好的内容。",
    "unsupported page type": "页面类型不符合当前 Wiki 规则。",
    "invalid Wiki target path": "页面保存位置不符合当前资料库规则。",
    "page type does not match target directory": "页面类型与保存目录不一致。",
    "application-managed structural files cannot be written by a plan": "这是由 Bobodan 维护的结构文件，计划不能直接修改。",
    "page title is required": "页面缺少标题。",
    "page body is required": "页面没有可写入的正文。",
    "at least one source reference is required": "页面缺少可追溯的原始资料引用。",
    "source references must contain document_id and source": "页面的原始资料引用不完整。",
  };
  return messages[error] || "页面没有通过安全写入检查。";
}

function stagedChanges(plan: WikiPlan) {
  const grouped = new Map<string, { change_id: string; errors: string[] }>();
  for (const item of plan.staging || []) {
    const existing = grouped.get(item.change_id);
    if (existing) existing.errors = Array.from(new Set([...existing.errors, ...item.errors]));
    else grouped.set(item.change_id, { change_id: item.change_id, errors: Array.from(new Set(item.errors)) });
  }
  return Array.from(grouped.values());
}

export function WikiPlanCard({
  plan,
  busy = false,
  onApply,
  onClose,
  onKeepExisting,
  onRegenerate,
  onUndo,
}: {
  plan: WikiPlan;
  busy?: boolean;
  onApply?: () => void;
  onClose?: () => void;
  onKeepExisting?: () => void;
  onRegenerate?: () => void;
  onUndo?: () => void;
}) {
  const staged = stagedChanges(plan);
  const applicable = plan.summary.add + plan.summary.update + plan.summary.merge;
  const safePageCount = Math.max(0, applicable - staged.length);
  if (plan.status === "replaced") {
    return <section className="wiki-plan-card replaced" aria-label="已替换的 Wiki 整理计划">
      <header className="wiki-plan-header"><div><span>Wiki Plan</span><h3>这份计划已被新版替换</h3><p>Bobodan 已根据校验问题重新规划，请继续查看下方的新计划。</p></div></header>
    </section>;
  }
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
      {staged.length > 0 && <section className="wiki-plan-recovery" aria-label="Wiki 计划需要处理">
        <header><span><AlertTriangle size={17} /><strong>{staged.length} 个页面需要你选择处理方式</strong></span><p>Bobodan 已暂停整次写入，现有 Wiki 没有被修改。你可以保留原页面并生成其余内容，也可以让 Bobodan 补全后重新规划。</p></header>
        <div className="wiki-plan-issues">{staged.map((item) => {
          const change = plan.changes.find((candidate) => candidate.change_id === item.change_id);
          return <details key={item.change_id}><summary><span><strong>{change?.title || "未命名页面"}</strong><small>{item.errors.map(validationMessage).join(" ")}</small></span><i>查看原因</i></summary><div>{item.errors.map((error) => <code key={error}>{error}</code>)}</div></details>;
        })}</div>
        <footer><div><ShieldCheck size={16} /><span><strong>推荐</strong><small>保留现有页面，避免丢失内容，并继续生成其余 {safePageCount} 个页面。</small></span></div><div>{onRegenerate && <button className="quiet-button" disabled={busy} onClick={onRegenerate}><RefreshCw size={15} />{busy ? "正在重新规划" : "补全后重新规划"}</button>}{onKeepExisting && <button className="primary-button" disabled={busy || safePageCount === 0} onClick={onKeepExisting}><ShieldCheck size={15} />{busy ? "正在继续生成" : `保留原页，生成其余 ${safePageCount} 页`}</button>}</div></footer>
      </section>}

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
        <span>{staged.length ? "尚未写入，请先选择上方处理方式" : plan.status === "planned" ? `确认后写入 ${applicable} 个页面` : `已写入 ${plan.written?.length || applicable} 个页面`}</span>
        <div>
          {plan.status === "applied" && onUndo && <button className="quiet-button" disabled={busy} onClick={onUndo}><Undo2 size={15} />撤销本轮</button>}
          {plan.status === "planned" && !staged.length && onApply && <button className="primary-button" disabled={busy || applicable === 0} onClick={onApply}><Check size={16} />{busy ? "正在写入" : "确认并生成"}</button>}
        </div>
      </footer>
    </section>
  );
}
