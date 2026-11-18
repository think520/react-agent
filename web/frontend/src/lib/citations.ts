/** Citation markers are linked after Markdown parsing so code samples remain literal. */

import type { Plugin } from "unified";

import type { SourceRef } from "../types";

const CITATION_PATTERN = /\[(S[0-9a-f]{6})\](?!\()/g;
const NON_TEXT_BLOCKS = new Set(["code", "inlineCode", "html", "link", "linkReference", "image", "imageReference"]);

export interface CitationTarget {
  label: string;
  /** 1 起的显示序号：按在回答里首次出现的顺序。 */
  index: number;
  source: SourceRef;
}

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

interface CitationPluginOptions {
  sources?: SourceRef[];
  targets: Map<string, CitationTarget>;
}

function citationNodes(value: string, byLabel: Map<string, SourceRef>, targets: Map<string, CitationTarget>): MarkdownNode[] {
  const nodes: MarkdownNode[] = [];
  let cursor = 0;
  for (const match of value.matchAll(CITATION_PATTERN)) {
    const label = match[1];
    const source = byLabel.get(label);
    const start = match.index ?? 0;
    if (!source) continue;
    if (start > cursor) nodes.push({ type: "text", value: value.slice(cursor, start) });
    let target = targets.get(label);
    if (!target) {
      target = { label, index: targets.size + 1, source };
      targets.set(label, target);
    }
    nodes.push({ type: "link", url: `cite:${label}`, children: [{ type: "text", value: String(target.index) }] });
    cursor = start + match[0].length;
  }
  if (cursor === 0) return [{ type: "text", value }];
  if (cursor < value.length) nodes.push({ type: "text", value: value.slice(cursor) });
  return nodes;
}

export function transformCitationNodes(tree: MarkdownNode, { sources, targets }: CitationPluginOptions): void {
  const byLabel = new Map<string, SourceRef>();
  for (const source of sources || []) {
    if (source.cite_label) byLabel.set(source.cite_label, source);
  }
  targets.clear();

  const transform = (parent: MarkdownNode) => {
    if (NON_TEXT_BLOCKS.has(parent.type) || !parent.children) return;
    parent.children = parent.children.flatMap((child) => {
      if (child.type === "text" && typeof child.value === "string") {
        return citationNodes(child.value, byLabel, targets);
      }
      transform(child);
      return [child];
    });
  };

  transform(tree);
}

export const remarkCitations: Plugin<[CitationPluginOptions], MarkdownNode> = (options) => (tree) => {
  transformCitationNodes(tree, options);
};
