/** Interactive Sigma.js + Graphology knowledge-map canvas. */

import { useEffect, useRef, type MutableRefObject } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import type { Settings as SigmaSettings } from "sigma/settings";
import type { NodeLabelDrawingFunction } from "sigma/rendering";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { prefersReducedMotion } from "../lib/motion";
import type { ConceptNode, RelationshipEdge } from "../types";

/** Fallback seed for a node without a saved position: spread around the
 *  centroid of positioned nodes on a golden-angle spiral. */
function positionOrSeed(positioned: ConceptNode[], angle: number, radius: number): number {
  if (!positioned.length) return Math.cos(angle) * radius;
  let min = Infinity;
  let max = -Infinity;
  for (const concept of positioned) {
    if (concept.x < min) min = concept.x;
    if (concept.x > max) max = concept.x;
  }
  return (min + max) / 2 + Math.cos(angle) * radius * 0.4;
}

function positionOrSeedY(positioned: ConceptNode[], angle: number, radius: number): number {
  if (!positioned.length) return Math.sin(angle) * radius;
  let min = Infinity;
  let max = -Infinity;
  for (const concept of positioned) {
    if (concept.y < min) min = concept.y;
    if (concept.y > max) max = concept.y;
  }
  return (min + max) / 2 + Math.sin(angle) * radius * 0.4;
}

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
  const hoverTweenRef = useRef(0);
  const hoverTargetRef = useRef(0);
  const hoverRafRef = useRef<number | null>(null);
  const searchQueryRef = useRef(searchQuery);
  const focusDegreeRef = useRef(focusDegree);
  // Edge identity for incremental syncs: composite key -> sigma edge key.
  const edgeKeysRef = useRef(new Map<string, string>());

  useEffect(() => {
    if (!containerRef.current) return;
    const edgeKeys = edgeKeysRef.current;

    // The renderer instance lives for the component's lifetime; graph data is
    // diffed in by the effect below so candidate reviews / concept edits no
    // longer tear down WebGL, replay the entrance, and yank the camera.
    const graph = new Graph({ type: "mixed" });

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
          size: (data.size as number) * (node === hoveredNodeRef.current ? 1 + 0.12 * hoverTweenRef.current : 1),
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

    let draggedNode: string | null = null;
    let isDragging = false;

    renderer.on("clickNode", ({ node }) => onNodeClick(node));
    renderer.on("clickStage", () => {
      if (!isDragging) onBackgroundClick();
    });
    // FE-4 recipe 2: hover transition — ease the hovered node's scale in/out.
    const stepHoverTween = () => {
      const target = hoverTargetRef.current;
      const current = hoverTweenRef.current;
      if (Math.abs(target - current) < 0.02) {
        hoverTweenRef.current = target;
        hoverRafRef.current = null;
        renderer.refresh({ skipIndexation: true });
        return;
      }
      const duration = target > current ? 180 : 280;
      hoverTweenRef.current = current + (target - current) * (16 / duration);
      renderer.refresh({ skipIndexation: true });
      hoverRafRef.current = requestAnimationFrame(stepHoverTween);
    };
    const startHoverTween = (target: number) => {
      hoverTargetRef.current = target;
      if (hoverRafRef.current === null && !prefersReducedMotion()) {
        hoverRafRef.current = requestAnimationFrame(stepHoverTween);
      }
    };

    renderer.on("enterNode", ({ node }) => {
      hoveredNodeRef.current = node;
      containerRef.current?.classList.add("node-hovered");
      startHoverTween(1);
      renderer.refresh({ skipIndexation: true });
    });
    renderer.on("leaveNode", () => {
      hoveredNodeRef.current = null;
      containerRef.current?.classList.remove("node-hovered");
      startHoverTween(0);
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
      if (hoverRafRef.current !== null) {
        cancelAnimationFrame(hoverRafRef.current);
        hoverRafRef.current = null;
      }
      resizeObserver.disconnect();
      if (actionsRef) actionsRef.current = null;
      renderer.kill();
      sigmaRef.current = null;
      graphRef.current = null;
      edgeKeys.clear();
    };
  // Instance effect: reducers read interaction state through refs, so nothing
  // else needs to be a dependency here.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Incremental data sync: add/update/remove nodes and edges in place. Only a
  // genuinely fresh graph (first fill, no saved positions) gets the Force
  // Atlas seed layout; later refreshes keep node positions and the camera.
  useEffect(() => {
    const graph = graphRef.current;
    const renderer = sigmaRef.current;
    if (!graph || !renderer) return;

    const firstFill = graph.order === 0 && concepts.length > 0;

    for (const node of [...graph.nodes()]) {
      if (!concepts.some((concept) => concept.concept_id === node)) graph.dropNode(node);
    }

    const positioned = concepts.filter((concept) => concept.x !== 0 || concept.y !== 0);
    let seededNewNode = false;
    for (const concept of concepts) {
      const size = concept.level === "cluster" ? 15 : concept.level === "core" ? 11 : 7;
      const attributes = {
        label: concept.name,
        size,
        color: nodeColor(concept.level),
        labelColor: C.inkBlue,
        level: concept.level,
      };
      if (graph.hasNode(concept.concept_id)) {
        // Positions are user state — only metadata merges.
        graph.mergeNodeAttributes(concept.concept_id, attributes);
        continue;
      }
      // Seed new nodes near an existing neighbor so refreshes don't reshuffle
      // the whole layout (and never near-zero pile onto the origin).
      const anchorRelationship = relationships.find(
        (rel) =>
          (rel.from_id === concept.concept_id && graph.hasNode(rel.to_id))
          || (rel.to_id === concept.concept_id && graph.hasNode(rel.from_id)),
      );
      const anchorId = anchorRelationship
        ? (anchorRelationship.from_id === concept.concept_id ? anchorRelationship.to_id : anchorRelationship.from_id)
        : null;
      const hasAnchor = Boolean(anchorId && graph.hasNode(anchorId));
      const angle = graph.order * 2.399963; // golden-angle spiral fallback
      const radius = 6 + Math.sqrt(graph.order + 1) * 2.4;
      graph.addNode(concept.concept_id, {
        ...attributes,
        x: hasAnchor
          ? (graph.getNodeAttribute(anchorId!, "x") as number) + Math.cos(angle) * 1.5
          : positionOrSeed(positioned, angle, radius),
        y: hasAnchor
          ? (graph.getNodeAttribute(anchorId!, "y") as number) + Math.sin(angle) * 1.5
          : positionOrSeedY(positioned, angle, radius),
      });
      seededNewNode = true;
    }

    const seenEdges = new Set<string>();
    for (const relationship of relationships) {
      if (!graph.hasNode(relationship.from_id) || !graph.hasNode(relationship.to_id)) continue;
      const key = `${relationship.from_id}\u0000${relationship.to_id}`;
      seenEdges.add(key);
      const color = edgeColor(relationship.evidence_level);
      const existingKey = edgeKeysRef.current.get(key);
      if (existingKey !== undefined && graph.hasEdge(existingKey)) {
        graph.mergeEdgeAttributes(existingKey, { label: relationship.rel_type, color });
        continue;
      }
      try {
        const edgeKey = graph.addEdge(relationship.from_id, relationship.to_id, {
          label: relationship.rel_type,
          color,
          size: 1.15,
          type: "arrow",
        });
        edgeKeysRef.current.set(key, edgeKey);
      } catch {
        // A duplicate relation is visually redundant.
      }
    }
    for (const [key, edgeKey] of [...edgeKeysRef.current]) {
      if (!seenEdges.has(key) || !graph.hasEdge(edgeKey)) {
        if (graph.hasEdge(edgeKey)) graph.dropEdge(edgeKey);
        edgeKeysRef.current.delete(key);
      }
    }

    const hasSavedPositions = positioned.length > 0;
    if (firstFill && !hasSavedPositions && graph.order > 0) {
      forceAtlas2.assign(graph, {
        iterations: 140,
        settings: { scalingRatio: 9, gravity: 0.65, slowDown: 2, adjustSizes: true },
      });
    } else if (seededNewNode && !hasSavedPositions) {
      // Give freshly seeded nodes a light settle so they don't overlap.
      forceAtlas2.assign(graph, {
        iterations: 24,
        settings: { scalingRatio: 9, gravity: 0.65, slowDown: 8, adjustSizes: true },
      });
    }

    renderer.refresh();

    // FE-4 recipe 1: entrance plays once, when the map fills for real.
    if (firstFill && !prefersReducedMotion()) {
      void renderer.getCamera().animatedReset({ duration: 600 });
    }
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
        const duration = prefersReducedMotion() ? 0 : 460;
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
