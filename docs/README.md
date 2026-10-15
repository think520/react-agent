# Bobodan 文档

文档已收敛：**路线看一个文件，产品边界和视觉规则各看一个文件**。

当前主线（2026-09-08）：先完成学习闭环的正确性与恢复，再评测并接入可选向量检索，最后进入桌面发布。除非任务明确涉及历史迁移，否则不要从 `archive/` 恢复旧路线。

## 当前文档集

| 文档 | 用途 | 什么时候读 |
|---|---|---|
| [`../README.md`](../README.md) | 用户入口：能力、快速开始、验证命令 | 想跑起来 |
| [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | 产品定位、当前成熟度、架构边界、发布门槛和编码纪律 | 任何开发工作前，必读 |
| [`ROADMAP.md`](ROADMAP.md) | **唯一执行路线：当前批次、后续批次、门禁、已拍板决策、明确不做** | 排期、开工、对齐方向时 |
| [`DESIGN.md`](DESIGN.md) | 视觉、交互、可访问性和页面验收硬约束 | 任何界面工作前，必读 |
| [`QUESTION_BANK_DESIGN.md`](QUESTION_BANK_DESIGN.md) | **题库立项设计（D1–D9 已定稿）**：边界、组织、收藏、对话/复习联动、UI 归属、数据模型、实施顺序与验收 | 做 E18 题库，或改练习/复习/对话取题逻辑时 |
| [`LIBRARY_TREE_DESIGN.md`](LIBRARY_TREE_DESIGN.md) | **资料库文件树与分栏阅读设计（22 项已定稿）**：资料边界、扫描规则、树、标签页阅读、资料范围联动、归档语义、AI 整理与批次 ①–⑤ | 做 E17、改 Library 或阅读器时 |
| [`REFERENCE_PROJECTS.md`](REFERENCE_PROJECTS.md) | **本地参考项目索引**：DeepTutor / OpenMAIC / openhanako 克隆路径、许可证、各自强项、已确认同构案例 | 遇到 bug 或设计难题、想找同构实现时 |
| [`Bobodan参考项目调研报告.md`](Bobodan参考项目调研报告.md) | DeepTutor / OpenMAIC / qiaomu 专项调研：ROADMAP 各条目的机制精讲与源码索引（活文档，随借鉴进度回读） | 实施某条路线条目前 |
| [`rag_design.md`](rag_design.md) | RAG 架构真相源（存储/解析/检索/RRF/配置） | 改 RAG 时 |
| [`MCP.md`](MCP.md) / [`tools/skills.md`](tools/skills.md) | MCP 与 Skills 使用说明 | 配置扩展能力时 |

使用规则：

- 想知道**做什么、不做什么、为什么**：`ROADMAP.md`。
- 想知道**当前做到哪里、能不能做、边界在哪**：`PROJECT_GUIDE.md`。
- 想画界面：`PROJECT_GUIDE.md` → `DESIGN.md`。
- 遇到 bug、报错或设计取舍：先读 `REFERENCE_PROJECTS.md`，在本地克隆里找同构实现，再决定做法。
- 做题库（E18）：先读 `QUESTION_BANK_DESIGN.md`，它是该功能的设计真相源。
- 做资料库树与阅读器（E17）：先读 `LIBRARY_TREE_DESIGN.md`，它是该功能的设计真相源。
- 实施借鉴条目（D/O/Q/F 编号）：先读 `Bobodan参考项目调研报告.md` 对应章节再动手。
- 版本变化：根目录 `CHANGELOG.md`。

权威关系：

- 路线和优先级以 `ROADMAP.md` 为准。
- 产品边界、技术真相和发布门槛以 `PROJECT_GUIDE.md` 为准。
- 视觉 token、交互规则和可访问性以 `DESIGN.md` 为准。
- RAG 的存储、解析、检索和配置以 `rag_design.md` 为准；它不能单独改变产品优先级。
- 调研报告只提供论据和实现参考，不产生新的排期；若与路线图冲突，以路线图为准。

已完成或被取代的历史文档（任务书、审查报告、被合并的路线）在 [`archive/`](archive/)，不再维护，仅供考古。
