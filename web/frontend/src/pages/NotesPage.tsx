import { useEffect, useMemo, useState } from "react";
import { BookOpen, Check, Pencil, Pin, Plus, Search, Trash2, X } from "lucide-react";
import { useOutletContext } from "react-router-dom";

import { api } from "../lib/api";
import type { AppOutletContext } from "../components/AppShell";
import { IconButton, LoadingState } from "../components/common";
import { MemoryManagerDialog } from "../components/MemoryManagerDialog";
import type { PersonalKnowledgeItem } from "../types";

interface NoteDraft {
  id: string;
  revision: number;
  scope: "global" | "library";
  title: string;
  content: string;
  pinned: boolean;
  references: Array<{ document_id: string; chunk_id?: string; title: string; page?: number }>;
}

const emptyDraft: NoteDraft = { id: "", revision: 0, scope: "library", title: "", content: "", pinned: false, references: [] };

/** P5G 体验整改：个人笔记一级入口。笔记 = 个人知识条目（kind=course_insight）。 */
export function NotesPage() {
  const { documents, activeLibrary, settings } = useOutletContext<AppOutletContext>();
  const [notes, setNotes] = useState<PersonalKnowledgeItem[]>([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [managerOpen, setManagerOpen] = useState(false);

  async function loadNotes() {
    setLoading(true);
    setError("");
    try {
      const result = await api.memoryKnowledge();
      setNotes(result.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取笔记。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadNotes(); }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return needle ? notes.filter((item) => `${item.title} ${item.content}`.toLocaleLowerCase().includes(needle)) : notes;
  }, [notes, query]);

  function startNew() {
    setDraft({ ...emptyDraft, scope: activeLibrary ? "library" : "global" });
    setError("");
    setNotice("");
  }

  function startEdit(item: PersonalKnowledgeItem) {
    setDraft({
      id: item.id,
      revision: item.revision,
      scope: item.scope,
      title: item.title,
      content: item.content,
      pinned: item.pinned,
      references: item.references || [],
    });
    setError("");
    setNotice("");
  }

  function toggleReference(documentId: string, title: string) {
    if (!draft) return;
    const exists = draft.references.some((ref) => ref.document_id === documentId);
    setDraft({
      ...draft,
      references: exists
        ? draft.references.filter((ref) => ref.document_id !== documentId)
        : [...draft.references, { document_id: documentId, title }],
    });
  }

  async function saveNote() {
    if (!draft) return;
    if (!draft.title.trim() || !draft.content.trim()) { setError("请填写标题和内容。"); return; }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      if (draft.id) {
        await api.updateMemoryKnowledge(draft.id, draft.revision, {
          title: draft.title.trim(),
          content: draft.content.trim(),
          pinned: draft.pinned,
          references: draft.references,
        });
      } else {
        await api.createMemoryKnowledge({
          scope: draft.scope,
          kind: "course_insight",
          title: draft.title.trim(),
          content: draft.content.trim(),
          pinned: draft.pinned,
          references: draft.references,
        });
      }
      setDraft(null);
      setNotice("笔记已保存。");
      await loadNotes();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败。");
    } finally {
      setWorking(false);
    }
  }

  async function togglePin(item: PersonalKnowledgeItem) {
    try {
      await api.updateMemoryKnowledge(item.id, item.revision, { pinned: !item.pinned });
      await loadNotes();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败。");
    }
  }

  async function removeNote(item: PersonalKnowledgeItem) {
    if (!window.confirm(`删除笔记“${item.title}”？`)) return;
    try {
      await api.deleteMemoryKnowledge(item.id);
      await loadNotes();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败。");
    }
  }

  return (
    <section className="page-scroll">
      <div className="page-container notes-container">
      <header className="notes-header">
        <div>
          <span>Personal Notes</span>
          <h2>我的笔记</h2>
          <p>你自己的思考、结论和摘录。引用资料后，阅读原文时也能看到这些笔记。</p>
        </div>
        <div className="notes-header-actions">
          <label className="notes-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索笔记" /></label>
          <button className="quiet-button" onClick={() => setManagerOpen(true)}>管理全部</button>
          <button className="primary-button" onClick={startNew}><Plus size={15} />写笔记</button>
        </div>
      </header>

      {error && <div className="settings-error">{error}</div>}
      {notice && <div className="settings-notice"><Check size={14} />{notice}</div>}

      {draft && (
        <section className="note-editor">
          <header><h3>{draft.id ? "编辑笔记" : "写笔记"}</h3><IconButton label="关闭编辑器" onClick={() => setDraft(null)}><X /></IconButton></header>
          <label className="wide"><span>标题</span><input value={draft.title} maxLength={120} disabled={working} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="一句话概括这条笔记" /></label>
          <label className="wide"><span>内容</span><textarea rows={6} value={draft.content} maxLength={5000} disabled={working} onChange={(event) => setDraft({ ...draft, content: event.target.value })} placeholder="写下你的想法、结论或摘录…" /></label>
          {documents.length > 0 && (
            <div className="wide note-references">
              <span>关联资料（可选）</span>
              <div className="note-reference-list">
                {documents.slice(0, 100).map((doc) => (
                  <label key={doc.document_id}><input type="checkbox" checked={draft.references.some((ref) => ref.document_id === doc.document_id)} disabled={working} onChange={() => toggleReference(doc.document_id, doc.title)} /><span>{doc.title}</span></label>
                ))}
              </div>
            </div>
          )}
          <footer>
            <button className="quiet-button" disabled={working} onClick={() => setDraft(null)}>取消</button>
            <button className="primary-button" disabled={working || !draft.title.trim() || !draft.content.trim()} onClick={() => void saveNote()}><Check size={15} />保存笔记</button>
          </footer>
        </section>
      )}

      {loading ? <LoadingState label="正在读取笔记…" /> : (
        <div className="notes-list">
          {filtered.map((item) => (
            <article key={item.id}>
              <div className="note-item-head">
                <IconButton label={item.pinned ? "取消置顶" : "置顶"} className={item.pinned ? "active" : ""} onClick={() => void togglePin(item)}><Pin size={15} /></IconButton>
                <h3>{item.title}</h3>
                <span className="note-item-meta">{item.scope === "global" ? "全局" : "本资料库"}</span>
              </div>
              <p>{item.content}</p>
              {(item.references || []).length > 0 && (
                <div className="note-item-refs">
                  <BookOpen size={12} />
                  {(item.references || []).map((ref) => <button key={ref.document_id} className="text-link" type="button" onClick={() => window.location.assign(`/library?collection=material&document=${encodeURIComponent(ref.document_id)}`)}>{ref.title}</button>)}
                </div>
              )}
              <div className="note-item-actions">
                <small>更新于 {new Date(item.updated_at).toLocaleString("zh-CN")}</small>
                <div>
                  <IconButton label="编辑" onClick={() => startEdit(item)}><Pencil size={15} /></IconButton>
                  <IconButton label="删除" onClick={() => void removeNote(item)}><Trash2 size={15} /></IconButton>
                </div>
              </div>
            </article>
          ))}
          {!filtered.length && <p className="settings-empty">{query ? "没有匹配的笔记。" : "还没有笔记。点「写笔记」开始记录你的第一条思考。"}</p>}
        </div>
      )}

      {managerOpen && <div className="settings-backdrop" role="presentation"><MemoryManagerDialog memoryEnabled={settings?.preferences.memory.enabled ?? true} onClose={() => { setManagerOpen(false); void loadNotes(); }} /></div>}
      </div>
    </section>
  );
}
