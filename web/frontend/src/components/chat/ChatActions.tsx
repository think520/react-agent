import { ArrowUpRight, BookOpen, Check, Copy, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { FollowUpSuggestion } from "../../lib/chatFollowUps";

/** Chat 的 Actions 层（W-F7）：回答下方的可执行动作（练习 / 复制 / 快捷追问）。 */
export function AnswerActions({
  content = "",
  onPreparePractice,
  followUps,
  disabled = false,
  onFollowUp,
}: {
  content?: string;
  onPreparePractice: () => void;
  followUps?: FollowUpSuggestion[];
  disabled?: boolean;
  onFollowUp?: (prompt: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  async function handleCopy() {
    if (!content) return;
    try {
      await navigator.clipboard?.writeText(content);
      setCopied(true);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="answer-footer-block">
      <div className="answer-actions">
        <button className="quiet-button" type="button" onClick={onPreparePractice}>
          <BookOpen size={15} />
          生成 5 道练习
        </button>
        {content && (
          <button
            className="quiet-button"
            type="button"
            aria-label={copied ? "已复制回答" : "复制回答"}
            onClick={() => void handleCopy()}
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
            {copied ? "已复制" : "复制"}
          </button>
        )}
      </div>
      {followUps && followUps.length > 0 && onFollowUp && (
        <div className="answer-followups" aria-label="继续追问">
          {followUps.map((item) => (
            <button
              key={item.label}
              type="button"
              className="followup-chip"
              disabled={disabled}
              onClick={() => onFollowUp(item.prompt)}
            >
              <span>{item.label}</span>
              <ArrowUpRight size={13} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AnswerFailure({ message, disabled, onRetry }: { message: string; disabled: boolean; onRetry: () => void }) {
  return <div className="answer-failure"><span>{message}</span><button className="quiet-button" disabled={disabled} onClick={onRetry}><RotateCcw size={15} />重新发送本轮</button></div>;
}
