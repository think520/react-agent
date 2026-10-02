import type { ImportBatchResult } from "./api";

export interface DocumentImportState {
  importing: boolean;
  notice: string;
  error: string;
  errorCode: string;
  duplicateCount: number;
  version: number;
  results: ImportBatchResult[] | null;
}

export function emptyDocumentImport(): DocumentImportState {
  return {
    importing: false,
    notice: "",
    error: "",
    errorCode: "",
    duplicateCount: 0,
    version: 0,
    results: null,
  };
}

/**
 * W1 E1：切资料库时重置导入状态。
 *
 * 导入报告、通知与可重试文件都属于**上一个**资料库；留着会串库 ——
 * 上一库的失败清单还挂在页面上，点「重试这 N 份」就会把文件导进新资料库。
 * （版本号保留：它只用来让界面知道"这次的批次是新的"。）
 */
export function clearImportReport(state: DocumentImportState): DocumentImportState {
  return { ...state, ...emptyDocumentImport(), version: state.version };
}
