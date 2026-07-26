import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpen, Brain, CheckCircle2, CircleHelp, Globe2, LogOut, Play, RotateCcw, Send, X } from "lucide-react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { AttributionBadges, BrandIllustration, EmptyState, ErrorNotice, LoadingState, formatRelativeDate } from "../components/common";
import { api, streamChat } from "../lib/api";
import { toErrorMessage } from "../lib/errors";
import { useHandoffStore } from "../stores/handoffStore";
import { useUiStore } from "../stores/uiStore";
import type { PracticeSession } from "../types";

interface AnswerResult {
  is_correct: boolean;
  feedback: string;
  correct_answer: string;
  explanation: string;
  attribution?: PracticeSession["questions"][number]["attribution"];
  session_completed: boolean;
}

interface WebPracticeConsent {
  query: string;
  reason: string;
  suggestedQuery?: string;
}

function questionTypeLabel(type: string, fallback: string) {
  if (type === "true_false") return "判断题";
  if (type === "single_choice") return "单选题";
  if (type === "short_answer") return "简答题";
  return fallback;
}

function difficultyLabel(value?: string) {
  if (value === "easy") return "简单难度";
  if (value === "hard") return "较难难度";
  if (value === "medium") return "中等难度";
  return value || "自适应难度";
}

export function PracticePage() {
  const { practiceSessionId } = useParams();
  const navigate = useNavigate();
  const { refreshSessions, selectedDocumentIds, selectedDocuments } = useOutletContext<AppOutletContext>();
  const id = practiceSessionId ? Number(practiceSessionId) : null;
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [active, setActive] = useState<Array<{ practice_session_id: number; updated_at: string; question_count: number }>>([]);
  const [topic, setTopic] = useState(() => useHandoffStore.getState().practiceTopic || "");
  const [webResearchId] = useState(() => useHandoffStore.getState().practiceWebResearchId || "");
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [loading, setLoading] = useState(Boolean(id));
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [webConsent, setWebConsent] = useState<WebPracticeConsent | null>(null);
  const [resolution, setResolution] = useState<{ original: string; resolved: string } | null>(null);
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
      setError(toErrorMessage(reason, "无法恢复练习。"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    useHandoffStore.getState().clearPracticeHandoff();
    setAnswer("");
    setResult(null);
    setAiOpen(false);
    setAiAnswer("");
    setAiError("");
    setWebConsent(null);
    if (id) {
      try { setResolution(JSON.parse(sessionStorage.getItem(`bobodan:practice-resolution:${id}`) || "null")); }
      catch { setResolution(null); }
    } else {
      setResolution(null);
    }
    if (id) void loadSession(id);
    else void api.activePractice().then((value) => setActive(value.sessions)).catch(() => setActive([]));
  }, [id, loadSession]);

  const currentQuestion = useMemo(() => {
    if (!session) return null;
    return session.questions[Math.min(session.progress.current_index, session.questions.length - 1)] || null;
  }, [session]);

  async function createPractice(event?: FormEvent, webConfirmed = false) {
    event?.preventDefault();
    setWorking(true);
    setError("");
    if (!webConfirmed) setWebConsent(null);
    try {
      const scopeTopic = selectedDocuments.map((document) => document.title || document.source).join("、");
      const query = topic.trim() || scopeTopic;
      const generated = query
        ? await api.generateQuestions(query, undefined, selectedDocumentIds, webResearchId || undefined, webConfirmed)
        : null;
      if (generated?.status === "web_consent_required") {
        setWebConsent({
          query: generated.query || query,
          reason: generated.reason || "当前本地资料不足。",
          suggestedQuery: generated.suggested_query,
        });
        return;
      }
      const created = await api.startPractice(
        undefined,
        generated?.question_ids || [],
        "practice",
        generated?.personalization || [],
      );
      const resolved = generated?.resolved_query || query;
      if (query && resolved && resolved.toLocaleLowerCase() !== query.toLocaleLowerCase()) {
        sessionStorage.setItem(`bobodan:practice-resolution:${created.practice_session_id}`, JSON.stringify({ original: query, resolved }));
      }
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(toErrorMessage(reason, "暂时无法创建练习。请先导入相关资料。"));
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
      setError(toErrorMessage(reason, "答案没有提交成功。"));
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
    try {
      const profile = useUiStore.getState().learningProfile;
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
      setAiError(toErrorMessage(reason, "暂时无法获得提示，请稍后重试。"));
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
          <div><input id="practice-topic" value={topic} onChange={(event) => { setTopic(event.target.value); setWebConsent(null); }} placeholder="例如：Dijkstra 的贪心证明" /><button className="primary-button" disabled={working}><Play size={16} />{working ? "正在准备" : "生成 5 题"}</button></div>
          <small>留空时会从现有题库与资料重点中选择。</small>
          {selectedDocuments.length > 0 && <div className="practice-scope"><BookOpen size={15} /><span>当前范围：{selectedDocuments.map((document) => document.title || document.source).slice(0, 3).join("、")}{selectedDocuments.length > 3 ? ` 等 ${selectedDocuments.length} 份` : ""}</span></div>}
          {webConsent && <section className="practice-web-consent">
            <BrandIllustration state="reading" size={54} />
            <div><strong>本地资料暂时不足</strong><p>{webConsent.reason}</p>{webConsent.suggestedQuery && <small>建议按“{webConsent.suggestedQuery}”继续查找</small>}</div>
            <button type="button" className="primary-button" disabled={working} onClick={() => void createPractice(undefined, true)}><Globe2 size={15} />联网找资料出题</button>
          </section>}
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
  const answerChoices = currentQuestion.type === "true_false"
    ? [
        { value: "true", marker: "对", label: "正确" },
        { value: "false", marker: "错", label: "错误" },
      ]
    : (currentQuestion.options || []).map((option, index) => ({
        value: option,
        marker: String.fromCharCode(65 + index),
        label: option,
      }));
  return (
    <section className="page-scroll practice-page">
      <div className="practice-container">
        <header className="practice-header"><div><span>{questionTypeLabel(currentQuestion.type, currentQuestion.type_label)} · {difficultyLabel(currentQuestion.difficulty)}</span><strong>第 {session.progress.current_index + 1} / {session.progress.total} 题</strong>{resolution && <small>已将“{resolution.original}”按“{resolution.resolved}”理解</small>}</div><button className="quiet-button" onClick={() => void abandon()}><LogOut size={15} />退出练习</button></header>
        <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        {session.personalization?.length ? <details className="personalization-chip practice-personalization"><summary><Brain size={13} />本轮个性化依据 <span>{session.personalization.length}</span></summary><div>{session.personalization.map((reference) => <section key={reference.id}><strong>{reference.title}</strong><p>{reference.content}</p><small>{reference.scope === "global" ? "全局" : "当前资料库"}</small></section>)}</div></details> : null}
        <form className="question-sheet" onSubmit={(event) => void submitAnswer(event)}>
          <h2>{currentQuestion.question}</h2>
          {answerChoices.length ? <div className="answer-options">{answerChoices.map((choice) => (
            <label className={`${answer === choice.value ? "selected" : ""} ${result ? "locked" : ""}`} key={choice.value}><input type="radio" name="answer" value={choice.value} checked={answer === choice.value} disabled={Boolean(result)} onChange={() => setAnswer(choice.value)} /><span>{choice.marker}</span><strong>{choice.label}</strong></label>
          ))}</div> : <textarea className="short-answer" rows={6} value={answer} disabled={Boolean(result)} onChange={(event) => setAnswer(event.target.value)} placeholder="用自己的话写下答案。可以不完整，Bobodan 会指出缺少的部分。" />}
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
