import type { DocumentSummary } from "../types";

export function readerEmptyState(document: Pick<DocumentSummary, "has_original" | "extraction_status">) {
  if (document.extraction_status === "error") {
    return {
      title: "原文提取失败",
      description: document.has_original === true ? "原件仍可查看，但暂时无法生成可定位的文本片段。" : "暂时无法读取原件或生成可定位的文本片段。",
    };
  }
  if (document.extraction_status === "empty") {
    return {
      title: "没有提取到可阅读文本",
      description: document.has_original === true ? "可以查看原件；当前没有可定位的文字片段。" : "这份资料没有可显示的原文或文字片段。",
    };
  }
  if (document.extraction_status === "partial") {
    return {
      title: "暂时没有可定位的片段",
      description: "文字提取不完整；可以查看原件或稍后重试提取。",
    };
  }
  return {
    title: "暂时没有可阅读的片段",
    description: document.has_original === true ? "原件存在，但当前没有可定位的文本片段。" : "这份资料当前没有可定位的文本片段。",
  };
}
