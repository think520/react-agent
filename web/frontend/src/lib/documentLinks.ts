/**
 * 资料跳转的统一落点。
 *
 * 以前三处（来源 chip、右侧来源栏、"引用"列表）各自拼 `/library?collection=…&document=…`
 * ——那是**资料库列表页**，而它不渲染 sections，于是 LibraryPage 里处理 `chunk` 的
 * 那段代码永远拿不到 `[data-chunk-id]` 节点："查看来源"跳过去以后**定位不到引用段落**。
 *
 * 现在一律进阅读器，并带上片段 id；阅读器读到 `chunk` 会落到分段视图并高亮那一段。
 */

export interface DocumentLinkSource {
  document_id?: string | null;
  collection?: string | null;
  /** 原文片段 id：本地来源的 source_id 就是 chunk id（web 来源不走这里）。 */
  source_id?: string | null;
  chunk_id?: string | null;
}

export function readerLocation(source: DocumentLinkSource | null | undefined): string | null {
  const documentId = source?.document_id;
  if (!documentId) return null;
  const collection = source?.collection === "wiki" ? "wiki" : "material";
  const chunk = source?.chunk_id || source?.source_id || "";
  const params = new URLSearchParams({ collection });
  if (chunk) params.set("chunk", chunk);
  return "/library/read/" + encodeURIComponent(documentId) + "?" + params.toString();
}
