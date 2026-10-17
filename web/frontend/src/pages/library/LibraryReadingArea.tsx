/** LibraryPage 阅读区（M2 store-lift · 分块搬出）：Wiki 视图侧栏 + 阅读/编辑器主列。只渲染。 */
import { readerLocation } from "../../lib/documentLinks";
import {} from "react";
import { CheckCircle2, FileText, FolderOpen, MessageCircle, MoreHorizontal, Pencil, RefreshCw, Search, Sparkles } from "lucide-react";
import {} from "react-router-dom";
import {} from "../../components/ImportDropZone";
import {} from "../../components/DocumentEditor";
import type {} from "../../components/AppShell";
import {} from "./libraryWikiActions";
import {} from "./wikiView";
import {} from "./LibraryTreePanel";
import {} from "./LibraryHeader";
import { createLibraryMaterialActions } from "./libraryActions";
import { EmptyState, formatRelativeDate } from "../../components/common";
import {} from "../../lib/api";
import type {} from "../../lib/api";
import { DocumentReader } from "../../components/DocumentReader";
import { ScrollIndicator } from "../../components/ScrollIndicator";
import {} from "../../stores/readerTabsStore";
import {} from "../../ui/Modal";
import type { DocumentExtractionStatus, DocumentSection, DocumentSummary } from "../../types";

import type { Dispatch, SetStateAction } from "react";
import type { NavigateFunction } from "react-router-dom";


import type { WikiViewType } from "./wikiView";

type MaterialActions = ReturnType<typeof createLibraryMaterialActions>;

export interface LibraryReadingAreaProps {
  retryFailedSections: MaterialActions["retryFailedSections"];
  searchParams: URLSearchParams;
  setError: (value: string) => void;
  setSections: (value: DocumentSection[]) => void;
  readerReloadToken: number;
  askAboutDocument: MaterialActions["askAboutDocument"];
  setEditingDocumentId: Dispatch<SetStateAction<string | null>>;
  closeTab: (tabId: string) => void;
  openIds: string[];
  collection: "material" | "wiki";
  wikiView: WikiViewType;
  documentQuery: string;
  setDocumentQuery: (value: string) => void;
  documents: DocumentSummary[];
  effectiveExtractionStatus: MaterialActions["effectiveExtractionStatus"];
  extractAndReview: MaterialActions["extractAndReview"];
  extractionStatuses: Record<string, DocumentExtractionStatus>;
  filteredDocuments: DocumentSummary[];
  hits: Array<{ chunk_id: string; document_id: string; collection?: string; title?: string; source?: string; text?: string }>;
  navigate: NavigateFunction;
  openExtractionReview: MaterialActions["openExtractionReview"];
  readerScrollRef: { current: HTMLElement | null };
  sections: DocumentSection[];
  selectDocument: MaterialActions["selectDocument"];
  selected: DocumentSummary | undefined;
  selectedId: string | null;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  startingExtractionId: string | null;
  wikiTypeLabels: Record<NonNullable<DocumentSummary["wiki_type"]>, string>;
}

export function LibraryReadingArea(props: LibraryReadingAreaProps) {
  const {
    closeTab,
    openIds,
    collection,
    wikiView,
    documentQuery,
    setDocumentQuery,
    documents,
    effectiveExtractionStatus,
    extractAndReview,
    extractionStatuses,
    filteredDocuments,
    hits,
    navigate,
    openExtractionReview,
    readerScrollRef,
    sections,
    selectDocument,
    selected,
    selectedId,
    setSelectedId,
    startingExtractionId,
    wikiTypeLabels,
    askAboutDocument,
    setEditingDocumentId,
    retryFailedSections,
    searchParams,
    setError,
    setSections,
    readerReloadToken,
  } = props;

  return (
    <>
  {collection === "wiki" && (
  <aside className="document-rail">
    <div className="rail-label"><FolderOpen size={15} />{wikiView === "knowledge" ? "知识页面" : wikiView === "sources" ? "资料索引" : wikiView === "notes" ? "个人笔记" : "全部页面"} <span>{filteredDocuments.length}</span></div>
    <label className="document-search"><Search size={14} /><input value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder="搜索资料" aria-label="搜索资料" /></label>
    {hits.length > 0 && (
      <div className="document-hits" aria-label="原文命中">
        {hits.map((hit) => (
          <button
            key={hit.chunk_id}
            className="document-hit"
            type="button"
            title={hit.text || ""}
            onClick={() =>
              navigate(
                readerLocation({
                  document_id: hit.document_id,
                  collection: hit.collection ?? collection,
                  chunk_id: hit.chunk_id,
                }) || "/library",
              )
            }
          >
            <Search size={13} />
            <span>
              <strong>{hit.title || hit.source}</strong>
              <small>{(hit.text || "").replace(/\s+/g, " ").slice(0, 56)}</small>
            </span>
          </button>
        ))}
      </div>
    )}
    {filteredDocuments.map((document) => (
      <div className={`document-row-wrap ${selectedId === document.document_id ? "active" : ""}`} key={document.document_id}>
        <button className="document-row" onClick={() => selectDocument(document.document_id)}>
          <span className="document-kind"><FileText size={17} /></span>
          {/* 这一栏现在只服务 wiki 三个视图：资料的阅读入口在文件夹树里。 */}
          <span><strong>{document.title || document.source}</strong><small>{(document.wiki_type ? wikiTypeLabels[document.wiki_type] : "历史整理")} · {document.chunk_count ? `${document.chunk_count} 个片段` : formatRelativeDate(document.updated_at)}</small></span>
          <i className={document.vector_status === "error" ? "error" : "ready"} title={document.vector_status || "已建立索引"} />
        </button>
      </div>
    ))}
    {!filteredDocuments.length && <p className="document-search-empty">没有找到匹配的资料。</p>}
  </aside>
  )}
  {/* 资料库没有列表栏时，右栏不能空着一条白条 —— 给一句"从哪开始"的指引。 */}
  {collection === "material" && !(selected || openIds.length > 0) && (
    <div className="library-reader-placeholder">
      <EmptyState
        state="reading"
        title="从左边选一份资料开始阅读"
        description="文件夹树里点一份资料，它会在这一栏打开；打开过的资料会留在标签条里。"
      />
    </div>
  )}
  {/* ④：标签条和阅读区必须是**同一个网格列**。标签条曾经是 .library-workspace 的
      第 4 个直接子元素，一开标签 3 列网格就自动换行：阅读区被挤到下一行，
      列表被顶到阅读区的位置（2026-09-24 用户截图发现的布局塌陷）。
      没有选中资料又没有标签时整列不渲染 —— 否则会留一条空白栏。 */}
  {/* 两层是必须的（2026-09-24 用户反馈"只有滚到最上面才看得见滑动条"）：
      滑块如果直接放在滚动容器里，它会**跟着内容一起滚走**（实测滚 1500px 后
      轨道 y 从 133 变成 -1367）。所以外面套一层不滚动的定位父层，滑块挂它身上。 */}
  {(selected || openIds.length > 0) && (
  <div className="library-reader-wrap">
  <ScrollIndicator targetRef={readerScrollRef} />
  <div className="library-reader-column" ref={(node) => { readerScrollRef.current = node; }}>
  {openIds.length > 0 && (
    <div className="reader-tabs" role="tablist" aria-label="打开的资料">
      {openIds.map((tabId) => (
        <span key={tabId} className={selectedId === tabId ? "reader-tab active" : "reader-tab"}>
          <button
            type="button"
            role="tab"
            aria-selected={selectedId === tabId}
            onClick={() => {
              selectDocument(tabId);
            }}
          >
            {documents.find((item) => item.document_id === tabId)?.title || tabId}
          </button>
          <button
            type="button"
            className="reader-tab-close"
            aria-label={`关闭 ${documents.find((item) => item.document_id === tabId)?.title || tabId}`}
            onClick={() => {
              const wasActive = selectedId === tabId;
              closeTab(tabId);
              if (wasActive) {
                const remaining = openIds.filter((item) => item !== tabId);
                const index = openIds.indexOf(tabId);
                const next = remaining[index] ?? remaining[index - 1];
                if (next) selectDocument(next);
                else setSelectedId(null);
              }
            }}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  )}
  <article className="document-reader">
    {selected && <header>
      <span>{selected.collection === "wiki" ? `历史整理 · ${selected.wiki_type ? wikiTypeLabels[selected.wiki_type] : "页面"}` : selected.kind || "本地资料"}{selected.course ? ` · ${selected.course}` : ""}</span>
      <h2>{selected.title || selected.source}</h2>
      {selected.collection === "material" && <div className="reader-actions">
        {effectiveExtractionStatus(selected) === "not_started" && (
          <button className="primary-button reader-extract" disabled={startingExtractionId === selected.document_id || !sections.length} onClick={() => void extractAndReview(selected)}><Sparkles size={15} />{startingExtractionId === selected.document_id ? "正在启动…" : "提取概念"}</button>
        )}
        {effectiveExtractionStatus(selected) === "extracting" && (
          <button className="quiet-button reader-extract status-extracting" onClick={() => openExtractionReview(selected, extractionStatuses[selected.document_id]!) }><RefreshCw size={15} />正在提取 · 查看进度</button>
        )}
        {effectiveExtractionStatus(selected) === "review" && (
          <button className="primary-button reader-extract" onClick={() => openExtractionReview(selected, extractionStatuses[selected.document_id]!) }><Sparkles size={15} />审查概念 · {extractionStatuses[selected.document_id]?.pending_count || 0}</button>
        )}
        {effectiveExtractionStatus(selected) === "completed" && (
          <button className="quiet-button reader-extract status-completed" onClick={() => navigate("/knowledge-map")}><CheckCircle2 size={15} />已提取 · 查看图谱</button>
        )}
        {(effectiveExtractionStatus(selected) === "failed" || effectiveExtractionStatus(selected) === "stale") && (
          <button className="primary-button reader-extract" disabled={startingExtractionId === selected.document_id || !sections.length} onClick={() => void extractAndReview(selected, true)}><RefreshCw size={15} />{effectiveExtractionStatus(selected) === "failed" ? "重新尝试" : "重新提取"}</button>
        )}
        <button className="quiet-button" onClick={askAboutDocument}><MessageCircle size={15} />基于此文档提问</button>
        {(selected.kind === "md" || selected.kind === "txt" || selected.kind === "markdown" || selected.kind === "course_document" || selected.kind === "obsidian_note") && (
          <button className="quiet-button" onClick={() => setEditingDocumentId(selected.document_id)}><Pencil size={15} />编辑</button>
        )}
        {["review", "completed"].includes(effectiveExtractionStatus(selected)) && (
          <details className="reader-extract-more">
            <summary className="icon-button" aria-label="更多概念操作" title="更多概念操作"><MoreHorizontal size={16} /></summary>
            <div>
              {!!extractionStatuses[selected.document_id]?.run.failed_sections?.length && <button onClick={() => void retryFailedSections(selected)}><RefreshCw size={14} />只重试失败章节</button>}
              <button onClick={() => void extractAndReview(selected, true)}><RefreshCw size={14} />重新提取</button>
            </div>
          </details>
        )}
      </div>}
      {selected.summary && <p>{selected.summary}</p>}
    </header>}
    {selected && (
      <DocumentReader
        key={selected.document_id}
        documentId={selected.document_id}
        collection={selected.collection === "wiki" ? "wiki" : "material"}
        chunkId={searchParams.get("chunk")}
        documentSummary={selected}
        scrollRef={readerScrollRef}
        onError={setError}
        onSectionsLoaded={setSections}
        reloadToken={readerReloadToken}
      />
    )}
  </article>
  </div>
  </div>
  )}
    </>
  );
}
