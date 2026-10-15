interface ImportBatchResult {
  filename?: string;
  status?: string;
  searchable?: boolean;
  extraction?: string | null;
  reason?: string;
  existing?: string;
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
  /** E8：用户中途取消了这次导入。 */
  cancelled?: boolean;
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

  // E8：取消要说清楚"已经收下什么、其余没处理"，不能显得像整批失败。
  if (result.cancelled) {
    const accepted = result.imported.length + (result.duplicates?.length || 0) + pending;
    return `导入已取消：已收下 ${accepted} 份，其余未处理。` + text;
  }

  // 全库增量单列一句，明说它是"资料库里其它资料"，不冒充本次上传的结果。
  const counts = result.library_sync?.extraction_counts || {};
  const librarySearchable = (counts.complete || 0) + (counts.partial || 0);
  const others = Math.max(0, librarySearchable - searchable);
  return others > 0 ? `${text}本次同步另外更新了资料库里其它 ${others} 份资料。` : text;
}

/**
 * E8：把**一份文件**的结果说成人话，并给出可行动的原因。
 *
 * 失败清单的价值就在这里 —— 之前整批只有一句"N 份解析失败"，用户既不知道是哪几份、
 * 也不知道能怎么办（核对结论：「失败清单不列文件名/原因/不能重试」）。
 */
export function describeImportOutcome(item: ImportBatchResult): string {
  const status = item.status || "";
  if (status === "imported") {
    if (item.searchable) return "已入库，可用于检索";
    if (item.extraction === "empty") return "已入库，但这份文件没有可提取的文本";
    if (item.extraction === "error") return "解析失败：没能从这份文件里提取出文本";
    return "已入库，正在建立索引";
  }
  if (status === "pending") return "库里已有相同内容，正在补建索引";
  if (status === "indexed") return "已补齐索引，可用于检索";
  if (status === "duplicate") {
    return item.existing
      ? `与库里的「${item.existing}」内容完全相同，已保留已有版本`
      : "与库里已有资料内容完全相同，已保留已有版本";
  }
  if (status === "rejected") {
    if (item.reason === "unsupported_file_type") return "格式不支持（可用 .md / .txt / .pdf / .docx / .pptx）";
    return "没有导入（格式或内容不被接受）";
  }
  if (status === "cancelled") return "已取消，没有导入";
  return "结果未知";
}
