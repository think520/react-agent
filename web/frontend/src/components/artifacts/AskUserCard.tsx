import { Check, CircleHelp } from "lucide-react";
import { useState } from "react";

import type { AskUserArtifact } from "../../types";

/**
 * E4: renders an ask_user interaction. The card is projected from the persisted
 * lifecycle, so a reload shows the answers in place instead of asking again.
 */
export function AskUserCard({ artifact, busy, onAnswer, onSkip }: {
  artifact: AskUserArtifact;
  busy: boolean;
  onAnswer: (artifact: AskUserArtifact, answers: Array<{ id: string; answer: string }>) => void;
  /** W1 E4：先不答 —— 关闭这张卡片并让暂停的那一轮继续（不是把用户晾在这儿）。 */
  onSkip?: (artifact: AskUserArtifact) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  // W1 E4：multi_select 的答案是**一组**，必须与单选分开存 —— 旧实现只有一份字符串草稿，
  // 点第二个选项就把第一个顶掉，"可以多选"从来没有兑现过。
  const [multiDraft, setMultiDraft] = useState<Record<string, string[]>>({});
  const resolved = artifact.status === "answered" || artifact.status === "graded";
  const answersById = new Map((artifact.answers || []).map((item) => [item.id, item.answer]));
  // A closed interaction is not necessarily an answered one: the session moving
  // on (or the data-hygiene window) skips it, and the card must say so instead
  // of rendering empty answers as if the user had chosen.
  const skipped = resolved && Boolean(artifact.closure) && artifact.closure !== "answered";

  if (resolved) {
    return <section className={["ask-user-card", "resolved", skipped ? "skipped" : ""].filter(Boolean).join(" ")}>
      <header><span><CircleHelp size={15} />需要你选择</span><strong>{skipped ? "没有作答，已跳过" : "已回答"}</strong></header>
      <div className="ask-user-summary">
        {artifact.questions.map((question) => (
          <div key={question.id}><small>{question.prompt}</small><p>{answersById.get(question.id) || (skipped ? "未回答" : "—")}</p></div>
        ))}
      </div>
    </section>;
  }

  const picks = (id: string) => multiDraft[id] || [];
  const complete = artifact.questions.every((question) => question.multi_select
    ? picks(question.id).length > 0
    : (draft[question.id] || "").trim().length > 0);

  function choose(question: { id: string; multi_select?: boolean }, option: string) {
    if (!question.multi_select) {
      setDraft((current) => ({ ...current, [question.id]: option }));
      return;
    }
    setMultiDraft((current) => {
      const currentPicks = current[question.id] || [];
      const next = currentPicks.includes(option)
        ? currentPicks.filter((item) => item !== option)
        : [...currentPicks, option];
      return { ...current, [question.id]: next };
    });
  }

  function answerFor(question: { id: string; multi_select?: boolean }): string {
    if (!question.multi_select) return (draft[question.id] || "").trim();
    return picks(question.id).join(", ");
  }
  return <section className="ask-user-card">
    <header><span><CircleHelp size={15} />需要你选择</span><strong>回答后 Bobodan 会继续</strong></header>
    <div className="ask-user-questions">
      {artifact.questions.map((question) => (
        <div key={question.id} className="ask-user-question">
          <p>{question.prompt}</p>
          {question.options && question.options.length > 0
            ? <div className="ask-user-options">
                {question.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={question.multi_select
                      ? (picks(question.id).includes(option) ? "active" : "")
                      : (draft[question.id] === option ? "active" : "")}
                    aria-pressed={question.multi_select ? picks(question.id).includes(option) : undefined}
                    onClick={() => choose(question, option)}
                  >{option}</button>
                ))}
              </div>
            : <input
                value={draft[question.id] || ""}
                onChange={(event) => setDraft((current) => ({ ...current, [question.id]: event.target.value }))}
                placeholder="写下你的回答"
              />}
        </div>
      ))}
    </div>
    <footer>
      {onSkip && (
        <button className="quiet-button" type="button" disabled={busy} onClick={() => onSkip(artifact)}>
          先不答，跳过
        </button>
      )}
      <button
        className="primary-button"
        disabled={busy || !complete}
        onClick={() => onAnswer(artifact, artifact.questions.map((question) => ({ id: question.id, answer: answerFor(question) })))}
      ><Check size={15} />提交</button>
    </footer>
  </section>;
}
