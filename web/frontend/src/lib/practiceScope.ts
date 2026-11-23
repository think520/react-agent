import type { DocumentSummary } from "../types";

export interface PracticeScopeGroup {
  key: string;
  label: string;
  course?: string;
  documentIds: string[];
  count: number;
}

function topFolderFromSource(doc: DocumentSummary): string {
  const raw = (doc.relative_path || doc.source || "").replace(/\\/g, "/").replace(/^\/+/, "");
  if (!raw) return "";
  const stripped = raw.replace(/^(?:course|obsidian)\//, "");
  const parts = stripped.split("/").filter(Boolean);
  if (parts.length <= 1) return "";
  // Skip bare container folders like "raw/inbox/..." when a deeper folder exists,
  // or keep the meaningful parent folder name directly.
  if (parts[0] === "raw" || parts[0] === "inbox") {
    return parts.length > 2 ? parts[1] : parts[0];
  }
  return parts[0];
}

/**
 * Derive selectable course / folder scope groups from library material documents.
 * Uses `course` metadata when present, falling back to the top folder segment.
 */
export function derivePracticeScopeGroups(documents: DocumentSummary[]): PracticeScopeGroup[] {
  const buckets = new Map<string, PracticeScopeGroup>();

  for (const doc of documents) {
    if (doc.collection === "wiki") continue;
    const course = doc.course?.trim() || "";
    let key: string;
    let label: string;
    let groupCourse: string | undefined;

    if (course) {
      key = `course:${course}`;
      label = course;
      groupCourse = course;
    } else {
      const folder = topFolderFromSource(doc);
      if (!folder) continue;
      key = `folder:${folder}`;
      label = folder;
    }

    const existing = buckets.get(key);
    if (existing) {
      if (!existing.documentIds.includes(doc.document_id)) {
        existing.documentIds.push(doc.document_id);
        existing.count = existing.documentIds.length;
      }
    } else {
      buckets.set(key, {
        key,
        label,
        course: groupCourse,
        documentIds: [doc.document_id],
        count: 1,
      });
    }
  }

  return Array.from(buckets.values()).sort((a, b) => a.label.localeCompare(b.label, "zh-Hans-CN"));
}

/**
 * Combine an explicit course/folder selection with any selected desk document IDs.
 * If the user picked specific files inside the chosen folder/course, narrow to that
 * intersection; otherwise use all documents in the chosen group.
 */
export function resolveEffectivePracticeScope(
  selectedGroup: PracticeScopeGroup | null,
  deskDocumentIds: string[],
): { course?: string; documentIds: string[] } {
  if (!selectedGroup) {
    return { documentIds: deskDocumentIds };
  }
  const groupSet = new Set(selectedGroup.documentIds);
  const intersected = deskDocumentIds.filter((id) => groupSet.has(id));
  return {
    course: selectedGroup.course,
    documentIds: intersected.length > 0 ? intersected : selectedGroup.documentIds,
  };
}
