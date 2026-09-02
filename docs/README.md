# Bobodan 文档

文档已收敛：**路线只看一个文件，边界只看两个文件**。

## 当前文档集

| 文档 | 用途 | 什么时候读 |
|---|---|---|
| [`../README.md`](../README.md) | 用户入口：能力、快速开始、验证命令 | 想跑起来 |
| [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | 项目主指南：产品定位、当前阶段、架构边界、编码纪律 | 任何开发工作前，必读 |
| [`ROADMAP.md`](ROADMAP.md) | **统一路线图：现在做什么、接下来做什么、已拍板决策、明确不做** | 排期、开工、对齐方向时 |
| [`DESIGN.md`](DESIGN.md) | 视觉与动效硬约束 | 任何界面工作前，必读 |
| [`Bobodan参考项目调研报告.md`](Bobodan参考项目调研报告.md) | DeepTutor / OpenMAIC / qiaomu 专项调研：ROADMAP 各条目的机制精讲与源码索引（活文档，随借鉴进度回读） | 实施某条路线条目前 |
| [`rag_design.md`](rag_design.md) | RAG 架构真相源（存储/解析/检索/RRF/配置） | 改 RAG 时 |
| [`MCP.md`](MCP.md) / [`tools/skills.md`](tools/skills.md) | MCP 与 Skills 使用说明 | 配置扩展能力时 |

使用规则：

- 想知道**做什么、不做什么、为什么**：`ROADMAP.md`。
- 想知道**能不能做、边界在哪**：`PROJECT_GUIDE.md`。
- 想画界面：`PROJECT_GUIDE.md` → `DESIGN.md`。
- 实施借鉴条目（D/O/Q/F 编号）：先读 `Bobodan参考项目调研报告.md` 对应章节再动手。
- 版本变化：根目录 `CHANGELOG.md`。

已完成或被取代的历史文档（任务书、审查报告、被合并的路线）在 [`archive/`](archive/)，不再维护，仅供考古。
