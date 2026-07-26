import { useMemo, useState } from "react";
import { MoreHorizontal, RefreshCw, Search, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { sessionGroup, SESSION_GROUP_LABELS } from "../lib/sessionGroup";
import type { ChatSessionSummary } from "../types";
import { formatSessionTime, IconButton, LoadingState } from "./common";

export function SessionRail({ sessions, loading, activeSessionId, refreshSessions }: {
  sessions: ChatSessionSummary[];
  loading: boolean;
  activeSessionId?: string;
  refreshSessions: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [sessionQuery, setSessionQuery] = useState("");

  const groupedSessions = useMemo(() => {
    const query = sessionQuery.trim().toLocaleLowerCase();
    const filtered = sessions.filter((session) => !query || (session.name || "未命名会话").toLocaleLowerCase().includes(query));
    return SESSION_GROUP_LABELS.map((label) => ({
      label,
      sessions: filtered.filter((session) => sessionGroup(session.last_active) === label),
    })).filter((group) => group.sessions.length);
  }, [sessionQuery, sessions]);

  async function saveRename(id: string) {
    const name = editingName.trim();
    if (!name) return;
    await api.renameSession(id, name);
    setEditingId(null);
    await refreshSessions();
  }

  async function removeSession(session: ChatSessionSummary) {
    if (!window.confirm(`删除会话「${session.name || "未命名会话"}」？此操作无法撤销。`)) return;
    await api.deleteSession(session.chat_session_id);
    if (activeSessionId === session.chat_session_id) navigate("/chat");
    await refreshSessions();
  }

  return (
    <div className="session-section">
      <div className="section-label"><span>最近对话</span><IconButton label="刷新会话" onClick={() => void refreshSessions()}><RefreshCw size={15} /></IconButton></div>
      <label className="session-search"><Search size={14} /><input value={sessionQuery} onChange={(event) => setSessionQuery(event.target.value)} placeholder="搜索对话" aria-label="搜索对话" /></label>
      {loading ? <LoadingState label="正在找回会话…" /> : groupedSessions.length ? (
        <div className="session-list">{groupedSessions.map((group) => <section className="session-group" key={group.label}><div className="session-group-label">{group.label}</div>{group.sessions.map((session) => (
          <div className={`session-row ${activeSessionId === session.chat_session_id ? "active" : ""}`} key={session.chat_session_id}>
            {editingId === session.chat_session_id ? (
              <form onSubmit={(event) => { event.preventDefault(); void saveRename(session.chat_session_id); }}>
                <input autoFocus value={editingName} maxLength={120} onChange={(event) => setEditingName(event.target.value)} onBlur={() => void saveRename(session.chat_session_id)} />
              </form>
            ) : (
              <button className="session-main" onClick={() => navigate(`/chat/${session.chat_session_id}`)}>
                <span>{session.name || "未命名会话"}</span><small>{formatSessionTime(session.last_active)}</small>
              </button>
            )}
            <div className="session-actions">
              <IconButton label="重命名" onClick={() => { setEditingId(session.chat_session_id); setEditingName(session.name || ""); }}><MoreHorizontal size={15} /></IconButton>
              <IconButton label="删除会话" onClick={() => void removeSession(session)}><Trash2 size={14} /></IconButton>
            </div>
          </div>
        ))}</section>)}</div>
      ) : <p className="sidebar-empty">{sessionQuery ? "没有找到匹配的对话。" : "你的学习对话会保存在这里。"}</p>}
    </div>
  );
}
