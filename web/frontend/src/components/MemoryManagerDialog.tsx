import { useEffect, useMemo, useState } from "react";
import { Brain, Check, Download, Edit3, Pin, Plus, Search, Trash2, X } from "lucide-react";

import { api } from "../lib/api";
import type {
  KnowledgeCandidate, KnowledgeKind, LearningEvent, LegacyMemoryPreview,
  MemoryOverview, PersonalKnowledgeItem,
} from "../types";
import { IconButton, LoadingState } from "./common";

type Tab = "knowledge" | "candidates" | "events" | "legacy";

const kindLabels: Record<KnowledgeKind, string> = {
  preference: "偏好",
  goal: "目标",
  profile_fact: "用户信息",
  learning_strategy: "学习策略",
  course_insight: "课程结论",
  study_pattern: "学习模式",
};

const eventLabels: Record<LearningEvent["type"], string> = {
  quiz_answered: "完成一道题",
  practice_completed: "完成练习",
  review_started: "开始复习",
  review_completed: "完成复习",
  document_opened: "阅读资料",
  reading_progress: "更新阅读进度",
  chat_completed: "整理学习对话",
};

interface KnowledgeDraft {
  id: string;
  revision: number;
  scope: "global" | "library";
  kind: KnowledgeKind;
  title: string;
  content: string;
  pinned: boolean;
}

const emptyDraft: KnowledgeDraft = {
  id: "",
  revision: 0,
  scope: "library",
  kind: "course_insight" as KnowledgeKind,
  title: "",
  content: "",
  pinned: false,
};

export function MemoryManagerDialog({ onClose, memoryEnabled }: { onClose: () => void; memoryEnabled: boolean }) {
  const [tab, setTab] = useState<Tab>("knowledge");
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [knowledge, setKnowledge] = useState<PersonalKnowledgeItem[]>([]);
  const [candidates, setCandidates] = useState<KnowledgeCandidate[]>([]);
  const [events, setEvents] = useState<LearningEvent[]>([]);
  const [legacy, setLegacy] = useState<LegacyMemoryPreview | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"all" | "global" | "library">("all");
  const [draft, setDraft] = useState(emptyDraft);
  const [candidateDraft, setCandidateDraft] = useState<KnowledgeCandidate | null>(null);
  const [legacySelections, setLegacySelections] = useState<Record<string, { scope: "global" | "library"; kind: KnowledgeKind }>>({});
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextKnowledge, nextCandidates, nextEvents] = await Promise.all([
        api.memoryOverview(),
        api.memoryKnowledge(),
        api.memoryCandidates(),
        api.memoryEvents(),
      ]);
      setOverview(nextOverview);
      setKnowledge(nextKnowledge.items);
      setCandidates(nextCandidates.candidates);
      setEvents(nextEvents.events);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取个人知识。" );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadAll(); }, []);
  useEffect(() => {
    if (tab !== "legacy" || legacy) return;
    void api.legacyMemoryPreview().then(setLegacy).catch((reason: Error) => setError(reason.message));
  }, [legacy, tab]);

  const filtered = useMemo(() => knowledge.filter((item) => {
    if (scope !== "all" && item.scope !== scope) return false;
    const needle = query.trim().toLocaleLowerCase();
    return !needle || `${item.title} ${item.content}`.toLocaleLowerCase().includes(needle);
  }), [knowledge, query, scope]);

  function editItem(item: PersonalKnowledgeItem) {
    setDraft({
      id: item.id,
      revision: item.revision,
      scope: item.scope,
      kind: item.kind,
      title: item.title,
      content: item.content,
      pinned: item.pinned,
    });
  }

  async function saveItem() {
    if (!draft.title.trim() || !draft.content.trim()) return;
    setWorking(true);
    setError("");
    try {
      if (draft.id) {
        await api.updateMemoryKnowledge(draft.id, draft.revision, {
          title: draft.title,
          content: draft.content,
          kind: draft.kind,
          pinned: draft.pinned,
        });
      } else {
        await api.createMemoryKnowledge({
          scope: draft.scope,
          kind: draft.kind,
          title: draft.title,
          content: draft.content,
          pinned: draft.pinned,
        });
      }
      setDraft(emptyDraft);
      setNotice("个人知识已保存");
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "个人知识没有保存成功。" );
    } finally {
      setWorking(false);
    }
  }

  async function patchItem(item: PersonalKnowledgeItem, patch: Record<string, unknown>) {
    setWorking(true);
    try {
      await api.updateMemoryKnowledge(item.id, item.revision, patch);
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新失败。" );
    } finally {
      setWorking(false);
    }
  }

  async function removeItem(item: PersonalKnowledgeItem) {
    if (!window.confirm(`删除“${item.title}”？删除后将立即停止用于个性化。`)) return;
    setWorking(true);
    try {
      await api.deleteMemoryKnowledge(item.id);
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败。" );
    } finally {
      setWorking(false);
    }
  }

  async function resolveCandidate(action: "confirm" | "reject", candidate: KnowledgeCandidate) {
    setWorking(true);
    setError("");
    try {
      if (action === "confirm") {
        const edited = candidateDraft?.id === candidate.id ? candidateDraft : candidate;
        await api.confirmMemoryCandidate(candidate.id, {
          scope: edited.scope,
          kind: edited.kind,
          title: edited.title,
          content: edited.content,
        });
      } else {
        await api.rejectMemoryCandidate(candidate.id);
      }
      setCandidateDraft(null);
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选处理失败。" );
    } finally {
      setWorking(false);
    }
  }

  async function importLegacy() {
    const selections = Object.entries(legacySelections).map(([name, value]) => ({ name, ...value }));
    if (!selections.length) return;
    setWorking(true);
    try {
      await api.importLegacyMemory(selections);
      setLegacySelections({});
      setNotice("旧记忆已转换为待确认候选");
      setTab("candidates");
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "旧记忆迁移失败。" );
    } finally {
      setWorking(false);
    }
  }

  async function exportKnowledge() {
    try {
      const content = await api.exportMemory(scope);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
      link.download = "bobodan-personal-knowledge.md";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出失败。" );
    }
  }

  return <section className="memory-manager" role="dialog" aria-modal="true" aria-label="管理个人知识">
    <header className="memory-manager-header"><div><span>Personal Knowledge</span><h2>管理个人知识</h2><p>只有已确认内容会参与个性化。学习记录用于进度判断，不会自动变成人格画像。</p></div><IconButton label="关闭个人知识" onClick={onClose}><X /></IconButton></header>
    <div className="memory-overview"><div><strong>{overview?.knowledge_count || 0}</strong><span>已确认</span></div><div><strong>{overview?.pending_candidate_count || 0}</strong><span>待确认</span></div><div><strong>{overview?.event_count || 0}</strong><span>学习记录</span></div><div><strong>{overview?.jobs.failed || 0}</strong><span>整理失败</span></div></div>
    <nav className="memory-tabs" role="tablist">
      <button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>已确认</button>
      <button className={tab === "candidates" ? "active" : ""} onClick={() => setTab("candidates")}>待确认{overview?.pending_candidate_count ? <span>{overview.pending_candidate_count}</span> : null}</button>
      <button className={tab === "events" ? "active" : ""} onClick={() => setTab("events")}>学习记录</button>
      <button className={tab === "legacy" ? "active" : ""} onClick={() => setTab("legacy")}>旧记忆</button>
    </nav>
    {!memoryEnabled && <div className="settings-notice">学习记忆已关闭。你仍可查看、删除、拒绝和导出内容；重新开启后才能新增、编辑或确认。</div>}
    {error && <div className="settings-error">{error}</div>}
    {notice && <div className="settings-notice"><Check size={14} />{notice}</div>}
    {loading ? <LoadingState label="正在读取个人知识…" /> : <main className="memory-manager-main">
      {tab === "knowledge" && <>
        <div className="memory-toolbar"><label><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索已确认知识" /></label><select value={scope} onChange={(event) => setScope(event.target.value as typeof scope)}><option value="all">全部作用域</option><option value="global">全局</option><option value="library">当前资料库</option></select><button className="quiet-button" disabled={!memoryEnabled} onClick={() => setDraft(emptyDraft)}><Plus size={15} />新增</button><button className="quiet-button" onClick={() => void exportKnowledge()}><Download size={15} />导出</button></div>
        <section className="memory-editor"><label><span>作用域</span><select value={draft.scope} disabled={Boolean(draft.id) || !memoryEnabled} onChange={(event) => setDraft({ ...draft, scope: event.target.value as "global" | "library" })}><option value="library">当前资料库</option><option value="global">所有资料库</option></select></label><label><span>类型</span><select value={draft.kind} disabled={!memoryEnabled} onChange={(event) => setDraft({ ...draft, kind: event.target.value as KnowledgeKind })}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="wide"><span>标题</span><input value={draft.title} disabled={!memoryEnabled} maxLength={120} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="wide"><span>内容</span><textarea rows={4} value={draft.content} disabled={!memoryEnabled} maxLength={5000} onChange={(event) => setDraft({ ...draft, content: event.target.value })} /></label><footer><label><input type="checkbox" checked={draft.pinned} disabled={!memoryEnabled} onChange={(event) => setDraft({ ...draft, pinned: event.target.checked })} />置顶</label>{draft.id && <button className="quiet-button" onClick={() => setDraft(emptyDraft)}>取消编辑</button>}<button className="primary-button" disabled={!memoryEnabled || working || !draft.title.trim() || !draft.content.trim()} onClick={() => void saveItem()}><Check size={15} />保存</button></footer></section>
        <div className="memory-list">{filtered.map((item) => <article key={item.id}><div className="memory-item-icon"><Brain size={17} /></div><div><span>{item.scope === "global" ? "全局" : "资料库"} · {kindLabels[item.kind]}</span><h3>{item.title}</h3><p>{item.content}</p><small>更新于 {new Date(item.updated_at).toLocaleString("zh-CN")}</small></div><div className="memory-item-actions"><IconButton label={item.pinned ? "取消置顶" : "置顶"} className={item.pinned ? "active" : ""} disabled={working || !memoryEnabled} onClick={() => void patchItem(item, { pinned: !item.pinned })}><Pin size={15} /></IconButton><IconButton label="编辑" disabled={working || !memoryEnabled} onClick={() => editItem(item)}><Edit3 size={15} /></IconButton><IconButton label="删除" disabled={working} onClick={() => void removeItem(item)}><Trash2 size={15} /></IconButton></div></article>)}{!filtered.length && <p className="settings-empty">还没有匹配的已确认知识。</p>}</div>
      </>}
      {tab === "candidates" && <div className="candidate-list">{candidates.map((candidate) => {
        const edited = candidateDraft?.id === candidate.id ? candidateDraft : candidate;
        return <article key={candidate.id}><header><span>{candidate.operation === "update" ? "更新建议" : "新知识候选"} · {kindLabels[candidate.kind]}</span><strong>{candidate.title}</strong><small>{candidate.reason}</small></header><details><summary>查看证据与编辑</summary><div className="candidate-editor"><label><span>作用域</span><select value={edited.scope} disabled={!memoryEnabled} onChange={(event) => setCandidateDraft({ ...edited, scope: event.target.value as "global" | "library" })}><option value="library">当前资料库</option><option value="global">所有资料库</option></select></label><label><span>类型</span><select value={edited.kind} disabled={!memoryEnabled} onChange={(event) => setCandidateDraft({ ...edited, kind: event.target.value as KnowledgeKind })}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="wide"><span>标题</span><input value={edited.title} disabled={!memoryEnabled} onChange={(event) => setCandidateDraft({ ...edited, title: event.target.value })} /></label><label className="wide"><span>内容</span><textarea rows={4} value={edited.content} disabled={!memoryEnabled} onChange={(event) => setCandidateDraft({ ...edited, content: event.target.value })} /></label><div className="candidate-evidence">{candidate.evidence.length ? candidate.evidence.map((item, index) => <p key={index}>{String(item.excerpt || item.source_id || "学习记录")}</p>) : <p>没有额外证据片段。</p>}</div></div></details><footer><button className="quiet-button" disabled={working} onClick={() => void resolveCandidate("reject", candidate)}>拒绝</button><button className="primary-button" disabled={working || !memoryEnabled} onClick={() => void resolveCandidate("confirm", candidate)}><Check size={15} />确认并保存</button></footer></article>;
      })}{!candidates.length && <p className="settings-empty">目前没有等待确认的知识候选。</p>}</div>}
      {tab === "events" && <div className="memory-event-list">{events.map((event) => <article key={event.id}><span>{eventLabels[event.type]}</span><strong>{event.concept || String(event.payload.origin || event.source_type)}</strong><small>{new Date(event.occurred_at).toLocaleString("zh-CN")}</small>{typeof event.payload.progress === "number" && <i>{event.payload.progress}%</i>}</article>)}{!events.length && <p className="settings-empty">还没有学习记录。</p>}</div>}
      {tab === "legacy" && <div className="legacy-memory"><p>旧 Markdown 记忆保持只读。选中的条目只会转为待确认候选，不会删除原文件。</p>{legacy ? <>{legacy.entries.map((entry) => { const selected = legacySelections[entry.name]; return <article key={entry.name}><input type="checkbox" disabled={!memoryEnabled} checked={Boolean(selected)} onChange={(event) => setLegacySelections((current) => { const next = { ...current }; if (event.target.checked) next[entry.name] = { scope: entry.suggested_scope, kind: entry.suggested_kind }; else delete next[entry.name]; return next; })} /><div><strong>{entry.name}</strong><p>{entry.content_preview}</p><small>{entry.description || entry.type}</small></div>{selected && <select value={selected.scope} disabled={!memoryEnabled} onChange={(event) => setLegacySelections({ ...legacySelections, [entry.name]: { ...selected, scope: event.target.value as "global" | "library" } })}><option value="global">全局</option><option value="library">资料库</option></select>}</article>})}<div className="legacy-daily"><strong>旧 daily 文件</strong><span>{legacy.daily_files.length ? `${legacy.daily_files.length} 个文件，只读保留` : "没有发现旧 daily 文件"}</span></div><footer><button className="primary-button" disabled={!memoryEnabled || working || !Object.keys(legacySelections).length} onClick={() => void importLegacy()}><Check size={15} />转为待确认候选</button></footer></> : <LoadingState label="正在读取旧记忆…" />}</div>}
    </main>}
  </section>;
}
