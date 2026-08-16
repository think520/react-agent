/**
 * ReaderPage — /library/read/:id (TASKS_LIBRARY_REWORK task 1).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, NotebookPen, Pencil, Quote, RefreshCw, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";

import type { AppOutletContext } from "../components/AppShell";
import { EmptyState, ErrorNotice, LoadingState } from "../components/common";
import { DocumentEditor } from "../components/DocumentEditor";
import { ApiError, api } from "../lib/api";
import { useHandoffStore } from "../stores/handoffStore";
import type { DocumentExtractionStatus, DocumentSection, DocumentSummary, PersonalKnowledgeItem } from "../types";

const EDITABLE_KINDS = new Set(["md", "txt", "markdown"]);

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
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [startingExtractionId, setStartingExtractionId] = useState<string | null>(null);
  const [extractionStatuses, setExtractionStatuses] = useState<Record<string, DocumentExtractionStatus>>({});
  const pageRef = useRef<HTMLElement>(null);
  const readingOpenedRef = useRef(false);
  const lastProgressRef = useRef(0);

  const selectedId = id ?? null;
  const selected = documents.find((document) => document.document_id === selectedId) ?? null;
  const selectedIndex = documents.findIndex((document) => document.document_id === selectedId);

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

  function recordReadingProgress() {
    const element = pageRef.current;
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
    if (force && !window.confirm("重新提取「" + (doc.title || doc.source) + "」的概念？这会再次调用模型并消耗 Token。")) return;
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
      <div className="page-container reader-container">
        <header className="reader-topbar">
          <button className="quiet-button" onClick={() => navigate("/library?collection=" + collection)}><ArrowLeft size={15} />返回资料库</button>
          <div className="reader-topbar-nav">
            <button className="icon-button" aria-label="上一份" disabled={!documents.length} onClick={() => goTo(-1)}><ArrowLeft size={15} /></button>
            <button className="icon-button" aria-label="下一份" disabled={!documents.length} onClick={() => goTo(1)}><ArrowRight size={15} /></button>
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
          </div>
        </header>

        {error && <ErrorNotice message={error} />}

        {loading ? (
          <LoadingState label="正在读取资料…" />
        ) : !selected ? (
          <EmptyState compact title="资料不存在" description="这份资料可能已被归档。" />
        ) : (
          <article className="reader-article">
            {selectionQuote && <div className="selection-toolbar"><Quote size={15} /><span>已选择 {selectionQuote.length} 个字符</span><button className="quiet-button" onClick={askAboutSelection}>带到对话</button><button className="quiet-button" onClick={() => setSelectionQuote("")}>取消</button></div>}
            {detailLoading ? <LoadingState label="正在打开资料…" /> : sections.length ? <div className="reader-prose" onMouseUp={captureSelection}>{sections.map((section, index) => {
              const previous = index > 0 ? sections[index - 1] : undefined;
              const showHeading = Boolean(section.heading) && section.heading !== previous?.heading;
              return (
                <section className={highlightedChunk === section.chunk_id ? "highlighted" : ""} data-chunk-id={section.chunk_id} key={section.chunk_id}>
                  {showHeading && <h3>{section.heading}</h3>}
                  <div className="section-location">{section.page_start ? "第 " + section.page_start + " 页" : section.slide_start ? "第 " + section.slide_start + " 页" : "资料片段"}</div>
                  <div className="reader-section-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{section.text}</ReactMarkdown></div>
                </section>
              );
            })}</div> : <EmptyState compact title="没有可阅读的片段" description="这份资料可能仍在建立索引。" />}

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
    </section>
  );
}
