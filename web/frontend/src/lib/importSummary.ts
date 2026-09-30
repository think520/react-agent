interface ImportBatchResult {
  filename?: string;
  status?: string;
  searchable?: boolean;
  extraction?: string | null;
}

interface ImportSummaryInput {
  imported: unknown[];
  duplicates?: unknown[];
  rejected: unknown[];
  pending?: unknown[];
  /** 本次上传的逐文件结果（F09：批次计数只认它）。 */
  results?: ImportBatchResult[];
  /** 全库增量同步：单独展示，**不参与**批次计数。 */
  library_sync?: { extraction_counts?: Record<string, number>; error_files?: number };
}

/** Describe extraction facts without claiming every accepted file is searchable. */
export function describeDocumentImport(result: ImportSummaryInput): string {
  // 只把**本次上传**的逐文件结果算进批次（审查 F09）。这里以前读的是全库同步统计，
  // 于是资料库里任意别的文件一变，本次上传就会被报成"更多份可用于检索"。
  const batch = result.results || [];
  const searchable = batch.filter((item) => item.searchable).length;
  const empty = batch.filter((item) => item.extraction === "empty").length;
  const failed = batch.filter((item) => item.extraction === "error").length;
  const pending = batch.filter((item) => item.status === "pending").length;

  const parts = ["已接收 " + result.imported.length + " 份文件"];
  if (searchable) parts.push(searchable + " 份可用于检索");
  if (empty) parts.push(empty + " 份没有可提取文本");
  if (failed) parts.push(failed + " 份解析失败");
  if (pending) parts.push(pending + " 份在等待建立索引");
  if (result.duplicates?.length) parts.push(result.duplicates.length + " 份重复文件已保留已有版本");
  if (result.rejected.length) parts.push(result.rejected.length + " 份未导入");
  const text = parts.join("，") + "。";

  // 全库增量单列一句，明说它是"资料库里其它资料"，不冒充本次上传的结果。
  const counts = result.library_sync?.extraction_counts || {};
  const librarySearchable = (counts.complete || 0) + (counts.partial || 0);
  const others = Math.max(0, librarySearchable - searchable);
  return others > 0 ? `${text}本次同步另外更新了资料库里其它 ${others} 份资料。` : text;
}
