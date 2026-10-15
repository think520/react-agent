interface PracticeProgress {
  correct: number;
  total: number;
  /** 三态计数（W1 E15 起由后端给出；老数据可能没有）。 */
  partial?: number;
  wrong?: number;
}

/**
 * 练习小结的第一句（W1 E15）。
 *
 * 事实：错题谓词**排除 partial**（«quiz/store.py» 的 «_WRONG_VERDICT_SQL»）——
 * "基本正确"既不算答对、也不会进错题本。所以文案必须分三种情况说，
 * 旧实现一律说"错题和薄弱点已经加入复习队列"，在"只有 partial"的一轮里就是假话。
 */
export function practiceSummaryLine(progress: PracticeProgress): string {
  const total = progress.total || 0;
  const correct = progress.correct || 0;
  const partial = progress.partial || 0;
  const head = `答对 ${correct} / ${total} 题` + (partial ? `，另有 ${partial} 题基本正确` : "");
  if (progress.wrong === undefined) {
    // 老数据没有三态计数：**不猜**错了几题，宁可不给"错题已入队"这句话。
    return `${head}。`;
  }
  const wrong = progress.wrong;

  if (total > 0 && correct === total && !wrong) {
    return `${head}。全部答对，复习队列没有新增错题。`;
  }
  if (!wrong) {
    // 只有 partial：它会计入薄弱点，但**没有**进错题本 —— 不能顺着旧文案说谎。
    return `${head}。这几题已计入薄弱点，但没有进错题本（partial 不算错）。`;
  }
  return `${head}。错题和薄弱点已经加入复习队列。`;
}
