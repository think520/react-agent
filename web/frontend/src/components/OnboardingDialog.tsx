import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, Database, ShieldCheck, Sparkles, UserRound } from "lucide-react";

import type { DocumentSummary, SettingsSummary } from "../types";
import { BrandIllustration } from "./common";

export interface LearningProfile {
  displayName: string;
  learningGoal: string;
  memoryEnabled: boolean;
  webEnabled: boolean;
}

export function OnboardingDialog({
  settings,
  documents,
  selectedDocumentIds,
  onToggleDocument,
  onComplete,
}: {
  settings: SettingsSummary | null;
  documents: DocumentSummary[];
  selectedDocumentIds: string[];
  onToggleDocument: (documentId: string) => void;
  onComplete: (profile: LearningProfile) => void;
}) {
  const [step, setStep] = useState(0);
  const [displayName, setDisplayName] = useState("");
  const [learningGoal, setLearningGoal] = useState("");
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [webEnabled, setWebEnabled] = useState(false);
  const provider = settings?.providers.find((item) => item.name === settings.default_provider);

  const steps = [
    { label: "你和目标", icon: UserRound },
    { label: "AI 连接", icon: Sparkles },
    { label: "学习空间", icon: Database },
    { label: "边界", icon: ShieldCheck },
  ];
  function complete() {
    onComplete({
      displayName: displayName.trim(),
      learningGoal: learningGoal.trim(),
      memoryEnabled,
      webEnabled,
    });
  }

  return (
    <div className="onboarding-backdrop" role="presentation">
      <section className="onboarding-dialog" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
        <header className="onboarding-header">
          <BrandIllustration state="listening" size={72} />
          <div><span>初次设置 · {step + 1}/4</span><h2 id="onboarding-title">{steps[step].label}</h2></div>
        </header>
        <div className="onboarding-progress" aria-hidden="true">{steps.map((item, index) => (
          <span className={index <= step ? "active" : ""} key={item.label} />
        ))}</div>

        <div className="onboarding-body">
          {step === 0 && <div className="onboarding-fields">
            <label>怎么称呼你<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="可稍后补充" /></label>
            <label>最近最想完成的学习目标<textarea rows={3} value={learningGoal} onChange={(event) => setLearningGoal(event.target.value)} placeholder="例如：两周内掌握图算法基础" /></label>
          </div>}

          {step === 1 && <div className="connection-check">
            <span className={provider?.configured ? "connection-mark ready" : "connection-mark"}><Sparkles /></span>
            <div><strong>{settings?.default_provider || "尚未选择模型"}</strong><p>{provider?.configured ? "连接已就绪，可以开始对话和出题。" : "当前模型尚未配置密钥。你仍可先整理资料，配置完成后再开始 AI 对话。"}</p></div>
          </div>}

          {step === 2 && <div className="onboarding-sources">
            <p>{documents.length ? "选择这段时间主要学习的资料。之后可以随时在资料库调整。" : "还没有学习资料。完成设置后可以从资料库导入。"}</p>
            {documents.slice(0, 8).map((document) => <button className={selectedDocumentIds.includes(document.document_id) ? "selected" : ""} onClick={() => onToggleDocument(document.document_id)} key={document.document_id}>
              <span><strong>{document.title || document.source}</strong><small>{document.course || document.kind || "本地资料"}</small></span>
              {selectedDocumentIds.includes(document.document_id) && <Check size={16} />}
            </button>)}
          </div>}

          {step === 3 && <div className="boundary-settings">
            <label><span><strong>沉淀学习记忆</strong><small>记住目标、偏好和长期进度</small></span><input type="checkbox" checked={memoryEnabled} onChange={(event) => setMemoryEnabled(event.target.checked)} /></label>
            <label><span><strong>允许模型自动联网</strong><small>本地资料不足或需要最新信息时使用，并明确标注来源</small></span><input type="checkbox" checked={webEnabled} onChange={(event) => setWebEnabled(event.target.checked)} /></label>
          </div>}
        </div>

        <footer className="onboarding-actions">
          {step > 0 ? <button className="quiet-button" onClick={() => setStep((value) => value - 1)}><ArrowLeft size={16} />上一步</button> : <span />}
          {step < 3
            ? <button className="primary-button" onClick={() => setStep((value) => value + 1)}>下一步<ArrowRight size={16} /></button>
            : <button className="primary-button" onClick={complete}><Check size={16} />开始学习</button>}
        </footer>
      </section>
    </div>
  );
}
