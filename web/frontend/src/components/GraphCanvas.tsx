/** Interactive Sigma.js + Graphology knowledge-map canvas. */

import { useEffect, useRef, type MutableRefObject } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import type { Settings as SigmaSettings } from "sigma/settings";
import type { NodeLabelDrawingFunction } from "sigma/rendering";
import forceAtlas2 from "graphology-layout-forceatlas2";
import type { ConceptNode, RelationshipEdge } from "../types";

const C = {
  inkBlue: "#1b365d",
  inkBlueFaint: "#4a6fa5",
  paperSoft: "#faf8f4",
  paperLabel: "rgba(250,248,244,.94)",
  faintNode: "#bdbab2",
  faintEdge: "#d4cfc4",
  sageSoft: "#5f8f84",
  slateNode: "#6f879f",
  detailNode: "#94a1aa",
  selectedNode: "#c7664f",
  hoverNode: "#d98a68",
} as const;

function nodeColor(level: string): string {
  if (level === "cluster") return C.inkBlue;
  return level === "detail" ? C.detailNode : C.slateNode;
}

function edgeColor(evidenceLevel: string): string {
  return evidenceLevel === "user" ? C.sageSoft : C.inkBlueFaint;
}

const drawNodeLabel: NodeLabelDrawingFunction = (context, data, settings) => {
  if (!data.label) return;
  const fontSize = settings.labelSize;
  const x = data.x + data.size + 5;
  const y = data.y + fontSize / 3;
  context.font = `${settings.labelWeight} ${fontSize}px ${settings.labelFont}`;
  const width = context.measureText(data.label).width;
  context.fillStyle = C.paperLabel;
  context.beginPath();
  context.roundRect(x - 4, y - fontSize, width + 8, fontSize + 6, 4);
  context.fill();
  context.fillStyle = (data as typeof data & { labelColor?: string }).labelColor || C.inkBlue;
  context.fillText(data.label, x, y);
};

export interface ForceParams {
  center: number;
  repel: number;
  link: number;
}

export interface GraphCanvasActions {
  fit: () => void;
  relayout: (params?: ForceParams) => void;
}

export interface GraphCanvasProps {
  concepts: ConceptNode[];
  relationships: RelationshipEdge[];
  selectedConceptId: string | null;
  showAll?: boolean;
  searchQuery?: string;
  focusDegree?: number;
  onNodeClick: (conceptId: string) => void;
  onBackgroundClick: () => void;
  onPositionsChanged?: (positions: Array<{ concept_id: string; x: number; y: number }>) => void;
  actionsRef?: MutableRefObject<GraphCanvasActions | null>;
  className?: string;
}

export function GraphCanvas({
  concepts,
  relationships,
  selectedConceptId,
  showAll = false,
  searchQuery = "",
  focusDegree = 1,
  onNodeClick,
  onBackgroundClick,
  onPositionsChanged,
  actionsRef,
  className = "",
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const selectedRef = useRef(selectedConceptId);
  const focusedNodesRef = useRef<Set<string>>(new Set());
  const showAllRef = useRef(showAll);
  const showDetailsRef = useRef(false);
  const hoveredNodeRef = useRef<string | null>(null);
  const hoveredEdgeRef = useRef<string | null>(null);
  const searchQueryRef = useRef(searchQuery);
  const focusDegreeRef = useRef(focusDegree);
  const reducedMotionRef = useRef(
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    if (!containerRef.current) return;

    const graph = new Graph({ type: "mixed" });
    for (const concept of concepts) {
      const size = concept.level === "cluster" ? 15 : concept.level === "core" ? 11 : 7;
      graph.addNode(concept.concept_id, {
        label: concept.name,
        size,
        color: nodeColor(concept.level),
        labelColor: C.inkBlue,
        x: concept.x !== 0 || concept.y !== 0 ? concept.x : Math.random() * 10,
        y: concept.x !== 0 || concept.y !== 0 ? concept.y : Math.random() * 10,
        level: concept.level,
      });
    }

    for (const relationship of relationships) {
      if (!graph.hasNode(relationship.from_id) || !graph.hasNode(relationship.to_id)) continue;
      try {
        graph.addEdge(relationship.from_id, relationship.to_id, {
          label: relationship.rel_type,
          color: edgeColor(relationship.evidence_level),
          size: 1.15,
          type: "arrow",
        });
      } catch {
        // A duplicate relation is visually redundant.
      }
    }

    const hasSavedPositions = concepts.some((concept) => concept.x !== 0 || concept.y !== 0);
    if (!hasSavedPositions && graph.order > 0) {
      forceAtlas2.assign(graph, {
        iterations: 140,
        settings: { scalingRatio: 9, gravity: 0.65, slowDown: 2, adjustSizes: true },
      });
    }

    const settings: Partial<SigmaSettings> = {
      defaultNodeColor: C.paperSoft,
      defaultEdgeColor: C.inkBlueFaint,
      labelFont: "var(--font-ui, ui-sans-serif, sans-serif)",
      labelSize: 12,
      labelWeight: "500",
      labelColor: { attribute: "labelColor", color: C.inkBlue },
      labelDensity: 1.15,
      labelGridCellSize: 130,
      labelRenderedSizeThreshold: 4,
      defaultDrawNodeLabel: drawNodeLabel,
      defaultNodeType: "circle",
      defaultEdgeType: "arrow",
      renderEdgeLabels: true,
      enableEdgeEvents: true,
      hideEdgesOnMove: false,
      allowInvalidContainer: true,
      nodeReducer: (node, data) => {
        const selected = selectedRef.current;
        const focused = focusedNodesRef.current;
        const query = searchQueryRef.current.trim().toLowerCase();
        const label = (data.label as string) || "";
        const matchesSearch = !query || label.toLowerCase().includes(query);
        const isFocused = !selected || focused.has(node);
        const level = graph.getNodeAttribute(node, "level") as string;
        const hideDetail = level === "detail" && !showAllRef.current && !showDetailsRef.current && !focused.has(node);
        return {
          ...data,
          hidden: hideDetail,
          color: !matchesSearch
            ? C.faintNode
            : !isFocused
              ? C.faintNode
              : node === selected
                ? C.selectedNode
                : hoveredNodeRef.current === node
                  ? C.hoverNode
                  : selected && focused.has(node)
                    ? C.sageSoft
                    : nodeColor(level),
          label: matchesSearch && (isFocused || !selected) ? data.label : "",
          labelColor: C.inkBlue,
          highlighted: matchesSearch && (node === selected || node === hoveredNodeRef.current || Boolean(query)),
          zIndex: node === selected || node === hoveredNodeRef.current ? 2 : 1,
        };
      },
      edgeReducer: (edge, data) => {
        const selected = selectedRef.current;
        const [source, target] = graph.extremities(edge);
        const connected = !selected || source === selected || target === selected;
        const sourceLevel = graph.getNodeAttribute(source, "level") as string;
        const targetLevel = graph.getNodeAttribute(target, "level") as string;
        const hideForDetails = !showAllRef.current && !showDetailsRef.current
          && !focusedNodesRef.current.has(source)
          && !focusedNodesRef.current.has(target)
          && (sourceLevel === "detail" || targetLevel === "detail");
        return {
          ...data,
          hidden: hideForDetails,
          color: connected ? data.color : C.faintEdge,
          size: connected ? 1.2 : 0.65,
          label: hoveredEdgeRef.current === edge ? data.label : "",
          forceLabel: hoveredEdgeRef.current === edge,
          zIndex: connected ? 1 : 0,
        };
      },
    };

    const renderer = new Sigma(graph, containerRef.current, settings);
    sigmaRef.current = renderer;
    graphRef.current = graph;

    // FE-4 recipe 1: entrance — a gentle camera reset on mount, skipped for
    // reduced-motion users (the CSS fade is likewise disabled by the global
    // prefers-reduced-motion rule).
    if (!reducedMotionRef.current) {
      void renderer.getCamera().animatedReset({ duration: 600 });
    }

    let draggedNode: string | null = null;
    let isDragging = false;

    renderer.on("clickNode", ({ node }) => onNodeClick(node));
    renderer.on("clickStage", () => {
      if (!isDragging) onBackgroundClick();
    });
    renderer.on("enterNode", ({ node }) => {
      hoveredNodeRef.current = node;
      containerRef.current?.classList.add("node-hovered");
      renderer.refresh({ skipIndexation: true });
    });
    renderer.on("leaveNode", () => {
      hoveredNodeRef.current = null;
      containerRef.current?.classList.remove("node-hovered");
      renderer.refresh({ skipIndexation: true });
    });
    renderer.on("enterEdge", ({ edge }) => {
      hoveredEdgeRef.current = edge;
      renderer.refresh({ skipIndexation: true });
    });
    renderer.on("leaveEdge", () => {
      hoveredEdgeRef.current = null;
      renderer.refresh({ skipIndexation: true });
    });
    let dragOriginalSize: number | null = null;
    renderer.on("downNode", ({ node }) => {
      isDragging = true;
      draggedNode = node;
      dragOriginalSize = graph.getNodeAttribute(node, "size") as number;
      // FE-4 recipe 6: grab feedback — scale up while grabbed.
      graph.setNodeAttribute(node, "size", dragOriginalSize * 1.25);
      renderer.refresh();
      if (!renderer.getCustomBBox()) renderer.setCustomBBox(renderer.getBBox());
    });
    renderer.on("moveBody", ({ event }) => {
      if (!isDragging || !draggedNode) return;
      const position = renderer.viewportToGraph(event);
      graph.setNodeAttribute(draggedNode, "x", position.x);
      graph.setNodeAttribute(draggedNode, "y", position.y);
      event.preventSigmaDefault();
      event.original.preventDefault();
      event.original.stopPropagation();
    });
    const finishDrag = () => {
      if (draggedNode) {
        // FE-4 recipe 6: release fall — restore the grabbed node's size.
        if (dragOriginalSize !== null) {
          graph.setNodeAttribute(draggedNode, "size", dragOriginalSize);
          dragOriginalSize = null;
        }
        onPositionsChanged?.([{
          concept_id: draggedNode,
          x: graph.getNodeAttribute(draggedNode, "x") as number,
          y: graph.getNodeAttribute(draggedNode, "y") as number,
        }]);
        renderer.refresh();
      }
      window.setTimeout(() => { isDragging = false; }, 0);
      draggedNode = null;
    };
    renderer.on("upNode", finishDrag);
    renderer.on("upStage", finishDrag);
    renderer.getCamera().on("updated", (cameraState) => {
      const nextShowDetails = cameraState.ratio < 0.72;
      if (nextShowDetails !== showDetailsRef.current) {
        showDetailsRef.current = nextShowDetails;
        renderer.refresh();
      }
    });

    const resizeObserver = new ResizeObserver(() => renderer.resize());
    resizeObserver.observe(containerRef.current);

    if (actionsRef) {
      actionsRef.current = {
        fit: () => {
          renderer.setCustomBBox(null);
          renderer.refresh();
          void renderer.getCamera().animatedReset({ duration: 220 });
        },
        relayout: (params?: ForceParams) => {
          renderer.setCustomBBox(null);
          forceAtlas2.assign(graph, {
            iterations: 180,
            settings: {
              scalingRatio: params?.repel ?? 10,
              gravity: params?.center ?? 0.6,
              slowDown: params?.link ?? 2,
              adjustSizes: true,
            },
          });
          renderer.refresh();
          onPositionsChanged?.(graph.nodes().map((node) => ({
            concept_id: node,
            x: graph.getNodeAttribute(node, "x") as number,
            y: graph.getNodeAttribute(node, "y") as number,
          })));
          void renderer.getCamera().animatedReset({ duration: 240 });
        },
      };
    }

    return () => {
      resizeObserver.disconnect();
      if (actionsRef) actionsRef.current = null;
      renderer.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
  // Rebuild only when graph data changes; reducers handle interaction state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [concepts, relationships]);

  useEffect(() => {
    selectedRef.current = selectedConceptId;
    const graph = graphRef.current;
    const renderer = sigmaRef.current;
    if (!graph || !renderer) return;
    const focused = new Set<string>();
    if (selectedConceptId && graph.hasNode(selectedConceptId)) {
      focused.add(selectedConceptId);
      // FE-4 recipe 3: degree walk — focus out to focusDegree hops (BFS).
      const degree = Math.max(1, focusDegreeRef.current);
      let frontier = [selectedConceptId];
      for (let hop = 0; hop < degree; hop++) {
        const next: string[] = [];
        for (const node of frontier) {
          graph.forEachNeighbor(node, (neighbor) => {
            if (!focused.has(neighbor)) {
              focused.add(neighbor);
              next.push(neighbor);
            }
          });
        }
        frontier = next;
      }
      const position = renderer.getNodeDisplayData(selectedConceptId);
      if (position) {
        const duration = reducedMotionRef.current ? 0 : 460;
        void renderer.getCamera().animate({ x: position.x, y: position.y }, { duration });
      }
    }
    focusedNodesRef.current = focused;
    renderer.refresh();
  }, [selectedConceptId]);

  useEffect(() => {
    showAllRef.current = showAll;
    searchQueryRef.current = searchQuery;
    focusDegreeRef.current = focusDegree;
    sigmaRef.current?.refresh();
  }, [showAll, searchQuery, focusDegree]);

  return (
    <div
      ref={containerRef}
      className={`graph-canvas ${className}`}
      aria-label="知识地图图谱画布"
      role="application"
    />
  );
}
