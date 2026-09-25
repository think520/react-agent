interface ImportSummaryInput {
  imported: unknown[];
  duplicates?: unknown[];
  rejected: unknown[];
  sync: { extraction_counts?: Record<string, number>; error_files?: number };
}

/** Describe extraction facts without claiming every accepted file is searchable. */
export function describeDocumentImport(result: ImportSummaryInput): string {
  const counts = result.sync.extraction_counts || {};
  const searchable = (counts.complete || 0) + (counts.partial || 0);
  const empty = counts.empty || 0;
  const failed = Math.max(counts.error || 0, result.sync.error_files || 0);
  const parts = ["已接收 " + result.imported.length + " 份文件"];
  if (searchable) parts.push(searchable + " 份可用于检索");
  if (empty) parts.push(empty + " 份没有可提取文本");
  if (failed) parts.push(failed + " 份解析失败");
  if (result.duplicates?.length) parts.push(result.duplicates.length + " 份重复文件已保留已有版本");
  if (result.rejected.length) parts.push(result.rejected.length + " 份未导入");
  return parts.join("，") + "。";
}
