import { useState } from "react";
import { Check, FileText, RotateCcw } from "lucide-react";

import { api } from "../lib/api";
import type { DocumentProposal } from "../types";

/**
 * Renders an AI edit proposal (LB-1.2): reason + diff + impact preview, with
 * confirm (apply) and, once applied, undo. AI never writes files directly —
 * the user confirms here first.
 */
export function DocumentProposalCard({
  proposal,
  onResolved,
}: {
  proposal: DocumentProposal;
  onResolved?: (proposal: DocumentProposal) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState(proposal);
  const [error, setError] = useState("");

  async function apply() {
    setBusy(true);
    setError("");
    try {
      const result = await api.applyDocumentProposal(current.proposal_id);
      setCurrent(result.proposal);
      onResolved?.(result.proposal);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "应用失败。");
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    setBusy(true);
    setError("");
    try {
      const result = await api.undoDocumentProposal(current.proposal_id);
      setCurrent(result.proposal);
      onResolved?.(result.proposal);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={"document-proposal-card " + current.status}>
      <header>
        <FileText size={14} />
        <strong>{current.kind === "create" ? "新建资料提案" : "资料编辑提案"}</strong>
        <span>{current.title}</span>
      </header>

      {current.reason && <p className="document-proposal-reason">{current.reason}</p>}

      {current.diff.length > 0 && (
        <details className="document-proposal-diff">
          <summary>查看改动（{current.diff.length} 行）</summary>
          <pre>
            {current.diff.map((item, index) => {
              const prefix = item.type === "add" ? "+ " : item.type === "remove" ? "- " : "  ";
              return <div key={index} className={"diff-" + item.type}>{prefix}{item.line}</div>;
            })}
          </pre>
        </details>
      )}

      {current.impact_count > 0 && (
        <p className="document-proposal-impact">
          会影响 {current.impact_count} 个 Wiki 页面：
          {current.impact.slice(0, 5).map((page) => page.title).join("、")}
          {current.impact.length > 5 ? "…" : ""}
        </p>
      )}

      {error && <p className="document-proposal-error">{error}</p>}

      <footer>
        {current.status === "proposed" && (
          <button className="primary-button" disabled={busy} onClick={() => void apply()}><Check size={15} />应用编辑</button>
        )}
        {current.status === "applied" && (
          <>
            <span className="document-proposal-applied">已应用</span>
            <button className="quiet-button" disabled={busy} onClick={() => void undo()}><RotateCcw size={15} />撤销</button>
          </>
        )}
        {current.status === "undone" && <span className="document-proposal-applied">已撤销</span>}
      </footer>
    </div>
  );
}
