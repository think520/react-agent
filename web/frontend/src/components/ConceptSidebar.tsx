/**
 * ConceptSidebar — slide-in detail panel for a selected concept node.
 *
 * Design (knowledge_map_design.md §9.6):
 *   - Slide in from right ~180ms ease-out, graph shifts left
 *   - Close: Esc or click canvas background
 *   - Fixed structure: name / definition / relations / excerpts / note / mastery
 */

import { useEffect, useRef, useState } from "react";
import { BookOpen, Edit2, ExternalLink, FileText, PenLine, X } from "lucide-react";
import { api } from "../lib/api";
import type { ConceptDetail, ConceptNode, RelationshipEdge } from "../types";

interface Props {
  conceptId: string | null;
  onClose: () => void;
  onConceptUpdated?: (concept: ConceptNode) => void;
}

const REL_LABELS: Record<string, string> = {
  "属于": "属于",
  "前置知识": "前置知识",
  "组成部分": "组成部分",
  "对比": "对比",
  "应用于": "应用于",
  "来源于": "来源于",
};

export function ConceptSidebar({ conceptId, onClose, onConceptUpdated }: Props) {
  const [detail, setDetail] = useState<ConceptDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingNote, setEditingNote] = useState(false);
  const [noteValue, setNoteValue] = useState("");
  const sidebarRef = useRef<HTMLElement>(null);

  // Load concept detail when conceptId changes
  useEffect(() => {
    if (!conceptId) {
      setDetail(null);
      return;
    }
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
      const result = await api.graphPatchConcept(detail.concept.concept_id, {
        name: detail.concept.name,
        level: detail.concept.level,
        definition: detail.concept.definition,
        aliases: detail.concept.aliases,
        topic_ids: detail.concept.topic_ids,
        note: noteValue,
      });
      setDetail((prev) => prev ? { ...prev, concept: result.concept } : prev);
      onConceptUpdated?.(result.concept);
    } catch {
      // silently swallow for now; user can retry
    } finally {
      setEditingNote(false);
    }
  }

  if (!conceptId) return null;

  return (
    <aside
      ref={sidebarRef}
      className={`concept-sidebar ${conceptId ? "open" : ""}`}
      aria-label="概念详情"
    >
      <div className="sidebar-header">
        <button
          className="icon-button sidebar-close"
          aria-label="关闭详情"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>

      {loading && (
        <div className="sidebar-loading" aria-live="polite">正在加载…</div>
      )}
      {error && (
        <div className="sidebar-error" role="alert">{error}</div>
      )}

      {detail && !loading && (
        <div className="sidebar-body">
          {/* Name + level badge */}
          <div className="sidebar-title-row">
            <span className={`concept-level-badge level-${detail.concept.level}`}>
              {detail.concept.level === "cluster" ? "主题簇"
                : detail.concept.level === "core" ? "核心概念"
                : "细分概念"}
            </span>
            <h2 className="sidebar-concept-name">{detail.concept.name}</h2>
          </div>

          {/* Definition */}
          {detail.concept.definition && (
            <p className="sidebar-definition">{detail.concept.definition}</p>
          )}

          {/* Relations */}
          {detail.relationships.length > 0 && (
            <section className="sidebar-section">
              <div className="sidebar-section-title">关系</div>
              <ul className="sidebar-rels">
                {detail.relationships.map((rel) => (
                  <RelationItem
                    key={rel.rel_id}
                    rel={rel}
                    selfId={detail.concept.concept_id}
                  />
                ))}
              </ul>
            </section>
          )}

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
                      {ev.location_value && (
                        <span className="excerpt-loc">
                          {" "}— {ev.location_type} {ev.location_value}
                        </span>
                      )}
                      {ev.location_stale && (
                        <span className="excerpt-stale" title="原文可能已更新">⚠</span>
                      )}
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
                <button
                  className="icon-button"
                  aria-label="编辑笔记"
                  onClick={() => setEditingNote(true)}
                >
                  <Edit2 size={13} />
                </button>
              )}
            </div>
            {editingNote ? (
              <div className="sidebar-note-editor">
                <textarea
                  autoFocus
                  value={noteValue}
                  onChange={(e) => setNoteValue(e.target.value)}
                  placeholder="记录你的理解、联想或问题…"
                  rows={4}
                />
                <div className="sidebar-note-actions">
                  <button className="btn-sm" onClick={() => void saveNote()}>保存</button>
                  <button
                    className="btn-sm btn-ghost"
                    onClick={() => {
                      setEditingNote(false);
                      setNoteValue(detail.concept.note || "");
                    }}
                  >
                    取消
                  </button>
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
              <a href="/practice" className="btn-sm btn-ghost mastery-practice">
                <PenLine size={13} />生成练习题
              </a>
            </div>
          </section>
        </div>
      )}
    </aside>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function RelationItem({ rel, selfId }: { rel: RelationshipEdge; selfId: string }) {
  const label = REL_LABELS[rel.rel_type] ?? rel.rel_type;
  const isFrom = rel.from_id === selfId;
  return (
    <li className="sidebar-rel-item">
      <span className="rel-type">{label}</span>
      <span className="rel-direction">{isFrom ? "→" : "←"}</span>
      <span className="rel-target-id">{isFrom ? rel.to_id : rel.from_id}</span>
    </li>
  );
}
