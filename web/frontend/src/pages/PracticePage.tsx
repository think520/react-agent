import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpen, CheckCircle2, CircleHelp, LogOut, Play, RotateCcw, Send, X } from "lucide-react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { AttributionBadges, BrandIllustration, EmptyState, ErrorNotice, LoadingState, formatRelativeDate } from "../components/common";
import { api, streamChat } from "../lib/api";
import type { PracticeSession } from "../types";

interface AnswerResult {
  is_correct: boolean;
  feedback: string;
  correct_answer: string;
  explanation: string;
  attribution?: PracticeSession["questions"][number]["attribution"];
  session_completed: boolean;
}

export function PracticePage() {
  const { practiceSessionId } = useParams();
  const navigate = useNavigate();
  const { refreshSessions, selectedDocumentIds, selectedDocuments } = useOutletContext<AppOutletContext>();
  const id = practiceSessionId ? Number(practiceSessionId) : null;
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [active, setActive] = useState<Array<{ practice_session_id: number; updated_at: string; question_count: number }>>([]);
  const [topic, setTopic] = useState(() => localStorage.getItem("bobodan:practice-topic") || "");
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [loading, setLoading] = useState(Boolean(id));
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [aiOpen, setAiOpen] = useState(false);
  const [aiQuestion, setAiQuestion] = useState("给我一个不直接揭示答案的提示。");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiStatus, setAiStatus] = useState("");
  const [aiError, setAiError] = useState("");
  const [aiWorking, setAiWorking] = useState(false);

  const loadSession = useCallback(async (sessionId: number) => {
    setLoading(true);
    setError("");
    try {
      setSession(await api.practice(sessionId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法恢复练习。" );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    localStorage.removeItem("bobodan:practice-topic");
    setAnswer("");
    setResult(null);
    setAiOpen(false);
    setAiAnswer("");
    setAiError("");
    if (id) void loadSession(id);
    else void api.activePractice().then((value) => setActive(value.sessions)).catch(() => setActive([]));
  }, [id, loadSession]);

  const currentQuestion = useMemo(() => {
    if (!session) return null;
    return session.questions[Math.min(session.progress.current_index, session.questions.length - 1)] || null;
  }, [session]);

  async function createPractice(event: FormEvent) {
    event.preventDefault();
    setWorking(true);
    setError("");
    try {
      const scopeTopic = selectedDocuments.map((document) => document.title || document.source).join("、");
      const query = topic.trim() || scopeTopic;
      const generated = query
        ? await api.generateQuestions(query, undefined, selectedDocumentIds)
        : null;
      const created = await api.startPractice(undefined, generated?.question_ids || []);
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "暂时无法创建练习。请先导入相关资料。" );
    } finally {
      setWorking(false);
    }
  }

  async function submitAnswer(event: FormEvent) {
    event.preventDefault();
    if (!id || !currentQuestion || !answer.trim()) return;
    setWorking(true);
    setError("");
    try {
      const response = await api.submitAnswer(id, currentQuestion.id, answer.trim());
      setResult(response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "答案没有提交成功。" );
    } finally {
      setWorking(false);
    }
  }

  async function nextQuestion() {
    if (!id) return;
    setAnswer("");
    setResult(null);
    await loadSession(id);
  }

  async function abandon() {
    if (!id || !window.confirm("退出并放弃这次练习？已提交的答案仍会保留。")) return;
    await api.abandonPractice(id);
    navigate("/practice");
  }

  async function askAi(event: FormEvent) {
    event.preventDefault();
    if (!currentQuestion || !aiQuestion.trim() || aiWorking) return;
    setAiWorking(true);
    setAiAnswer("");
    setAiError("");
    setAiStatus("正在理解这道题");
    let nextSessionId: string | undefined;
    let profile: { learningGoal?: string; memoryEnabled?: boolean; webEnabled?: boolean } = {};
    try {
      try { profile = JSON.parse(localStorage.getItem("bobodan:learning-profile") || "{}"); }
      catch { profile = {}; }
      const prompt = [
        `我正在做这道题：${currentQuestion.question}`,
        `我的当前答案：${answer || "还没有作答"}`,
        `我的问题：${aiQuestion.trim()}`,
        "请只围绕当前题目给出分步提示或指出思考方向，不要直接替我完成答案。",
      ].join("\n\n");
      await streamChat(prompt, undefined, selectedDocumentIds, profile, (streamEvent) => {
        if (streamEvent.event === "run_started") nextSessionId = streamEvent.data.chat_session_id;
        if (streamEvent.event === "status") setAiStatus(streamEvent.data.message);
        if (streamEvent.event === "message_delta") {
          setAiStatus("正在整理提示");
          setAiAnswer((current) => current + streamEvent.data.content);
        }
        if (streamEvent.event === "run_failed") throw new Error(streamEvent.data.error.message);
        if (streamEvent.event === "run_completed") setAiStatus("");
      });
      await refreshSessions();
      if (nextSessionId) void api.generateSessionTitle(nextSessionId).then(refreshSessions).catch(() => undefined);
    } catch (reason) {
      setAiError(reason instanceof Error ? reason.message : "暂时无法获得提示，请稍后重试。");
      setAiStatus("");
    } finally {
      setAiWorking(false);
    }
  }

  if (loading) return <section className="page-scroll"><div className="page-container illustrated-loading"><BrandIllustration state="reading" size={76} /><LoadingState label="正在恢复练习进度…" /></div></section>;

  if (!id) return (
    <section className="page-scroll">
      <div className="page-container practice-start">
        <header className="page-heading"><div><span>Practice</span><h2>开始一轮练习</h2><p>默认生成 5 题，题目和批改结果会回流到掌握度与今日复习。</p></div></header>
        {error && <ErrorNotice message={error} />}
        <form className="practice-create" onSubmit={(event) => void createPractice(event)}>
          <label htmlFor="practice-topic">想练习什么？</label>
          {working && <BrandIllustration state="writing" size={64} />}
          <div><input id="practice-topic" value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="例如：Dijkstra 的贪心证明" /><button className="primary-button" disabled={working}><Play size={16} />{working ? "正在准备" : "生成 5 题"}</button></div>
          <small>留空时会从现有题库与资料重点中选择。</small>
          {selectedDocuments.length > 0 && <div className="practice-scope"><BookOpen size={15} /><span>当前范围：{selectedDocuments.map((document) => document.title || document.source).slice(0, 3).join("、")}{selectedDocuments.length > 3 ? ` 等 ${selectedDocuments.length} 份` : ""}</span></div>}
        </form>
        {active.length > 0 && <section className="resume-section"><h3>继续未完成练习</h3>{active.map((item) => (
          <button className="resume-row" key={item.practice_session_id} onClick={() => navigate(`/practice/${item.practice_session_id}`)}>
            <span><BookOpen size={17} /><strong>练习 #{item.practice_session_id}</strong><small>{item.question_count} 题 · {formatRelativeDate(item.updated_at)}</small></span><ArrowRight size={17} />
          </button>
        ))}</section>}
      </div>
    </section>
  );

  if (error && !session) return <section className="page-scroll"><div className="page-container"><ErrorNotice message={error} action={<button className="quiet-button" onClick={() => id && void loadSession(id)}><RotateCcw size={15} />重试</button>} /></div></section>;

  if (!session || !currentQuestion || session.progress.completed) return (
    <section className="page-scroll"><div className="page-container"><EmptyState state="resting" title="这一轮练习已完成" description={`答对 ${session?.progress.correct || 0} / ${session?.progress.total || 0} 题。错题和薄弱点已经加入复习队列。`} action={<button className="primary-button" onClick={() => navigate("/review")}><CheckCircle2 size={17} />查看复习建议</button>} /></div></section>
  );

  const progress = Math.max(4, ((session.progress.current_index + (result ? 1 : 0)) / session.progress.total) * 100);
  return (
    <section className="page-scroll practice-page">
      <div className="practice-container">
        <header className="practice-header"><div><span>{currentQuestion.type_label} · {currentQuestion.difficulty || "自适应"}</span><strong>第 {session.progress.current_index + 1} / {session.progress.total} 题</strong></div><button className="quiet-button" onClick={() => void abandon()}><LogOut size={15} />退出练习</button></header>
        <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        <form className="question-sheet" onSubmit={(event) => void submitAnswer(event)}>
          <h2>{currentQuestion.question}</h2>
          {currentQuestion.options?.length ? <div className="answer-options">{currentQuestion.options.map((option, index) => {
            const value = option;
            return <label className={`${answer === value ? "selected" : ""} ${result ? "locked" : ""}`} key={option}><input type="radio" name="answer" value={value} checked={answer === value} disabled={Boolean(result)} onChange={() => setAnswer(value)} /><span>{String.fromCharCode(65 + index)}</span><strong>{option}</strong></label>;
          })}</div> : <textarea className="short-answer" rows={6} value={answer} disabled={Boolean(result)} onChange={(event) => setAnswer(event.target.value)} placeholder="用自己的话写下答案。可以不完整，Bobodan 会指出缺少的部分。" />}
          <AttributionBadges attribution={currentQuestion.attribution} />
          {error && <ErrorNotice message={error} />}
          {result && <div className={`answer-feedback ${result.is_correct ? "correct" : "review"}`}><div>{result.is_correct ? <img className="brand-expression" src="/assets/brand/expressions/bobodan-expression-content.webp" width="42" height="42" alt="" /> : <CheckCircle2 size={19} />}<strong>{result.is_correct ? "答对了" : "需要再复习一下"}</strong></div><p>{result.feedback}</p>{result.explanation && <p>{result.explanation}</p>}{!result.is_correct && result.correct_answer && <small>参考答案：{result.correct_answer}</small>}</div>}
          <footer className="practice-actions">
            <button type="button" className="quiet-button" onClick={() => setAiOpen(true)}><CircleHelp size={16} />问 AI</button>
            {result ? <button type="button" className="primary-button" onClick={() => void nextQuestion()}>{result.session_completed ? "查看小结" : "下一题"}<ArrowRight size={16} /></button>
              : <button type="submit" className="primary-button" disabled={!answer.trim() || working}>{working ? "正在批改" : "提交答案"}<ArrowRight size={16} /></button>}
          </footer>
        </form>
      </div>
      {aiOpen && <aside className="practice-ai-drawer" role="dialog" aria-modal="false" aria-labelledby="practice-ai-title">
        <header><div><span>当前题目辅导</span><strong id="practice-ai-title">问 Bobodan</strong></div><button className="icon-button" type="button" aria-label="关闭问 AI" onClick={() => setAiOpen(false)}><X size={18} /></button></header>
        <div className="practice-ai-context"><small>只围绕第 {session.progress.current_index + 1} 题</small><p>{currentQuestion.question}</p></div>
        {aiAnswer && <div className="practice-ai-answer">{aiAnswer}</div>}
        {aiStatus && <div className="practice-ai-status" role="status">{aiStatus}</div>}
        {aiError && <ErrorNotice message={aiError} />}
        <form onSubmit={(event) => void askAi(event)}>
          <textarea rows={3} value={aiQuestion} aria-label="向 AI 追问当前题目" onChange={(event) => setAiQuestion(event.target.value)} />
          <button className="primary-button" disabled={aiWorking || !aiQuestion.trim()}><Send size={15} />{aiWorking ? "正在思考" : "发送"}</button>
        </form>
      </aside>}
    </section>
  );
}
