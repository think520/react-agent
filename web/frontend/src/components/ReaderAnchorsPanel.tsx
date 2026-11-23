import type { ReactNode } from "react";
import { NotebookPen, Quote, Target, Trash2 } from "lucide-react";

export interface ReaderAnchor {
  anchor_id: string;
  chunk_id: string;
  quote: string;
  resolution?: {
    status: string;
    char_start: number | null;
    char_end: number | null;
    /** 重锚定之后引文实际落在哪一段（跨分段找回时与 chunk_id 不同）。 */
    chunk_id?: string | null;
  };
}

const STATUS_LABEL: Record<string, string> = {
  exact: "位置未变",
  relocated: "位置已更新",
  stale: "已失效，需重新指认",
};

/** 定位要跳哪一段：优先用重锚定找回来的那一段（引文可能已经换了 chunk）。 */
export function anchorLocateChunkId(anchor: ReaderAnchor): string {
  return anchor.resolution?.chunk_id || anchor.chunk_id;
}

export function anchorStatusLabel(status?: string): string {
  if (!status) return "";
  return STATUS_LABEL[status] || status;
}

/**
 * W1 E7：这份资料上的划线列表。
 *
 * 每条都显示**还能不能指到**（exact / relocated / stale）—— 资料被编辑或分段重切之后，
 * 划线可能已经对不上原文；那时的正确做法是说出来，而不是假装还指得到。
 */
export function ReaderAnchorsPanel({
  anchors,
  onLocate,
  onDelete,
  onSaveToNote,
  onSaveAllToNote,
  savingNote = false,
  noteActionSlot,
}: {
  anchors: ReaderAnchor[];
  onLocate: (anchor: ReaderAnchor) => void;
  onDelete: (anchor: ReaderAnchor) => void;
  onSaveToNote?: (anchor: ReaderAnchor) => void;
  onSaveAllToNote?: () => void;
  savingNote?: boolean;
  noteActionSlot?: ReactNode;
}) {
  if (!anchors.length) return null;
  return (
    <section className="reader-anchors" aria-label="我的划线">
      <header>
        <div className="reader-anchors-title">
          <Quote size={14} />
          <strong>我的划线（{anchors.length}）</strong>
        </div>
        {onSaveAllToNote && (
          <div className="reader-anchors-header-actions">
            <button
              type="button"
              className="quiet-button"
              disabled={savingNote}
              onClick={onSaveAllToNote}
            >
              <NotebookPen size={14} />
              {savingNote ? "正在写入..." : "全部转笔记"}
            </button>
          </div>
        )}
      </header>
      {noteActionSlot}
      <ul>
        {anchors.map((anchor) => (
          <li key={anchor.anchor_id} className={`reader-anchor ${anchor.resolution?.status || ""}`}>
            <button type="button" className="reader-anchor-quote" onClick={() => onLocate(anchor)}>
              {anchor.quote}
            </button>
            <div className="reader-anchor-actions">
              <small>{anchorStatusLabel(anchor.resolution?.status)}</small>
              {onSaveToNote && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label="转为笔记"
                  title="转为笔记"
                  disabled={savingNote}
                  onClick={() => onSaveToNote(anchor)}
                >
                  <NotebookPen size={14} />
                </button>
              )}
              <button type="button" className="icon-button" aria-label="定位到这段" onClick={() => onLocate(anchor)}>
                <Target size={14} />
              </button>
              <button type="button" className="icon-button" aria-label="删除这条划线" onClick={() => onDelete(anchor)}>
                <Trash2 size={14} />
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
