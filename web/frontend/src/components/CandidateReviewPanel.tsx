/**
 * CandidateReviewPanel — card-based review for pending concept candidates.
 *
 * Design (knowledge_map_design.md §8):
 *  - 5–8 cards at a time, sorted by confidence (high first)
 *  - Keyboard: Enter=confirm, M=merge(skip), L=label, X=reject, Space=expand
 *  - Top bar: "全部确认（置信度高）" / "稍后处理"
 *  - On confirm: concept fades into map ~200ms
 */

import { useCallback, useEffect, useState } from "react";
import { CheckCircle, ChevronDown, ChevronUp, Tag, X } from "lucide-react";
import { api } from "../lib/api";
import type { ConceptCandidate } from "../types";

interface Props {
  onClose: () => void;
  onCandidatesChanged: () => void;
}

const BATCH = 8;

export function CandidateReviewPanel({ onClose, onCandidatesChanged }: Props) {
  const [candidates, setCandidates] = useState<ConceptCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);

  const loadCandidates = useCallback(() => {
    setLoading(true);
    setError(null);
    api.graphCandidates("pending")
      .then((r) => setCandidates(r.candidates.slice(0, BATCH)))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadCandidates(); }, [loadCandidates]);

  // Keyboard shortcuts when panel is open
  useEffect(() => {
    const focused = () => candidates.find((c) => c.candidate_id === expandedId) ?? candidates[0];
    const handler = (e: KeyboardEvent) => {
      // Ignore when user is typing in an input
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") return;
      const cand = focused();
      if (!cand) return;
      if (e.key === "Enter") { void act(cand.candidate_id, "confirm"); }
      else if (e.key === "l" || e.key === "L") { void act(cand.candidate_id, "label"); }
      else if (e.key === "x" || e.key === "X") { void act(cand.candidate_id, "reject"); }
      else if (e.key === " ") {
        e.preventDefault();
        setExpandedId((id) => id === cand.candidate_id ? null : cand.candidate_id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates, expandedId]);

  async function act(candidateId: string, action: "confirm" | "reject" | "label") {
    setActing(candidateId);
    try {
      await api.graphCandidateAction(candidateId, action);
      setCandidates((prev) => prev.filter((c) => c.candidate_id !== candidateId));
      onCandidatesChanged();
      if (expandedId === candidateId) setExpandedId(null);
    } catch {
      // keep in list on failure
    } finally {
      setActing(null);
    }
  }

  async function confirmAllHigh() {
    const highConf = candidates.filter((c) => c.confidence === "high");
    for (const c of highConf) {
      await act(c.candidate_id, "confirm");
    }
  }

  const confidenceLabel = (c: CandidateConfidence) =>
    c === "high" ? "置信度：高" : c === "medium" ? "置信度：中" : "置信度：低";

  const highCount = candidates.filter((c) => c.confidence === "high").length;

  return (
    <div className="candidate-panel" role="dialog" aria-label="概念候选审查">
      {/* Header */}
      <div className="candidate-panel-header">
        <div className="candidate-panel-title">
          <span>待审查概念候选</span>
          {candidates.length > 0 && (
            <span className="candidate-badge">{candidates.length}</span>
          )}
        </div>
        <div className="candidate-panel-actions">
          {highCount > 0 && (
            <button
              className="btn-sm"
              onClick={() => void confirmAllHigh()}
              disabled={acting !== null}
            >
              全部确认（置信度高 · {highCount} 个）
            </button>
          )}
          <button className="btn-sm btn-ghost" onClick={onClose}>稍后处理</button>
        </div>
      </div>

      {/* Keyboard hint */}
      <div className="candidate-kbd-hint" aria-hidden="true">
        <kbd>Enter</kbd> 确认 &nbsp;
        <kbd>L</kbd> 降为标签 &nbsp;
        <kbd>X</kbd> 忽略 &nbsp;
        <kbd>Space</kbd> 展开/收起
      </div>

      {/* Content */}
      {loading && <div className="candidate-loading">正在加载候选…</div>}
      {error && <div className="candidate-error" role="alert">{error}</div>}
      {!loading && !error && candidates.length === 0 && (
        <div className="candidate-empty">
          <CheckCircle size={32} />
          <p>没有待审查的概念候选</p>
        </div>
      )}

      <ul className="candidate-list">
        {candidates.map((cand) => (
          <CandidateCard
            key={cand.candidate_id}
            candidate={cand}
            expanded={expandedId === cand.candidate_id}
            acting={acting === cand.candidate_id}
            onToggleExpand={() =>
              setExpandedId((id) => id === cand.candidate_id ? null : cand.candidate_id)
            }
            onConfirm={() => void act(cand.candidate_id, "confirm")}
            onLabel={() => void act(cand.candidate_id, "label")}
            onReject={() => void act(cand.candidate_id, "reject")}
            confidenceLabel={confidenceLabel(cand.confidence)}
          />
        ))}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------
// Card
// ------------------------------------------------------------------

type CandidateConfidence = "high" | "medium" | "low";

interface CardProps {
  candidate: ConceptCandidate;
  expanded: boolean;
  acting: boolean;
  onToggleExpand: () => void;
  onConfirm: () => void;
  onLabel: () => void;
  onReject: () => void;
  confidenceLabel: string;
}

function CandidateCard({
  candidate: cand,
  expanded,
  acting,
  onToggleExpand,
  onConfirm,
  onLabel,
  onReject,
  confidenceLabel,
}: CardProps) {
  return (
    <li className={`candidate-card confidence-${cand.confidence} ${acting ? "acting" : ""}`}>
      {/* Top row */}
      <div className="candidate-card-top">
        <div className="candidate-card-meta">
          <span className={`concept-level-badge level-${cand.level}`}>
            {cand.level === "core" ? "核心概念" : "细分概念"}
          </span>
          <span className="candidate-confidence">{confidenceLabel}</span>
        </div>
        <button
          className="icon-button candidate-expand"
          aria-label={expanded ? "收起" : "展开"}
          onClick={onToggleExpand}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Name + definition */}
      <div className="candidate-name">{cand.name}</div>
      {cand.definition && (
        <p className="candidate-definition">{cand.definition}</p>
      )}

      {/* Expanded: excerpt + suggested rels */}
      {expanded && (
        <div className="candidate-expanded">
          {cand.excerpt && (
            <blockquote className="candidate-excerpt">
              "{cand.excerpt}"
              {cand.source_doc_title && (
                <cite> — 《{cand.source_doc_title}》</cite>
              )}
            </blockquote>
          )}
          {cand.suggested_rels.length > 0 && (
            <div className="candidate-rels">
              <span className="candidate-rels-label">建议关系：</span>
              {cand.suggested_rels.map((r, i) => (
                <span key={i} className="candidate-rel-chip">
                  {r.rel_type} {r.to_name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="candidate-card-actions">
        <button
          className="btn-sm btn-confirm"
          onClick={onConfirm}
          disabled={acting}
        >
          <CheckCircle size={13} />确认
        </button>
        <button
          className="btn-sm btn-ghost"
          onClick={onLabel}
          disabled={acting}
          title="降为标签，不占用图谱节点"
        >
          <Tag size={13} />标签
        </button>
        <button
          className="btn-sm btn-ghost"
          onClick={onReject}
          disabled={acting}
          title="忽略，14天内不再出现"
        >
          <X size={13} />忽略
        </button>
      </div>
    </li>
  );
}
