/**
 * ReaderPage — /library/read/:id (TASKS_LIBRARY_REWORK task 1).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, NotebookPen, Pencil, Quote, RefreshCw, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { EmptyState, ErrorNotice, LoadingState } from "../components/common";
import { DocumentEditor } from "../components/DocumentEditor";
import { ApiError, api, documentAssetUrl, documentRawEmbedUrl, fetchDocumentRawText, openDocumentRaw, splitFrontmatter } from "../lib/api";
import { useHandoffStore } from "../stores/handoffStore";
import { useReaderTabsStore } from "../stores/readerTabsStore";
import { useConfirm } from "../ui/Modal";
import type { DocumentExtractionStatus, DocumentSection, DocumentSummary, PersonalKnowledgeItem } from "../types";

const EDITABLE_KINDS = new Set(["md", "txt", "markdown", "course_document", "obsidian_note"]);

/** 页内原文视图的状态模型（Q2/Q7 的共识）。 */
type ReaderView = "original" | "sections";
const READER_VIEW_KEY = "bobodan:reader-view";
/** 只有浏览器能当文本渲染的格式才进页内原文；pdf 走 iframe，docx/pptx 走系统打开。 */
const INLINE_ORIGINAL_EXTENSIONS = new Set(["md", "markdown", "txt"]);

function documentExtension(source: string | undefined): string {
  const name = (source || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1) : "";
}

export function ReaderPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const collection = searchParams.get("collection") === "wiki" ? "wiki" : "material";
  const { activeLibrary, selectedDocumentIds, toggleDocumentScope } = useOutletContext<AppOutletContext>();

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [sections, setSections] = useState<DocumentSection[]>([]);
  const [relatedNotes, setRelatedNotes] = useState<PersonalKnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [highlightedChunk, setHighlightedChunk] = useState<string | null>(null);
  const [selectionQuote, setSelectionQuote] = useState("");
  const { confirm, confirmElement } = useConfirm();
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [startingExtractionId, setStartingExtractionId] = useState<string | null>(null);
  const [extractionStatuses, setExtractionStatuses] = useState<Record<string, DocumentExtractionStatus>>({});
  const [view, setView] = useState<ReaderView>(() => {
    try {
      return window.localStorage.getItem(READER_VIEW_KEY) === "sections" ? "sections" : "original";
    } catch {
      return "original";
    }
  });
  const [forcedSections, setForcedSections] = useState(false);
  const [originalText, setOriginalText] = useState("");
  const [originalError, setOriginalError] = useState("");
  const [railOpen, setRailOpen] = useState(false);
  const pageRef = useRef<HTMLElement>(null);
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

  const selectedId = id ?? null;
  const selected = documents.find((document) => document.document_id === selectedId) ?? null;
  const extension = documentExtension(selected?.source);
  const inlineOriginal: "markdown" | "pdf" | null =
    INLINE_ORIGINAL_EXTENSIONS.has(extension) ? "markdown" : extension === "pdf" ? "pdf" : null;
  const canShowOriginal = Boolean(selected?.has_original) && inlineOriginal !== null;
  // 带跳转意图进来（搜索/引用）时强制分段视图，但不动用户偏好。
  const effectiveView: ReaderView = forcedSections || !canShowOriginal ? "sections" : view;
  const showOriginal = effectiveView === "original";
  const originalParts = splitFrontmatter(originalText);
  const selectedIndex = documents.findIndex((document) => document.document_id === selectedId);
  const openTab = useReaderTabsStore((state) => state.open);
  const closeTab = useReaderTabsStore((state) => state.close);
  const setTabScroll = useReaderTabsStore((state) => state.setScroll);
  const openIds = useReaderTabsStore((state) => state.openIds);
  const scrolls = useReaderTabsStore((state) => state.scrolls);

  const loadDocuments = useCallback(async () => {
    if (!activeLibrary) { setDocuments([]); setLoading(false); return; }
    setLoading(true);
    setError("");
    try {
      setDocuments(await api.documents(collection));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取资料库。");
    } finally {
      setLoading(false);
    }
  }, [activeLibrary, collection]);

  useEffect(() => { void loadDocuments(); }, [loadDocuments]);

  // Multi-doc tabs: open the current doc and restore its scroll position.
  useEffect(() => {
    if (!selectedId) return;
    openTab(selectedId);
    if (pageRef.current) pageRef.current.scrollTop = scrolls[selectedId] || 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    setSelectionQuote("");
    setRelatedNotes([]);
    setHighlightedChunk(null);
    if (!selectedId) { setSections([]); return; }
    let cancelled = false;
    setDetailLoading(true);
    void api.document(selectedId)
      .then((result) => { if (!cancelled) setSections(result.sections); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    if (collection === "material") {
      void api.knowledgeByDocument(selectedId)
        .then((result) => { if (!cancelled) setRelatedNotes(result.items); })
        .catch(() => { if (!cancelled) setRelatedNotes([]); });
    }
    return () => { cancelled = true; };
  }, [selectedId, collection]);

  useEffect(() => {
    if (!activeLibrary || collection !== "material") { setExtractionStatuses({}); return; }
    let cancelled = false;
    let timer: number | undefined;
    async function refresh() {
      try {
        const result = await api.graphExtractionStatuses();
        if (cancelled) return;
        setExtractionStatuses(result.documents);
        if (Object.values(result.documents).some((item) => item.status === "extracting")) {
          timer = window.setTimeout(refresh, 1500);
        }
      } catch { /* non-blocking */ }
    }
    void refresh();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [activeLibrary, collection]);

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
    setForcedSections(false);
  }, [selectedId]);

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

  function recordReadingProgress() {
    const element = pageRef.current;
    if (element && selectedId) setTabScroll(selectedId, element.scrollTop);
    if (!element || !selectedId || !readingOpenedRef.current) return;
    const available = element.scrollHeight - element.clientHeight;
    const raw = available > 0 ? Math.round((element.scrollTop / available) * 100) : 100;
    const progress = raw >= 100 ? 100 : Math.floor(raw / 10) * 10;
    if (progress < 10 || progress <= lastProgressRef.current) return;
    lastProgressRef.current = progress;
    void api.updateReadingProgress(selectedId, progress).catch(() => undefined);
  }

  function goTo(delta: number) {
    if (!documents.length) return;
    const next = (selectedIndex + delta + documents.length) % documents.length;
    const target = documents[next];
    if (target) navigate("/library/read/" + target.document_id + "?collection=" + collection);
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") { navigate("/library?collection=" + collection); return; }
      if (e.shiftKey && (e.key === "J" || e.key === "j")) goTo(1);
      if (e.shiftKey && (e.key === "K" || e.key === "k")) goTo(-1);
      if (e.key === "[") closeRail();
      if (e.key === "]") setRailOpen(true);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIndex, documents.length, collection]);

  function captureSelection() {
    const text = window.getSelection()?.toString().trim() || "";
    setSelectionQuote(text.slice(0, 1200));
  }

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

  function jumpToChunk(chunkId: string) {
    const target = Array.from(document.querySelectorAll<HTMLElement>("[data-chunk-id]"))
      .find((element) => element.dataset.chunkId === chunkId);
    if (!target) return;
    setHighlightedChunk(chunkId);
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function documentContentVersion(doc: DocumentSummary) {
    return doc.content_hash || [doc.updated_at || "", doc.chunk_count || 0].join(":");
  }

  function effectiveExtractionStatus(document: DocumentSummary) {
    const status = extractionStatuses[document.document_id];
    const currentVersion = documentContentVersion(document);
    const extractedVersion = status?.run.content_version || "";
    if (status && (status.status === "completed" || status.status === "review") && extractedVersion && currentVersion && extractedVersion !== currentVersion) {
      return "stale" as const;
    }
    return status ? status.status : "not_started" as const;
  }

  function openExtractionReview(doc: DocumentSummary, status: DocumentExtractionStatus) {
    navigate("/knowledge-map", { state: { extractionRunId: status.run.run_id, extractingDocumentId: doc.document_id, extractingDocumentTitle: doc.title || doc.source } });
  }

  async function extractAndReview(doc: DocumentSummary, force = false) {
    if (startingExtractionId || !sections.length) return;
    const existing = extractionStatuses[doc.document_id];
    if (!force && existing && existing.status !== "failed") { openExtractionReview(doc, existing); return; }
    if (force && !(await confirm({ title: `重新提取「${doc.title || doc.source}」的概念？`, detail: "这会再次调用模型并消耗 Token。", confirmLabel: "重新提取" }))) return;
    setStartingExtractionId(doc.document_id);
    setError("");
    const content = sections.map((s) => s.text).join("\n\n");
    try {
      const request = { document_id: doc.document_id, document_title: doc.title || doc.source, content, sections, content_version: documentContentVersion(doc), force };
      let extractionRunId: string | undefined;
      try {
        const { run } = await api.graphStartExtraction(request);
        extractionRunId = run.run_id;
        setExtractionStatuses((current) => ({ ...current, [doc.document_id]: { status: run.status === "failed" ? "failed" : run.status === "completed" || run.status === "completed_with_warnings" ? "review" : "extracting", pending_count: 0, run } }));
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 404) throw reason;
        await api.graphExtract(request);
      }
      navigate("/knowledge-map", { state: { extractionRunId, extractingDocumentId: doc.document_id, extractingDocumentTitle: doc.title || doc.source } });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法启动概念提取。");
    } finally {
      setStartingExtractionId(null);
    }
  }

  if (!activeLibrary) {
    return <EmptyState state="reading" title="尚未选择资料库" description="先创建或打开一个资料库。" />;
  }

  const editAction = selected && EDITABLE_KINDS.has(selected.kind) ? (
    <button className="quiet-button" onClick={() => setEditingDocumentId(selected.document_id)}><Pencil size={15} />编辑</button>
  ) : null;

  return (
    <section className="page-scroll reader-page" ref={pageRef} onScroll={recordReadingProgress}>
      {confirmElement}
      <div className="page-container reader-container">
        <header className="reader-topbar">
          <button className="quiet-button" title="Esc 返回列表" onClick={() => navigate("/library?collection=" + collection)}><ArrowLeft size={15} />返回资料库</button>
          <div className="reader-topbar-nav">
            <button className="icon-button" aria-label="上一份" title="上一份 · Shift+K" disabled={!documents.length} onClick={() => goTo(-1)}><ArrowLeft size={15} /></button>
            <button className="icon-button" aria-label="下一份" title="下一份 · Shift+J" disabled={!documents.length} onClick={() => goTo(1)}><ArrowRight size={15} /></button>
          </div>
          <div className="reader-topbar-title">
            <span>{selected ? selected.kind || "资料" : ""}{selected?.course ? " · " + selected.course : ""}</span>
            <h2>{selected?.title || selected?.source || "资料"}</h2>
          </div>
          <div className="reader-topbar-actions">
            {selected?.collection === "material" && effectiveExtractionStatus(selected) === "not_started" && (
              <button className="primary-button reader-extract" disabled={startingExtractionId === selected.document_id || !sections.length} onClick={() => void extractAndReview(selected)}><Sparkles size={15} />提取概念</button>
            )}
            {selected?.collection === "material" && effectiveExtractionStatus(selected) === "review" && (
              <button className="primary-button reader-extract" onClick={() => openExtractionReview(selected, extractionStatuses[selected.document_id]!)}><Sparkles size={15} />审查概念 · {extractionStatuses[selected.document_id]?.pending_count || 0}</button>
            )}
            {selected?.collection === "material" && effectiveExtractionStatus(selected) === "completed" && (
              <button className="quiet-button reader-extract status-completed" onClick={() => navigate("/knowledge-map")}><CheckCircle2 size={15} />已提取 · 查看图谱</button>
            )}
            {selected?.collection === "material" && (effectiveExtractionStatus(selected) === "failed" || effectiveExtractionStatus(selected) === "stale") && (
              <button className="primary-button reader-extract" disabled={startingExtractionId === selected.document_id || !sections.length} onClick={() => void extractAndReview(selected, true)}><RefreshCw size={15} />重新提取</button>
            )}
            {editAction}
            {selected && canShowOriginal && (
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
            {selected && !canShowOriginal && Boolean(selected.has_original) && (
              <button
                className="quiet-button reader-original"
                title="用系统打开原件（这类格式浏览器无法页内渲染）"
                onClick={() => {
                  void openDocumentRaw(selected.document_id).catch((reason) =>
                    setError(reason instanceof Error ? reason.message : "无法打开原文。"),
                  );
                }}
              >
                用系统打开
              </button>
            )}
          </div>
        </header>

        {openIds.length > 1 && (
          <div className="reader-tabs" onWheel={(e) => { e.currentTarget.scrollLeft += e.deltaY; }}>
            {openIds.map((tabId) => {
              const doc = documents.find((d) => d.document_id === tabId);
              return (
                <button
                  key={tabId}
                  className={"reader-tab" + (tabId === selectedId ? " active" : "")}
                  onClick={() => navigate("/library/read/" + tabId + "?collection=" + collection)}
                  onDoubleClick={() => closeTab(tabId)}
                >
                  {doc?.title || doc?.source || "资料"}
                </button>
              );
            })}
          </div>
        )}

        {error && <ErrorNotice message={error} />}

        {loading ? (
          <LoadingState label="正在读取资料…" state="reading" />
        ) : !selected ? (
          <EmptyState compact title="资料不存在" description="这份资料可能已被归档。" state="resting" />
        ) : (
          <article className="reader-article">
            {selectionQuote && <div className="selection-toolbar"><Quote size={15} /><span>已选择 {selectionQuote.length} 个字符</span><button className="quiet-button" onClick={askAboutSelection}>带到对话</button><button className="quiet-button" onClick={createPracticeFromSelection}>基于此出题</button><button className="quiet-button" onClick={() => setSelectionQuote("")}>取消</button></div>}
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
                <section className={highlightedChunk === section.chunk_id ? "highlighted" : ""} data-chunk-id={section.chunk_id} key={section.chunk_id}>
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
        )}
      </div>
      {editingDocumentId && selected && (
        <DocumentEditor
          documentId={editingDocumentId}
          title={selected.title || selected.source}
          onClose={() => setEditingDocumentId(null)}
          onSaved={() => {
            setEditingDocumentId(null);
            void loadDocuments();
            if (selectedId) {
              setDetailLoading(true);
              void api.document(selectedId).then((result) => setSections(result.sections)).finally(() => setDetailLoading(false));
            }
          }}
        />
      )}
      {/* TASKS_LIBRARY_REWORK task 2: chapter rail (right-edge 64px hover zone).
          The zone only exists while the rail is closed. Because it lands directly
          under the pointer that just closed the rail, onMouseEnter has to ignore
          the hover coming from exactly where the X was (openRail / closeRail). */}
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
    </section>
  );
}
