import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Bookmark, BookmarkCheck, Play, RefreshCw, Search, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AttributionBadges, EmptyState, ErrorNotice, LoadingState, formatRelativeDate } from "../components/common";
import { api } from "../lib/api";
import { toErrorMessage } from "../lib/errors";
import type { QuestionBank, QuestionBankItem, QuestionBankState } from "../types";

const PAGE_SIZE = 20;

const FILTERS: Array<{ key: string; label: string }> = [
  { key: "all", label: "全部" },
  { key: "unanswered", label: "未作答" },
  { key: "incorrect", label: "错题" },
  { key: "partial", label: "基本正确" },
  { key: "correct", label: "答对" },
  { key: "bookmarked", label: "已收藏" },
];

const STATE_LABELS: Record<QuestionBankState, string> = {
  unanswered: "未作答",
  correct: "答对",
  partial: "基本正确",
  incorrect: "答错",
};

function stateLabel(state: QuestionBankState) {
  return STATE_LABELS[state] || state;
}

function filterCount(overview: QuestionBank["overview"], key: string) {
  if (key === "all") return overview.total;
  if (key === "bookmarked") return overview.bookmarked;
  if (key === "unanswered") return overview.unanswered;
  if (key === "correct") return overview.correct;
  if (key === "partial") return overview.partial;
  if (key === "incorrect") return overview.incorrect;
  return 0;
}

export function QuestionBankPage() {
  const navigate = useNavigate();
  const [state, setState] = useState("all");
  const [concept, setConcept] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [page, setPage] = useState(0);
  const [bank, setBank] = useState<QuestionBank | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(0);
  const [starting, setStarting] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
      setPage(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setBank(await api.questionBank({
        state,
        concept: concept || undefined,
        query: debouncedQuery || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }));
    } catch (reason) {
      setError(toErrorMessage(reason, "无法读取题库。"));
    } finally {
      setLoading(false);
    }
  }, [state, concept, debouncedQuery, page]);

  useEffect(() => { void load(); }, [load]);

  function selectFilter(key: string) {
    setState(key);
    setPage(0);
  }

  async function toggleBookmark(item: QuestionBankItem) {
    setBusyId(item.id);
    setError("");
    try {
      const result = await api.bookmarkQuestion(item.id, !item.bookmarked);
      setBank((current) => current ? {
        ...current,
        items: current.items.map((entry) => entry.id === item.id
          ? { ...entry, bookmarked: result.bookmarked }
          : entry),
        overview: {
          ...current.overview,
          bookmarked: Math.max(0, current.overview.bookmarked + (result.bookmarked ? 1 : -1)),
        },
      } : current);
      // The "已收藏" view is defined by the bookmark itself, so it has to re-read.
      if (state === "bookmarked") await load();
    } catch (reason) {
      setError(toErrorMessage(reason, "标记失败，请稍后重试。"));
    } finally {
      setBusyId(0);
    }
  }

  async function startPractice(item: QuestionBankItem) {
    setStarting(`question-${item.id}`);
    setError("");
    try {
      const created = await api.startBankPractice([item.id]);
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法开始这一题。"));
      setStarting("");
    }
  }

  async function practiceSelection() {
    setStarting("selection");
    setError("");
    try {
      const created = await api.startBankPractice([], state, 5);
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法开始练习。"));
      setStarting("");
    }
  }

  const overview = bank?.overview;
  const totalPages = bank ? Math.max(1, Math.ceil(bank.total / PAGE_SIZE)) : 1;
  const conceptPool = overview?.by_concept || [];

  return (
    <section className="page-scroll">
      <div className="page-container review-container">
        <header className="page-heading">
          <div><span>Practice</span><h2>题库</h2><p>已经生成过的题目都在这里，按最近一次作答的状态归类。</p></div>
          <button className="quiet-button" type="button" onClick={() => void load()}><RefreshCw size={16} />刷新</button>
        </header>
        <nav className="wiki-view-tabs practice-view-tabs" aria-label="练习视图">
          <button type="button" onClick={() => navigate("/practice")}>开始练习</button>
          <button type="button" className="active" aria-current="page">题库</button>
        </nav>
        {error && <ErrorNotice message={error} />}

        <div className="bank-toolbar">
          <div className="mention-tabs bank-filters" role="tablist" aria-label="按状态筛选">
            {FILTERS.map((filter) => (
              <button
                key={filter.key}
                type="button"
                role="tab"
                aria-selected={state === filter.key}
                className={state === filter.key ? "active" : ""}
                onClick={() => selectFilter(filter.key)}
              >
                {filter.label}
                {overview ? <small>{filterCount(overview, filter.key)}</small> : null}
              </button>
            ))}
          </div>
          <label className="bank-search">
            <Search size={14} />
            <input value={query} placeholder="搜索题干或知识点" aria-label="搜索题库" onChange={(event) => setQuery(event.target.value)} />
            {query && <button type="button" className="icon-button" aria-label="清除搜索" onClick={() => setQuery("")}><X size={14} /></button>}
          </label>
        </div>

        {conceptPool.length > 0 && (
          <div className="bank-concepts">
            {concept && <button type="button" className="quiet-button" onClick={() => { setConcept(""); setPage(0); }}>概念：{concept}<X size={13} /></button>}
            {!concept && conceptPool.slice(0, 8).map((entry) => (
              <button type="button" className="bank-concept" key={entry.concept} onClick={() => { setConcept(entry.concept); setPage(0); }}>{entry.concept}<small>{entry.count}</small></button>
            ))}
          </div>
        )}

        {state !== "all" && state !== "bookmarked" && (bank?.total || 0) > 0 && (
          <div className="bank-bulk">
            <button className="quiet-button" type="button" disabled={starting === "selection"} onClick={() => void practiceSelection()}>
              <Play size={15} />{starting === "selection" ? "正在准备" : `重练前 5 道${FILTERS.find((filter) => filter.key === state)?.label || ""}`}
            </button>
          </div>
        )}

        {loading && !bank ? <LoadingState label="正在整理题库…" state="thinking" />
          : !bank || bank.items.length === 0 ? (
            <EmptyState
              state="resting"
              title={query || concept || state !== "all" ? "没有符合条件的题目" : "题库还是空的"}
              description={query || concept || state !== "all" ? "换一个筛选条件或清除搜索再试。" : "先开始一轮练习，生成过的题目会自动进入题库。"}
              action={<button className="primary-button" type="button" onClick={() => navigate("/practice")}>开始练习</button>}
            />
          ) : <div className="bank-list">
            {bank.items.map((item) => (
              <article className="bank-row" key={item.id}>
                <div className="bank-row-main">
                  <div className="bank-row-head">
                    <span className={`bank-state ${item.state}`}>{stateLabel(item.state)}</span>
                    <small>{item.type_label}</small>
                    {item.concepts.map((name) => (
                      <button type="button" className="bank-concept" key={name} onClick={() => { setConcept(name); setPage(0); }}>{name}</button>
                    ))}
                  </div>
                  <h3>{item.question}</h3>
                  <div className="bank-row-meta">
                    {item.source && <span>{item.source}</span>}
                    <span>{formatRelativeDate(item.created_at)}</span>
                    {item.last_attempt && <span>你的答案：{item.last_attempt.user_answer || "（空）"}</span>}
                  </div>
                  <AttributionBadges attribution={item.attribution} />
                  {item.answer && <details className="bank-reveal">
                    <summary>查看参考答案与解析</summary>
                    <p>参考答案：{item.answer}</p>
                    {item.explanation && <p>{item.explanation}</p>}
                    {item.last_attempt?.feedback && <p>上次批改：{item.last_attempt.feedback}</p>}
                  </details>}
                </div>
                <div className="bank-row-actions">
                  <button
                    className="quiet-button"
                    type="button"
                    disabled={busyId === item.id}
                    aria-pressed={item.bookmarked}
                    onClick={() => void toggleBookmark(item)}
                  >
                    {item.bookmarked ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
                    {item.bookmarked ? "已收藏" : "收藏"}
                  </button>
                  <button className="primary-button" type="button" disabled={starting === `question-${item.id}`} onClick={() => void startPractice(item)}>
                    {starting === `question-${item.id}` ? "正在准备" : "练这题"}<ArrowRight size={15} />
                  </button>
                </div>
              </article>
            ))}
          </div>}

        {bank && bank.total > 0 && (
          <nav className="bank-pager" aria-label="题库分页">
            <span>共 {bank.total} 题 · 第 {page + 1} / {totalPages} 页</span>
            <span>
              <button className="quiet-button" type="button" disabled={page === 0 || loading} onClick={() => setPage((value) => Math.max(0, value - 1))}>上一页</button>
              <button className="quiet-button" type="button" disabled={page + 1 >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>下一页</button>
            </span>
          </nav>
        )}
      </div>
    </section>
  );
}
