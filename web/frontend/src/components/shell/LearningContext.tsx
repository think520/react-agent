/**
 * 学习书桌（右栏内容）：回答边界 / 当前资料范围 / 本轮来源 / 相关知识 / 学习回流。
 * 2026-10-17 从 AppShell.tsx 抽出（M2 拆分，行数不变、行为不变）。
 */
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, Library, Map, PenLine, Sparkles } from "lucide-react";

import { readerLocation } from "../../lib/documentLinks";
import { groupAttributionSources, textValue } from "../common";
import type { Attribution, DocumentSummary, KnowledgeContext, ReviewQueue } from "../../types";

export function LearningContext({
  documents,
  review,
  selectedDocumentIds,
  toggleDocumentScope,
  knowledgeContext,
  sourceContext,
  onOpenConcept,
  onOpenMap,
}: {
  documents: DocumentSummary[];
  review: ReviewQueue | null;
  selectedDocumentIds: string[];
  toggleDocumentScope: (documentId: string) => void;
  knowledgeContext: KnowledgeContext | null;
  sourceContext: Attribution | null;
  onOpenConcept: (conceptId: string) => void;
  onOpenMap: (conceptId: string) => void;
}) {
  const [tab, setTab] = useState<"sources" | "learning">("sources");
  const due = review?.due_concepts.length || 0;
  const weak = review?.weaknesses.length || 0;
  return (
    <div className="context-content">
      <div className="context-tabs" role="tablist" aria-label="学习书桌视图">
        <button className={tab === "sources" ? "active" : ""} role="tab" aria-selected={tab === "sources"} onClick={() => setTab("sources")}>资料</button>
        <button className={tab === "learning" ? "active" : ""} role="tab" aria-selected={tab === "learning"} onClick={() => setTab("learning")}>学习</button>
      </div>
      {tab === "sources" ? <>
        <section className="context-section">
          <div className="context-heading"><Sparkles size={16} />回答边界</div>
          <p className="context-copy">优先使用本地资料；网页来源、AI 补充和待核实内容会分别标注。</p>
        </section>
        <section className="context-section">
          <div className="context-heading"><Library size={16} />当前资料范围</div>
          {documents.length ? <div className="context-list">{documents.slice(0, 5).map((document) => (
            <button className={`context-document scope-document ${selectedDocumentIds.includes(document.document_id) ? "selected" : ""}`} key={document.document_id} onClick={() => toggleDocumentScope(document.document_id)}>
              <span className="document-icon"><FileText size={15} /></span>
              <span><strong>{document.title || document.source}</strong><small>{document.course || document.kind || "本地资料"}</small></span>
              <i aria-hidden="true" />
            </button>
          ))}</div> : <div className="context-empty-action"><p className="context-empty">还没有导入资料。</p><NavLink to="/library" className="text-link">导入第一份资料</NavLink></div>}
          {documents.length > 5 && <NavLink to="/library" className="text-link context-library-link">在资料库中选择更多</NavLink>}
        </section>
        {sourceContext && <section className="context-section response-sources">
          <div className="context-heading"><FileText size={16} />本轮回答来源</div>
          <div className="context-source-list">
            {groupAttributionSources(sourceContext.sources).map((group) => {
              return <details className="context-source-group" key={group.key}>
                <summary><strong>{group.title}</strong><small>命中 {group.sources.length} 处</small></summary>
                <div>{group.sources.map((source, index) => <section key={source.source_id || index}>
                  <small>{source.heading || (source.page ? `第 ${source.page} 页` : source.slide ? `第 ${source.slide} 页` : "原文片段")}</small>
                  {source.excerpt && <p>{source.excerpt}</p>}
                  {source.document_id && <NavLink className="text-link" to={readerLocation(source) ?? "/library"}>打开原文</NavLink>}
                </section>)}</div>
              </details>;
            })}
            {!sourceContext.sources.length && <p className="context-empty">资料库中没有找到直接依据。</p>}
          </div>
        </section>}
        {knowledgeContext && <section className="context-section related-knowledge">
          <div className="context-heading"><Map size={16} />相关知识</div>
          <div className="context-relation-list">
            {(knowledgeContext.relationships || []).slice(0, 6).map((relation) => <div className="context-relation" key={relation.rel_id}>
              <button type="button" onClick={() => onOpenConcept(relation.from_id)}>{relation.from_name}</button>
              <span>{relation.rel_type}</span>
              <button type="button" onClick={() => onOpenConcept(relation.to_id)}>{relation.to_name}</button>
              {relation.evidence_status !== "valid" && <small>{relation.evidence_status === "stale" ? "来源已变化" : "暂无原文证据"}</small>}
            </div>)}
            {!(knowledgeContext.relationships || []).length && knowledgeContext.concepts.slice(0, 6).map((concept) => <button className="context-concept" type="button" key={concept.concept_id} onClick={() => onOpenConcept(concept.concept_id)}>{concept.name}</button>)}
          </div>
          {knowledgeContext.concepts[0] && <button className="text-link" type="button" onClick={() => onOpenMap(knowledgeContext.root?.concept_id || knowledgeContext.concepts[0].concept_id)}>在知识地图查看</button>}
        </section>}
      </> : <>
        <section className="context-section">
          <div className="context-heading"><BookOpen size={16} />学习回流</div>
          <div className="context-metrics">
            <div><strong>{due}</strong><span>到期概念</span></div>
            <div><strong>{weak}</strong><span>薄弱点</span></div>
          </div>
          <NavLink to="/review" className="text-link">查看今日复习</NavLink>
        </section>
        <section className="context-section">
          <div className="context-heading"><PenLine size={16} />接下来</div>
          <div className="context-next-list">
            {(review?.due_concepts || []).slice(0, 3).map((item, index) => <div key={index}><span>{index + 1}</span><strong>{textValue(item, ["concept", "title", "name"], "待复习知识点")}</strong></div>)}
            {!due && <p className="context-empty">今天没有到期内容，可以开始一轮新练习。</p>}
          </div>
        </section>
      </>}
    </div>
  );
}
