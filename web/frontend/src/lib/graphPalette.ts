/**
 * 知识地图画布的配色（2026-11-11 审查）。
 *
 * Sigma 画在 canvas / WebGL 上，CSS 变量够不着它，所以以前整套颜色写死成浅色 hex：
 * 暗色主题下节点标签是一块块米白贴片，深蓝节点落在深色背景上几乎看不见。
 * 现在从当前主题的 CSS 变量读出调色板；主题切换时由画布重新取色并刷新。
 */

export interface GraphPalette {
  inkBlue: string;
  inkBlueFaint: string;
  paperSoft: string;
  paperLabel: string;
  faintNode: string;
  faintEdge: string;
  sageSoft: string;
  slateNode: string;
  detailNode: string;
  selectedNode: string;
  hoverNode: string;
  newConcept: string;
}

/** 浅色主题的取值（也是读不到变量时的兜底，与改造前逐项相同）。 */
export const LIGHT_GRAPH_PALETTE: GraphPalette = {
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
  // W1 E16：刚确认的概念 —— 比"选中"更醒目，几秒后自己回到常态。
  newConcept: "#b45309",
};

/** 暗色主题：节点要在深色纸面上可辨，标签贴片跟着纸面变深。 */
const DARK_OVERRIDES: Partial<GraphPalette> = {
  inkBlueFaint: "#7f9cc4",
  faintNode: "#4a4741",
  faintEdge: "#3a3732",
  sageSoft: "#8fb5aa",
  slateNode: "#8ea4bb",
  detailNode: "#7d8a93",
  selectedNode: "#e08a72",
  hoverNode: "#e6a284",
  newConcept: "#f0a35b",
};

type ReadVar = (name: string) => string;

function withAlpha(color: string, alpha: number): string {
  const hex = color.trim().match(/^#([0-9a-f]{6})$/i);
  if (!hex) return color;
  const value = parseInt(hex[1], 16);
  return `rgba(${(value >> 16) & 255},${(value >> 8) & 255},${value & 255},${alpha})`;
}

/**
 * 由主题算出调色板。``readVar`` 读 CSS 变量（测试里可以直接传查表函数）。
 * 跟主题走的只有三类：主色（--blue）、纸面（--paper-soft，标签贴片随之变）、暗色时的节点阶梯。
 */
export function graphPalette(theme: string | undefined, readVar: ReadVar): GraphPalette {
  const read = (name: string, fallback: string) => readVar(name).trim() || fallback;
  const base = theme === "dark" ? { ...LIGHT_GRAPH_PALETTE, ...DARK_OVERRIDES } : { ...LIGHT_GRAPH_PALETTE };
  const paper = read("--paper-soft", base.paperSoft);
  return {
    ...base,
    inkBlue: read("--blue", base.inkBlue),
    paperSoft: paper,
    paperLabel: withAlpha(paper, 0.94),
  };
}

/** 浏览器里：按 <html data-theme> 与计算样式取色。 */
export function currentGraphPalette(): GraphPalette {
  if (typeof document === "undefined") return { ...LIGHT_GRAPH_PALETTE };
  const root = document.documentElement;
  const style = getComputedStyle(root);
  return graphPalette(root.dataset.theme, (name) => style.getPropertyValue(name));
}
