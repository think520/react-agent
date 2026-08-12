/**
 * CandidateReviewPanel — card-based review for pending concept candidates.
 *
 * Design (knowledge_map_design.md §8):
 *  - 5–8 cards at a time, sorted by confidence (high first)
 *  - Keyboard: Enter=confirm, M=merge(skip), L=label, X=reject, Space=expand
 *  - Top bar: "全部确认（置信度高）" / "稍后处理"
 *  - On confirm: concept fades into map ~200ms
 *  - Extraction mode: follow one durable background job and show its
 *    completed/failed state before reviewing that document's candidates.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, ChevronDown, ChevronUp, Tag, X } from "lucide-react";
import { api } from "../lib/api";
import type { ConceptCandidate } from "../types";

interface ExtractionSource {
  documentId: string;
  documentTitle: string;
  runId?: string;
}

interface Props {
  onClose: () => void;
  onCandidatesChanged: () => void;
  onReturnToSource?: () => void;
  /** When present the panel starts in extraction mode, polling until candidates arrive. */
  extractionSource?: ExtractionSource;
}

const BATCH = 8;
const POLL_INTERVAL_MS = 1200;
const RELATION_TYPES = ["属于", "前置知识", "组成部分", "对比", "应用于", "来源于", "影响", "优化", "示例"];

interface RelationEdit {
  candidate_id: string;
  index: number;
  enabled: boolean;
  rel_type: string;
  direction: "outgoing" | "incoming";
}

type Phase = "extracting" | "ready" | "failed";

export function CandidateReviewPanel({ onClose, onCandidatesChanged, onReturnToSource, extractionSource }: Props) {
  const [candidates, setCandidates] = useState<ConceptCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>(extractionSource?.runId ? "extracting" : "ready");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [completedCount, setCompletedCount] = useState<number | null>(null);
  const [runStage, setRunStage] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [hasReviewed, setHasReviewed] = useState(false);
  const [relationEdits, setRelationEdits] = useState<Record<string, RelationEdit[]>>({});

  useEffect(() => {
    setRelationEdits((current) => {
      const next = { ...current };
      for (const candidate of candidates) {
        if (!next[candidate.candidate_id]) {
          next[candidate.candidate_id] = candidate.suggested_rels.map((relation, index) => ({
            candidate_id: candidate.candidate_id,
            index,
            enabled: relation.enabled !== false,
            rel_type: relation.rel_type,
            direction: relation.direction || "outgoing",
          }));
        }
      }
      return next;
    });
  }, [candidates]);

  // ── Normal load (no extraction intent) ──────────────────────────────
  const loadCandidates = useCallback(() => {
    setLoading(true);
    setError(null);
    api.graphCandidates("pending", extractionSource?.documentId)
      .then((r) => {
        setCandidates(r.candidates.slice(0, BATCH));
        if (extractionSource && !extractionSource.runId) setCompletedCount(r.count);
      })
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [extractionSource]);

  useEffect(() => {
    if (extractionSource?.runId) return; // handled by polling effect
    loadCandidates();
  }, [loadCandidates, extractionSource]);

  // ── Poll the exact extraction job, not the global candidate count ───
  useEffect(() => {
    if (phase !== "extracting" || !extractionSource?.runId) return;
    const source = extractionSource;
    const runId = source.runId as string;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const { run } = await api.graphExtraction(runId);
        if (cancelled) return;
        setRunStage(run.stage || "");
        // Anchor the elapsed timer to the server-side start time so closing
        // and reopening the panel does not reset it to zero (task is not rerun).
        if (typeof run.started_at === "number") {
          setElapsedSeconds(Math.max(0, Math.floor(Date.now() / 1000 - run.started_at)));
        }
        if (run.status === "completed" || run.status === "completed_with_warnings") {
          const result = await api.graphCandidates("pending", source.documentId);
          if (cancelled) return;
          setCandidates(result.candidates.slice(0, BATCH));
          setCompletedCount(run.stored_count);
          setWarnings(run.warnings || []);
          setError(null);
          setLoading(false);
          setPhase("ready");
          onCandidatesChanged();
          return;
        }
        if (run.status === "failed" || run.status === "interrupted") {
          setError(run.error || (run.status === "interrupted"
            ? "提取任务在应用重启时中断，请返回资料后重新提取。"
            : "概念提取失败，请返回资料后重试。"));
          setLoading(false);
          setPhase("failed");
          return;
        }
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "暂时无法读取提取状态。");
        }
      }
      if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
    }

    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [phase, extractionSource, onCandidatesChanged]);

  useEffect(() => {
    if (phase !== "extracting") return;
    const timer = setInterval(() => setElapsedSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase !== "ready" || loading || !hasReviewed || candidates.length > 0) return;
    const timer = window.setTimeout(onClose, 700);
    return () => window.clearTimeout(timer);
  }, [candidates.length, hasReviewed, loading, onClose, phase]);

  // ── Keyboard shortcuts ───────────────────────────────────────────────
  // `act` reads the live `relationEdits` state to decide which relations to
  // submit. The keyboard effect below intentionally does not depend on `act`
  // (its identity changes every render), so we always invoke the latest one
  // through a ref — otherwise the keyboard handler would submit stale
  // relationEdits captured when the effect last ran. The ref is refreshed in
  // an effect because refs may not be written during render.
  const actRef = useRef(act);
  // `act` intentionally changes identity every render; run on every commit so
  // the ref stays fresh. The keyboard effect reads actRef, not `act`.
  useEffect(() => {
    actRef.current = act;
  });
  useEffect(() => {
    if (phase !== "ready") return;
    const focused = () => candidates.find((c) => c.candidate_id === expandedId) ?? candidates[0];
    const handler = (e: KeyboardEvent) => {
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") return;
      const cand = focused();
      if (!cand) return;
      if (e.key === "Enter") { void actRef.current(cand.candidate_id, "confirm"); }
      else if (e.key === "l" || e.key === "L") { void actRef.current(cand.candidate_id, "label"); }
      else if (e.key === "x" || e.key === "X") { void actRef.current(cand.candidate_id, "reject"); }
      else if (e.key === " ") {
        e.preventDefault();
        setExpandedId((id) => id === cand.candidate_id ? null : cand.candidate_id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [candidates, expandedId, phase]);

  async function act(candidateId: string, action: "confirm" | "reject" | "label") {
    setActing(candidateId);
    setError(null);
    try {
      await api.graphCandidateAction(candidateId, action, 14, action === "confirm" ? relationEdits[candidateId] || [] : []);
      setHasReviewed(true);
      setCandidates((prev) => prev.filter((c) => c.candidate_id !== candidateId));
      onCandidatesChanged();
      if (expandedId === candidateId) setExpandedId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请重试。");
    } finally {
      setActing(null);
    }
  }

  async function confirmAllHigh() {
    const highConf = candidates.filter((c) => c.confidence === "high");
    if (!highConf.length) return;
    setActing("batch");
    setError(null);
    try {
      await api.graphConfirmCandidates(
        highConf.map((candidate) => candidate.candidate_id),
        highConf.flatMap((candidate) => relationEdits[candidate.candidate_id] || []),
      );
      setHasReviewed(true);
      setCandidates((current) => current.filter((candidate) => candidate.confidence !== "high"));
      onCandidatesChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量确认失败，请重试。");
    } finally {
      setActing(null);
    }
  }

  function updateRelation(candidateId: string, index: number, changes: Partial<RelationEdit>) {
    setRelationEdits((current) => ({
      ...current,
      [candidateId]: (current[candidateId] || []).map((item) => item.index === index ? { ...item, ...changes } : item),
    }));
  }

  const confidenceLabel = (c: CandidateConfidence) =>
    c === "high" ? "置信度：高" : c === "medium" ? "置信度：中" : "置信度：低";

  const highCount = candidates.filter((c) => c.confidence === "high").length;
  const stageLabel: Record<string, string> = {
    scanning_sections: "正在扫描章节",
    merging_concepts: "正在合并并去重概念",
    analyzing_local_relationships: "概念已识别，正在分析章节内关系",
    analyzing_cross_section_relationships: "正在补全跨章节关系",
    quality_check: "正在检查提取质量",
    supplementing: "质量不足，正在定向补提一次",
    ready_for_review: "候选已准备好",
  };

  return (
    <div className="candidate-panel" role="dialog" aria-modal="true" aria-label="概念候选审查">
      {/* Header */}
      <div className="candidate-panel-header">
        <div className="candidate-panel-title">
          {phase !== "ready" && extractionSource ? (
            <span>
              来源：《{extractionSource.documentTitle}》
            </span>
          ) : (
            <>
              <span>待审查概念候选</span>
              {candidates.length > 0 && (
                <span className="candidate-badge">{candidates.length}</span>
              )}
            </>
          )}
        </div>
        <div className="candidate-panel-actions">
          {phase === "ready" && highCount > 0 && (
            <button
              className="btn-sm"
              onClick={() => void confirmAllHigh()}
              disabled={acting !== null}
            >
              全部确认（置信度高 · {highCount} 个）
            </button>
          )}
          <button className="btn-sm btn-ghost" onClick={onClose}>{phase === "extracting" ? "关闭并后台继续" : "稍后处理"}</button>
          <button className="icon-button candidate-panel-close" aria-label="关闭审查窗口" onClick={onClose}><X size={16} /></button>
        </div>
      </div>

      {/* Keyboard hint — only in review mode */}
      {phase === "ready" && (
        <div className="candidate-kbd-hint" aria-hidden="true">
          <kbd>Enter</kbd> 确认 &nbsp;
          <kbd>L</kbd> 降为标签 &nbsp;
          <kbd>X</kbd> 忽略 &nbsp;
          <kbd>Space</kbd> 展开/收起
        </div>
      )}

      {/* Extraction progress */}
      {phase === "extracting" && extractionSource && (
        <div className="candidate-extracting" role="status" aria-live="polite">
          <div className="extracting-spinner" aria-hidden="true" />
          <p className="extracting-message">
            {stageLabel[runStage] || "正在提取概念"} · <cite>《{extractionSource.documentTitle}》</cite>
          </p>
          <p className="extracting-hint">
            已等待 {elapsedSeconds} 秒。任务会在后台继续，完成后自动展示候选。
          </p>
          {elapsedSeconds >= 30 && <p className="extracting-slow">当前模型响应较慢，你可以稍后处理，不会中断任务。</p>}
        </div>
      )}

      {/* Failed */}
      {phase === "failed" && (
        <div className="candidate-error" role="alert">
          <strong>提取失败</strong>
          <p>{error || "模型没有返回可用结果。"}</p>
          {onReturnToSource && <button className="btn-sm" onClick={onReturnToSource}>返回资料重试</button>}
        </div>
      )}

      {phase === "ready" && completedCount !== null && (
        <div className="candidate-complete" role="status">
          <CheckCircle size={16} />
          <span>提取完成，找到 {completedCount} 个候选概念{warnings.length ? ` · ${warnings.join("；")}` : ""}</span>
        </div>
      )}

      {/* Normal loading/error/empty (review phase) */}
      {phase === "ready" && loading && (
        <div className="candidate-loading">正在加载候选…</div>
      )}
      {phase === "ready" && error && (
        <div className="candidate-error" role="alert">{error}</div>
      )}
      {phase === "ready" && !loading && !error && candidates.length === 0 && (
        <div className="candidate-empty">
          <CheckCircle size={32} />
          <p>{hasReviewed ? "审查完成，正在返回图谱…" : completedCount === 0 ? "这份资料没有识别到足够明确的概念" : "没有待审查的概念候选"}</p>
        </div>
      )}

      {phase === "ready" && (
        <ul className="candidate-list">
          {candidates.map((cand) => (
            <CandidateCard
              key={cand.candidate_id}
              candidate={cand}
              expanded={expandedId === cand.candidate_id}
              acting={acting === cand.candidate_id || acting === "batch"}
              onToggleExpand={() =>
                setExpandedId((id) => id === cand.candidate_id ? null : cand.candidate_id)
              }
              onConfirm={() => void act(cand.candidate_id, "confirm")}
              onLabel={() => void act(cand.candidate_id, "label")}
              onReject={() => void act(cand.candidate_id, "reject")}
              confidenceLabel={confidenceLabel(cand.confidence)}
              relationEdits={relationEdits[cand.candidate_id] || []}
              onRelationEdit={(index, changes) => updateRelation(cand.candidate_id, index, changes)}
            />
          ))}
        </ul>
      )}
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
  relationEdits: RelationEdit[];
  onRelationEdit: (index: number, changes: Partial<RelationEdit>) => void;
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
  relationEdits,
  onRelationEdit,
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
              {cand.suggested_rels.map((relation, index) => {
                const edit = relationEdits.find((item) => item.index === index) || {
                  enabled: true, rel_type: relation.rel_type, direction: "outgoing" as const,
                };
                return <div key={index} className={`candidate-relation-review ${edit.enabled ? "" : "disabled"}`}>
                  <label><input type="checkbox" checked={edit.enabled} onChange={(event) => onRelationEdit(index, { enabled: event.target.checked })} />保留</label>
                  <span>{edit.direction === "outgoing" ? cand.name : relation.to_name}</span>
                  <select value={edit.rel_type} disabled={!edit.enabled} onChange={(event) => onRelationEdit(index, { rel_type: event.target.value })}>
                    {RELATION_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                  </select>
                  <span>{edit.direction === "outgoing" ? relation.to_name : cand.name}</span>
                  <button className="btn-sm btn-ghost" type="button" disabled={!edit.enabled} onClick={() => onRelationEdit(index, { direction: edit.direction === "outgoing" ? "incoming" : "outgoing" })}>反转方向</button>
                  {relation.excerpt && <blockquote>“{relation.excerpt}”</blockquote>}
                </div>;
              })}
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
