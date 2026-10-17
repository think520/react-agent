/** Wiki 视图过滤谓词（2026-10-17：从 LibraryPage 提到独立模块，页面与动作层共用）。 */
import type { DocumentSummary } from "../../types";

export type WikiViewType = "knowledge" | "sources" | "notes" | "all";

export function wikiViewForType(type: DocumentSummary["wiki_type"]): WikiViewType {
  if (type === "source") return "sources";
  if (type === "note") return "notes";
  return "knowledge";
}

export function matchesWikiView(document: DocumentSummary, view: WikiViewType): boolean {
  if (view === "all") return true;
  return wikiViewForType(document.wiki_type) === view;
}
