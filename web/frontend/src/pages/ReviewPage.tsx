import { useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpenCheck, Brain, CheckCircle2, RefreshCw, Target } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { EmptyState, ErrorNotice, LoadingState, textValue } from "../components/common";
import { api } from "../lib/api";
import type { ReviewQueue } from "../types";

interface ReviewItem {
  id: string;
  kind: "到期" | "错题" | "薄弱点";
  title: string;
  meta: string;
  questionIds: number[];
  attemptId?: number;
}

function questionIds(record: Record<string, unknown>): number[] {
  if (Array.isArray(record.question_ids)) {
    return record.question_ids.filter((value): value is number => typeof value === "number");
  }
  return typeof record.question_id === "number" ? [record.question_id] : [];
}

export function ReviewPage() {
  const navigate = useNavigate();
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState("");
  const [error, setError] = useState("");

  async function loadQueue() {
    setLoading(true);
    setError("");
    try { setQueue(await api.reviewQueue()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "无法读取复习队列。"); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadQueue(); }, []);

  const items = useMemo<ReviewItem[]>(() => {
    if (!queue) return [];
    const dueMeta = (status: unknown) => {
      if (status === "mastered") return "已掌握，按计划到期复习";
      if (status === "learning") return "学习中，按计划到期复习";
      if (status === "needs_review") return "需要复习，今天到期";
      return "按照学习计划到期";
    };
    return [
      ...queue.due_concepts.map((record, index) => ({ id: `due-${index}`, kind: "到期" as const, title: textValue(record, ["concept", "title", "name"], "待复习知识点"), meta: dueMeta(textValue(record, ["status"], "按照学习计划到期")), questionIds: questionIds(record) })),
      ...queue.wrong_answers.map((record, index) => ({ id: `wrong-${index}`, kind: "错题" as const, title: textValue(record, ["question", "concept", "title"], "需要回看的错题"), meta: textValue(record, ["feedback", "course"], "将生成考察同一误区的变式题"), questionIds: questionIds(record), attemptId: typeof record.attempt_id === "number" ? record.attempt_id : undefined })),
      ...queue.weaknesses.map((record, index) => ({ id: `weak-${index}`, kind: "薄弱点" as const, title: textValue(record, ["concept", "name", "title"], "尚未掌握的知识点"), meta: textValue(record, ["reason", "status"], "建议进行针对性练习"), questionIds: questionIds(record) })),
    ];
  }, [queue]);

  async function startReview(item: ReviewItem) {
    setWorkingId(item.id);
    setError("");
    try {
      let ids: number[];
      if (item.kind === "错题" && item.attemptId) {
        ids = [(await api.generateWrongAnswerVariant(item.attemptId)).question_id];
      } else {
        ids = item.questionIds.length ? item.questionIds : (await api.generateQuestions(item.title)).question_ids || [];
      }
      const practice = await api.startPractice(undefined, ids, "review");
      navigate(`/practice/${practice.practice_session_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法准备复习题。");
      setWorkingId("");
    }
  }

  return (
    <section className="page-scroll">
      <div className="page-container review-container">
        <header className="page-heading"><div><span>Review</span><h2>今天的复习</h2><p>先处理到期内容，再回到新的学习任务。</p></div><button className="quiet-button" onClick={() => void loadQueue()}><RefreshCw size={16} />刷新</button></header>
        {error && <ErrorNotice message={error} />}
        {loading ? <LoadingState label="正在整理复习队列…" /> : items.length ? <>
          {queue?.personalization?.length ? <details className="personalization-chip review-personalization"><summary><Brain size={13} />复习排序依据 <span>{queue.personalization.length}</span></summary><div>{queue.personalization.map((reference) => <section key={reference.id}><strong>{reference.title}</strong><p>{reference.content}</p><small>{reference.scope === "global" ? "全局" : "当前资料库"}</small></section>)}</div></details> : null}
          <div className="review-summary">
            <div><strong>{queue?.due_concepts.length || 0}</strong><span>到期知识点</span></div>
            <div><strong>{queue?.wrong_answers.length || 0}</strong><span>需要回看的错题</span></div>
            <div><strong>{queue?.weaknesses.length || 0}</strong><span>当前薄弱点</span></div>
          </div>
          <div className="review-list">{items.map((item, index) => (
            <article className="review-row" key={item.id}>
              <span className="review-index">{String(index + 1).padStart(2, "0")}</span>
              <span className={`review-kind ${item.kind}`}>{item.kind}</span>
              <div><h3>{item.title}</h3><p>{item.meta}</p></div>
              <button className="quiet-button" disabled={Boolean(workingId)} onClick={() => void startReview(item)}>{workingId === item.id ? "正在准备" : item.kind === "错题" ? "生成变式题" : "开始复习"}<ArrowRight size={15} /></button>
            </article>
          ))}</div>
        </> : <EmptyState state="resting" title="今天没有到期内容" description="可以开始一轮新练习，或回到资料库继续阅读。" action={<button className="primary-button" onClick={() => navigate("/practice")}><BookOpenCheck size={17} />开始练习</button>} />}
        <section className="review-note"><Target size={20} /><div><strong>复习不是重新读一遍</strong><p>Bobodan 会优先让你主动回忆，再用解释和资料定位补齐缺口。</p></div><CheckCircle2 size={18} /></section>
      </div>
    </section>
  );
}
