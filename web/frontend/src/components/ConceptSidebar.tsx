/**
 * ConceptSidebar — slide-in detail panel for a selected concept node.
 *
 * Design (knowledge_map_design.md §9.6):
 *   - Slide in from right ~180ms ease-out, graph shifts left
 *   - Close: Esc or click canvas background
 *   - Fixed structure: name / definition / relations / excerpts / note / mastery
 *
 * TASKS_LIBRARY_REWORK task 4 adds graph editing: rename concept, delete
 * relationship, add relationship — all explicit user actions writing
 * evidence_level='user'.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, Edit2, FileText, Link2, MessageCircle, PenLine, Plus, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useHandoffStore } from "../stores/handoffStore";
import type { ConceptDetail, ConceptNode, RelationshipEdge } from "../types";

interface Props {
  conceptId: string | null;
  onClose: () => void;
  onConceptUpdated?: (concept: ConceptNode) => void;
  onNavigateConcept?: (conceptId: string) => void;
  embedded?: boolean;
}

const REL_LABELS: Record<string, string> = {
  "属于": "属于",
  "前置知识": "前置知识",
  "组成部分": "组成部分",
  "对比": "对比",
  "应用于": "应用于",
  "来源于": "来源于",
};

const REL_TYPE_OPTIONS = ["属于", "前置知识", "组成部分", "对比", "应用于", "来源于"];

export function ConceptSidebar({ conceptId, onClose, onConceptUpdated, onNavigateConcept, embedded = false }: Props) {
  const [detail, setDetail] = useState<ConceptDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingNote, setEditingNote] = useState(false);
  const [noteValue, setNoteValue] = useState("");
  // Graph edit state (task 4)
  const [editingConcept, setEditingConcept] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDefinition, setEditDefinition] = useState("");
  const [editAliases, setEditAliases] = useState("");
  const [editNote, setEditNote] = useState("");
  const [addingRelation, setAddingRelation] = useState(false);
  const [relTargetQuery, setRelTargetQuery] = useState("");
  const [relType, setRelType] = useState("属于");
  const [relNote, setRelNote] = useState("");
  const [allConcepts, setAllConcepts] = useState<ConceptNode[]>([]);
  const [busy, setBusy] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const navigate = useNavigate();

  function askAboutConcept(name: string) {
    useHandoffStore.getState().setChatDraft(`请帮我讲讲「${name}」这个概念。`);
    navigate("/chat");
  }

  const loadDetail = useCallback(() => {
    if (!conceptId) return;
    setLoading(true);
    setError(null);
    api.graphConcept(conceptId)
      .then((d) => {
        setDetail(d);
        setNoteValue(d.concept.note || "");
      })
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [conceptId]);

  // Load concept detail when conceptId changes
  useEffect(() => {
    if (!conceptId) {
      setDetail(null);
      setEditingConcept(false);
      setAddingRelation(false);
      return;
    }
    loadDetail();
  }, [conceptId, loadDetail]);

  // Esc key to close
  useEffect(() => {
    if (!conceptId) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [conceptId, onClose]);

  // Focus trap: move focus into sidebar when it opens
  useEffect(() => {
    if (conceptId && sidebarRef.current) {
      const first = sidebarRef.current.querySelector<HTMLElement>("button, input, textarea, [tabindex]");
      first?.focus();
    }
  }, [conceptId]);

  async function saveNote() {
    if (!detail) return;
    try {
      const result = await api.updateConcept(detail.concept.concept_id, { note: noteValue });
      setDetail((prev) => prev ? { ...prev, concept: result.concept } : prev);
      onConceptUpdated?.(result.concept);
    } catch {
      // keep current note; user can retry
    } finally {
      setEditingNote(false);
    }
  }

  function openEditConcept() {
    if (!detail) return;
    setEditName(detail.concept.name);
    setEditDefinition(detail.concept.definition || "");
    setEditAliases((detail.concept.aliases || []).join("，"));
    setEditNote(detail.concept.note || "");
    setError(null);
    setEditingConcept(true);
  }

  async function saveConceptEdit() {
    if (!detail) return;
    if (!editName.trim()) { setError("名称不能为空"); return; }
    setBusy(true);
    try {
      const result = await api.updateConcept(detail.concept.concept_id, {
        name: editName.trim(),
        definition: editDefinition,
        aliases: editAliases.split(/[，,]/).map((s) => s.trim()).filter(Boolean),
        note: editNote,
      });
      setDetail((prev) => prev ? { ...prev, concept: result.concept } : prev);
      onConceptUpdated?.(result.concept);
      setEditingConcept(false);
      loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteRelation(relId: string) {
    if (!window.confirm("删除这条关系？")) return;
    setBusy(true);
    try {
      await api.deleteRelationship(relId);
      if (detail) onConceptUpdated?.(detail.concept);
      loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  function openAddRelation() {
    setRelTargetQuery("");
    setRelType("属于");
    setRelNote("");
    setError(null);
    setAddingRelation(true);
    api.graphState({ include_candidates: false })
      .then((s) => setAllConcepts(s.concepts))
      .catch(() => setAllConcepts([]));
  }

  async function saveAddRelation(targetId: string) {
    if (!detail) return;
    setBusy(true);
    try {
      await api.createRelationship({
        from_id: detail.concept.concept_id,
        to_id: targetId,
        rel_type: relType,
        note: relNote,
      });
      onConceptUpdated?.(detail.concept);
      setAddingRelation(false);
      loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加失败");
    } finally {
      setBusy(false);
    }
  }

  if (!conceptId) return null;

  const matchingTargets = allConcepts
    .filter((c) => c.concept_id !== detail?.concept.concept_id)
    .filter((c) => !relTargetQuery.trim() || c.name.toLowerCase().includes(relTargetQuery.trim().toLowerCase()))
    .slice(0, 20);

  return (
    <section
      ref={sidebarRef}
      className={`concept-sidebar ${embedded ? "embedded" : ""} ${conceptId ? "open" : ""}`}
      aria-label="概念详情"
    >
      {!embedded && <div className="sidebar-header">
        <button className="icon-button sidebar-close" aria-label="关闭详情" onClick={onClose}><X size={16} /></button>
      </div>}

      {loading && <div className="sidebar-loading" aria-live="polite">正在加载…</div>}
      {error && <div className="sidebar-error" role="alert">{error}</div>}

      {detail && !loading && (
        <div className="sidebar-body">
          {/* Name + level badge */}
          <div className="sidebar-title-row">
            <span className={`concept-level-badge level-${detail.concept.level}`}>
              {detail.concept.level === "cluster" ? "主题簇" : detail.concept.level === "core" ? "核心概念" : "细分概念"}
            </span>
            <h2 className="sidebar-concept-name">{detail.concept.name}</h2>
            <div className="sidebar-title-actions">
              <button className="btn-sm btn-ghost sidebar-ask" onClick={() => askAboutConcept(detail.concept.name)}><MessageCircle size={13} />问 AI</button>
              <button className="btn-sm btn-ghost sidebar-ask" onClick={openEditConcept}><Edit2 size={13} />编辑</button>
            </div>
          </div>

          {/* Edit concept form */}
          {editingConcept && (
            <div className="sidebar-edit-form">
              <label><span>名称</span><input value={editName} onChange={(e) => setEditName(e.target.value)} /></label>
              <label><span>定义</span><textarea value={editDefinition} onChange={(e) => setEditDefinition(e.target.value)} rows={3} /></label>
              <label><span>别名（逗号分隔）</span><input value={editAliases} onChange={(e) => setEditAliases(e.target.value)} /></label>
              <label><span>笔记</span><textarea value={editNote} onChange={(e) => setEditNote(e.target.value)} rows={2} /></label>
              <div className="sidebar-edit-actions">
                <button className="btn-sm" disabled={busy} onClick={() => void saveConceptEdit()}>保存</button>
                <button className="btn-sm btn-ghost" onClick={() => setEditingConcept(false)}>取消</button>
              </div>
            </div>
          )}

          {/* Definition */}
          {!editingConcept && detail.concept.definition && (
            <p className="sidebar-definition">{detail.concept.definition}</p>
          )}

          {/* Relations */}
          <section className="sidebar-section">
            <div className="sidebar-section-title sidebar-section-title--action">
              <span>关系</span>
              <button className="icon-button" aria-label="添加关系" onClick={openAddRelation}><Plus size={13} /></button>
            </div>
            {detail.relationships.length > 0 && (
              <ul className="sidebar-rels">
                {detail.relationships.map((rel) => (
                  <RelationItem
                    key={rel.rel_id}
                    rel={rel}
                    selfId={detail.concept.concept_id}
                    onNavigate={onNavigateConcept}
                    onDelete={(relId) => void deleteRelation(relId)}
                  />
                ))}
              </ul>
            )}

            {addingRelation && (
              <div className="sidebar-add-relation">
                <input
                  autoFocus
                  value={relTargetQuery}
                  onChange={(e) => setRelTargetQuery(e.target.value)}
                  placeholder="搜索目标概念…"
                />
                <select value={relType} onChange={(e) => setRelType(e.target.value)}>
                  {REL_TYPE_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <input value={relNote} onChange={(e) => setRelNote(e.target.value)} placeholder="备注（可选）" />
                <div className="sidebar-rel-candidates">
                  {matchingTargets.map((c) => (
                    <button key={c.concept_id} disabled={busy} onClick={() => void saveAddRelation(c.concept_id)}>
                      <Link2 size={13} />{c.name}
                    </button>
                  ))}
                  {matchingTargets.length === 0 && <span className="text-faint">没有匹配的概念</span>}
                </div>
                <div className="sidebar-edit-actions">
                  <button className="btn-sm btn-ghost" onClick={() => setAddingRelation(false)}>取消</button>
                </div>
              </div>
            )}
          </section>

          {/* Evidence / excerpts */}
          {Object.values(detail.evidence).some((ev) => ev.length > 0) && (
            <section className="sidebar-section">
              <div className="sidebar-section-title">原文摘录</div>
              {detail.relationships.map((rel) =>
                (detail.evidence[rel.rel_id] || []).map((ev) => (
                  <div key={ev.evidence_id} className="sidebar-excerpt">
                    <blockquote>"{ev.excerpt}"</blockquote>
                    <cite>
                      <FileText size={12} />
                      {ev.document_title}
                      {ev.location_value && (<span className="excerpt-loc">{" "}— {ev.location_type} {ev.location_value}</span>)}
                      {ev.location_stale && (<span className="excerpt-stale" title="原文可能已更新">⚠</span>)}
                    </cite>
                  </div>
                ))
              )}
            </section>
          )}

          {/* Personal note */}
          <section className="sidebar-section">
            <div className="sidebar-section-title sidebar-section-title--action">
              <span>个人笔记</span>
              {!editingNote && (
                <button className="icon-button" aria-label="编辑笔记" onClick={() => setEditingNote(true)}><Edit2 size={13} /></button>
              )}
            </div>
            {editingNote ? (
              <div className="sidebar-note-editor">
                <textarea autoFocus value={noteValue} onChange={(e) => setNoteValue(e.target.value)} placeholder="记录你的理解、联想或问题…" rows={4} />
                <div className="sidebar-note-actions">
                  <button className="btn-sm" onClick={() => void saveNote()}>保存</button>
                  <button className="btn-sm btn-ghost" onClick={() => { setEditingNote(false); setNoteValue(detail.concept.note || ""); }}>取消</button>
                </div>
              </div>
            ) : (
              <p className="sidebar-note-text">
                {detail.concept.note || <span className="text-faint">点击编辑添加笔记…</span>}
              </p>
            )}
          </section>

          {/* Mastery placeholder */}
          <section className="sidebar-section sidebar-mastery">
            <div className="sidebar-section-title">掌握状态</div>
            <div className="mastery-row">
              <BookOpen size={14} />
              <span className="mastery-label">尚未练习</span>
              <a href="/practice" className="btn-sm btn-ghost mastery-practice"><PenLine size={13} />生成练习题</a>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function RelationItem({ rel, selfId, onNavigate, onDelete }: {
  rel: RelationshipEdge;
  selfId: string;
  onNavigate?: (conceptId: string) => void;
  onDelete?: (relId: string) => void;
}) {
  const label = REL_LABELS[rel.rel_type] ?? rel.rel_type;
  const isFrom = rel.from_id === selfId;
  const targetId = isFrom ? rel.to_id : rel.from_id;
  const targetName = isFrom ? rel.to_name : rel.from_name;
  return (
    <li className="sidebar-rel-item">
      <span className="rel-type">{label}</span>
      <span className="rel-direction">{isFrom ? "→" : "←"}</span>
      <button className="rel-target" onClick={() => onNavigate?.(targetId)} disabled={!onNavigate}>
        {targetName || "未命名概念"}
      </button>
      {onDelete && (
        <button className="icon-button rel-delete" aria-label="删除关系" onClick={() => onDelete(rel.rel_id)}><Trash2 size={13} /></button>
      )}
    </li>
  );
}
