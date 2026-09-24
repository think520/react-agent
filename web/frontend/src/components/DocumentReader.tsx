/**
 * DocumentReader — 阅读区的唯一渲染实现（④ 两套阅读实现合一，第 1 步）。
 *
 * 整块从 pages/ReaderPage.tsx 搬过来：小节加载、原文/按小节切换、PDF 内嵌、
 * 章节导轨（目录）、引用提示条、选区工具条都归它。api.* 的调用点与加载/错误
 * 语义跟搬之前逐字一致；顶栏、标签条、上一份/下一份仍留在路由外壳里。
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { NotebookPen, Quote, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createPortal } from "react-dom";
import { useNavigate, useOutletContext } from "react-router-dom";

import type { AppOutletContext } from "./AppShell";
import { EmptyState, LoadingState } from "./common";
import { api, documentAssetUrl, documentRawEmbedUrl, downloadDocumentRaw, fetchDocumentRawText, splitFrontmatter } from "../lib/api";
import { READER_VIEW_KEY, resolveReaderView, type ReaderView } from "../lib/readerView";
import { useHandoffStore } from "../stores/handoffStore";
import { useReaderTabsStore } from "../stores/readerTabsStore";
import type { DocumentSection, DocumentSummary, PersonalKnowledgeItem } from "../types";

export interface DocumentReaderProps {
  /** 要读的资料 id（外壳从路由参数解析出来的那个）。 */
  documentId: string;
  /** 资料库集合：决定相关笔记与请求的 collection。 */
  collection: "material" | "wiki";
  /** 引用/搜索跳转带进来的 chunk_id（可选）：到了就切分段并定位那一段。 */
  chunkId?: string | null;
  /** 外壳的资料列表里已经查到的那一份（元数据 + 原件信息），不重复请求。 */
  documentSummary: DocumentSummary;
  /** 外壳的滚动容器：阅读进度按它的 scrollTop 记账（外壳自己还用它恢复标签位置）。 */
  scrollRef?: RefObject<HTMLElement | null>;
  /** 阅读区里的数据错误仍旧由外壳的 ErrorNotice 显示；请传稳定引用（setState 本身稳定）。 */
  onError?: (message: string) => void;
  /** 小节加载好后回给外壳一份：顶栏的「提取概念」用它判断按钮可用与正文内容。 */
  onSectionsLoaded?: (sections: DocumentSection[]) => void;
  /** 外壳保存资料编辑后递增，用来重新拉一次小节。 */
  reloadToken?: number;
}

export function DocumentReader({
  documentId,
  collection,
  chunkId = null,
  documentSummary,
  scrollRef,
  onError,
  onSectionsLoaded,
  reloadToken = 0,
}: DocumentReaderProps) {
  const navigate = useNavigate();
  const { selectedDocumentIds, toggleDocumentScope } = useOutletContext<AppOutletContext>();

  const [sections, setSections] = useState<DocumentSection[]>([]);
  const [relatedNotes, setRelatedNotes] = useState<PersonalKnowledgeItem[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [highlightedChunk, setHighlightedChunk] = useState<string | null>(null);
  const [selectionQuote, setSelectionQuote] = useState("");
  const [view, setView] = useState<ReaderView>(() => {
    try {
      return window.localStorage.getItem(READER_VIEW_KEY) === "sections" ? "sections" : "original";
    } catch {
      return "original";
    }
  });
  const [forcedSections, setForcedSections] = useState(false);
  const [pendingChunk, setPendingChunk] = useState<string | null>(null);
  const [originalText, setOriginalText] = useState("");
  const [originalError, setOriginalError] = useState("");
  const [railOpen, setRailOpen] = useState(false);
  const readingOpenedRef = useRef(false);
  const lastProgressRef = useRef(0);
  // Closing the rail mounts the 64px edge zone under the pointer, and the browser
  // recomputes hover when the element under the cursor changes — so a plain
  // setRailOpen(false) was immediately undone by the mouseenter it caused and the
  // X looked dead (2026-09-14 bug report). Remember where the close happened and
  // ignore the hover that comes from that very spot until the pointer leaves.
  const railClosePoint = useRef<{ x: number; y: number } | null>(null);
  const closeRail = useCallback((event?: { clientX: number; clientY: number }) => {
    railClosePoint.current = event ? { x: event.clientX, y: event.clientY } : null;
    setRailOpen(false);
  }, []);
  const openRail = useCallback((event: { clientX: number; clientY: number }) => {
    const point = railClosePoint.current;
    if (point && Math.abs(event.clientX - point.x) < 8 && Math.abs(event.clientY - point.y) < 8) return;
    railClosePoint.current = null;
    setRailOpen(true);
  }, []);

  // selectedId / selected 沿用外壳里的名字，搬过来的调用点一行都不用改。
  const selectedId = documentId;
  const selected = documentSummary;
  // 视图规则是纯函数（src/lib/readerView.ts）：默认原文、pdf 走内嵌阅读器、
  // 浏览器排不了的格式不给切换、跳转时强制分段且不动偏好。
  const readerView = resolveReaderView({
    hasOriginal: Boolean(selected?.has_original),
    source: selected?.source,
    preference: view,
    forcedSections,
  });
  const canShowOriginal = readerView.showSwitch;
  const inlineOriginal = readerView.inlineKind;
  const effectiveView = readerView.view;
  const showOriginal = readerView.view === "original";
  const originalParts = splitFrontmatter(originalText);
  const arrivedViaCitation = Boolean(chunkId) && forcedSections;
  // PDF 的原件没法高亮（浏览器内置阅读器不暴露文本），所以定位只能发生在"按小节"
  // 视图里——这句话要说清楚，否则用户会以为原件那边也该亮起来。
  const citationBarText =
    inlineOriginal === "pdf"
      ? "已定位到引用段落 · PDF 原件无法高亮，已在「按小节」"
      : "已定位到引用段落";

  const scrollToChunk = useCallback((targetChunkId: string) => {
    const target = Array.from(document.querySelectorAll<HTMLElement>("[data-chunk-id]"))
      .find((element) => element.dataset.chunkId === targetChunkId);
    if (!target) return;
    setHighlightedChunk(targetChunkId);
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }, []);
  const setTabScroll = useReaderTabsStore((state) => state.setScroll);

  useEffect(() => {
    setSelectionQuote("");
    setRelatedNotes([]);
    if (!chunkId) setHighlightedChunk(null);
    if (!selectedId) { setSections([]); onSectionsLoaded?.([]); return; }
    let cancelled = false;
    setDetailLoading(true);
    void api.document(selectedId)
      .then((result) => {
        if (cancelled) return;
        setSections(result.sections);
        // 顶栏的「提取概念」要用同一份小节，这里把结果回给外壳一份。
        onSectionsLoaded?.(result.sections);
      })
      .catch((reason: Error) => { if (!cancelled) onError?.(reason.message); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    if (collection === "material") {
      void api.knowledgeByDocument(selectedId)
        .then((result) => { if (!cancelled) setRelatedNotes(result.items); })
        .catch(() => { if (!cancelled) setRelatedNotes([]); });
    }
    return () => { cancelled = true; };
    // chunkId 决定这次进入是否带引用片段（要不要保留高亮），列进依赖；
    // reloadToken 是外壳在资料被编辑保存后递增的重取信号。
  }, [selectedId, collection, chunkId, reloadToken, onError, onSectionsLoaded]);

  useEffect(() => {
    readingOpenedRef.current = false;
    lastProgressRef.current = 0;
    if (!selectedId || detailLoading || !sections.length) return;
    let visibleSeconds = 0;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      visibleSeconds += 1;
      if (visibleSeconds < 10 || readingOpenedRef.current) return;
      readingOpenedRef.current = true;
      void api.updateReadingProgress(selectedId, lastProgressRef.current, true).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [selectedId, detailLoading, sections.length]);

  // 跳转（搜索/引用）一律走分段视图：高亮靠"一 chunk 一个 DOM 节点"，而 chunk 的
  // char 偏移是相对 section 文本算的（2026-09-23 验证），映射回整篇文件并不便宜。
  useEffect(() => {
    if (highlightedChunk) setForcedSections(true);
  }, [highlightedChunk]);

  // 复审发现的 bug：forcedSections 是"本次跳转"的临时状态，换资料必须复位，
  // 否则跳转过一次之后，后面每份资料都会停在分段视图（而偏好并没有变）。
  useEffect(() => {
    if (chunkId) return;
    setForcedSections(false);
    setPendingChunk(null);
  }, [selectedId, chunkId]);

  // 从原文/PDF 视图发起的跳转：等分段视图渲染出 [data-chunk-id] 之后再滚动高亮。
  // 引用跳转的落点交给下面那个 section 的 ref 回调：节点挂载那一刻就知道"到了"。
  // 这里曾经用 useEffect + querySelectorAll 去"找"目标，实测证明它在目标绘制之前
  // 就把 pending 清掉了（pending=- 而 hl=-、DOM 里却已有 64 个节点）。

  // 从别处（聊天的「查看来源」）带着 chunk 进来：落到分段视图并定位那一段。
  // 之前阅读器完全不读这个参数，于是"跳过来找不到引用的段落"。
  useEffect(() => {
    if (!chunkId) return;
    setForcedSections(true);
    setPendingChunk(chunkId);
  }, [chunkId]);

  useEffect(() => {
    setOriginalText("");
    setOriginalError("");
    if (!selected || !canShowOriginal || !showOriginal) return;
    let cancelled = false;
    void fetchDocumentRawText(selected.document_id)
      .then((text) => {
        if (!cancelled) setOriginalText(text);
      })
      .catch((reason) => {
        if (!cancelled) setOriginalError(reason instanceof Error ? reason.message : "无法读取原文。");
      });
    return () => {
      cancelled = true;
    };
  }, [selected, canShowOriginal, showOriginal]);

  function chooseView(next: ReaderView) {
    setForcedSections(false);
    setView(next);
    try {
      window.localStorage.setItem(READER_VIEW_KEY, next);
    } catch {
      // 隐私模式：不记住也无妨，默认就是原文
    }
  }

  // 滚动容器由外壳持有（顶栏与标签条也在里面），所以滚动记账在这里挂原生监听。
  const recordReadingProgress = useCallback(() => {
    const element = scrollRef?.current;
    if (element && selectedId) setTabScroll(selectedId, element.scrollTop);
    if (!element || !selectedId || !readingOpenedRef.current) return;
    const available = element.scrollHeight - element.clientHeight;
    const raw = available > 0 ? Math.round((element.scrollTop / available) * 100) : 100;
    const progress = raw >= 100 ? 100 : Math.floor(raw / 10) * 10;
    if (progress < 10 || progress <= lastProgressRef.current) return;
    lastProgressRef.current = progress;
    void api.updateReadingProgress(selectedId, progress).catch(() => undefined);
  }, [scrollRef, selectedId, setTabScroll]);

  useEffect(() => {
    const element = scrollRef?.current;
    if (!element) return;
    element.addEventListener("scroll", recordReadingProgress);
    return () => element.removeEventListener("scroll", recordReadingProgress);
  }, [scrollRef, recordReadingProgress]);

  // 章节导轨的开关键（[ / ]）：顶栏那半边（Esc、Shift+J/K）留在了外壳里。
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "[") closeRail();
      if (e.key === "]") setRailOpen(true);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [closeRail]);

  // 选区工具条要**贴着选区**出现（用户反馈：原来钉在正文顶部，选到文章中间时离得很远）。
  // 记下 Range 本身，滚动时按它重算位置 —— Range 会跟着文档走，不需要缓存坐标。
  const selectionRangeRef = useRef<Range | null>(null);
  const [selectionAnchor, setSelectionAnchor] = useState<{ x: number; y: number } | null>(null);

  function captureSelection() {
    const selection = window.getSelection();
    const text = selection?.toString().trim() || "";
    setSelectionQuote(text.slice(0, 1200));
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed || !text) {
      selectionRangeRef.current = null;
      setSelectionAnchor(null);
      return;
    }
    const range = selection.getRangeAt(0).cloneRange();
    selectionRangeRef.current = range;
    const rect = range.getBoundingClientRect();
    setSelectionAnchor({ x: rect.left + rect.width / 2, y: rect.top });
  }

  useEffect(() => {
    const reposition = () => {
      const range = selectionRangeRef.current;
      if (!range) return;
      const rect = range.getBoundingClientRect();
      setSelectionAnchor({ x: rect.left + rect.width / 2, y: rect.top });
    };
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, []);

  /** 气泡的落点：贴着选区上沿，并且始终留在视口内（选到很靠边时也要点得到）。 */
  const selectionToolbarStyle = selectionAnchor
    ? {
        left: Math.min(Math.max(selectionAnchor.x, 160), Math.max(160, window.innerWidth - 160)),
        top: Math.min(Math.max(selectionAnchor.y - 10, 64), Math.max(64, window.innerHeight - 24)),
      }
    : undefined;

  function askAboutSelection() {
    if (!selectionQuote || !selected) return;
    useHandoffStore.getState().setChatDraft(
      "请结合资料《" + (selected.title || selected.source) + "》解释下面这段内容：\n\n> " + selectionQuote.replace(/\n/g, "\n> "),
    );
    if (!selectedDocumentIds.includes(selected.document_id) && selected.collection === "material") {
      toggleDocumentScope(selected.document_id);
    }
    navigate("/chat");
  }

  // TASKS_LIBRARY_REWORK task 2: selection -> practice.
  function createPracticeFromSelection() {
    if (!selectionQuote || !selected) return;
    useHandoffStore.getState().setPracticeTopic(
      "《" + (selected.title || selected.source) + "》\n\n> " + selectionQuote.slice(0, 400),
    );
    navigate("/practice");
  }

  function jumpToChunk(targetChunkId: string) {
    // 章节导航靠 [data-chunk-id] 节点定位，而那些节点只存在于分段视图——原文/PDF
    // 视图下点了会毫无反应（复审发现的真 bug）。跳转一律先切到分段视图，落到
    // DOM 之后再滚动高亮，这也正是共识里"跳转 → 分段并高亮"的那条规则。
    if (showOriginal) {
      setForcedSections(true);
      setPendingChunk(targetChunkId);
      return;
    }
    scrollToChunk(targetChunkId);
  }

  return (
    <>
      <article className="reader-article">
        {(canShowOriginal || readerView.offerSystemOpen) && (
          <div className="reader-view-row">
            {canShowOriginal && (
              <div className="reader-view-switch" role="group" aria-label="阅读视图">
                <button
                  className={effectiveView === "original" ? "active" : ""}
                  onClick={() => chooseView("original")}
                >
                  原文
                </button>
                <button
                  className={effectiveView === "sections" ? "active" : ""}
                  onClick={() => chooseView("sections")}
                >
                  按小节
                </button>
              </div>
            )}
            {readerView.offerSystemOpen && (
              <button
                className="quiet-button reader-original"
                title="这类格式浏览器无法页内渲染：下载原件，用系统应用打开"
                onClick={() => {
                  const name = (selected.source || "").split("/").pop() || selected.document_id;
                  void downloadDocumentRaw(selected.document_id, name).catch((reason) =>
                    onError?.(reason instanceof Error ? reason.message : "无法取回原件。"),
                  );
                }}
              >
                用系统打开
              </button>
            )}
          </div>
        )}
        {arrivedViaCitation && (
          <div className="reader-citation-bar" role="status">
            <span>{citationBarText}</span>
            <button className="quiet-button" type="button" onClick={() => chooseView("original")}>
              看原文
            </button>
          </div>
        )}
        {selectionQuote && createPortal(<div className={selectionAnchor ? "selection-toolbar floating" : "selection-toolbar"} style={selectionToolbarStyle}><Quote size={15} /><span>已选择 {selectionQuote.length} 个字符</span><button className="quiet-button" onClick={askAboutSelection}>带到对话</button><button className="quiet-button" onClick={createPracticeFromSelection}>基于此出题</button><button className="quiet-button" onClick={() => setSelectionQuote("")}>取消</button></div>, document.body)}
        {detailLoading && !sections.length ? <LoadingState label="正在打开资料…" state="reading" /> : showOriginal ? (
          inlineOriginal === "pdf" ? (
            <div className="reader-pdf">
              <div className="reader-pdf-toolbar">
                <span className="text-faint">{selected.title || selected.source}</span>
                <a
                  className="quiet-button"
                  href={documentRawEmbedUrl(selected.document_id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  在系统打开
                </a>
              </div>
              <p className="text-faint reader-pdf-hint">
                要引用或问 AI，请切到「按小节」——PDF 阅读器里的选区读不到页面。
              </p>
              <iframe
                className="reader-pdf-frame"
                title={selected.title || selected.source}
                src={documentRawEmbedUrl(selected.document_id)}
                style={{ width: "100%", height: "72vh", border: "0" }}
              />
            </div>
          ) : (
          <div className="reader-prose reader-original" onMouseUp={captureSelection}>
            {originalParts.meta && (
              <details className="reader-meta">
                <summary>元数据</summary>
                <pre>{originalParts.meta}</pre>
              </details>
            )}
            {originalParts.body ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  img: ({ src, alt }) => (
                    <img
                      src={documentAssetUrl(selected.document_id, src ?? "")}
                      alt={alt ?? ""}
                      loading="lazy"
                    />
                  ),
                }}
              >
                {originalParts.body}
              </ReactMarkdown>
            ) : originalError ? (
              <p className="text-faint">{originalError}</p>
            ) : (
              <LoadingState label="正在读取原文…" state="reading" />
            )}
          </div>
          )
        ) : sections.length ? <div className={`reader-prose ${detailLoading ? "refreshing" : ""}`} onMouseUp={captureSelection}>{sections.map((section, index) => {
          const previous = index > 0 ? sections[index - 1] : undefined;
          const showHeading = Boolean(section.heading) && section.heading !== previous?.heading;
          return (
            <section className={highlightedChunk === section.chunk_id ? "highlighted" : ""} data-chunk-id={section.chunk_id}
              ref={(element) => {
                // 只对"这次要跳过去的"那一段动手；挂载即命中，不依赖计时器。
                if (element && pendingChunk === section.chunk_id) {
                  setHighlightedChunk(section.chunk_id);
                  element.scrollIntoView({ block: "center", behavior: "smooth" });
                  setPendingChunk(null);
                }
              }} key={section.chunk_id}>
              {showHeading && <h3>{section.heading}</h3>}
              <div className="section-location">{section.page_start ? "第 " + section.page_start + " 页" : section.slide_start ? "第 " + section.slide_start + " 页" : "资料片段"}</div>
              <div className="reader-section-prose">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    // Relative image paths only resolve through our asset
                    // endpoint: parsing kept the markdown, but the file was
                    // never reachable from the browser before.
                    img: ({ src, alt }) => (
                      <img
                        src={documentAssetUrl(selected.document_id, src ?? "")}
                        alt={alt ?? ""}
                        loading="lazy"
                      />
                    ),
                  }}
                >
                  {section.text}
                </ReactMarkdown>
              </div>
            </section>
          );
        })}</div> : <EmptyState compact title="没有可阅读的片段" description="这份资料可能仍在建立索引。" state="resting" />}

        {selected.collection === "material" && relatedNotes.length > 0 && (
          <div className="reader-related-notes">
            <span><NotebookPen size={14} />相关笔记</span>
            {relatedNotes.map((note) => (
              <div key={note.id}><strong>{note.title}</strong><p>{note.content}</p><small>更新于 {new Date(note.updated_at).toLocaleString("zh-CN")}</small></div>
            ))}
          </div>
        )}
      </article>
      {/* TASKS_LIBRARY_REWORK task 2: chapter rail (right-edge 64px hover zone).
          The zone only exists while the rail is closed. Because it lands directly
          under the pointer that just closed the rail, onMouseEnter has to ignore
          the hover coming from exactly where the X was (openRail / closeRail).

          2026-09-24：导轨与选区气泡都改从 body 渲染。路由过渡层 `.route-fade` 带
          transform + will-change，会**成为 fixed 元素的包含块** —— 留在页面里时它们
          会以那一层为准定位（实测整体偏下 68px、滚动时还会跟着走），portal 到 body
          才真正贴住视口。 */}
      {createPortal(
        <>
          {!railOpen && (
            <div
              className="chapter-rail-zone"
              onMouseLeave={() => { railClosePoint.current = null; }}
              onMouseEnter={(event) => openRail(event)}
            />
          )}
          {railOpen && (
            <aside className="chapter-rail">
              <header>
                <span>章节</span>
                <button className="icon-button" aria-label="关闭章节" onClick={(event) => closeRail(event)}><X size={14} /></button>
              </header>
              <div>
                {sections.filter((section) => section.heading).map((section) => (
                  <button key={section.chunk_id} onClick={() => jumpToChunk(section.chunk_id)}>{section.heading}</button>
                ))}
                {!sections.some((section) => section.heading) && <p className="text-faint">暂无章节标题。</p>}
              </div>
            </aside>
          )}
        </>,
        document.body,
      )}
    </>
  );
}
