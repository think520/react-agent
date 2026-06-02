# Bobodan 本地知识学习助手迭代计划

## 1. 一句话定位

Bobodan 不是通用 coding agent，也不是简单的聊天壳。

它的核心方向是：

> 一个 local-first 的个人学习 Agent：把用户的 Obsidian 笔记、课程资料、PDF、实验文档和学习记录，整理成可检索、可复习、可出题、可规划学习路径的个人知识系统。

后续所有功能都应该服务这个主线：

```text
导入资料 -> 构建知识库 -> 整理 wiki -> 提问答疑 -> 生成题库 -> 做题反馈 -> 诊断薄弱点 -> 生成学习路径 -> 复习巩固
```

## 2. 当前判断

当前项目已经不是空架子。Bobodan 已有：

- ReAct Agent 主循环
- 多 Provider 支持
- 工具系统
- Skills 系统
- 本地知识库
- RAG 检索
- 知识图谱
- Obsidian 同步
- 持久记忆
- 每日记忆与晋升机制
- 题库系统
- 学习路径系统
- CLI REPL

真正的问题不是“还缺一个大功能”，而是：

- 架构边界还需要稳定
- 文档和路线需要收敛
- RAG 检索质量需要升级
- workflow 还没有统一抽象
- CLI 和 runtime 还没有彻底解耦
- 后续全栈化需要提前留边界

## 3. 当前 active 文档

当前只保留 4 份 active docs：

| 文档 | 用途 |
|------|------|
| `LOCAL_KNOWLEDGE_LEARNING_AGENT_PLAN.md` | 主迭代计划 |
| `BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md` | 架构边界规范 |
| `RAG_KNOWLEDGE_GRAPH_MVP.md` | 当前 RAG + 图谱使用说明 |
| `OLLAMA_RAG_EMBEDDING_PLAN.md` | Ollama embedding 接入方案 |

其他历史调研、review、早期设计已移动到 `docs/archive/`。

## 4. 产品边界

### 应该做

- 本地个人知识库
- Obsidian 深度融合
- 课程资料导入
- RAG 检索
- 知识图谱关系查询
- LLM wiki 编译层
- 题库生成与练习
- 错题和薄弱点分析
- 学习路径和复习计划
- 本地模型 embedding
- 未来 Web UI / 桌面化

### 暂时不要做

- 多用户 SaaS
- 云端同步
- 插件市场
- 移动端 App
- 复杂图谱可视化
- 大规模 OCR
- 过早商业化
- 完整多 Agent 平台

原因：

这些方向会稀释主线。当前最重要的是把“个人本地学习闭环”做稳。

## 5. 架构边界

详细边界以 `BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md` 为准。这里给出主视图：

```text
UI Layer
  CLI / future Web UI

Agent Runtime Layer
  core / providers / session / event stream

Tool & Extension Layer
  tools / skills / future plugins

Workflow Layer
  kb sync / wiki ingest / quiz generate / learning plan

Knowledge Layer
  rag / graph / wiki / knowledge

Learning Layer
  quiz / learning / review / mastery

Memory Layer
  memory / daily memory / permanent memory / FTS5

Storage Layer
  .knowledge / .bobodan / .session / Obsidian vault
```

核心规则：

- `core/` 只管 Agent runtime
- `providers/` 只管模型调用
- `tools/` 只做 Agent 能力入口
- `rag/` 管 embedding、vector store、检索
- `knowledge/` 管知识库状态
- `wiki/` 管 LLM 编译层
- `quiz/` 管题库和答题
- `learning/` 管学习路径和复习
- `memory/` 管用户长期上下文
- `cli/` 只做交互，不承载业务核心

## 6. 近期主线

当前最重要的不是继续加散功能，而是先把底座梳理稳。

近期主线按优先级排序：

1. RAG 后端抽象
2. Ollama embedding 接入
3. wiki 编译层稳定
4. workflow runtime 抽象
5. event stream 统一
6. Web UI 最小闭环

## 7. P1：RAG 后端抽象与 Ollama embedding

目标：

让 Bobodan 支持本地 Ollama embedding，同时不破坏现有本地检索。

设计原则：

- 现有 sparse RAG 保留
- 新增 dense RAG
- 两套索引分开
- auto 模式优先 Ollama
- Ollama 不可用自动回退 local

推荐模块：

```text
rag/ollama.py        # OllamaEmbeddingClient
rag/dense_store.py   # DenseVectorStore
rag/router.py        # VectorStoreRouter
```

配置：

```yaml
rag:
  embedding_backend: auto
  ollama_url: "http://localhost:11434"
  ollama_model: "qwen3-embedding:0.6b"
  probe_timeout: 3
```

验收标准：

- Ollama 启动时，RAG 使用 dense embedding
- Ollama 停止时，RAG 回退 sparse 检索
- `/kb status` 显示当前 embedding backend
- `/kb sync` 不破坏原有索引
- 测试覆盖 available / unavailable / fallback

## 8. P2：Wiki 编译层

目标：

让 LLM 主动整理笔记资料，生成结构化知识页，而不是只做被动检索。

定位：

```text
原始资料 = truth source
wiki 页面 = 编译层
.knowledge = 运行时索引层
```

规则：

- wiki 不复制源文件全文
- wiki 只生成 entities / concepts
- `source_registry.json` 只记录来源元数据
- `/kb sync` 可以索引 wiki 页面
- `wiki ingest` 默认跳过 `wiki/`，避免循环生成

建议模块：

```text
wiki/schema.py
wiki/compiler.py
wiki/index.py
wiki/lint.py
tools/wiki_tools.py
```

验收标准：

- 能把源文件编译成 entity / concept 页面
- 页面带 frontmatter、source_paths、source_hash
- 不产生重复源头数据
- `/wiki lint` 能检测断链、孤儿页、过期页
- `/kb search` 可以检索 wiki 页面

## 9. P3：Workflow Runtime

目标：

把复杂流程从“大函数”和“CLI 命令”里拆出来，形成可恢复、可观测的 workflow。

优先 workflow：

- `/kb sync`
- `/wiki ingest`
- `/quiz generate`
- `/learning plan`

每个 workflow 应包含：

- input schema
- state
- steps
- progress event
- error report
- checkpoint
- final result

建议目录：

```text
workflow/
  kb_sync.py
  wiki_ingest.py
  quiz_generate.py
  learning_plan.py
```

验收标准：

- CLI 只触发 workflow，不写流程细节
- workflow 可输出进度事件
- 出错时能给出明确阶段和原因
- 后续 Web UI 可以复用同一套 workflow

## 10. P4：学习闭环强化

目标：

让题库、错题、掌握度、学习路径和记忆形成闭环。

当前应强化：

- 题目必须绑定知识点和来源
- 做题结果写入掌握度
- 错题进入复习计划
- 学习路径参考薄弱点
- 每日学习活动写入 daily memory
- 高价值记忆晋升为 permanent memory

数据流：

```text
RAG/wiki -> question_generate -> quiz_start -> quiz_submit
    -> mastery update -> weakness analysis -> learning_review
    -> daily memory -> promotion
```

验收标准：

- 用户做题后能看到薄弱知识点
- 学习路径能根据错题调整
- 复习列表不是静态文本，而是来自真实学习记录

## 11. P5：Event Stream 与 Trace

目标：

CLI 和未来 Web UI 都消费统一运行事件。

事件建议：

```text
run_start
thinking_start
thinking_delta
tool_start
tool_end
workflow_start
workflow_step
workflow_end
assistant_delta
run_end
error
```

验收标准：

- CLI 不直接依赖内部实现细节
- Web UI 可以复用同一套事件
- `/status` 能显示最近 workflow、工具调用和 fallback 状态

## 12. P6：最小 Web UI

目标：

把 Bobodan 从 CLI 项目推进到本地全栈学习助手。

推荐技术栈：

- FastAPI：本地服务层
- Next.js：前端 UI
- SQLite：本地结构化数据
- 本地 JSON / SQLite vector index：当前阶段继续保留
- Ollama：本地 embedding
- Tauri：后续桌面化

第一版页面：

- 对话页
- 知识库状态页
- 文件导入页
- wiki 页面列表
- 题库练习页
- 学习路径页

不要一开始做复杂后台管理系统。

## 13. 可吸收的外部框架设计

Bobodan 可以学习这些框架，但不应该迁移到它们：

| 框架/项目 | 吸收点 |
|----------|--------|
| Pydantic AI | 类型安全工具、依赖注入、eval |
| LangGraph | workflow、状态机、可恢复流程 |
| Agno | Agent 平台化、session、trace、storage |
| Mastra | 全栈产品化、Studio、workflow UI |
| OpenAI Agents SDK | handoff、guardrails、run state、event stream |
| Pi | CLI/TUI、extension、skills、packages |
| Goose | MCP、本地工具扩展 |
| Cline | 人类确认式工具调用 |
| LlamaIndex / Haystack | ingestion 和 retrieval pipeline |

吸收顺序：

```text
类型安全工具层
-> RAG backend 抽象
-> Workflow Runtime
-> Event Stream
-> Trace / Status 面板
-> 本地插件协议
-> Web UI / Studio
```

## 14. 不变的底线

后续任何改动必须遵守：

- 不破坏原有 CLI
- 不破坏原有 RAG
- 不破坏已有记忆系统
- 不把生成内容当作唯一事实来源
- 不把用户原始笔记复制成多份
- 不让 Ollama 失败影响主流程
- 不让 CLI 承载业务核心
- 不为了框架化牺牲学习主线

## 15. 当前建议执行顺序

最现实的下一步：

```text
1. 完成 OllamaEmbeddingClient
2. 完成 DenseVectorStore
3. 完成 VectorStoreRouter
4. config.yaml 增加 rag section
5. /kb status 显示 embedding backend
6. 补测试
7. 再推进 wiki ingest
8. 再抽 workflow runtime
```

原因：

RAG 是知识库、题库、学习路径、wiki 的底座。先把检索质量和 fallback 机制做好，后面的学习功能才不会虚。

## 16. 最终判断

Bobodan 后续不要做成“什么都能做的通用 Agent”。

它应该成为：

> 一个围绕本地知识库、个人学习、Obsidian、RAG、wiki、题库、学习路径构建的 lightweight learning agent framework。

框架化是为了支撑学习主线，不是为了追逐通用 Agent 形态。

