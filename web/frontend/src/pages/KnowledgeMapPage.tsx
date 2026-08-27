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
import { Link, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { List, Map as MapIcon, Link2, Maximize2, Network, Plus, Search, Sparkles, Table, X } from "lucide-react";
import { api } from "../lib/api";
import { useUiStore } from "../stores/uiStore";
import type {
  ConceptNode,
  GraphState,
  KnowledgeMapView,
  RelationshipEdge,
} from "../types";
import { GraphCanvas, type ForceParams } from "../components/GraphCanvas";
import { CandidateReviewPanel } from "../components/CandidateReviewPanel";
import { DropdownSelect } from "../components/DropdownSelect";
import { Modal } from "../ui/Modal";
import type { AppOutletContext } from "../components/AppShell";

interface ExtractionSource {
  documentId: string;
  documentTitle: string;
  runId?: string;
}

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export function KnowledgeMapPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { conceptDetailId, openConceptDetail, closeConceptDetail } = useOutletContext<AppOutletContext>();
  const locationState = location.state as {
    extractionRunId?: string;
    extractingDocumentId?: string;
    extractingDocumentTitle?: string;
    focusConceptId?: string;
  } | null;

  // Derive extraction intent from router state on first mount
  const initialExtraction: ExtractionSource | null =
    locationState?.extractingDocumentId
      ? {
          documentId: locationState.extractingDocumentId,
          documentTitle: locationState.extractingDocumentTitle ?? "",
          runId: locationState.extractionRunId,
        }
      : null;

  const [view, setView] = useState<KnowledgeMapView>("map");
  const [graphState, setGraphState] = useState<GraphState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAllNodes, setShowAllNodes] = useState(false);
  const [focusDegree, setFocusDegree] = useState(1);
  const [forceParams, setForceParams] = useState<ForceParams>({ center: 0.6, repel: 10, link: 2 });
  const [showCandidates, setShowCandidates] = useState(initialExtraction !== null);
  const [showAddConcept, setShowAddConcept] = useState(false);
  const [showAddRelation, setShowAddRelation] = useState(false);
  const [extractionSource, setExtractionSource] = useState<ExtractionSource | null>(initialExtraction);
  const positionsSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const graphActionsRef = useRef<{ fit: () => void; relayout: (params?: ForceParams) => void } | null>(null);
  const initialFocusHandled = useRef(false);
  const graphRevision = useUiStore((state) => state.graphRevision);
  const lastGraphRevisionRef = useRef(graphRevision);

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

  // Reload the graph after a concept/relationship edit (bumped via uiStore).
  useEffect(() => {
    if (lastGraphRevisionRef.current === graphRevision) return;
    lastGraphRevisionRef.current = graphRevision;
    void loadGraph();
  }, [graphRevision, loadGraph]);

  useEffect(() => {
    setSelectedConceptId(conceptDetailId);
  }, [conceptDetailId]);

  useEffect(() => {
    if (initialFocusHandled.current || !locationState?.focusConceptId || !graphState) return;
    if (!graphState.concepts.some((concept) => concept.concept_id === locationState.focusConceptId)) return;
    initialFocusHandled.current = true;
    setSelectedConceptId(locationState.focusConceptId);
    openConceptDetail(locationState.focusConceptId);
  }, [graphState, locationState?.focusConceptId, openConceptDetail]);

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
    openConceptDetail(conceptId);
  }

  function handleBackgroundClick() {
    setSelectedConceptId(null);
    closeConceptDetail();
  }

  // FE-4 recipe 3: degree walk — +/- extend focus to 2/3 hops, Esc clears.
  useEffect(() => {
    setFocusDegree(1);
  }, [selectedConceptId]);

  useEffect(() => {
    if (!selectedConceptId) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "+" || e.key === "=") setFocusDegree((d) => Math.min(3, d + 1));
      else if (e.key === "-") setFocusDegree((d) => Math.max(1, d - 1));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedConceptId]);

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

  const handleCandidatesChanged = useCallback(() => {
    void loadGraph();
  }, [loadGraph]);

  const pendingCount = graphState?.pending_count ?? 0;
  const isEmpty = !loading && !error && (graphState?.total_concepts ?? 0) === 0;

  return (
    <div className="knowledge-map-page">
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
          <DropdownSelect
            className="km-topic-filter"
            ariaLabel="按主题筛选"
            value={selectedTopicId ?? ""}
            onChange={(value) => setSelectedTopicId(value || null)}
            options={[{ value: "", label: "全部主题" }, ...topics.map((t) => ({ value: t.concept_id, label: t.name }))]}
          />
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

        {view === "map" && !isEmpty && (
          <div className="km-map-actions">
            <button className={`km-density-toggle ${showAllNodes ? "active" : ""}`} onClick={() => setShowAllNodes((value) => !value)}>{showAllNodes ? "渐进显示" : "显示全部"}</button>
            <button className="icon-button" title="适配视图" aria-label="适配视图" onClick={() => graphActionsRef.current?.fit()}><Maximize2 size={15} /></button>
            <button className="icon-button" title="重新布局" aria-label="重新布局" onClick={() => graphActionsRef.current?.relayout(forceParams)}><Network size={15} /></button>
            <button className="km-edit-action" title="添加概念" aria-label="添加概念" onClick={() => setShowAddConcept(true)}><Plus size={15} />概念</button>
            <button className="km-edit-action" title="添加关系" aria-label="添加关系" onClick={() => setShowAddRelation(true)}><Link2 size={15} />关系</button>
            <details className="km-force-params">
              <summary>力参数</summary>
              <div>
                <label>向心 <input type="range" min={0} max={1} step={0.05} value={forceParams.center} onChange={(e) => setForceParams((p) => ({ ...p, center: Number(e.target.value) }))} /></label>
                <label>排斥 <input type="range" min={1} max={30} step={1} value={forceParams.repel} onChange={(e) => setForceParams((p) => ({ ...p, repel: Number(e.target.value) }))} /></label>
                <label>连线 <input type="range" min={1} max={5} step={0.5} value={forceParams.link} onChange={(e) => setForceParams((p) => ({ ...p, link: Number(e.target.value) }))} /></label>
              </div>
            </details>
          </div>
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
            <Link to="/library" className="btn-sm">
              去资料库
            </Link>
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
                showAll={showAllNodes}
                searchQuery={searchQuery}
                focusDegree={focusDegree}
                onNodeClick={handleNodeClick}
                onBackgroundClick={handleBackgroundClick}
                onPositionsChanged={handlePositionsChanged}
                actionsRef={graphActionsRef}
              />
            )}
          </div>
        )}

        {/* Directory view */}
        {view === "directory" && (
          <DirectoryView
            concepts={filteredConcepts}
            selectedConceptId={selectedConceptId}
            onSelect={handleNodeClick}
          />
        )}

        {/* Sources view */}
        {view === "sources" && (
          <SourcesView
            concepts={filteredConcepts}
            relationships={graphState?.relationships ?? []}
            selectedConceptId={selectedConceptId}
            onConceptSelect={handleNodeClick}
          />
        )}
      </div>

      {/* Add concept / add relation dialogs (toolbar edit entries) */}
      {showAddConcept && (
        <AddConceptDialog
          onClose={() => setShowAddConcept(false)}
          onCreated={() => { setShowAddConcept(false); void loadGraph(); }}
        />
      )}
      {showAddRelation && graphState && (
        <AddRelationDialog
          concepts={graphState.concepts}
          onClose={() => setShowAddRelation(false)}
          onCreated={() => { setShowAddRelation(false); void loadGraph(); }}
        />
      )}

      {/* Candidate review panel */}
      {showCandidates && (
        <Modal onClose={() => { setShowCandidates(false); setExtractionSource(null); }} ariaLabel="候选审查" zIndex={120}>
          <CandidateReviewPanel
            extractionSource={extractionSource ?? undefined}
            onReturnToSource={extractionSource ? () => navigate(`/library?document=${encodeURIComponent(extractionSource.documentId)}`) : undefined}
            onClose={() => {
              setShowCandidates(false);
              setExtractionSource(null);
            }}
            onCandidatesChanged={handleCandidatesChanged}
          />
        </Modal>
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

function DirectorySection({
  title,
  items,
  selectedConceptId,
  onSelect,
}: {
  title: string;
  items: ConceptNode[];
  selectedConceptId: string | null;
  onSelect: (conceptId: string) => void;
}) {
  if (!items.length) return null;
  return (
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
  );
}

function DirectoryView({ concepts, selectedConceptId, onSelect }: DirectoryViewProps) {
  const clusters = concepts.filter((c) => c.level === "cluster");
  const cores = concepts.filter((c) => c.level === "core");
  const details = concepts.filter((c) => c.level === "detail");

  if (!concepts.length) {
    return (
      <div className="km-dir-empty">
        <p>没有找到匹配的概念。</p>
      </div>
    );
  }

  return (
    <div className="km-directory">
      <DirectorySection title="主题簇" items={clusters} selectedConceptId={selectedConceptId} onSelect={onSelect} />
      <DirectorySection title="核心概念" items={cores} selectedConceptId={selectedConceptId} onSelect={onSelect} />
      <DirectorySection title="细分概念" items={details} selectedConceptId={selectedConceptId} onSelect={onSelect} />
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

// ------------------------------------------------------------------
// Add concept / add relation dialogs (toolbar edit entries)
// ------------------------------------------------------------------

const REL_TYPES = ["属于", "前置知识", "组成部分", "对比", "应用于", "来源于", "user:custom"];

function AddConceptDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [level, setLevel] = useState("core");
  const [definition, setDefinition] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.graphUpsertConcept({ name: trimmed, level, definition: definition.trim(), note: "" });
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} ariaLabel="添加概念" className="km-dialog" zIndex={125}>
        <header>
          <h3>添加概念</h3>
          <button className="icon-button" aria-label="关闭" onClick={onClose}><X size={15} /></button>
        </header>
        <label>
          <span>名称</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="概念名称（必填）" autoFocus />
        </label>
        <label>
          <span>层级</span>
          <DropdownSelect ariaLabel="层级" value={level} onChange={setLevel}
            options={[{ value: "cluster", label: "主题簇" }, { value: "core", label: "核心概念" }, { value: "detail", label: "细分概念" }]} />
        </label>
        <label>
          <span>定义</span>
          <textarea value={definition} onChange={(e) => setDefinition(e.target.value)} rows={3} placeholder="一句话定义（可选）" />
        </label>
        {error && <p className="km-dialog-error">{error}</p>}
        <footer>
          <button className="quiet-button" onClick={onClose}>取消</button>
          <button className="primary-button" disabled={busy || !name.trim()} onClick={() => void submit()}>创建</button>
        </footer>
    </Modal>
  );
}

function AddRelationDialog({ concepts, onClose, onCreated }: { concepts: ConceptNode[]; onClose: () => void; onCreated: () => void }) {
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [relType, setRelType] = useState(REL_TYPES[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = concepts.map((c) => ({ value: c.concept_id, label: c.name }));

  async function submit() {
    if (!fromId || !toId || fromId === toId || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.createRelationship({ from_id: fromId, to_id: toId, rel_type: relType, note: note.trim() || undefined });
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} ariaLabel="添加关系" className="km-dialog" zIndex={125}>
        <header>
          <h3>添加关系</h3>
          <button className="icon-button" aria-label="关闭" onClick={onClose}><X size={15} /></button>
        </header>
        <label>
          <span>起点概念</span>
          <DropdownSelect ariaLabel="起点概念" value={fromId} onChange={setFromId}
            options={[{ value: "", label: "选择概念…" }, ...options]} />
        </label>
        <label>
          <span>终点概念</span>
          <DropdownSelect ariaLabel="终点概念" value={toId} onChange={setToId}
            options={[{ value: "", label: "选择概念…" }, ...options]} />
        </label>
        <label>
          <span>关系类型</span>
          <DropdownSelect ariaLabel="关系类型" value={relType} onChange={setRelType}
            options={REL_TYPES.map((t) => ({ value: t, label: t === "user:custom" ? "自定义" : t }))} />
        </label>
        <label>
          <span>备注</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="可选" />
        </label>
        {error && <p className="km-dialog-error">{error}</p>}
        {fromId && toId && fromId === toId && <p className="km-dialog-error">起点和终点不能是同一个概念。</p>}
        <footer>
          <button className="quiet-button" onClick={onClose}>取消</button>
          <button className="primary-button" disabled={busy || !fromId || !toId || fromId === toId} onClick={() => void submit()}>创建关系</button>
        </footer>
    </Modal>
  );
}
