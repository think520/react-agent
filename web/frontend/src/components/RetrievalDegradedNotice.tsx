import type { RetrievalSemanticReason } from "../types";

/**
 * W2 降级可见性：检索降级时，界面上不能只说"降级了"。
 *
 * 后端在 `rag/retrieval_status.py` 里把原因整理成 code / title / detail / action；
 * 这里把它渲染成一句结论 + 事实 + 下一步。没有原因载荷（老会话）时退回原来的文案，
 * 保证不会比以前更含糊。
 */

export function degradedHeadline(
  reason: RetrievalSemanticReason | undefined,
  hitCount: number | undefined,
): string {
  if (reason?.title) return reason.title;
  return hitCount ? "当前仅使用关键词检索" : "关键词检索未命中，向量检索当前不可用";
}

export function RetrievalDegradedNotice({
  reason,
  hitCount,
}: {
  reason?: RetrievalSemanticReason;
  hitCount?: number;
}) {
  return (
    <details className="retrieval-degraded">
      <summary>{degradedHeadline(reason, hitCount)}</summary>
      {reason?.detail && <p className="retrieval-degraded-detail">{reason.detail}</p>}
      {reason?.action && (
        <p className="retrieval-degraded-action">下一步：{reason.action}</p>
      )}
      {!reason && (
        <p className="retrieval-degraded-detail">
          这次回答只用到了关键词检索；语义（向量）检索当时不可用。
        </p>
      )}
    </details>
  );
}
