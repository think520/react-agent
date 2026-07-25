/**
 * KnowledgeMapPage — P5E.6 主页面
 *
 * 三视图：地图 / 目录 / 来源
 * 共享筛选状态：selectedTopicId / searchQuery
 * 设计约束：
 *  - 视图切换淡入 ~120ms，无位置动画
 *  - 节点详情侧栏 slide-in ~180ms（由 ConceptSidebar 负责）
 *  - 候选区单独面板（CandidateReviewPanel）
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { List, Map as MapIcon, Search, Sparkles, Table } from "lucide-react";
import { api } from "../lib/api";
import type {
  ConceptCandidate,
  ConceptNode,
  GraphState,
  KnowledgeMapView,
  RelationshipEdge,
} from "../types";
import { GraphCanvas } from "../components/GraphCanvas";
import { ConceptSidebar } from "../components/ConceptSidebar";
import { CandidateReviewPanel } from "../components/CandidateReviewPanel";

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export function KnowledgeMapPage() {
  const [view, setView] = useState<KnowledgeMapView>("map");
  const [graphState, setGraphState] = useState<GraphState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCandidates, setShowCandidates] = useState(false);
  const positionsSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const state = await api.graphState({
        topic_id: selectedTopicId ?? undefined,
        include_candidates: false,
      });
      setGraphState(state);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载图谱失败");
    } finally {
      setLoading(false);
    }
  }, [selectedTopicId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  // Filtered data for directory + sources views
  const filteredConcepts = (graphState?.concepts ?? []).filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLocaleLowerCase();
    return (
      c.name.toLocaleLowerCase().includes(q) ||
      c.definition.toLocaleLowerCase().includes(q)
    );
  });

  const topics = (graphState?.concepts ?? []).filter(
    (c) => c.level === "cluster",
  );

  function handleNodeClick(conceptId: string) {
    setSelectedConceptId(conceptId);
  }

  function handleBackgroundClick() {
    setSelectedConceptId(null);
  }

  function handleViewSwitch(next: KnowledgeMapView) {
    setView(next);
    // selectedConceptId / selectedTopicId carry over across views
  }

  // Debounced position save after drag
  function handlePositionsChanged(
    positions: Array<{ concept_id: string; x: number; y: number }>,
  ) {
    if (positionsSaveTimer.current) clearTimeout(positionsSaveTimer.current);
    positionsSaveTimer.current = setTimeout(() => {
      void api.graphSavePositions(positions);
    }, 800);
  }

  function handleCandidatesChanged() {
    void loadGraph();
  }

  const pendingCount = graphState?.pending_count ?? 0;
  const isEmpty = !loading && !error && (graphState?.total_concepts ?? 0) === 0;

  return (
    <div className={`knowledge-map-page ${selectedConceptId ? "sidebar-open" : ""}`}>
      {/* Top toolbar */}
      <div className="km-toolbar">
        <div className="km-view-tabs" role="tablist" aria-label="知识地图视图">
          {(
            [
              { id: "map", label: "地图", icon: MapIcon },
              { id: "directory", label: "目录", icon: List },
              { id: "sources", label: "来源", icon: Table },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              aria-selected={view === id}
              className={`km-tab ${view === id ? "active" : ""}`}
              onClick={() => handleViewSwitch(id)}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>

        {/* Topic filter */}
        {topics.length > 0 && (
          <select
            className="km-topic-filter"
            value={selectedTopicId ?? ""}
            onChange={(e) => setSelectedTopicId(e.target.value || null)}
            aria-label="按主题筛选"
          >
            <option value="">全部主题</option>
            {topics.map((t) => (
              <option key={t.concept_id} value={t.concept_id}>
                {t.name}
              </option>
            ))}
          </select>
        )}

        {/* Search (directory + sources) */}
        {view !== "map" && (
          <label className="km-search">
            <Search size={14} aria-hidden="true" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索概念名称…"
              aria-label="搜索概念"
            />
          </label>
        )}

        {/* Candidate alert */}
        {pendingCount > 0 && !showCandidates && (
          <button
            className="km-candidate-alert"
            onClick={() => setShowCandidates(true)}
          >
            <Sparkles size={14} />
            {pendingCount} 个待审查概念候选
          </button>
        )}
      </div>

      {/* Main content */}
      <div className="km-content">
        {/* Error */}
        {error && (
          <div className="km-error" role="alert">
            {error}
            <button onClick={() => void loadGraph()}>重试</button>
          </div>
        )}

        {/* Empty state */}
        {isEmpty && !error && (
          <div className="km-empty">
            <MapIcon size={40} />
            <h3>还没有概念</h3>
            <p>
              在资料库导入资料后，点击资料卡上的"提取概念"按钮，
              AI 会识别核心概念和关系候选，由你确认后加入图谱。
            </p>
            <a href="/library" className="btn-sm">
              去资料库
            </a>
          </div>
        )}

        {/* Map view */}
        {view === "map" && !isEmpty && (
          <div className="km-map-wrapper">
            {loading ? (
              <div className="km-loading" aria-live="polite">正在加载图谱…</div>
            ) : (
              <GraphCanvas
                concepts={graphState?.concepts ?? []}
                relationships={graphState?.relationships ?? []}
                selectedConceptId={selectedConceptId}
                onNodeClick={handleNodeClick}
                onBackgroundClick={handleBackgroundClick}
              />
            )}
          </div>
        )}

        {/* Directory view */}
        {view === "directory" && (
          <DirectoryView
            concepts={filteredConcepts}
            selectedConceptId={selectedConceptId}
            onSelect={setSelectedConceptId}
          />
        )}

        {/* Sources view */}
        {view === "sources" && (
          <SourcesView
            concepts={filteredConcepts}
            relationships={graphState?.relationships ?? []}
            selectedConceptId={selectedConceptId}
            onConceptSelect={setSelectedConceptId}
          />
        )}
      </div>

      {/* Concept detail sidebar */}
      <ConceptSidebar
        conceptId={selectedConceptId}
        onClose={() => setSelectedConceptId(null)}
        onConceptUpdated={(updated) => {
          setGraphState((prev) =>
            prev
              ? {
                  ...prev,
                  concepts: prev.concepts.map((c) =>
                    c.concept_id === updated.concept_id ? { ...c, ...updated } : c,
                  ),
                }
              : prev,
          );
        }}
      />

      {/* Candidate review panel */}
      {showCandidates && (
        <div className="km-candidate-overlay">
          <CandidateReviewPanel
            onClose={() => setShowCandidates(false)}
            onCandidatesChanged={handleCandidatesChanged}
          />
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------
// Directory view
// ------------------------------------------------------------------

interface DirectoryViewProps {
  concepts: ConceptNode[];
  selectedConceptId: string | null;
  onSelect: (id: string) => void;
}

function DirectoryView({ concepts, selectedConceptId, onSelect }: DirectoryViewProps) {
  const clusters = concepts.filter((c) => c.level === "cluster");
  const cores = concepts.filter((c) => c.level === "core");
  const details = concepts.filter((c) => c.level === "detail");

  const Section = ({
    title,
    items,
  }: {
    title: string;
    items: ConceptNode[];
  }) =>
    items.length ? (
      <section className="km-dir-section">
        <div className="km-dir-section-title">{title}</div>
        <ul className="km-dir-list">
          {items.map((c) => (
            <li key={c.concept_id}>
              <button
                className={`km-dir-item ${selectedConceptId === c.concept_id ? "selected" : ""}`}
                onClick={() => onSelect(c.concept_id)}
              >
                <span className="km-dir-name">{c.name}</span>
                {c.definition && (
                  <span className="km-dir-def">{c.definition}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </section>
    ) : null;

  if (!concepts.length) {
    return (
      <div className="km-dir-empty">
        <p>没有找到匹配的概念。</p>
      </div>
    );
  }

  return (
    <div className="km-directory">
      <Section title="主题簇" items={clusters} />
      <Section title="核心概念" items={cores} />
      <Section title="细分概念" items={details} />
    </div>
  );
}

// ------------------------------------------------------------------
// Sources view — concepts grouped by source document
// ------------------------------------------------------------------

interface SourcesViewProps {
  concepts: ConceptNode[];
  relationships: RelationshipEdge[];
  selectedConceptId: string | null;
  onConceptSelect: (id: string) => void;
}

function SourcesView({ concepts, relationships, selectedConceptId, onConceptSelect }: SourcesViewProps) {
  if (!concepts.length) {
    return <div className="km-src-empty"><p>暂无概念数据。</p></div>;
  }
  return (
    <div className="km-sources">
      <p className="km-src-hint">
        来源视图显示已确认概念列表及其关系数量。
        点击概念名可查看详情。
      </p>
      <table className="km-src-table" aria-label="概念来源表">
        <thead>
          <tr>
            <th>概念</th>
            <th>层级</th>
            <th>关系数</th>
            <th>定义</th>
          </tr>
        </thead>
        <tbody>
          {concepts.map((c) => {
            const relCount = relationships.filter(
              (r) => r.from_id === c.concept_id || r.to_id === c.concept_id,
            ).length;
            return (
              <tr
                key={c.concept_id}
                className={selectedConceptId === c.concept_id ? "selected" : ""}
              >
                <td>
                  <button className="km-src-name" onClick={() => onConceptSelect(c.concept_id)}>
                    {c.name}
                  </button>
                </td>
                <td>
                  <span className={`concept-level-badge level-${c.level}`}>
                    {c.level === "cluster" ? "主题簇"
                      : c.level === "core" ? "核心"
                      : "细分"}
                  </span>
                </td>
                <td>{relCount}</td>
                <td className="km-src-def">{c.definition || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
