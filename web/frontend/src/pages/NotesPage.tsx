import { useEffect, useMemo, useState } from "react";
import { BookOpen, Check, Eye, Pencil, PenLine, Pin, Plus, Search, Trash2, X } from "lucide-react";
import { useOutletContext } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api } from "../lib/api";
import type { AppOutletContext } from "../components/AppShell";
import { IconButton, LoadingState } from "../components/common";
import { MemoryManagerDialog } from "../components/MemoryManagerDialog";
import type { PersonalKnowledgeItem } from "../types";

interface NoteDraft {
  id: string;
  revision: number;
  scope: "global" | "library";
  markdown: string;
  pinned: boolean;
  references: Array<{ document_id: string; chunk_id?: string; title: string; page?: number }>;
}

const emptyDraft: NoteDraft = { id: "", revision: 0, scope: "library", markdown: "", pinned: false, references: [] };

/** 笔记以 Markdown 正文为主角；第一行 `# 标题` 自动提取为标题。 */
function toMarkdown(item: PersonalKnowledgeItem): string {
  return `# ${item.title}\n\n${item.content}`;
}

function parseMarkdown(markdown: string): { title: string; content: string } {
  const lines = markdown.split("\n");
  const first = (lines[0] || "").trim();
  if (first.startsWith("# ")) {
    const title = first.slice(2).trim();
    return { title: title || "无标题笔记", content: lines.slice(1).join("\n").trim() };
  }
  return { title: first.slice(0, 30) || "无标题笔记", content: markdown.trim() };
}

/** P5G.5 体验整改：个人笔记一级入口，沉浸式 Markdown 编辑（非填表）。 */
export function NotesPage() {
  const { documents, activeLibrary, settings } = useOutletContext<AppOutletContext>();
  const [notes, setNotes] = useState<PersonalKnowledgeItem[]>([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [preview, setPreview] = useState(false);
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

  const draftTitle = useMemo(() => (draft ? parseMarkdown(draft.markdown).title : ""), [draft]);

  function startNew() {
    setDraft({ ...emptyDraft, scope: activeLibrary ? "library" : "global" });
    setPreview(false);
    setError("");
    setNotice("");
  }

  function startEdit(item: PersonalKnowledgeItem) {
    setDraft({
      id: item.id,
      revision: item.revision,
      scope: item.scope,
      markdown: toMarkdown(item),
      pinned: item.pinned,
      references: item.references || [],
    });
    setPreview(false);
    setError("");
    setNotice("");
  }

  function closeEditor() {
    setDraft(null);
    setPreview(false);
    setError("");
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

  function handleEditorKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") { event.preventDefault(); closeEditor(); }
    else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void saveNote(); }
  }

  async function saveNote() {
    if (!draft) return;
    const { title, content } = parseMarkdown(draft.markdown);
    if (!title.trim() || !content.trim()) { setError("先写下笔记正文，再保存。"); return; }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      if (draft.id) {
        await api.updateMemoryKnowledge(draft.id, draft.revision, {
          title: title.trim(),
          content: content.trim(),
          pinned: draft.pinned,
          references: draft.references,
        });
      } else {
        await api.createMemoryKnowledge({
          scope: draft.scope,
          kind: "course_insight",
          title: title.trim(),
          content: content.trim(),
          pinned: draft.pinned,
          references: draft.references,
        });
      }
      setDraft(null);
      setPreview(false);
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
          <header className="note-editor-toolbar">
            <div className="note-editor-heading">
              <span>{draft.id ? "编辑笔记" : "写笔记"}</span>
              <h3>{draftTitle || "无标题笔记"}</h3>
            </div>
            <div className="note-editor-toolbar-actions">
              <button className="quiet-button" type="button" onClick={() => setPreview((value) => !value)}><Eye size={14} />{preview ? "编辑" : "预览"}</button>
              <IconButton label="关闭编辑器" onClick={closeEditor}><X /></IconButton>
            </div>
          </header>
          {preview ? (
            <article className="note-preview reader-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{draft.markdown || "*还没有内容。*"}</ReactMarkdown></article>
          ) : (
            <textarea className="note-body" autoFocus value={draft.markdown} disabled={working} onKeyDown={handleEditorKeyDown} placeholder={"# 标题\n\n写下你的想法、结论或摘录…（支持 Markdown）"} onChange={(event) => setDraft({ ...draft, markdown: event.target.value })} />
          )}
          <footer className="note-editor-footer">
            {documents.length > 0 && (
              <details className="note-references">
                <summary><BookOpen size={13} />关联资料{draft.references.length ? `（${draft.references.length}）` : ""}</summary>
                <div className="note-reference-list">
                  {documents.slice(0, 100).map((doc) => (
                    <label key={doc.document_id}><input type="checkbox" checked={draft.references.some((ref) => ref.document_id === doc.document_id)} disabled={working} onChange={() => toggleReference(doc.document_id, doc.title)} /><span>{doc.title}</span></label>
                  ))}
                </div>
              </details>
            )}
            <span className="note-editor-hint">Ctrl+Enter 保存 · Esc 关闭</span>
            <button className="primary-button" disabled={working} onClick={() => void saveNote()}><Check size={15} />保存笔记</button>
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
          {!filtered.length && (query
            ? <p className="settings-empty">没有匹配的笔记。</p>
            : <div className="notes-empty"><PenLine size={28} /><h3>还没有笔记</h3><p>记录你的思考、结论和摘录。笔记可关联资料，阅读原文时也能看到。</p><button className="primary-button" onClick={startNew}><Plus size={15} />写第一条笔记</button></div>)}
        </div>
      )}

      {managerOpen && <div className="settings-backdrop" role="presentation"><MemoryManagerDialog memoryEnabled={settings?.preferences.memory.enabled ?? true} onClose={() => { setManagerOpen(false); void loadNotes(); }} /></div>}
      </div>
    </section>
  );
}
