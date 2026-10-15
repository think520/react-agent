import { useCallback, useRef, useState } from "react";

import { api } from "../lib/api";
import type { QuestionPipelineEvent } from "../lib/api";

export interface PipelineQuestion {
  id: number;
  question: string;
  type?: string;
  /** W1 E5：实时卡片要显示的东西 —— 只发题干的话界面只能列一行字。 */
  options: string[];
  difficulty?: string;
}

type Status = "idle" | "running" | "done" | "failed" | "cancelled";

/**
 * W1 E5 第二批："每题就绪即渲染"的前端一半。
 *
 * 事件到了就累积，**不等整批出完**；失败与取消都保留已经就绪的题
 * （取消不删东西，和后端一致）。
 */
export function useQuestionPipeline() {
  const [status, setStatus] = useState<Status>("idle");
  const [questions, setQuestions] = useState<PipelineQuestion[]>([]);
  const [questionIds, setQuestionIds] = useState<number[]>([]);
  const [plan, setPlan] = useState<Array<{ topic: string; question_type?: string; difficulty?: string }>>([]);
  const [planSource, setPlanSource] = useState("");
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const handle = useCallback((event: QuestionPipelineEvent) => {
    if (event.event === "quiz_plan") {
      setPlan(event.plan || []);
      setPlanSource(event.source || "");
      return;
    }
    if (event.event === "quiz_question_emitted") {
      const payload = event.question;
      setQuestions((current) => [
        ...current,
        {
          id: payload?.id ?? event.question_id,
          question: payload?.question || "",
          type: payload?.type,
          options: payload?.options || [],
          difficulty: payload?.difficulty,
        },
      ]);
      setQuestionIds((current) => [...current, event.question_id]);
      return;
    }
    if (event.event === "pipeline_done") {
      if (event.question_ids?.length) setQuestionIds(event.question_ids);
      setStatus("done");
      return;
    }
    if (event.event === "pipeline_cancelled") {
      setStatus("cancelled");
      return;
    }
    if (event.event === "pipeline_failed") {
      setError(event.error || "逐题生成失败。");
      setStatus("failed");
      return;
    }
    if (event.event === "pipeline_result" && event.ok === false) {
      setError("没有找到可用于出题的资料。");
      setStatus("failed");
    }
  }, []);

  const start = useCallback(async (topic: string, count = 5, documentIds: string[] = []) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("running");
    setQuestions([]);
    setQuestionIds([]);
    setPlan([]);
    setPlanSource("");
    setError("");
    try {
      await api.streamQuestionPipeline({ topic, count, document_ids: documentIds }, handle, controller.signal);
      setStatus((current) => (current === "running" ? "done" : current));
    } catch (reason) {
      if (controller.signal.aborted) {
        setStatus("cancelled");
        return;
      }
      setError(reason instanceof Error ? reason.message : "逐题生成失败。");
      setStatus("failed");
    }
  }, [handle]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return { status, questions, questionIds, plan, planSource, error, start, cancel };
}
