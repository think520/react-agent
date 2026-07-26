import { Brain } from "lucide-react";

import type { KnowledgeContext, KnowledgeContextArtifact } from "../../types";

export function KnowledgeContextCard({ artifact, onShowContext, onOpenConcept, onOpenMap }: {
  artifact: KnowledgeContextArtifact;
  onShowContext: (context: KnowledgeContext) => void;
  onOpenConcept: (conceptId: string) => void;
  onOpenMap: (conceptId: string) => void;
}) {
  const context = artifact.context;
  return <section className="knowledge-context-block" key={artifact.artifact_id}>
    <header><span><Brain size={15} />概念关系</span><button className="text-link" type="button" onClick={() => onShowContext(context)}>在学习书桌查看</button></header>
    <div>{(context.relationships || []).slice(0, 5).map((relation) => <p key={relation.rel_id}>
      <button type="button" onClick={() => onOpenConcept(relation.from_id)}>{relation.from_name}</button>
      <span>{relation.rel_type}</span>
      <button type="button" onClick={() => onOpenConcept(relation.to_id)}>{relation.to_name}</button>
      {relation.evidence_status === "stale" && <small>来源已变化</small>}
    </p>)}</div>
    {context.concepts[0] && <button className="quiet-button" type="button" onClick={() => onOpenMap(context.root?.concept_id || context.concepts[0].concept_id)}>在知识地图查看</button>}
  </section>;
}
