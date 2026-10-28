# Bobodan 文档

> **现在按哪份走？** 排期看 [`ROADMAP.md`](ROADMAP.md)，能不能做看 [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md)，界面硬约束看 [`DESIGN.md`](DESIGN.md)，前端实施顺序看 [`FRONTEND_UPGRADE_PLAN.md`](FRONTEND_UPGRADE_PLAN.md)，RAG 事实看 [`rag_design.md`](rag_design.md) + [`RAG_EVAL.md`](RAG_EVAL.md)。其余文档都是这几层的专题展开，冲突按第 1 节顺序裁决。
>
> 本页是文档的**唯一入口**；不要靠记忆或旧链接找文档。版本：2026-10-28。

## 0. 按任务查文档（30 秒定位）

| 你要做的事 | 只看这份 | 别再翻 |
|---|---|---|
| 决定下一步做什么、先做什么、不做什么 | [`ROADMAP.md`](ROADMAP.md) | 任何评审报告或调研报告的排期结论 |
| 判断某能力是否在边界内、架构真相、发布门槛 | [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | 根 `README.md` 的能力介绍（给人看的，不是契约） |
| 改界面：颜色、字号、间距、圆角、动效、可访问性 | [`DESIGN.md`](DESIGN.md) | `VISUAL_SYSTEM_PLAN.md`（已归档） |
| 改前端：组件迁移、页面配方、依赖引入、迁移顺序 | [`FRONTEND_UPGRADE_PLAN.md`](FRONTEND_UPGRADE_PLAN.md) | 历史 `FRONTEND_OPTIMIZATION*.md` |
| 改 RAG：分块、embedding、FTS、RRF、检索权重 | [`rag_design.md`](rag_design.md)，评测看 [`RAG_EVAL.md`](RAG_EVAL.md) | 调研报告里的 RAG 章节 |
| 改资料库：文件树、分栏阅读、资料范围、归档 | [`LIBRARY_TREE_DESIGN.md`](LIBRARY_TREE_DESIGN.md) | `archive/` 里的旧资料库任务书 |
| 改题库 / 练习 / 复习取题 | [`QUESTION_BANK_DESIGN.md`](QUESTION_BANK_DESIGN.md) | — |
| 改流式请求、导入、后台任务的中止 | [`CANCELLATION_DESIGN.md`](CANCELLATION_DESIGN.md) | — |
| 改 Agent 人格、教学风格 | [`PERSONA.md`](PERSONA.md) | 调研报告的 prompt 章节 |
| 配置 MCP / Skills 扩展 | [`MCP.md`](MCP.md) / [`tools/skills.md`](tools/skills.md) | — |
| 找同构实现、借鉴机制 | [`REFERENCE_PROJECTS.md`](REFERENCE_PROJECTS.md) → [`Bobodan参考项目调研报告.md`](Bobodan参考项目调研报告.md) | 直接读参考仓 |
| 查某个决策是怎么来的 | [`reviews/`](reviews/) + [`archive/`](archive/) + [`../CHANGELOG.md`](../CHANGELOG.md) | — |
| 想把它跑起来 | [`../README.md`](../README.md) | — |

## 1. 权威链（冲突裁决顺序）

两份文档说法冲突时，按下面顺序取高位者，并**把低位那份改掉**（不是两处都留着）：

1. [`ROADMAP.md`](ROADMAP.md) —— 做什么、什么顺序、什么不做、门禁数字。
2. [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) —— 产品边界、架构真相、发布门槛、编码纪律。
3. [`DESIGN.md`](DESIGN.md)（视觉硬约束）与 [`FRONTEND_UPGRADE_PLAN.md`](FRONTEND_UPGRADE_PLAN.md)（前端实施细节）。两者冲突以 `DESIGN.md` 为准，并把结论回写进 `DESIGN.md`；`FRONTEND_UPGRADE_PLAN.md` 已于 2026-10-21 拍板为前端唯一整合方案。
4. 专题真相源：`rag_design.md` / `RAG_EVAL.md` / `LIBRARY_TREE_DESIGN.md` / `QUESTION_BANK_DESIGN.md` / `CANCELLATION_DESIGN.md` / `PERSONA.md`。
5. 参考与追溯：`REFERENCE_PROJECTS.md`、`Bobodan参考项目调研报告.md`、`reviews/`、`archive/`、`CHANGELOG.md`。

**第 5 层不产生新排期，也不能推翻第 1–4 层。** 参考项目只能提供实现同构，不能直接往路线图增项：新参考项目必须先证明现有能力无法满足用户目标（ROADMAP §1 的既有规则）。

## 2. 状态口径（读任何文档前先看这一节）

- 每份文档写于某一天，里面的**行号、测试数量、分支名、文件名都是当时的快照**，不是当前验收结果。
- 当前状态只有一个答案：[`ROADMAP.md`](ROADMAP.md) 的 §0 门禁数字、§1.1「下一步候选」、以及 [`../CHANGELOG.md`](../CHANGELOG.md) 的 `[未发布]` 段。
- 文档里的标记含义固定：`✅` 已落地且有代码或测试；`🟡 / ⏳` 计划中或未交付；`待核对` 表示描述可能已部分完成，开工前必须先看代码。
- 发现文档与代码不一致：**先修文档**，再跑 `web/frontend/src/lib/designTokens.test.ts`（设计类）或对应回归（功能类）确认。
- 契约测试分两层，别混用（详见 `DESIGN.md` §16.3）：**L1 文本契约**（vitest 读 CSS/组件源码比对字符串）只能证明「文档与源码文本一致」，证明不了运行时生效的值；**L2 计算样式契约**（Playwright `getComputedStyle`）才证明「浏览器里真的是这个值」。改样式覆盖关系时必须同时补 L2。

## 3. 已知过期段落登记（保留用于追溯，别当现状引用）

| 位置 | 为什么过期 | 现在的真相在 |
|---|---|---|
| `PROJECT_GUIDE.md` 的历史阶段/验收段 | 记录的是 2026-08 前后的阶段与数字 | `ROADMAP.md` §0 门禁与 §2 交付记录 |
| `ROADMAP.md` §0 的 2026-09-08 快照段 | 那是复测快照，后续条目（如 G4 召回评测）已在 §1.1 / §2 更新 | `ROADMAP.md` §1.1、§2 |
| [`rag_design.md`](rag_design.md) 开头状态段与 §4.1 schema / §7 路由 / §14 测试清单 | 状态段停在 2026-09-08；schema 与路由有未回写的增量 | [`RAG_EVAL.md`](RAG_EVAL.md) + `rag/` 代码 + 文首的事实基准横幅 |
| `reviews/` 全部评审 | 按当时基线与范围写的，不自动代表当前代码 | `ROADMAP.md` |
| `archive/` 全部 | 已完成、已交付或被取代 | 同名专题的当前版本 |

## 4. 索引

### 决策与规范

| 文档 | 用途 |
|---|---|
| [`ROADMAP.md`](ROADMAP.md) | 唯一执行路线：W1–W5 工作池、状态口径、已拍板决策、明确不做、来源索引 |
| [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | 产品定位、成熟度、架构真相、数据边界、发布门槛与编码纪律 |
| [`DESIGN.md`](DESIGN.md) | 可执行设计规范：token、排版、表面阶梯、动效、可访问性、性能预算、打包清单、契约测试 |
| [`FRONTEND_UPGRADE_PLAN.md`](FRONTEND_UPGRADE_PLAN.md) | 前端唯一整合方案：token 落地、组件行为、页面配方、依赖矩阵、迁移顺序与验收 |

### 专题真相源

| 文档 | 用途 |
|---|---|
| [`rag_design.md`](rag_design.md) | RAG 架构：存储、解析、检索、RRF 与配置 |
| [`RAG_EVAL.md`](RAG_EVAL.md) | 召回评测方法、真实库基线（hit@5 / MRR）与判据 |
| [`LIBRARY_TREE_DESIGN.md`](LIBRARY_TREE_DESIGN.md) | 资料库文件树、分栏阅读、资料范围、归档与 AI 整理 |
| [`QUESTION_BANK_DESIGN.md`](QUESTION_BANK_DESIGN.md) | 题库边界、组织、收藏、对话/复习联动、数据模型与验收 |
| [`CANCELLATION_DESIGN.md`](CANCELLATION_DESIGN.md) | 协作取消的边界、原语与接线 |
| [`PERSONA.md`](PERSONA.md) | 人格载体与优先级裁决 |
| [`MCP.md`](MCP.md) / [`tools/skills.md`](tools/skills.md) | MCP 与 Skills 使用说明 |

### 参考与品牌

| 文档 | 用途 |
|---|---|
| [`REFERENCE_PROJECTS.md`](REFERENCE_PROJECTS.md) | 本地参考项目索引、许可证与可借鉴范围 |
| [`Bobodan参考项目调研报告.md`](Bobodan参考项目调研报告.md) | D/O/Q/F/H 条目的机制精讲与源码索引（活文档） |
| [`assets/brand/BOBODAN_MASCOT.md`](assets/brand/BOBODAN_MASCOT.md) | 品牌吉祥物与品牌色来源（hex 以 `web/frontend/src/styles/tokens.css` 为准） |

### 追溯与历史

| 位置 | 用途 |
|---|---|
| [`archive/README.md`](archive/README.md) | 归档清单与去向表 |
| [`reviews/README.md`](reviews/README.md) | 项目审查与整改复审索引 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 变更流水：每批改了什么、怎么验证的、哪些尝试被回滚 |
| [`../CLAUDE.md`](../CLAUDE.md) | Agent 编码契约（命令、架构骨架、关键不变量） |

历史文档可能保留当时有效的行号、测试数量、分支状态或产品名称。需要追溯决策时读它们，不要拿其中的旧数字当作当前验收结果。
