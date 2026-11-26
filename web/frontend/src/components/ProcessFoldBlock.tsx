import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { ProcessFold, foldProcess } from "../lib/processFold";

/**
 * Renders a run of process steps (no raw chain-of-thought). Below the threshold
 * they show inline as compact tool chips; at or above it they fold into a
 * smooth grid accordion matching Bobodan's warm-paper tokens.
 */
export function ProcessFoldBlock({ steps }: { steps?: ProcessFold["steps"] }) {
  const { folded, summary, steps: list } = foldProcess(steps);
  const [open, setOpen] = useState(false);

  if (!list.length) return null;

  if (!folded) {
    return (
      <div className="process-fold process-fold-inline">
        {list.map((step, index) => (
          <span className="process-step-chip" key={index}>
            <i className="process-step-dot" aria-hidden="true" />
            <span>{step.message}</span>
            {step.elapsed != null && <small>{step.elapsed.toFixed(1)}s</small>}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="process-fold process-fold-collapsed" data-open={open}>
      <button
        type="button"
        className="process-fold-trigger"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <ChevronRight size={14} className="process-fold-chevron" aria-hidden="true" />
        <span className="process-fold-summary">{summary}</span>
        <span className="process-fold-count">{list.length} 步</span>
      </button>
      <div className="process-fold-panel" aria-hidden={!open}>
        <div className="process-fold-panel-inner">
          {list.map((step, index) => (
            <p className="process-fold-row" key={index}>
              <span className="process-step-dot" aria-hidden="true" />
              <span className="process-fold-msg">{step.message}</span>
              {step.elapsed != null && <small>{step.elapsed.toFixed(1)}s</small>}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
