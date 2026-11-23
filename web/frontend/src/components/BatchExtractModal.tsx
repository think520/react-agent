import { useEffect, useMemo, useState } from "react";
import { Sparkles, X } from "lucide-react";

import { api } from "../lib/api";
import type {
  BatchExtractionResponse,
  DocumentExtractionStatus,
  DocumentSummary,
} from "../types";
import { Modal } from "../ui/Modal";

const MAX_BATCH_SELECT = 20;

interface BatchExtractModalProps {
  onClose: () => void;
  onStarted?: (res: BatchExtractionResponse) => void;
  initialFilenames?: string[];
  initialDocumentIds?: string[];
}

function baseName(value: string): string {
  const cleaned = value.trim().replace(/\\/g, "/");
  const last = cleaned.split("/").pop() || "";
  return last.toLowerCase();
}

function statusMeta(entry: DocumentExtractionStatus | undefined): { label: string; className: string } {
  if (!entry) return { label: "未提取", className: "km-batch-badge" };
  if (entry.status === "extracting") return { label: "提取中", className: "km-batch-badge tone-extracting" };
  if (entry.status === "review") return { label: `待审查 ${entry.pending_count}`, className: "km-batch-badge tone-review" };
  if (entry.status === "completed") return { label: "已提取", className: "km-batch-badge tone-completed" };
  if (entry.status === "failed") return { label: "上次失败", className: "km-batch-badge tone-failed" };
  return { label: "未提取", className: "km-batch-badge" };
}

export function BatchExtractModal({
  onClose,
  onStarted,
  initialFilenames,
  initialDocumentIds,
}: BatchExtractModalProps) {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [statuses, setStatuses] = useState<Record<string, DocumentExtractionStatus>>({});
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      api.documents("material"),
      api.graphExtractionStatuses().catch(() => ({ documents: {} as Record<string, DocumentExtractionStatus> })),
    ])
      .then(([allDocs, statusRes]) => {
        if (cancelled) return;
        const searchable = (allDocs || []).filter((doc) => (doc.chunk_count ?? 0) > 0);
        const statusMap = statusRes?.documents || {};
        setDocs(searchable);
        setStatuses(statusMap);

        const idSet = new Set(initialDocumentIds || []);
        const nameSet = new Set(
          (initialFilenames || []).flatMap((name) => {
            const lower = name.trim().toLowerCase();
            const base = baseName(name);
            return [lower, base].filter(Boolean);
          }),
        );

        const initial: string[] = (idSet.size > 0 || nameSet.size > 0)
          ? searchable
            .filter((doc) => statusMap[doc.document_id]?.status !== "extracting")
            .filter((doc) => (
              idSet.has(doc.document_id)
              || nameSet.has(doc.source.toLowerCase())
              || nameSet.has(baseName(doc.source))
              || nameSet.has((doc.relative_path || "").toLowerCase())
              || nameSet.has(baseName(doc.relative_path || ""))
              || nameSet.has((doc.title || "").toLowerCase())
            ))
            .slice(0, 5)
            .map((doc) => doc.document_id)
          : searchable
            .filter((doc) => {
              const st = statusMap[doc.document_id]?.status;
              return !st || st === "failed";
            })
            .slice(0, 3)
            .map((doc) => doc.document_id);
        setSelectedIds(initial);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "无法读取资料列表。");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [initialDocumentIds, initialFilenames]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const atLimit = selectedIds.length >= MAX_BATCH_SELECT;

  function toggleDoc(documentId: string) {
    setSelectedIds((prev) => {
      if (prev.includes(documentId)) return prev.filter((id) => id !== documentId);
      if (prev.length >= MAX_BATCH_SELECT) return prev;
      return [...prev, documentId];
    });
  }

  function selectUnextracted() {
    const next = docs
      .filter((doc) => {
        const st = statuses[doc.document_id]?.status;
        return !st || st === "failed";
      })
      .slice(0, MAX_BATCH_SELECT)
      .map((doc) => doc.document_id);
    setSelectedIds(next);
  }

  async function submit() {
    if (!selectedIds.length || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.graphStartBatchExtraction({ document_ids: selectedIds });
      onStarted?.(response);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "启动批量提取失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal onClose={onClose} ariaLabel="批量提取概念" className="km-dialog km-batch-dialog" zIndex={125}>
      <header>
        <h3>批量提取概念</h3>
        <button type="button" className="icon-button" aria-label="关闭" onClick={onClose}>
          <X size={15} />
        </button>
      </header>
      <p className="km-batch-note">
        将按顺序在后台提取概念候选，完成后需在「待审查候选」中确认才会加入图谱。
      </p>

      {loading ? (
        <p className="km-batch-status" aria-live="polite">正在读取可提取资料…</p>
      ) : docs.length === 0 ? (
        <p className="km-batch-status">暂无已建立索引的资料，请先到资料库导入并解析文档。</p>
      ) : (
        <>
          <div className="km-batch-tools">
            <button type="button" className="btn-sm btn-ghost" onClick={selectUnextracted}>仅选未提取</button>
            <button type="button" className="btn-sm btn-ghost" onClick={() => setSelectedIds([])}>清空</button>
            <span className="km-batch-count">已选 {selectedIds.length} / {MAX_BATCH_SELECT} 份</span>
          </div>
          <ul className="km-batch-list">
            {docs.map((doc) => {
              const entry = statuses[doc.document_id];
              const badge = statusMeta(entry);
              const isExtracting = entry?.status === "extracting";
              const checked = selectedSet.has(doc.document_id);
              const disabled = isExtracting || (!checked && atLimit);
              return (
                <li key={doc.document_id}>
                  <label className={`km-batch-row ${disabled ? "is-disabled" : ""}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggleDoc(doc.document_id)}
                    />
                    <span className="km-batch-doc">
                      <strong>{doc.title || doc.source}</strong>
                      <small>{doc.course ? `${doc.course} · ` : ""}{doc.chunk_count ?? 0} 个片段</small>
                    </span>
                    <span className={badge.className}>{badge.label}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </>
      )}

      {error && <p className="km-dialog-error" role="alert">{error}</p>}

      <footer>
        <button type="button" className="quiet-button" onClick={onClose}>取消</button>
        <button
          type="button"
          className="primary-button"
          disabled={loading || submitting || selectedIds.length === 0}
          onClick={() => void submit()}
        >
          <Sparkles size={14} />
          {submitting ? "正在启动…" : `开始提取（${selectedIds.length}）`}
        </button>
      </footer>
    </Modal>
  );
}
