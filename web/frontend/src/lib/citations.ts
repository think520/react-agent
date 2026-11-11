/**
 * W2-EVID-01：回答正文里的引用标签（`[S3fa9c1]`）→ 可点的来源标记。
 *
 * 标签由后端按 source_id 确定性算出并随来源一起下发（`cite_label`），
 * 前端只做查表，不自己算哈希 —— 一个口径，不会漂。
 * 运行时门禁已经保证最终回答里不会出现未知标签；查不到时（旧会话、流式中途）
 * 保留原文本，不伪造一个能点的出处。
 */

import type { SourceRef } from "../types";

export const CITATION_PATTERN = /\[(S[0-9A-Za-z]{1,16})\]/g;

export interface CitationTarget {
  label: string;
  /** 1 起的显示序号：按在回答里首次出现的顺序。 */
  index: number;
  source: SourceRef;
}

export function citationTargets(text: string, sources: SourceRef[] | undefined): Map<string, CitationTarget> {
  const byLabel = new Map<string, SourceRef>();
  for (const source of sources || []) {
    if (source.cite_label) byLabel.set(source.cite_label, source);
  }
  const targets = new Map<string, CitationTarget>();
  for (const match of text.matchAll(CITATION_PATTERN)) {
    const label = match[1];
    const source = byLabel.get(label);
    if (!source || targets.has(label)) continue;
    targets.set(label, { label, index: targets.size + 1, source });
  }
  return targets;
}

/** 把已知标签换成 Markdown 链接（`cite:` 协议由渲染层接管）；未知标签原样保留。 */
export function linkCitations(text: string, targets: Map<string, CitationTarget>): string {
  if (!targets.size) return text;
  return text.replace(CITATION_PATTERN, (whole, label: string) => {
    const target = targets.get(label);
    return target ? `[${target.index}](cite:${label})` : whole;
  });
}
