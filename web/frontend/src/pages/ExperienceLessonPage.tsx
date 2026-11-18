import { useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, RotateCcw } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { readExperienceProgress, writeExperienceProgress } from "../lib/experienceLesson";

const OPTIONS = [
  { value: "A", text: "先生成答案，再补一个看起来相关的来源。" },
  { value: "B", text: "先检索相关原文，再根据检索到的片段组织回答。" },
  { value: "C", text: "先把整个资料库都交给模型，再让它自行寻找重点。" },
];

export function ExperienceLessonPage() {
  const navigate = useNavigate();
  const [progress, setProgress] = useState(readExperienceProgress);
  const correct = progress.answer === "B";

  function chooseAnswer(answer: string) {
    const next = { answer, completed: false };
    setProgress(next);
    writeExperienceProgress(next);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!progress.answer) return;
    const next = { ...progress, completed: true };
    setProgress(next);
    writeExperienceProgress(next);
  }

  function retry() {
    const next = { ...progress, completed: false };
    setProgress(next);
    writeExperienceProgress(next);
  }

  return (
    <section className="page-scroll">
      <div className="page-container experience-page">
        <header className="experience-header">
          <button className="icon-button" type="button" aria-label="返回对话" onClick={() => navigate("/chat")}><ArrowLeft size={18} /></button>
          <div><span>体验课 · 示例讲义</span><h2>先检索，再回答</h2></div>
        </header>
        <p className="experience-boundary"><BookOpen size={15} />示例内容，不写入你的资料库、题库或学习记录。</p>

        <article className="experience-source" aria-labelledby="experience-source-title">
          <p className="experience-source-location">示例讲义 · 第 1 节</p>
          <h3 id="experience-source-title">检索增强生成（RAG）</h3>
          <p id="experience-source-detail">RAG 会先从资料中检索与问题相关的片段，再让模型依据这些片段组织回答。这样，回答可以带着来源回到原文核对，而不是只依赖模型已经学过的内容。</p>
          <p>引用提供核对入口，但引用存在并不自动证明结论正确；还需要检查原文是否真的支持这句话。</p>
          <a className="text-link" href="#experience-question">去做一道离线题<ArrowRight size={14} /></a>
        </article>

        <form className="experience-question" id="experience-question" onSubmit={submit}>
          <span>离线单选 · 1 题</span>
          <h3>RAG 流程中，哪一步应先于生成回答？</h3>
          <fieldset>
            <legend className="visually-hidden">选择一个答案</legend>
            {OPTIONS.map((option) => (
              <label className={progress.answer === option.value ? "experience-option selected" : "experience-option"} key={option.value}>
                <input type="radio" name="experience-answer" value={option.value} checked={progress.answer === option.value} onChange={() => chooseAnswer(option.value)} />
                <strong>{option.value}</strong><span>{option.text}</span>
              </label>
            ))}
          </fieldset>
          {!progress.completed ? (
            <button className="primary-button" type="submit" disabled={!progress.answer}>检查答案<ArrowRight size={16} /></button>
          ) : (
            <div className={correct ? "experience-result correct" : "experience-result incorrect"} role="status">
              <strong><CheckCircle2 size={17} />{correct ? "答对了" : "再核对一下讲义"}</strong>
              <p>先检索相关原文，回答才有明确依据；引用还需要与原文内容逐项核对。</p>
              <a className="text-link" href="#experience-source-detail">回到讲义原文 · 第 1 节</a>
              {!correct && <button className="quiet-button" type="button" onClick={retry}><RotateCcw size={14} />再答一次</button>}
              {correct && <button className="quiet-button" type="button" onClick={() => navigate("/chat")}>返回对话</button>}
            </div>
          )}
        </form>
      </div>
    </section>
  );
}
