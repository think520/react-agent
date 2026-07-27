# Bobodan 文档

文档已经收敛，日常只读一个主入口：

| 文档 | 用途 |
|---|---|
| [`../README.md`](../README.md) | 用户入口：当前能力、快速开始、运行方式和验证命令 |
| [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | 项目主指南：产品定位、当前阶段、下一步、功能分层、架构边界 |
| [`DESIGN.md`](DESIGN.md) | Web / TUI / 官网视觉硬约束，界面设计开工前必须先读 |
| [`rag_design.md`](rag_design.md) | RAG v2 详细设计 |
| [`MCP.md`](MCP.md) | MCP 客户端使用说明 |
| [`tools/skills.md`](tools/skills.md) | Skills 系统说明 |
| [`project_review_2026-07-26.md`](project_review_2026-07-26.md) | 2026-07-26 项目审查、问题证据与整改追踪 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 版本与未发布变更记录 |

使用规则：

- 想知道项目是什么、现在到哪、下一步做什么：看 `PROJECT_GUIDE.md`。
- 想做 Web UI、页面、组件、原型或任何视觉设计：先看 `PROJECT_GUIDE.md`，再必须看 `DESIGN.md`。
- 想改 RAG：看 `rag_design.md`。
- 想配置 MCP：看 `MCP.md`。
- 想改 skills：看 `tools/skills.md`。
- 想核对本轮审查发现了什么、哪些已经整改：看 `project_review_2026-07-26.md`。
- 想快速启动项目：看根目录 `README.md`；想看版本变化：看根目录 `CHANGELOG.md`。

旧的产品计划、架构计划、阶段计划和历史调研已从当前文档集中移除，避免 AI 和人读到过时方向。
