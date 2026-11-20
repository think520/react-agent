import { useMemo, useState } from "react";
import { ArrowRight, Brain, ChevronDown, ChevronUp, Map as MapIcon } from "lucide-react";

import type { KnowledgeContext, KnowledgeContextArtifact } from "../../types";

const COLLAPSED_RELATION_LIMIT = 3;

export function KnowledgeContextCard({ artifact, onShowContext, onOpenConcept, onOpenMap }: {
  artifact: KnowledgeContextArtifact;
  onShowContext: (context: KnowledgeContext) => void;
  onOpenConcept: (conceptId: string) => void;
  onOpenMap: (conceptId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const context = artifact.context;
  const rootId = context.root?.concept_id || context.concepts[0]?.concept_id || "";

  const orderedConcepts = useMemo(() => {
    const list = context.concepts || [];
    if (!rootId) return list.slice(0, 6);
    const root = list.find((item) => item.concept_id === rootId);
    const rest = list.filter((item) => item.concept_id !== rootId);
    return (root ? [root, ...rest] : rest).slice(0, 6);
  }, [context.concepts, rootId]);

  const orderedRelations = useMemo(() => {
    const list = context.relationships || [];
    if (!rootId) return list;
    return [...list].sort((a, b) => {
      const aRoot = a.from_id === rootId || a.to_id === rootId ? 0 : 1;
      const bRoot = b.from_id === rootId || b.to_id === rootId ? 0 : 1;
      return aRoot - bRoot;
    });
  }, [context.relationships, rootId]);

  if (!orderedConcepts.length && !orderedRelations.length) return null;

  const hasStale = orderedRelations.some((relation) => relation.evidence_status === "stale");
  const visibleRelations = expanded ? orderedRelations : orderedRelations.slice(0, COLLAPSED_RELATION_LIMIT);
  const hiddenCount = Math.max(0, orderedRelations.length - COLLAPSED_RELATION_LIMIT);

  return (
    <section className="knowledge-context-block" key={artifact.artifact_id}>
      <header>
        <span className="kc-heading">
          <Brain size={14} aria-hidden="true" />
          <strong>核心概念与关系</strong>
          {hasStale && <small className="kc-stale-badge">部分来源已更新</small>}
        </span>
        <span className="kc-actions">
          {rootId && (
            <button className="text-link" type="button" onClick={() => onOpenMap(rootId)}>
              <MapIcon size={13} aria-hidden="true" />知识地图
            </button>
          )}
          <button className="text-link" type="button" onClick={() => onShowContext(context)}>
            学习书桌
          </button>
        </span>
      </header>

      {orderedConcepts.length > 0 && (
        <div className="kc-concepts" aria-label="核心概念">
          {orderedConcepts.map((concept) => (
            <button
              key={concept.concept_id}
              type="button"
              className={concept.concept_id === rootId ? "kc-concept-pill is-root" : "kc-concept-pill"}
              onClick={() => onOpenConcept(concept.concept_id)}
              title={concept.definition || concept.name}
            >
              {concept.name}
            </button>
          ))}
        </div>
      )}

      {visibleRelations.length > 0 && (
        <div className="kc-relations">
          {visibleRelations.map((relation) => (
            <p key={relation.rel_id}>
              <button type="button" onClick={() => onOpenConcept(relation.from_id)}>{relation.from_name}</button>
              <span className="kc-rel-tag"><ArrowRight size={11} aria-hidden="true" />{relation.rel_type}</span>
              <button type="button" onClick={() => onOpenConcept(relation.to_id)}>{relation.to_name}</button>
            </p>
          ))}
        </div>
      )}

      {hiddenCount > 0 && (
        <button
          className="kc-expand"
          type="button"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <><ChevronUp size={13} aria-hidden="true" />收起关系</> : <><ChevronDown size={13} aria-hidden="true" />展开其余 {hiddenCount} 条关系</>}
        </button>
      )}
    </section>
  );
}
