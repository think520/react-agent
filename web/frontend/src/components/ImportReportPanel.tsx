import { AlertTriangle, CheckCircle2, Info, RotateCcw, X } from "lucide-react";

import { describeImportOutcome } from "../lib/importSummary";
import type { ImportBatchResult } from "../lib/api";

interface ImportReportPanelProps {
  results: ImportBatchResult[];
  /** 还能拿到原文件对象时才允许重试（E8：不能给假按钮）。 */
  canRetry?: boolean;
  retrying?: boolean;
  onRetryFailed: () => void;
  onDismiss: () => void;
}

/** 这一份要不要人管：解析失败 / 格式被拒 / 取消了。 */
function needsAttention(item: ImportBatchResult): boolean {
  if (item.status === "rejected" || item.status === "cancelled") return true;
  return item.status === "imported" && !item.searchable;
}

/**
 * E8：导入结果**逐文件**列清楚（文件名 + 可行动原因 + 重试）。
 *
 * 之前整批只有一句汇总（"N 份解析失败"），用户既不知道是哪几份、也不知道能怎么办。
 * 参考 OpenMAIC 的逐项失败列表：失败是"这一项失败"，不是整批失败。
 */
export function ImportReportPanel({
  results,
  canRetry = false,
  retrying = false,
  onRetryFailed,
  onDismiss,
}: ImportReportPanelProps) {
  if (!results.length) return null;
  const attention = results.filter(needsAttention);
  const ordered = [...attention, ...results.filter((item) => !needsAttention(item))];

  return (
    <section className="import-report" aria-label="导入结果">
      <header className="import-report-head">
        <div>
          <strong>本次导入 {results.length} 份</strong>
          <span className="text-faint">
            {attention.length ? `${attention.length} 份需要处理` : "全部处理完成"}
          </span>
        </div>
        <div className="import-report-actions">
          {canRetry && attention.length > 0 && (
            <button className="quiet-button" disabled={retrying} onClick={onRetryFailed}>
              <RotateCcw size={14} />{retrying ? "正在重试" : `重试这 ${attention.length} 份`}
            </button>
          )}
          <button className="quiet-button" aria-label="关闭导入结果" onClick={onDismiss}><X size={14} /></button>
        </div>
      </header>
      <ul className="import-report-list">
        {ordered.map((item) => {
          const flagged = needsAttention(item);
          return (
            <li className="import-report-row" data-testid="import-report-row" key={item.filename}>
              {flagged
                ? <AlertTriangle size={14} className="import-report-icon is-warning" />
                : item.status === "duplicate"
                  ? <Info size={14} className="import-report-icon" />
                  : <CheckCircle2 size={14} className="import-report-icon is-ok" />}
              <span className="import-report-name">{item.filename}</span>
              <span className="text-faint">{describeImportOutcome(item)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
