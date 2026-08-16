import { ProcessFold, foldProcess } from "../lib/processFold";

/**
 * Renders a run of process steps. Below the threshold they show inline; at or
 * above it they collapse into a fold block with a summary and an expandable
 * panel (FE-3). The streaming trailing turn is rendered separately and is
 * never folded.
 */
export function ProcessFoldBlock({ steps }: { steps?: ProcessFold["steps"] }) {
  const { folded, summary, steps: list } = foldProcess(steps);
  if (!list.length) return null;

  if (!folded) {
    return (
      <div className="process-fold process-fold-inline">
        {list.map((step, index) => (
          <span key={index}>{step.message}</span>
        ))}
      </div>
    );
  }

  return (
    <details className="process-fold process-fold-collapsed">
      <summary>{summary}</summary>
      <div>
        {list.map((step, index) => (
          <p key={index}>
            <span>{step.message}</span>
            {step.elapsed != null && <small>{step.elapsed.toFixed(1)}s</small>}
          </p>
        ))}
      </div>
    </details>
  );
}
