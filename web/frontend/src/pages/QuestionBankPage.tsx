import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Bookmark, BookmarkCheck, CircleHelp, Download, FolderPlus, Pencil, Play, RefreshCw, Search, Trash2, Upload, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AttributionBadges, EmptyState, ErrorNotice, LoadingState, formatRelativeDate } from "../components/common";
import { DropdownSelect } from "../components/DropdownSelect";
import { api } from "../lib/api";
import { toErrorMessage } from "../lib/errors";
import { useHandoffStore } from "../stores/handoffStore";
import { notifyInfo } from "../stores/noticeStore";
import { useConfirm } from "../ui/Modal";
import type { QuestionBank, QuestionBankItem, QuestionBankState, QuestionSetSummary } from "../types";

const PAGE_SIZE = 20;

const FILTERS: Array<{ key: string; label: string }> = [
  { key: "all", label: "全部" },
  { key: "unanswered", label: "未作答" },
  { key: "incorrect", label: "错题" },
  { key: "partial", label: "基本正确" },
  { key: "correct", label: "答对" },
  { key: "bookmarked", label: "已收藏" },
];

// The state is the noun the bulk action operates on, so no verb has to be
// guessed per state ("重练" is only right for the wrong-answer bucket).
const BULK_NOUNS: Record<string, string> = {
  unanswered: "未作答题",
  incorrect: "错题",
  partial: "基本正确题",
  correct: "答对题",
  bookmarked: "收藏题",
};

const TYPE_OPTIONS = [
  { value: "", label: "全部题型" },
  { value: "single_choice", label: "单选题" },
  { value: "true_false", label: "判断题" },
  { value: "short_answer", label: "简答题" },
];

const DIFFICULTY_OPTIONS = [
  { value: "", label: "全部难度" },
  { value: "easy", label: "简单" },
  { value: "medium", label: "中等" },
  { value: "hard", label: "较难" },
];

/** A material is stored as a full path; the tail is what identifies it in a menu. */
function materialLabel(source: string) {
  const tail = source.split(/[\\/]/).pop() || source;
  const name = tail.replace(/\.[^.]+$/, "");
  return name.length > 26 ? name.slice(0, 25) + "…" : name;
}

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

/** D7: a local-first product must let the user take their data out and put it back. */
function todayStamp() {
  return new Date().toISOString().slice(0, 10);
}

function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function QuestionBankPage() {
  const navigate = useNavigate();
  const [state, setState] = useState("all");
  const [concept, setConcept] = useState("");
  const [qtype, setQtype] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [page, setPage] = useState(0);
  const [bank, setBank] = useState<QuestionBank | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(0);
  const [starting, setStarting] = useState("");
  const [sets, setSets] = useState<QuestionSetSummary[]>([]);
  const [setId, setSetId] = useState<number | null>(null);
  const [newSetName, setNewSetName] = useState("");
  const [renamingId, setRenamingId] = useState(0);
  const [renameDraft, setRenameDraft] = useState("");
  const [setsWorking, setSetsWorking] = useState(false);
  const [transfer, setTransfer] = useState("");
  // null = follow the data (open as soon as a set exists); explicit after a toggle.
  const [setsOpen, setSetsOpen] = useState<boolean | null>(null);
  const { confirm, confirmElement } = useConfirm();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
      setPage(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const loadSets = useCallback(async () => {
    try {
      setSets((await api.questionSets()).sets);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法读取练习集。"));
    }
  }, []);

  useEffect(() => { void loadSets(); }, [loadSets]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.questionBank({
        state,
        setId: setId || undefined,
        concept: concept || undefined,
        qtype: qtype || undefined,
        difficulty: difficulty || undefined,
        source: source || undefined,
        query: debouncedQuery || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setBank(result);
      // The current page can fall out of range when the result set shrinks —
      // e.g. un-bookmarking the last row while filtered on "已收藏".
      const lastPage = Math.max(0, Math.ceil(result.total / PAGE_SIZE) - 1);
      if (page > lastPage) setPage(lastPage);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法读取题库。"));
    } finally {
      setLoading(false);
    }
  }, [state, concept, qtype, difficulty, source, setId, debouncedQuery, page]);

  useEffect(() => { void load(); }, [load]);

  function selectFilter(key: string) {
    setState(key);
    setPage(0);
  }

  /** Any filter change restarts paging, so a page can never run off the end. */
  function changeFilter(setter: (value: string) => void) {
    return (value: string) => {
      setter(value);
      setPage(0);
    };
  }

  function clearFilters() {
    setState("all");
    setConcept("");
    setQtype("");
    setDifficulty("");
    setSource("");
    setQuery("");
    setPage(0);
  }

  /** A short, human name for the current filter, used as the default set name. */
  function filterSummary() {
    const parts: string[] = [];
    if (state !== "all") parts.push(FILTERS.find((filter) => filter.key === state)?.label || state);
    if (concept) parts.push(concept);
    if (qtype) parts.push(TYPE_OPTIONS.find((option) => option.value === qtype)?.label || qtype);
    if (difficulty) parts.push(DIFFICULTY_OPTIONS.find((option) => option.value === difficulty)?.label || difficulty);
    if (source) parts.push(materialLabel(source));
    if (debouncedQuery) parts.push(debouncedQuery);
    return parts.filter(Boolean).join(" · ").slice(0, 40);
  }

  async function createSet(event: FormEvent) {
    event.preventDefault();
    const name = newSetName.trim() || filterSummary() || "我的练习集";
    setSetsWorking(true);
    setError("");
    try {
      const created = await api.createQuestionSet({
        name,
        state,
        concept: concept || undefined,
        questionType: qtype || undefined,
        difficulty: difficulty || undefined,
        source: source || undefined,
        query: debouncedQuery || undefined,
        limit: 200,
      });
      setNewSetName("");
      await loadSets();
      setSetId(created.set_id);
      setPage(0);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法创建练习集。"));
    } finally {
      setSetsWorking(false);
    }
  }

  async function addToSet(item: QuestionBankItem, value: string) {
    if (!value) return;
    setSetsWorking(true);
    setError("");
    try {
      if (value === "new") {
        const created = await api.createQuestionSet({
          name: `来自「${item.concepts[0] || "题库"}」的练习集`,
          questionIds: [item.id],
        });
        setSetId(created.set_id);
      } else {
        await api.addQuestionToSet(Number(value), item.id);
      }
      await loadSets();
      setPage(0);
      await load();
    } catch (reason) {
      setError(toErrorMessage(reason, "无法加入练习集。"));
    } finally {
      setSetsWorking(false);
    }
  }

  async function removeFromSet(item: QuestionBankItem) {
    if (!setId) return;
    setSetsWorking(true);
    setError("");
    try {
      await api.removeQuestionFromSet(setId, item.id);
      await loadSets();
      await load();
    } catch (reason) {
      setError(toErrorMessage(reason, "无法移出练习集。"));
    } finally {
      setSetsWorking(false);
    }
  }

  async function saveRename(item: QuestionSetSummary) {
    const name = renameDraft.trim();
    if (!name || name === item.name) {
      setRenamingId(0);
      return;
    }
    setSetsWorking(true);
    setError("");
    try {
      await api.renameQuestionSet(item.id, name);
      setRenamingId(0);
      await loadSets();
      await load();
    } catch (reason) {
      setError(toErrorMessage(reason, "改名失败。"));
    } finally {
      setSetsWorking(false);
    }
  }

  async function deleteSet(item: QuestionSetSummary) {
    const ok = await confirm({
      title: `删除练习集「${item.name}」？`,
      detail: "只删除这个集合，题目本身不会被删除。",
      confirmLabel: "删除",
      danger: true,
    });
    if (!ok) return;
    setSetsWorking(true);
    setError("");
    try {
      await api.deleteQuestionSet(item.id);
      if (setId === item.id) setSetId(null);
      await loadSets();
      setPage(0);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法删除练习集。"));
    } finally {
      setSetsWorking(false);
    }
  }

  async function practiceSet(item: QuestionSetSummary) {
    setStarting(`set-${item.id}`);
    setError("");
    try {
      const created = await api.startSetPractice(item.id);
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法开始这一集。", ));
      setStarting("");
    }
  }

  function viewSet(item: QuestionSetSummary) {
    setSetId(item.id);
    setPage(0);
  }
  async function exportMarkdown() {
    setTransfer("markdown");
    setError("");
    try {
      const result = await api.exportBankMarkdown({
        state,
        setId: setId || undefined,
        concept: concept || undefined,
        qtype: qtype || undefined,
        difficulty: difficulty || undefined,
        source: source || undefined,
        query: debouncedQuery || undefined,
      });
      download(`bobodan-题库-${todayStamp()}.md`, result.markdown, "text/markdown;charset=utf-8");
      if (result.excluded_third_party > 0) {
        notifyInfo(`已排除 ${result.excluded_third_party} 道第三方（联网来源）题目。`);
      }
    } catch (reason) {
      setError(toErrorMessage(reason, "导出失败。"));
    } finally {
      setTransfer("");
    }
  }

  async function exportBackup() {
    setTransfer("backup");
    setError("");
    try {
      const result = await api.exportBankBackup();
      download(
        `bobodan-题库备份-${todayStamp()}.json`,
        JSON.stringify(result.backup, null, 2),
        "application/json",
      );
    } catch (reason) {
      setError(toErrorMessage(reason, "备份失败。"));
    } finally {
      setTransfer("");
    }
  }

  async function restoreBackup(file: File) {
    const ok = await confirm({
      title: "用这个备份覆盖整个题库？",
      detail: "当前的题目、作答记录、收藏和练习集都会被备份里的内容替换，且不能撤销。",
      confirmLabel: "覆盖题库",
      danger: true,
    });
    if (!ok) return;
    setTransfer("restore");
    setError("");
    try {
      const parsed = JSON.parse(await file.text());
      const result = await api.restoreBankBackup(parsed);
      await loadSets();
      await load();
      notifyInfo(`已恢复 ${result.restored.questions ?? 0} 道题。`);
    } catch (reason) {
      setError(toErrorMessage(reason, "恢复失败，请确认这个文件是 Bobodan 题库的备份。"));
    } finally {
      setTransfer("");
    }
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
      const created = await api.startBankPractice({ questionIds: [item.id] });
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法开始这一题。"));
      setStarting("");
    }
  }

  /** D4: the same stable id drives both the practice and the explanation. The
   *  draft names question_id so the agent can read it back through bank_list. */
  function askAi(item: QuestionBankItem) {
    useHandoffStore.getState().setChatDraft([
      `讲解题库第 ${item.id} 题（question_id=${item.id}）：${item.question}`,
      "",
      "先点出它在考察什么，再一步步引导我，不要直接给答案。",
    ].join("\n"));
    navigate("/chat");
  }

  async function practiceSelection() {
    setStarting("selection");
    setError("");
    try {
      // "Practice what I am looking at": the same filter set the list used.
      const created = await api.startBankPractice({
        state,
        concept: concept || undefined,
        questionType: qtype || undefined,
        difficulty: difficulty || undefined,
        source: source || undefined,
        query: debouncedQuery || undefined,
        limit: 5,
      });
      navigate(`/practice/${created.practice_session_id}`);
    } catch (reason) {
      setError(toErrorMessage(reason, "无法开始练习。"));
      setStarting("");
    }
  }

  const overview = bank?.overview;
  const totalPages = bank ? Math.max(1, Math.ceil(bank.total / PAGE_SIZE)) : 1;
  const conceptPool = overview?.by_concept || [];
  const sourceOptions = [
    { value: "", label: "全部资料" },
    ...(overview?.by_source || []).map((entry) => ({
      value: entry.source,
      label: materialLabel(entry.source),
      hint: String(entry.count),
    })),
  ];
  const filtersActive = state !== "all"
    || Boolean(concept || qtype || difficulty || source || debouncedQuery);
  const practiceCount = Math.max(1, Math.min(bank?.total || 0, 5));

  return (
    <section className="page-scroll">
      {confirmElement}
      <div className="page-container review-container">
        <header className="page-heading">
          <div><span>Practice</span><h2>题库</h2><p>已经生成过的题目都在这里，按最近一次作答的状态归类。</p></div>
          <div className="heading-actions">
            <button className="quiet-button" type="button" disabled={transfer === "markdown"} onClick={() => void exportMarkdown()}><Download size={16} />导出 Markdown</button>
            <button className="quiet-button" type="button" disabled={transfer === "backup"} onClick={() => void exportBackup()}><Download size={16} />备份</button>
            <label className="quiet-button bank-restore">
              <Upload size={16} />{transfer === "restore" ? "正在恢复" : "恢复"}
              <input
                type="file"
                accept="application/json,.json"
                aria-label="选择题库备份文件"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) void restoreBackup(file);
                }}
              />
            </label>
            <button className="quiet-button" type="button" onClick={() => void load()}><RefreshCw size={16} />刷新</button>
          </div>
        </header>
        <nav className="wiki-view-tabs practice-view-tabs" aria-label="练习视图">
          <button type="button" onClick={() => navigate("/practice")}>开始练习</button>
          <button type="button" className="active" aria-current="page">题库</button>
        </nav>
        {error && <ErrorNotice message={error} />}

        <details
          className="bank-sets"
          open={setsOpen ?? sets.length > 0}
          onToggle={(event) => setSetsOpen(event.currentTarget.open)}
        >
          <summary>
            练习集
            <small>{sets.length ? `${sets.length} 个` : "还没有练习集"}</small>
          </summary>
          <div className="bank-sets-open">
            <div className="bank-sets-head">
              <form onSubmit={(event) => void createSet(event)}>
                <input
                  value={newSetName}
                  placeholder={filterSummary() || "练习集名称"}
                  aria-label="练习集名称"
                  onChange={(event) => setNewSetName(event.target.value)}
                />
                <button className="quiet-button" disabled={setsWorking}>
                  <FolderPlus size={15} />存为练习集（{bank?.total ?? 0} 题）
                </button>
              </form>
            </div>
            {sets.length === 0
              ? <p className="bank-sets-empty">把当前筛选结果存成一个命名集合，之后可以一键重练。</p>
              : <div className="bank-set-list">{sets.map((item) => (
                <div className={`bank-set-row ${setId === item.id ? "active" : ""}`} key={item.id}>
                  {renamingId === item.id ? <>
                    <input
                      value={renameDraft}
                      aria-label="新的练习集名称"
                      onChange={(event) => setRenameDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void saveRename(item);
                        if (event.key === "Escape") setRenamingId(0);
                      }}
                    />
                    <button className="quiet-button" type="button" onClick={() => void saveRename(item)}>保存</button>
                  </> : <>
                    <button className="bank-set-name" type="button" onClick={() => viewSet(item)}>
                      {item.name}<small>{item.question_count} 题</small>
                    </button>
                    <button className="quiet-button" type="button" disabled={setsWorking || item.question_count === 0 || starting === `set-${item.id}`} onClick={() => void practiceSet(item)}>
                      <Play size={14} />练这集
                    </button>
                    <button className="icon-button" type="button" aria-label={`重命名 ${item.name}`} onClick={() => { setRenamingId(item.id); setRenameDraft(item.name); }}><Pencil size={14} /></button>
                    <button className="icon-button" type="button" aria-label={`删除 ${item.name}`} onClick={() => void deleteSet(item)}><Trash2 size={14} /></button>
                  </>}
                </div>
              ))}</div>}
          </div>
        </details>

        {setId && (
          <p className="bank-set-banner">
            正在查看练习集「{bank?.set_name || "…"}」· {bank?.total ?? 0} 题
            <button className="text-link" type="button" onClick={() => { setSetId(null); setPage(0); }}>返回全部题目</button>
          </p>
        )}

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
          <DropdownSelect ariaLabel="按题型筛选" value={qtype} onChange={changeFilter(setQtype)} options={TYPE_OPTIONS} />
          <DropdownSelect ariaLabel="按难度筛选" value={difficulty} onChange={changeFilter(setDifficulty)} options={DIFFICULTY_OPTIONS} />
          <DropdownSelect ariaLabel="按资料筛选" value={source} onChange={changeFilter(setSource)} options={sourceOptions} />
          {filtersActive && <button className="quiet-button" type="button" onClick={clearFilters}><X size={14} />清除筛选</button>}
        </div>

        {conceptPool.length > 0 && (
          <div className="bank-concepts">
            {concept && <button type="button" className="quiet-button" onClick={() => { setConcept(""); setPage(0); }}>概念：{concept}<X size={13} /></button>}
            {!concept && conceptPool.slice(0, 8).map((entry) => (
              <button type="button" className="bank-concept" key={entry.concept} onClick={() => { setConcept(entry.concept); setPage(0); }}>{entry.concept}<small>{entry.count}</small></button>
            ))}
          </div>
        )}

        {filtersActive && (bank?.total || 0) > 0 && (
          <div className="bank-bulk">
            <button className="quiet-button" type="button" disabled={starting === "selection"} onClick={() => void practiceSelection()}>
              <Play size={15} />{starting === "selection" ? "正在准备" : `练这 ${practiceCount} 道${BULK_NOUNS[state] || "题"}`}
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
              <article className={`bank-row state-${item.state}`} key={item.id}>
                <div className="bank-row-head">
                  <span className={`bank-state ${item.state}`}>{stateLabel(item.state)}</span>
                  <small>{item.type_label}</small>
                  {item.concepts.map((name) => (
                    <button type="button" className="bank-concept" key={name} onClick={() => { setConcept(name); setPage(0); }}>{name}</button>
                  ))}
                </div>
                <h3>{item.question}</h3>
                {item.answer && (
                  <details className="bank-reveal">
                    <summary>查看参考答案与解析</summary>
                    <div className={`bank-answer ${item.state === "incorrect" ? "incorrect" : ""}`}>
                      <div className="bank-answer-grid">
                        <div>
                          <span className="bank-answer-label">你的答案</span>
                          <p className="bank-answer-value">{item.last_attempt?.user_answer || "（空）"}</p>
                        </div>
                        <div>
                          <span className="bank-answer-label">参考答案</span>
                          <p className="bank-answer-value">{item.answer}</p>
                        </div>
                      </div>
                    </div>
                    {item.explanation && <p>{item.explanation}</p>}
                    {item.last_attempt?.feedback && <p>上次批改：{item.last_attempt.feedback}</p>}
                  </details>
                )}
                <div className="bank-footer">
                  <div className="bank-row-meta">
                    {item.last_attempt && (
                      <span className="bank-mine">你的答案：<strong>{item.last_attempt.user_answer || "（空）"}</strong></span>
                    )}
                    <span>{formatRelativeDate(item.created_at)}</span>
                  </div>
                  <AttributionBadges attribution={item.attribution} />
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
                    <button className="quiet-button" type="button" onClick={() => askAi(item)}>
                      <CircleHelp size={15} />问 AI
                    </button>
                    <DropdownSelect
                      ariaLabel="把这一题加入练习集"
                      value=""
                      placeholder="加入练习集"
                      disabled={setsWorking}
                      onChange={(value) => void addToSet(item, value)}
                      options={[
                        { value: "", label: "加入练习集" },
                        ...sets.map((entry) => ({ value: String(entry.id), label: entry.name, hint: String(entry.question_count) })),
                        { value: "new", label: "新建练习集…" },
                      ]}
                    />
                    {setId ? <button className="quiet-button" type="button" disabled={setsWorking} onClick={() => void removeFromSet(item)}><X size={14} />移出这集</button> : null}
                    <button className="primary-button" type="button" disabled={starting === `question-${item.id}`} onClick={() => void startPractice(item)}>
                      {starting === `question-${item.id}` ? "正在准备" : "练这题"}<ArrowRight size={15} />
                    </button>
                  </div>
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
