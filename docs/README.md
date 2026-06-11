# Bobodan Docs Index

这个目录只保留当前日常需要读取的文档。已实现方案、历史设计和调研材料放在 `archive/`。

## 当前入口

| 文档 | 用途 |
|------|------|
| [`NEXT_STEPS_EXECUTION_PLAN.md`](NEXT_STEPS_EXECUTION_PLAN.md) | 当前下一步执行顺序。排期和开新分支前先看它 |
| [`DESIGN.md`](DESIGN.md) | Web UI / TUI / 官网的长期视觉设计参考（Natural Editorial Zen），后续 UI 相关工作默认先看它 |
| [`LOCAL_KNOWLEDGE_LEARNING_AGENT_PLAN.md`](LOCAL_KNOWLEDGE_LEARNING_AGENT_PLAN.md) | Bobodan 作为本地知识学习助手的产品主线 |
| [`BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md`](BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md) | 模块边界和架构规则 |
| [`OPENAI_AGENT_CODEX_REFERENCE_FOR_BOBODAN.md`](OPENAI_AGENT_CODEX_REFERENCE_FOR_BOBODAN.md) | OpenAI Agents SDK / Codex CLI 的工程边界借鉴：run state、event trace、tool policy、handoff，不作为产品方向替代 |
| [`RAG_KNOWLEDGE_GRAPH_MVP.md`](RAG_KNOWLEDGE_GRAPH_MVP.md) | RAG + 知识图谱当前用法 |
| [`MCP.md`](MCP.md) | MCP 用户文档 |

## 归档文档

| 文档 | 用途 |
|------|------|
| [`archive/agents_design.md`](archive/agents_design.md) | Learning Agent Orchestrator v1 详细设计 |
| [`archive/AGENT_HARNESS_IMPROVEMENT_PLAN.md`](archive/AGENT_HARNESS_IMPROVEMENT_PLAN.md) | Agent harness 历史详细计划 |
| [`archive/mcp_design.md`](archive/mcp_design.md) | MCP 客户端详细设计 |
| [`archive/OLLAMA_RAG_EMBEDDING_PLAN.md`](archive/OLLAMA_RAG_EMBEDDING_PLAN.md) | 已实现的 Ollama RAG embedding 方案 |

## 使用规则

- 想知道现在做什么：看 `NEXT_STEPS_EXECUTION_PLAN.md`。
- 想确认模块边界：看 `BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md`。
- 想参考 OpenAI Agents SDK / Codex CLI 的运行时边界：看 `OPENAI_AGENT_CODEX_REFERENCE_FOR_BOBODAN.md`。
- 想了解产品方向：看 `LOCAL_KNOWLEDGE_LEARNING_AGENT_PLAN.md`。
- 想参考 UI 设计：看 `DESIGN.md`。
- 想使用现有能力：看 `RAG_KNOWLEDGE_GRAPH_MVP.md` 或 `MCP.md`。
- 想查历史设计：看 `archive/`。
