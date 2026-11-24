import { useInRouterContext, useSearchParams } from "react-router-dom";

import type { RetrievalSemanticReason } from "../types";

/**
 * W2 降级可见性：检索降级时，界面上不能只说"降级了"。
 *
 * 后端在 `rag/retrieval_status.py` 里把原因整理成 code / title / detail / action；
 * 这里把它渲染成一句结论 + 事实 + 下一步 + 直达「检索与 RAG」的按钮。
 */
export function degradedHeadline(
  reason: RetrievalSemanticReason | undefined,
  hitCount: number | undefined,
): string {
  if (reason?.title) return reason.title;
  return hitCount ? "当前仅使用关键词检索" : "关键词检索未命中，向量检索当前不可用";
}

function RouterRagJumpButton({ onOpenRagSettings }: { onOpenRagSettings?: () => void }) {
  const [searchParams, setSearchParams] = useSearchParams();

  function openRag() {
    if (onOpenRagSettings) {
      onOpenRagSettings();
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set("settings", "rag");
    setSearchParams(next, { replace: true });
  }

  return (
    <button type="button" className="retrieval-degraded-link" onClick={openRag}>
      去「检索与 RAG」处理 →
    </button>
  );
}

export function RetrievalDegradedNotice({
  reason,
  hitCount,
  onOpenRagSettings,
}: {
  reason?: RetrievalSemanticReason;
  hitCount?: number;
  onOpenRagSettings?: () => void;
}) {
  const inRouter = useInRouterContext();
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
      {(inRouter || onOpenRagSettings) && (
        <div className="retrieval-degraded-actions">
          {inRouter ? (
            <RouterRagJumpButton onOpenRagSettings={onOpenRagSettings} />
          ) : (
            <button type="button" className="retrieval-degraded-link" onClick={onOpenRagSettings}>
              去「检索与 RAG」处理 →
            </button>
          )}
        </div>
      )}
    </details>
  );
}
