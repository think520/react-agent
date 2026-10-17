import { BookOpen, RotateCcw } from "lucide-react";

/** Chat 的 Actions 层（W-F7）：回答下方的可执行动作（练习 / 重试）。 */
export function AnswerActions({ onPreparePractice }: { onPreparePractice: () => void }) {
  return <div className="answer-actions"><button className="quiet-button" onClick={onPreparePractice}><BookOpen size={15} />生成 5 道练习</button></div>;
}

export function AnswerFailure({ message, disabled, onRetry }: { message: string; disabled: boolean; onRetry: () => void }) {
  return <div className="answer-failure"><span>{message}</span><button className="quiet-button" disabled={disabled} onClick={onRetry}><RotateCcw size={15} />重新发送本轮</button></div>;
}
