# W1「学习闭环升级」交付清单（2026-10-02）

一页看完这次做完的事。详细逐条说明在 [`ROADMAP.md`](ROADMAP.md) 的 §0.1「W1 收口结论」，过程与回归数字在 [`CHANGELOG.md`](../CHANGELOG.md) 顶部。

## 结论

ROADMAP §1 W1 的 **E1–E16 全部交付**（E17/E18 属既有工作流，见各自行）。**所有提交都在本地**：分支 `codex/audit-remediation-2026-09-25`，比远端 **领先 39 个提交**，按用户要求**一次都没有推送**（所以 GitHub / PR #5 上看不到这批东西）。

日期说明（2026-10-15 更正）：本机时钟在 2026-10-15 之前**慢了约 13 天**，所以这批提交里的「2026-10-01 / 10-02」是**提交时间戳，不是真实日期**；真实日期无法精确还原，只能说**截至 2026-10-15 交付完毕**。此前我按当时错误的时钟把文档日期「更正」成 10-02，**方向是错的** —— 已在 CHANGELOG 顶部留下说明与教训（写日期前先与外部时间源对时）。

## 这次会话交付的条目

| 条目 | 做了什么（一句话） | 主要落点 |
|---|---|---|
| E1 | 错误码上屏 + 导入状态不跨库泄漏 | `web/frontend/src/lib/errorHints.ts`、`lib/importState.ts` |
| E2 | 新建资料库默认路径改为后端单一来源 | `web/frontend/src/components/LibrarySetupDialog.tsx` |
| E3 | 错题变式回退链在未配置模型时也能活 | `service/quiz_service.py` |
| E4 | ask_user 生命周期：多选真判定、**跳过 + 唤醒暂停的 run**、**超时策略（默认 48h，可配）**、**迟到的回答仍算数** | `service/interaction_service.py`、`AskUserCard.tsx` |
| E5 | 出题三阶段流式管线 → SSE → 界面逐题卡片；管线吃 `course`、**尊重资料范围**、吃个性化上下文 | `quiz/pipeline.py`、`web/backend/routers/quiz.py`、`hooks/useQuestionPipeline.ts` |
| E6 | 掌握度：逐次作答落库 + 纯函数引擎 + 复习队列/下一步接线 + **`learning_status` 工具（agent 能读引擎）** | `learning/engine.py`、`tools/learning_tools.py` |
| E7 | 划线闭环：锚点存储与诚实重锚定 → **跨分段找回引文** → 面板定位 → **正文内上色** → **笔记托管区块** | `memory/anchors.py`、`lib/domHighlight.ts`、`lib/managedBlocks.ts` |
| E8 | 导入：协作式取消、逐文件进度、失败清单、拖拽热区、运行态界面 | `service/kb_service.py`、`ImportDropZone.tsx`、`ImportReportPanel.tsx` |
| E9 | 到期复习薄弱原因（修掉「全对也进薄弱点」） | `service/learning_service.py` |
| E10 | Socratic persona 技能载体 + 优先级裁决文档 | `skills/socratic-persona/SKILL.md`、`docs/PERSONA.md` |
| E11 | 单循环契约：`finish_reason` → **截断续写** → 探索预算 + 结算期 → `call_role` → 界面消费 | `providers/`、`core/agent_loop.py`、`web/backend/events.py` |
| E12 | prompt 具名块字节稳定 + KB seed 预检索 | `core/prompt_blocks.py` |
| E13 | 出题卡防绕过：白名单收紧 + 纯文本收尾重定向 | `web/backend/routers/chat.py`、`service/evidence_policy.py` |
| E14 | 会话类别 `kind`（chat / practice / review） | `core/session.py`、`web/backend/routers/chat.py` |
| E15 | 简答三态判分与「学习中」口径统一 | `service/quiz_service.py` |
| E16 | 新确认概念返回坐标 + 界面高亮数秒 | `graph/concept_store.py`、`KnowledgeMap` 相关组件 |

## 怎么验证（可复跑）

```powershell
cd 'F:\claude projects\openclaw-main\project_class'

# 后端
.venv\Scripts\python.exe -m pytest -q          # 最近一次：1799 passed

# 前端（cd web/frontend）
npx tsc --noEmit ; npm run lint ; npx vitest run ; npm run build
# 最近一次：tsc/lint/build 全 0，41 files / 241 passed

# 真实后端 live（需要 8000 端口的服务在跑）
$env:BOBODAN_E2E_LIVE='1'; npx playwright test e2e/live.spec.ts --project=desktop
# 最近一次：7 passed
```

## 仍未做（如实列出，不藏）

1. **练习页没有课程选择器**：管线已支持 `course`，但界面只发资料范围。
2. **掌握度调度仍是原 SM-2 增量逻辑**：这次只补了「能读引擎」，没有改调度行为。
3. **划线同步只能进正在编辑的这篇笔记**：没有「把 A 资料的划线同步到另一篇」的选择器；对源资料保持只读。

## 过程中抓到的真 bug（都由测试/探针逼出来）

1. `skipInteraction / resolveInteraction / sendResume` 用 `if (!sessionId) return`，而卡片在流中途就渲染 → 用户点「跳过/回答」**静默无效**。
2. 逐题管线**完全忽略 `document_ids`** → 用户选的资料范围无效，可能拿到范围外证据。
3. `answer()` 把所有 `graded` 当「已作答」→ **用户迟到的回答被静默丢弃**。
4. 工具轮的过渡说明从来没发给界面（已用 `call_role` 修好，进「过程」不进正文）。
5. 截断续写到上限时重复计了一段（内容重复）。

## 纪律声明

- **没有推送**：39 个提交全在本地；远端仍是被审的那一版（PR #5 看到的是修复前版本）。
- **没有动真实资料库内容**：近两天 `note/vault` 内被写入的文件仅 `.bobodan/` 运行时索引（9 个文件，非用户内容 0 处）。
- 每条都按「先写会失败的测试 → 实现 → 全量门禁 → 一个本地提交 → 记账」推进；审查错判与未做项都写进了 CHANGELOG。
