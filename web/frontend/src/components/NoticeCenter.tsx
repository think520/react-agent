import { X } from "lucide-react";

import { useNoticeStore } from "../stores/noticeStore";

/**
 * App-level error surface (E1). Mounted once in AppShell so an operation that
 * fails inside a chat card, dialog or side panel is still visible wherever the
 * user is looking. Kept deliberately plain: the fuller toast system is H-c.
 */
export function NoticeCenter() {
  const notices = useNoticeStore((state) => state.notices);
  const dismissNotice = useNoticeStore((state) => state.dismissNotice);
  if (notices.length === 0) return null;
  return (
    <div className="notice-center">
      {notices.map((notice) => (
        <div
          key={notice.id}
          className={`notice notice-${notice.tone}`}
          role={notice.tone === "error" ? "alert" : "status"}
        >
          <span>{notice.message}</span>
          <button type="button" className="notice-dismiss" aria-label="关闭提示" onClick={() => dismissNotice(notice.id)}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
