import { Check, CircleHelp } from "lucide-react";
import { useState } from "react";

import type { AskUserArtifact } from "../../types";

/**
 * E4: renders an ask_user interaction. The card is projected from the persisted
 * lifecycle, so a reload shows the answers in place instead of asking again.
 */
export function AskUserCard({ artifact, busy, onAnswer }: {
  artifact: AskUserArtifact;
  busy: boolean;
  onAnswer: (artifact: AskUserArtifact, answers: Array<{ id: string; answer: string }>) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const resolved = artifact.status === "answered" || artifact.status === "graded";
  const answersById = new Map((artifact.answers || []).map((item) => [item.id, item.answer]));

  if (resolved) {
    return <section className="ask-user-card resolved">
      <header><span><CircleHelp size={15} />需要你选择</span><strong>已回答</strong></header>
      <div className="ask-user-summary">
        {artifact.questions.map((question) => (
          <div key={question.id}><small>{question.prompt}</small><p>{answersById.get(question.id) || "—"}</p></div>
        ))}
      </div>
    </section>;
  }

  const complete = artifact.questions.every((question) => (draft[question.id] || "").trim().length > 0);
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
                    className={draft[question.id] === option ? "active" : ""}
                    onClick={() => setDraft((current) => ({ ...current, [question.id]: option }))}
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
      <button
        className="primary-button"
        disabled={busy || !complete}
        onClick={() => onAnswer(artifact, artifact.questions.map((question) => ({ id: question.id, answer: (draft[question.id] || "").trim() })))}
      ><Check size={15} />提交</button>
    </footer>
  </section>;
}
