/**
 * Process folding (FE-3): collapse a run of pure-process steps into a fold
 * block when it reaches the threshold. Pure helpers keep it testable.
 */

export interface ProcessStep {
  phase: string;
  message: string;
  toolName?: string;
  elapsed?: number;
}

export interface ProcessFold {
  folded: boolean;
  summary: string;
  steps: ProcessStep[];
}

export const PROCESS_FOLD_THRESHOLD = 3;

export function foldProcess(steps: ProcessStep[] | undefined, threshold = PROCESS_FOLD_THRESHOLD): ProcessFold {
  const list = steps ?? [];
  const folded = list.length >= threshold;
  const summary = folded
    ? (list[0]?.message || "处理中") + " · 共 " + list.length + " 个步骤"
    : list.map((step) => step.message).join(" · ");
  return { folded, summary, steps: list };
}
