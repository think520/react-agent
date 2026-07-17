import { AlertTriangle, Check, FilePlus2, GitMerge, ListTree, MinusCircle, RefreshCw, ShieldCheck, Undo2, X } from "lucide-react";
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
  split: { label: "待拆分", icon: ListTree },
};

const pageTypeLabels: Record<WikiPlan["changes"][number]["page_type"], string> = {
  wiki_source: "资料摘要",
  wiki_entity: "实体页",
  wiki_concept: "概念页",
  wiki_analysis: "综合分析",
  wiki_question: "问题与发现",
  wiki_note: "个人笔记",
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
  onCancel,
  onUndo,
  onResume,
  onCatalog,
  onContinue,
  onSwitchProvider,
}: {
  plan: WikiPlan;
  busy?: boolean;
  onApply?: () => void;
  onClose?: () => void;
  onKeepExisting?: () => void;
  onRegenerate?: () => void;
  onCancel?: () => void;
  onUndo?: () => void;
  onResume?: () => void;
  onCatalog?: () => void;
  onContinue?: () => void;
  onSwitchProvider?: () => void;
}) {
  const changes = plan.changes || [];
  const persistedSummary = plan.summary as Partial<WikiPlan["summary"]> | undefined;
  const summary = {
    add: persistedSummary?.add ?? 0,
    update: persistedSummary?.update ?? 0,
    merge: persistedSummary?.merge ?? 0,
    conflict: persistedSummary?.conflict ?? 0,
    skip: persistedSummary?.skip ?? 0,
    split: persistedSummary?.split ?? 0,
  };
  const scopeDocuments = plan.scope?.documents || [];
  if (plan.status === "planning") {
    const phaseLabels: Record<string, string> = {
      queued: "正在准备资料范围",
      discovering: "正在分批阅读资料并发现概念",
      drafting: "正在生成小型互链页面",
      cancelling: "正在停止本轮整理",
      paused_budget: "已到达本轮额度上限",
    };
    const detail = plan.phase === "discovering"
      ? `已完成 ${plan.completed_batches || 0} / ${plan.total_batches || 0} 个资料批次`
      : plan.phase === "drafting"
        ? `已生成 ${plan.completed_pages || 0} / ${plan.total_pages || 0} 个页面草稿`
        : `${scopeDocuments.length} 份资料将在后台分批处理`;
    return <section className="wiki-plan-card planning" aria-label="Wiki 正在生成计划">
      <header className="wiki-plan-header"><div><span>Wiki Run</span><h3>{phaseLabels[plan.phase || "queued"] || "正在生成 Wiki 计划"}</h3><p>{detail}</p></div></header>
      <div className="wiki-run-thinking" aria-hidden="true"><i /><i /><i /></div>
      <footer className="wiki-plan-actions"><span>{plan.usage ? `${plan.usage.requests} 次请求 · 输入约 ${plan.usage.input_tokens.toLocaleString()} Token · 缓存复用 ${plan.usage.cache_hits} 次` : "可以切换会话或刷新页面，任务状态会保留。"}</span>{onCancel && <div><button className="quiet-button" disabled={plan.phase === "cancelling"} onClick={onCancel}>{plan.phase === "cancelling" ? "正在停止" : "取消本轮"}</button></div>}</footer>
    </section>;
  }
  if (plan.status === "paused_budget") {
    return <section className="wiki-plan-card replaced" aria-label="Wiki 整理已暂停">
      <header className="wiki-plan-header"><div><span>Wiki Paused</span><h3>已保存当前草稿并暂停</h3><p>{plan.error || "本轮请求或 Token 已达到设定上限。"}</p></div></header>
      <div className="wiki-plan-summary"><span className="add"><strong>{changes.length}</strong>已完成草稿</span><span className="skip"><strong>{plan.remaining_pages || 0}</strong>尚待生成</span></div>
      <footer className="wiki-plan-actions"><span>{plan.usage ? `${plan.usage.requests} 次请求 · 输入约 ${plan.usage.input_tokens.toLocaleString()} Token` : "继续时会复用已完成的精确缓存。"}</span><div>{onCatalog && <button className="quiet-button" onClick={onCatalog}>改用快速建档</button>}{onResume && <button className="primary-button" onClick={onResume}>追加额度并继续</button>}</div></footer>
    </section>;
  }
  if (plan.status === "failed") {
    return <section className="wiki-plan-card replaced" aria-label="Wiki 计划生成失败">
      <header className="wiki-plan-header"><div><span>Wiki Run</span><h3>这轮计划没有生成完成</h3><p>{plan.error || "资料和现有 Wiki 没有被修改，请重新发起整理。"}</p></div>{onClose && <IconButton label="关闭 Wiki 计划" onClick={onClose}><X size={17} /></IconButton>}</header>
      {(onResume || onCatalog || onSwitchProvider) && <footer className="wiki-plan-actions"><span>已完成的精确缓存仍然保留，重试不会重复消耗相同输入。</span><div>{onSwitchProvider && <button className="quiet-button" onClick={onSwitchProvider}>切换模型</button>}{onCatalog && <button className="quiet-button" onClick={onCatalog}>改用快速建档</button>}{onResume && <button className="primary-button" onClick={onResume}>重试本轮</button>}</div></footer>}
    </section>;
  }
  const staged = stagedChanges(plan);
  const applicable = summary.add + summary.update + summary.merge;
  const safePageCount = Math.max(0, applicable - staged.length);
  if (plan.status === "replaced") {
    return <section className="wiki-plan-card replaced" aria-label="已替换的 Wiki 整理计划">
      <header className="wiki-plan-header"><div><span>Wiki Plan</span><h3>这份计划已被新版替换</h3><p>Bobodan 已根据校验问题重新规划，请继续查看下方的新计划。</p></div></header>
    </section>;
  }
  if (plan.status === "cancelled") {
    return <section className="wiki-plan-card replaced" aria-label="已取消的 Wiki 整理计划">
      <header className="wiki-plan-header"><div><span>Wiki Run</span><h3>本轮整理已取消</h3><p>原始资料和现有 Wiki 页面没有被修改；已完成的精确草稿缓存仍然保留。</p></div></header>
      {changes.length > 0 && <div className="wiki-plan-summary"><span className="add"><strong>{changes.length}</strong>已完成草稿</span></div>}
      {changes.length > 0 && <details className="wiki-cancelled-review"><summary>审查已完成内容</summary><div>{changes.map((change) => <article key={change.change_id}><strong>{change.title}</strong><small>{pageTypeLabels[change.page_type]} · {change.source_count} 个原文位置</small><ReactMarkdown remarkPlugins={[remarkGfm]}>{change.content}</ReactMarkdown></article>)}</div></details>}
      {(onResume || onCatalog) && <footer className="wiki-plan-actions"><span>可以稍后继续，也可以改用不调用模型的快速建档。</span><div>{onCatalog && <button className="quiet-button" onClick={onCatalog}>改用快速建档</button>}{onResume && <button className="primary-button" onClick={onResume}>继续本轮</button>}</div></footer>}
    </section>;
  }
  return (
    <section className={`wiki-plan-card ${plan.status}`} aria-label="Wiki 整理计划">
      <header className="wiki-plan-header">
        <div>
          <span>{plan.status === "applied" ? "Wiki Updated" : "Wiki Plan"}</span>
          <h3>{plan.status === "applied" ? "Wiki 已按计划更新" : "先审查这份整理计划"}</h3>
          <p>{plan.batches?.length ? `${scopeDocuments.length} 份资料 · ${plan.batches.length} 个批次` : scopeDocuments.join("、") || "当前学习资料"}</p>
        </div>
        {onClose && <IconButton label="关闭 Wiki 计划" onClick={onClose}><X size={17} /></IconButton>}
      </header>

      <div className="wiki-plan-summary">
        {(Object.keys(changeMeta) as WikiChangeKind[]).map((kind) => {
          const Icon = changeMeta[kind].icon;
            return <span className={kind} key={kind}><Icon size={14} /><strong>{summary[kind] || 0}</strong>{changeMeta[kind].label}</span>;
        })}
      </div>

      {summary.conflict > 0 && (
        <div className="wiki-plan-warning"><AlertTriangle size={16} />同名用户页面不会被覆盖，冲突项会保留原样。</div>
      )}
      {(summary.split || 0) > 0 && <div className="wiki-plan-warning"><ListTree size={16} />{summary.split} 个大型主题需要拆成总览页与子概念页，本轮不会用短草稿覆盖原页面。</div>}
      {plan.batches?.length ? <section className="wiki-run-scope" aria-label="Wiki 全库发现范围">
        <div><strong>采用资料</strong><span>{scopeDocuments.length}</span><small>{plan.scope.mode === "uncovered" ? "未覆盖或原文已变化" : plan.scope.mode === "selected_only" ? "严格仅选中" : plan.scope.mode === "course" ? "当前课程" : "全库发现并优先选择项"}</small></div>
        <div><strong>处理批次</strong><span>{plan.batches.length}</span><small>每批最多 5 份资料</small></div>
        <div><strong>资料摘要页</strong><span>{changes.filter((item) => item.page_type === "wiki_source").length}</span><small>每份资料独立可追溯</small></div>
      </section> : null}
      {staged.length > 0 && <section className="wiki-plan-recovery" aria-label="Wiki 计划需要处理">
        <header><span><AlertTriangle size={17} /><strong>{staged.length} 个页面需要你选择处理方式</strong></span><p>Bobodan 已暂停整次写入，现有 Wiki 没有被修改。你可以保留原页面并生成其余内容，也可以让 Bobodan 补全后重新规划。</p></header>
        <div className="wiki-plan-issues">{staged.map((item) => {
          const change = changes.find((candidate) => candidate.change_id === item.change_id);
          return <details key={item.change_id}><summary><span><strong>{change?.title || "未命名页面"}</strong><small>{item.errors.map(validationMessage).join(" ")}</small></span><i>查看原因</i></summary><div>{item.errors.map((error) => <code key={error}>{error}</code>)}</div></details>;
        })}</div>
        <footer><div><ShieldCheck size={16} /><span><strong>推荐</strong><small>保留现有页面，避免丢失内容，并继续生成其余 {safePageCount} 个页面。</small></span></div><div>{onRegenerate && <button className="quiet-button" disabled={busy} onClick={onRegenerate}><RefreshCw size={15} />{busy ? "正在重新规划" : "补全后重新规划"}</button>}{onKeepExisting && <button className="primary-button" disabled={busy || safePageCount === 0} onClick={onKeepExisting}><ShieldCheck size={15} />{busy ? "正在继续生成" : `保留原页，生成其余 ${safePageCount} 页`}</button>}</div></footer>
      </section>}

      <div className="wiki-plan-changes">
        {changes.map((change) => {
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
                {change.kind === "split" && !change.content ? <p>页面主题过大或现有内容较长，需要先拆分为小型互链页面；本轮不会写入这一项。</p> : <ReactMarkdown remarkPlugins={[remarkGfm]}>{change.content}</ReactMarkdown>}
              </div>
            </details>
          );
        })}
      </div>

      <footer className="wiki-plan-actions">
        <span>{staged.length ? "尚未写入，请先选择上方处理方式" : plan.status === "planned" ? `确认后写入 ${applicable} 个页面` : `已写入 ${plan.written?.length || applicable} 个页面`}</span>
        <div>
          {plan.status === "applied" && onUndo && <button className="quiet-button" disabled={busy} onClick={onUndo}><Undo2 size={15} />撤销本轮</button>}
          {plan.status === "applied" && plan.remaining_document_ids?.length && onContinue && <button className="primary-button" disabled={busy} onClick={onContinue}>继续下一批 · {plan.remaining_document_ids.length}</button>}
          {plan.status === "planned" && !staged.length && onApply && <button className="primary-button" disabled={busy || applicable === 0} onClick={onApply}><Check size={16} />{busy ? "正在写入" : "确认并生成"}</button>}
        </div>
      </footer>
    </section>
  );
}
