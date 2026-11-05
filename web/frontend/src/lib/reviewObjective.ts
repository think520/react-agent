/**
 * W1 E6 接线：复习页要说清楚两件事 ——
 * ① 今天下一件该做什么（纯函数引擎给的优先级）；
 * ② 这条掌握度是**推导**出来的还是老数据里的**存量**（不冒充）。
 */

export interface NextObjective {
  kind: "pending_question" | "due_review" | "unseen_concept" | string;
  concept?: string;
  prompt?: string;
  interaction_id?: string;
}

export interface MasteryFields {
  mastery?: number;
  evidence?: number;
  mastery_source?: "history" | "stored" | string;
  /** E6.2：状态来源（manual / history / stored / none），用来区分「你标的」和「算出来的」。 */
  status_source?: "manual" | "history" | "stored" | "none" | string;
}

export function nextObjectiveText(objective?: NextObjective | null): string {
  if (!objective) return "";
  if (objective.kind === "pending_question") {
    const prompt = (objective.prompt || "").trim();
    return prompt ? `先回答上面的问题：${prompt}` : "先回答上面的问题，Bobodan 才能继续。";
  }
  if (objective.kind === "due_review" && objective.concept) {
    return `现在该复习「${objective.concept}」。`;
  }
  if (objective.kind === "unseen_concept" && objective.concept) {
    return `接下来学「${objective.concept}」。`;
  }
  return "";
}

export function masteryLabel(item: MasteryFields): string {
  if (typeof item.mastery !== "number") return "";
  if (item.status_source === "manual") {
    // 用户自己标的，不冒充系统推导；顺带说清它之后还有没有新证据。
    return `掌握度 ${item.mastery}（你手动标记）`;
  }
  if (item.mastery_source === "history") {
    const evidence = item.evidence || 0;
    return `掌握度 ${item.mastery}（${evidence} 次作答记录）`;
  }
  return `掌握度 ${item.mastery}（存量分数，没有逐次记录）`;
}
