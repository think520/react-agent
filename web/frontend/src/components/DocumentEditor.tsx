import { useEffect, useRef, useState } from "react";
import { Columns2, History, Save, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ApiError, api } from "../lib/api";

interface DocumentEditorProps {
  documentId: string;
  title: string;
  onClose: () => void;
  onSaved: () => void;
}

interface Version {
  id: string;
  created_at: string;
  content_hash: string;
}

/**
 * Markdown editor for managed material documents (LB-1.1 + TASKS_LIBRARY_REWORK
 * task 3.4.2). Split-pane edit + live preview with bidirectional scroll sync
 * (MiaoYan-inspired, 60fps rAF), Ctrl+\ to toggle split/pure-edit, and a
 * draggable divider. Keeps checkpoints / 10-version history / rollback / the
 * Obsidian double-open hash-conflict three options.
 */
export function DocumentEditor({ documentId, title, onClose, onSaved }: DocumentEditorProps) {
  const [content, setContent] = useState("");
  const [expectedHash, setExpectedHash] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [versions, setVersions] = useState<Version[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [splitView, setSplitView] = useState(true);
  const [previewPct, setPreviewPct] = useState(45);

  const editRef = useRef<HTMLTextAreaElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const syncingRef = useRef(false);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.documentContent(documentId)
      .then((result) => {
        if (cancelled) return;
        setContent(result.content);
        setExpectedHash(result.content_hash);
        setLoading(false);
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "无法加载文档内容。");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [documentId]);

  // Ctrl+\ (or Cmd+\) toggles split / pure-edit.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "\\") {
        e.preventDefault();
        setSplitView((value) => !value);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  function syncScroll(source: HTMLElement, target: HTMLElement) {
    if (syncingRef.current) return;
    syncingRef.current = true;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      const sourceMax = source.scrollHeight - source.clientHeight;
      const targetMax = target.scrollHeight - target.clientHeight;
      const ratio = sourceMax > 0 ? source.scrollTop / sourceMax : 0;
      target.scrollTop = ratio * Math.max(0, targetMax);
      window.setTimeout(() => { syncingRef.current = false; }, 60);
    });
  }

  function onEditScroll() {
    if (!splitView || !editRef.current || !previewRef.current) return;
    syncScroll(editRef.current, previewRef.current);
  }
  function onPreviewScroll() {
    if (!splitView || !editRef.current || !previewRef.current) return;
    syncScroll(previewRef.current, editRef.current);
  }

  function startDividerDrag(e: React.PointerEvent) {
    e.preventDefault();
    const move = (ev: PointerEvent) => {
      const editor = document.querySelector<HTMLElement>(".document-editor-split");
      if (!editor) return;
      const rect = editor.getBoundingClientRect();
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      setPreviewPct(Math.max(20, Math.min(80, pct)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  async function save(action: "overwrite" | "abandon" | "save_as_new" = "overwrite") {
    setSaving(true);
    setError("");
    try {
      await api.editDocument(documentId, { content, expected_hash: expectedHash, conflict_action: action });
      onSaved();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "document_conflict") {
        setConflict(true);
      } else {
        setError(reason instanceof Error ? reason.message : "保存失败，请重试。");
      }
    } finally {
      setSaving(false);
    }
  }

  async function loadVersions() {
    try {
      const result = await api.documentVersions(documentId);
      setVersions(result.versions);
      setShowVersions(true);
    } catch {
      setError("无法加载历史版本。");
    }
  }

  async function rollback(versionId: string) {
    setSaving(true);
    setError("");
    try {
      await api.rollbackDocument(documentId, versionId);
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回滚失败。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="document-editor-backdrop" role="dialog" aria-label="编辑资料">
      <div className="document-editor">
        <header>
          <div>
            <span>编辑资料</span>
            <h3>{title}</h3>
          </div>
          <div className="document-editor-header-actions">
            <button className="icon-button" type="button" aria-label="切换分栏" title="Ctrl+\ 切换分栏" onClick={() => setSplitView((value) => !value)}><Columns2 size={17} /></button>
            <button className="icon-button" type="button" aria-label="关闭编辑" onClick={onClose}><X size={18} /></button>
          </div>
        </header>

        {loading ? (
          <main><p className="document-editor-hint">正在加载原文…</p></main>
        ) : conflict ? (
          <main>
            <div className="document-editor-conflict">
              <strong>这份资料在磁盘上发生了变化</strong>
              <p>可能你同时在 Obsidian 里打开了它。请选择如何处理：</p>
              <div>
                <button className="primary-button" disabled={saving} onClick={() => void save("overwrite")}>覆盖外部修改</button>
                <button className="quiet-button" disabled={saving} onClick={() => void save("save_as_new")}>另存为新文件</button>
                <button className="quiet-button" disabled={saving} onClick={onClose}>放弃本次编辑</button>
              </div>
            </div>
          </main>
        ) : splitView ? (
          <main className="document-editor-split">
            <textarea
              ref={editRef}
              className="document-editor-textarea split"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              onScroll={onEditScroll}
              spellCheck={false}
            />
            <div className="document-editor-divider" role="separator" aria-label="拖动调整预览宽度" onPointerDown={startDividerDrag} />
            <div
              className="document-editor-preview"
              ref={previewRef}
              onScroll={onPreviewScroll}
              style={{ flexBasis: previewPct + "%" }}
            >
              <article className="reader-prose document-editor-preview-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || "还没有正文。"}</ReactMarkdown>
              </article>
            </div>
          </main>
        ) : (
          <main>
            <textarea
              ref={editRef}
              className="document-editor-textarea"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              spellCheck={false}
            />
          </main>
        )}

        {showVersions && (
          <aside className="document-editor-versions">
            <header><History size={14} />历史版本（最近 10 个）</header>
            {versions.length === 0 && <p className="document-editor-hint">还没有历史版本。</p>}
            {versions.map((version) => (
              <div key={version.id}>
                <span>{new Date(version.created_at).toLocaleString("zh-CN")}</span>
                <button className="quiet-button" disabled={saving} onClick={() => void rollback(version.id)}>回滚到此版本</button>
              </div>
            ))}
          </aside>
        )}

        {error && <p className="document-editor-error">{error}</p>}

        <footer>
          <button className="quiet-button" type="button" onClick={() => void loadVersions()}><History size={14} />历史版本</button>
          <div>
            <button className="quiet-button" type="button" disabled={saving || loading} onClick={onClose}>取消</button>
            <button className="primary-button" type="button" disabled={saving || loading || conflict} onClick={() => void save("overwrite")}><Save size={15} />保存</button>
          </div>
        </footer>
      </div>
    </div>
  );
}
