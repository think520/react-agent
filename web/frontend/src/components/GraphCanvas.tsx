/**
 * GraphCanvas — WebGL graph renderer using Sigma.js + Graphology.
 *
 * Design constraints (knowledge_map_design.md §9.3):
 *  - Nodes fade in ~200ms, edges extend ~300ms ease-out
 *  - Hover: colour deepen ~100ms, no scale, no bounce
 *  - Candidate nodes: opacity 0.6, dashed border (drawn as SVG label overlay)
 *  - Positions come from backend; layout algorithm runs only when no saved
 *    positions exist
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import type { Settings as SigmaSettings } from "sigma/settings";
import forceAtlas2 from "graphology-layout-forceatlas2";
import type { ConceptNode, RelationshipEdge } from "../types";

// ------------------------------------------------------------------
// Colour tokens (mirror CSS variables for WebGL rendering)
// ------------------------------------------------------------------
const C = {
  parchment:    "#F3EFE5",
  inkBlue:      "#1b365d",
  inkBlueFaint: "#4a6fa5",
  paperSoft:    "#faf8f4",
  sage:         "#5a7a6a",
  sageSoft:     "#8aaa9a",
  muted:        "#7a7060",
  faint:        "#b0a898",
  wheat:        "#c8b87a",
} as const;

// Node colours by level
function nodeColor(level: string, isCandidate: boolean): string {
  if (isCandidate) return C.faint;
  if (level === "cluster") return C.inkBlue;
  return C.paperSoft;
}
function nodeBorderColor(level: string, isCandidate: boolean): string {
  if (isCandidate) return C.faint;
  if (level === "cluster") return C.inkBlue;
  return C.inkBlue;
}
function nodeLabelColor(level: string): string {
  return level === "cluster" ? C.paperSoft : C.inkBlue;
}
function edgeColor(evidenceLevel: string): string {
  if (evidenceLevel === "user") return C.sageSoft;
  return C.inkBlueFaint;
}

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface GraphCanvasProps {
  concepts: ConceptNode[];
  relationships: RelationshipEdge[];
  selectedConceptId: string | null;
  onNodeClick: (conceptId: string) => void;
  onBackgroundClick: () => void;
  className?: string;
}

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export function GraphCanvas({
  concepts,
  relationships,
  selectedConceptId,
  onNodeClick,
  onBackgroundClick,
  className = "",
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);

  // Build or update Sigma on data change
  useEffect(() => {
    if (!containerRef.current) return;

    // Build graphology graph
    const g = new Graph({ type: "mixed" });

    for (const c of concepts) {
      const isCandidate = c.level === "detail" && c.concept_id.startsWith("cand-");
      const size = c.level === "cluster" ? 18 : c.level === "core" ? 12 : 8;
      g.addNode(c.concept_id, {
        label: c.name,
        size,
        color: nodeColor(c.level, isCandidate),
        borderColor: nodeBorderColor(c.level, isCandidate),
        labelColor: nodeLabelColor(c.level),
        x: c.x !== 0 || c.y !== 0 ? c.x : Math.random() * 10,
        y: c.x !== 0 || c.y !== 0 ? c.y : Math.random() * 10,
        level: c.level,
        isCandidate,
      });
    }

    for (const rel of relationships) {
      if (!g.hasNode(rel.from_id) || !g.hasNode(rel.to_id)) continue;
      try {
        g.addEdge(rel.from_id, rel.to_id, {
          label: rel.rel_type,
          color: edgeColor(rel.evidence_level),
          size: 1.5,
          type: "arrow",
        });
      } catch {
        // duplicate edge — skip
      }
    }

    // Run force layout only when positions are all at origin (no saved positions)
    const hasPositions = concepts.some((c) => c.x !== 0 || c.y !== 0);
    if (!hasPositions && g.order > 0) {
      forceAtlas2.assign(g, {
        iterations: 80,
        settings: { scalingRatio: 4, gravity: 1, adjustSizes: true },
      });
    }

    // Sigma settings
    const settings: Partial<SigmaSettings> = {
      defaultNodeColor: C.paperSoft,
      defaultEdgeColor: C.inkBlueFaint,
      labelFont: "var(--body-font, ui-sans-serif, sans-serif)",
      labelSize: 12,
      labelWeight: "normal",
      labelColor: { attribute: "labelColor", color: C.inkBlue },
      defaultNodeType: "circle",
      defaultEdgeType: "arrow",
      renderEdgeLabels: false,
      enableEdgeEvents: false,
      allowInvalidContainer: true,
    };

    // Destroy previous instance
    if (sigmaRef.current) {
      sigmaRef.current.kill();
    }

    const renderer = new Sigma(g, containerRef.current, settings);
    sigmaRef.current = renderer;
    graphRef.current = g;

    // Events
    renderer.on("clickNode", ({ node }) => {
      onNodeClick(node);
    });
    renderer.on("clickStage", () => {
      onBackgroundClick();
    });

    // Node hover: deepen colour (100ms via CSS, not Sigma animation)
    renderer.on("enterNode", ({ node }) => {
      g.setNodeAttribute(node, "color",
        g.getNodeAttribute(node, "level") === "cluster"
          ? "#142a4a"
          : "#e8e4d8",
      );
      renderer.refresh();
    });
    renderer.on("leaveNode", ({ node }) => {
      const lvl = g.getNodeAttribute(node, "level") as string;
      const isCandidate = g.getNodeAttribute(node, "isCandidate") as boolean;
      g.setNodeAttribute(node, "color", nodeColor(lvl, isCandidate));
      renderer.refresh();
    });

    return () => {
      renderer.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [concepts, relationships]);

  // Highlight selected node
  useEffect(() => {
    const g = graphRef.current;
    const renderer = sigmaRef.current;
    if (!g || !renderer) return;
    g.forEachNode((node) => {
      g.setNodeAttribute(node, "highlighted", node === selectedConceptId);
    });
    renderer.refresh();
  }, [selectedConceptId]);

  return (
    <div
      ref={containerRef}
      className={`graph-canvas ${className}`}
      aria-label="知识地图图谱画布"
      role="application"
    />
  );
}
