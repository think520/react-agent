# 本地知识库学习助手 Agent 迭代计划

## 1. 结论

这个项目适合继续往“本地优先的个人学习助手 Agent”方向走，而不是继续和 OpenClaw、Claude Code 这类通用 Agent 正面对比。

通用 Agent 的核心价值是“替用户做事”，你的项目更应该聚焦在“把用户自己的资料变成可学习、可提问、可复习、可出题、可规划的个人知识系统”。这条路线更具体，也更容易形成差异化。

一句话定位：

> Bobodan 是一个本地优先的个人学习助手 Agent：它能导入用户的笔记和课程资料，构建个人知识库，并基于本地知识和联网信息生成问答、题库、学习路线和复习计划。

## 2. 市场调研带来的判断

两份调研文档共同指向几个趋势：

- AI Agent 正在从“聊天工具”变成“能调工具、能处理资料、能执行任务”的工作流系统。
- 知识库产品的核心痛点不是能不能问答，而是资料导入麻烦、上下文容易丢、答案缺少来源、难以形成长期学习闭环。
- 学习类产品如果只做“回答问题”，很容易变成普通 ChatGPT 包壳；必须做“练习、路径、诊断、复习”。
- 本地优先、隐私优先、个人知识资产沉淀，是大厂云端知识库不容易彻底满足的差异点。
- 大学生、计算机学习者、考证用户、Obsidian 用户是比较适合的早期人群。

因此项目不要追求“什么都能做”，而应该先打穿一个学习闭环：

```text
导入资料 -> 构建知识库 -> 提问答疑 -> 生成题库 -> 做题反馈 -> 诊断薄弱点 -> 生成学习路线 -> 复习巩固
```

## 3. 当前项目已有能力

当前项目已经不是空架子，核心底座基本具备：

- ReAct Agent 循环：`core/agent_loop.py`
- 多 Provider：MiniMax、DeepSeek、OpenAI-compatible
- 工具系统：文件、目录、HTTP、RAG、图谱、记忆
- 本地知识库：`.knowledge/`
- Obsidian 同步：`obsidian/`、`tools/obsidian_tool.py`
- RAG 检索：`rag/`、`tools/rag_search.py`
- 图谱查询：`graph/`、`tools/graph_query.py`
- 持久化记忆：`core/memory.py`、`tools/memory_tools.py`
- CLI 入口和 `/kb` 命令：`cli/repl.py`
- 课程学习 skill：`skills/course-learning/SKILL.md`

也就是说，当前项目已经完成了“能导入、能检索、能问答、能查关系”的 MVP。后续重点不应该是继续堆 Agent 基础能力，而是把学习场景做深。

## 4. 当前缺口

### 4.1 知识库构建还不够产品化

已有 `/kb sync`，但用户视角仍然偏工程化。后续需要让用户能自然地完成：

- 上传或指定 PDF、PPT、Word、Markdown、TXT、网页、Obsidian Vault
- 查看导入进度、失败文件、解析质量
- 对知识库进行增量更新
- 删除、重建、按课程管理知识库
- 查看每份资料被切成了多少 chunk，是否进入图谱

### 4.2 RAG 质量还需要升级

当前本地 RAG 是轻量检索，适合 MVP，但如果要真正当学习助手，需要更强的检索质量：

- 支持正式 embedding provider
- 支持向量库可替换，比如 Chroma、FAISS、LanceDB
- 支持 hybrid search：关键词 + 向量
- 支持 rerank
- 回答必须带来源引用
- 对“本地资料没有答案”的情况要明确提示，不要硬编

### 4.3 图谱关系还偏浅

当前图谱主要依赖 Obsidian 双链、tag、frontmatter。它稳定，但不够智能。

后续应该增加“候选关系抽取”：

- 概念
- 定义
- 前置知识
- 相似概念
- 易混概念
- 章节归属
- 题目关联知识点

注意：LLM 自动抽关系会污染图谱，所以必须设计“待确认关系”和“已确认关系”两层。

### 4.4 还没有题库闭环

你的想法里“根据本地知识库和网上知识创建题库”是关键功能，这会把项目从问答工具推进到学习产品。

题库系统至少需要：

- 题目生成
- 答案与解析
- 来源引用
- 难度
- 知识点标签
- 题型：选择、填空、简答、判断、代码题
- 做题记录
- 错题本
- 薄弱点统计

### 4.5 学习路线需要用户状态

学习路线不是简单列目录。它至少需要三类输入：

- 目标：我要学什么，考试还是项目还是补基础
- 资料：本地知识库里有什么
- 用户状态：哪些会，哪些不会，哪些错过

所以学习路线应该和题库、记忆、做题记录联动，而不是单独生成一段文本。

## 5. 产品边界建议

### 应该做

- 本地个人知识库
- 多格式资料导入
- Obsidian 深度融合
- 基于来源的问答
- 知识图谱关系查询
- 学习路线生成
- 题库生成和错题分析
- 联网补充资料，但必须和本地资料区分来源
- 记忆用户学习目标、水平、偏好

### 暂时不要做

- 多用户协作
- 云端同步
- 社区知识库市场
- 移动端 App
- 完整 Web 大平台
- 太复杂的自动知识抽取
- 过早商业化

原因很直接：这些功能都很大，会稀释主线。先把“个人本地学习闭环”做顺，比做一个半成品平台更重要。

## 6. 推荐架构

```text
用户输入层
  - CLI
  - 后续 Web UI
  - 文件上传 / 目录同步 / Obsidian Vault

资料处理层
  - Markdown / TXT / PDF / PPT / Word / 网页解析
  - 清洗、分块、元数据提取
  - 文件 hash 增量同步

知识层
  - RAG index
  - Knowledge graph
  - Question bank
  - Learning records
  - Memory

Agent 能力层
  - rag_search
  - graph_query
  - question_generate
  - quiz_session
  - learning_path
  - web_search
  - obsidian_sync

输出层
  - 答案 + 来源
  - 题库
  - 错题本
  - 学习路线
  - Obsidian Markdown 写回
```

## 7. 新增核心模块建议

### 7.1 `knowledge/`：统一知识库管理

当前 `.knowledge/` 是运行数据目录，但代码层还缺一个统一管理模块。建议新增：

```text
knowledge/
  library.py       # 知识库元数据、课程、资料集合
  documents.py     # 文档记录、导入状态、hash
  sources.py       # 来源类型：obsidian/pdf/ppt/web/manual
  manifest.py      # .knowledge/manifest.json 读写
```

目的：让知识库从“几个 JSON 文件”升级为“有状态、有边界、有管理能力的资料库”。

### 7.2 `quiz/`：题库系统

```text
quiz/
  schema.py        # Question, Answer, Explanation, Attempt
  generator.py     # 基于 RAG/图谱生成题目
  evaluator.py     # 批改答案
  store.py         # 本地题库和做题记录
  review.py        # 错题本和复习计划
```

题目数据建议包含：

```json
{
  "id": "q_001",
  "type": "single_choice",
  "question": "Dijkstra 算法适用于哪类图？",
  "options": ["负权图", "非负权图", "无向完全图", "有环图"],
  "answer": "非负权图",
  "explanation": "Dijkstra 要求边权非负。",
  "concepts": ["Dijkstra 算法", "最短路径", "非负权"],
  "difficulty": "basic",
  "sources": ["course/graph/Dijkstra.md#chunk-3"]
}
```

### 7.3 `learning/`：学习路线与诊断

```text
learning/
  path.py          # 学习路线生成
  diagnosis.py     # 薄弱点诊断
  progress.py      # 学习进度
  scheduler.py     # 复习计划
```

核心逻辑：

- 图谱提供前置关系
- RAG 提供资料依据
- 题库记录提供掌握度
- Memory 提供用户目标和偏好

### 7.4 `ingestion/`：多格式导入

当前 `rag/ingest.py` 可继续保留，但随着 PPT、Word、网页、OCR 加入，建议抽出独立导入层：

```text
ingestion/
  markdown.py
  pdf.py
  ppt.py
  docx.py
  web.py
  pipeline.py
```

第一阶段先支持：

- Markdown
- TXT
- PDF
- Obsidian

第二阶段再支持：

- PPT/PPTX
- DOCX
- 网页收藏
- 图片 OCR

## 8. Agent 工具规划

### 已有工具

- `obsidian_sync`
- `rag_search`
- `graph_query`
- `memory_save`
- `memory_recall`
- `http_request`

### 建议新增工具

#### `knowledge_import`

用途：导入文件、目录或 URL 到本地知识库。

```json
{
  "path": "courses/os",
  "type": "auto",
  "course": "操作系统"
}
```

#### `knowledge_status`

用途：查看知识库状态，比 `/kb status` 更适合 Agent 调用。

#### `question_generate`

用途：基于知识库生成题目。

```json
{
  "topic": "Dijkstra 算法",
  "count": 10,
  "types": ["single_choice", "short_answer"],
  "difficulty": "mixed",
  "use_web": false
}
```

#### `quiz_start`

用途：开启一轮练习。

#### `quiz_submit`

用途：提交答案并获得批改、解析和知识点反馈。

#### `learning_path`

用途：生成学习路线。

```json
{
  "goal": "学会操作系统期末考试重点",
  "level": "beginner",
  "deadline": "2026-06-20"
}
```

#### `weakness_analyze`

用途：根据错题和问答历史分析薄弱知识点。

#### `obsidian_writeback`

用途：把学习路线、错题、总结写回 Obsidian。

## 9. 关键用户流程

### 9.1 首次构建知识库

```text
用户：导入我的操作系统课程资料和 Obsidian 笔记
Agent：
1. 扫描资料
2. 识别文件类型
3. 解析文本
4. 建立 RAG 索引
5. 提取基础图谱关系
6. 输出导入报告
```

验收标准：

- 用户能看到导入了哪些文件
- 用户能看到失败文件和原因
- 用户能立刻问“这些资料主要讲什么”

### 9.2 基于本地知识库提问

```text
用户：进程和线程有什么区别？
Agent：
1. 先查本地 RAG
2. 再查图谱关系
3. 如果本地资料不足，明确说明
4. 可选联网补充
5. 输出答案、来源、相关知识点
```

验收标准：

- 答案必须带本地来源
- 本地没有资料时不能装作有
- 联网内容必须标记为“外部补充”

### 9.3 生成题库

```text
用户：根据操作系统进程管理生成 20 道题
Agent：
1. 检索相关资料
2. 提取知识点
3. 生成题目
4. 生成答案解析
5. 绑定来源和知识点
6. 保存到本地题库
```

验收标准：

- 每道题有答案、解析、来源
- 每道题绑定知识点
- 用户可以继续做题，而不是只得到一段文本

### 9.4 做题和错题诊断

```text
用户：开始练习昨天生成的题
Agent：
1. 一题一题展示
2. 用户作答
3. 自动批改
4. 记录错误原因
5. 更新掌握度
6. 生成错题本
```

验收标准：

- 能记录每次作答
- 能统计薄弱知识点
- 能重新生成针对性练习

### 9.5 生成学习路线

```text
用户：我想两周内复习完操作系统
Agent：
1. 读取课程资料结构
2. 查询知识图谱前置关系
3. 读取做题记录和记忆
4. 生成每日学习计划
5. 输出到 CLI 或写回 Obsidian
```

验收标准：

- 路线不是泛泛建议，而是引用用户已有资料
- 每一步能对应具体资料和题目
- 能根据错题动态调整

## 10. 分阶段路线图

### Phase 1：把知识库入口产品化 ✅ 已实现 (2026-05-19)

目标：让用户稳定导入资料，并清楚知道知识库里有什么。

任务：

- [x] 增强 `/kb status`：显示课程、文件数、chunk 数、图谱节点数、失败文件
- [x] 新增导入报告：`.knowledge/import_report.json`
- [x] 支持课程级管理：course、chapter、source_type（通过 `knowledge/documents.py`）
- [ ] 增强 PDF 解析错误提示
- [x] 为 Agent 增加 `knowledge_status` 工具

实现：`knowledge/` 模块（documents、manifest、import_report、library）、`tools/knowledge_status.py`、`obsidian/sync.py` 改造。

验收：

- 用户导入资料后，不需要看文件系统就知道导入结果
- 全量测试通过（216 tests）

### Phase 2：提高 RAG 可信度

目标：让问答从“能回答”升级为“可信回答”。

任务：

- 引入可插拔 embedding provider
- 增加 hybrid search
- 增加引用格式标准
- 回答区分“本地资料依据”和“外部联网补充”
- 增加“资料不足”判断

验收：

- 每个知识库回答都能追溯来源
- 本地资料不足时会明确说明

### Phase 3：题库系统 MVP ✅ 已实现 (2026-05-19)

目标：完成”生成题目 -> 做题 -> 批改 -> 错题记录”的闭环。

任务：

- [x] 新增 `quiz/` 模块（schema、store、generator、evaluator、review）
- [x] 新增 `question_generate` 工具
- [x] 新增 `quiz_start`、`quiz_submit` 工具
- [x] 题目保存到 `.knowledge/bobodan.db`（SQLite，替代原计划的 JSON）
- [x] 做题记录保存到 `.knowledge/bobodan.db`（同上）
- [x] 支持选择题、判断题、简答题

实现：`quiz/` 模块 5 个文件、`tools/quiz_tools.py`、`cli/repl.py` 新增 `/quiz` 命令。存储从 JSON 改为 SQLite（stdlib sqlite3，无新依赖）。

验收：

- 能基于指定课程或知识点生成题目
- 能进行一轮交互式练习
- 能输出错题和薄弱知识点

### Phase 4：学习路线和复习计划 ✅ 已实现 (2026-05-19)

目标：把知识库、图谱、题库和记忆串起来。

任务：

- [x] 新增 `learning/` 模块（schema、store、scheduler、progress、path）
- [x] 新增 `learning_path` 工具（基于 LLM 的个性化学习计划）
- [x] 新增 `learning_progress` 工具（掌握度概览，替代原计划的 weakness_analyze）
- [x] 新增 `learning_review` 工具（今日复习清单）
- [x] 根据做题记录自动更新知识点掌握度
- [x] 简单间隔重复（1/3/7/14天），遗忘曲线放后续计划
- [ ] 支持写回 Obsidian（待实现）

实现：`learning/` 模块 5 个文件、`tools/learning_tools.py`、`cli/repl.py` 新增 `/learning` 命令。SQLite 新增 `mastery` 和 `learning_plans` 表。

验收：

- [x] 能生成带资料引用的学习路线
- [x] 能基于错题调整路线
- [x] 能生成每日复习清单

### Phase 4.5：记忆系统升级 ✅ 已实现 (2026-05-20)

目标：给记忆系统加每日缓冲、FTS5 检索、晋升机制，让记忆有生命周期。

详细计划见 `docs/MEMORY_UPGRADE_PLAN.md`。

任务：

- [x] 新增 `memory/store.py`：SQLite 索引 + FTS5 虚拟表（chunks、recall_log、promotion_log）
- [x] 新增 `memory/daily.py`：每日记忆文件管理（append、read、list_recent、get_today、get_yesterday）
- [x] 新增 `memory/search.py`：FTS5 主检索 + 向量 fallback
- [x] 新增 `memory/promotion.py`：晋升评分（频率 0.4 + 做题 0.4 + 时间衰减 0.2），阈值 score ≥ 0.6 且 recalls ≥ 2
- [x] 改造 `core/memory.py`：save/forget 自动同步 FTS5，build_memory_prompt 注入今日+昨日每日记忆，search 改为 FTS5 优先
- [x] 新增 Agent 工具：`memory_daily_save`、`memory_daily_read`、`memory_promote`
- [x] 改造 `memory_recall` 工具：FTS5 搜索覆盖每日+永久
- [x] 新增 REPL 命令：`/memory daily`、`/memory promote`、`/memory review`
- [ ] 做题结束自动写每日记忆（待集成到 quiz_submit）

实现：`memory/` 模块 4 个文件、改造 `core/memory.py`、改造 `tools/memory_tools.py`、改造 `cli/repl.py`、`tests/test_memory_upgrade.py` 34 个测试。

验收：

- [x] FTS5 搜索覆盖每日和永久记忆
- [x] 晋升机制能筛选有价值的每日记忆升级为永久记忆
- [x] `/memory daily` 能写入和查看每日记忆
- [x] `/memory promote` 能检查并执行晋升
- [x] 全量测试通过（285 tests）

### Phase 5：体验层优化

目标：降低非技术用户门槛。

任务：

- 设计 Web UI 或轻量本地页面
- 支持拖拽上传
- 可视化知识图谱
- 可视化题库和错题
- 学习进度面板

验收：

- 用户不需要记住 CLI 命令也能完成核心流程

## 11. 数据存储建议

继续保持本地优先。建议 `.knowledge/` 逐步扩展为：

```text
.knowledge/
  manifest.json              # 知识库总状态
  import_report.json         # 最近一次导入报告
  rag_index.json             # RAG 索引
  graph_store.json           # 本地图谱
  sync_state.json            # 增量同步状态
  question_bank.json         # 题库
  quiz_attempts.json         # 做题记录
  mastery.json               # 知识点掌握度
  learning_plans/            # 学习路线
```

后续如果数据变大，可以从 JSON 迁移到 SQLite。不要一开始就引入太重的数据库，否则会提高使用门槛。

## 12. 需要注意的问题

### 12.1 不要让联网内容污染本地知识库

联网内容可以作为补充，但默认不应该直接写入个人知识库。除非用户明确确认：

```text
是否把这段联网资料保存到知识库？
```

原因：个人知识库的价值在于可信和可控。

### 12.2 自动生成题目必须绑定来源

没有来源的题目会变成幻觉风险。每道题都应该能追溯到：

- 哪个文件
- 哪个 chunk
- 哪些知识点
- 是否使用了联网补充

### 12.3 学习路线不能只靠 LLM 生成

LLM 可以组织语言，但路线依据应该来自：

- 课程章节
- 图谱前置关系
- 用户做题记录
- 用户目标和截止时间

否则路线会很像普通建议，缺少个人化。

### 12.4 图谱抽取要有人机确认

自动抽取“前置知识”“相似概念”“易混概念”时，必须保留置信度和来源。建议分成：

- `candidate_relationships`
- `confirmed_relationships`

先让系统建议，再让用户确认。

## 13. 最近三次迭代建议

### 迭代 1：知识库状态和导入报告

优先级最高，因为它解决“用户不知道系统到底导入了什么”的问题。

交付：

- `.knowledge/manifest.json`
- `.knowledge/import_report.json`
- `/kb status` 增强
- `knowledge_status` 工具

### 迭代 2：题库 MVP

这是学习助手的核心差异点。

交付：

- `quiz/schema.py`
- `quiz/store.py`
- `quiz/generator.py`
- `tools/question_generate.py`
- `.knowledge/question_bank.json`

### 迭代 3：做题记录和薄弱点分析

让题库从“生成内容”变成“学习闭环”。

交付：

- `quiz/evaluator.py`
- `quiz/review.py`
- `tools/quiz_submit.py`
- `.knowledge/quiz_attempts.json`
- `.knowledge/mastery.json`

## 14. 最小可展示 Demo

建议下一版 Demo 做成这样：

```text
1. 用户导入一门课程资料和 Obsidian 笔记
2. 系统显示知识库状态
3. 用户问一个知识点
4. Agent 基于本地资料回答并给来源
5. 用户要求生成 10 道题
6. Agent 生成题库并保存
7. 用户开始练习
8. Agent 批改并指出薄弱知识点
9. Agent 生成下一步学习路线
```

这个 Demo 比“我有很多工具”更有说服力，因为它展示的是完整学习闭环。

## 15. 最终判断

你的方向是成立的，但需要收敛：

- 不要做通用 OpenClaw 替代品。
- 不要只做 RAG 问答。
- 不要太早做大而全的 Web 平台。
- 要做“个人本地知识库 + 学习闭环”。

真正有价值的差异点是：

```text
我的资料 -> 我的知识库 -> 我的题库 -> 我的错题 -> 我的学习路线
```

这条线跑通后，Bobodan 就不是一个普通 Agent，而是一个能陪用户长期学习的个人知识系统。

## 16. 全栈技术栈建议

如果这个项目要从 CLI Agent 进化成全栈产品，建议不要推翻现有 Python Agent 后端，而是在现有能力外面包一层 Web API 和前端体验。

推荐路线：

```text
Python Agent Core
        |
        v
FastAPI API Server
        |
        +--> Next.js / React Web UI
        +--> Local file upload
        +--> Streaming chat
        +--> Knowledge dashboard
        +--> Quiz and learning plan UI
```

### 16.1 推荐主技术栈

| 层级 | 推荐技术 | 选择原因 |
|------|----------|----------|
| 后端 API | FastAPI | 和当前 Python 项目兼容，适合文件上传、后台任务、WebSocket/SSE 流式输出 |
| Agent 核心 | 保留现有 `core/`、`tools/`、`rag/`、`graph/` | 已经有 ReAct、Provider、RAG、图谱、记忆能力，不需要重写 |
| 前端 | Next.js + React + TypeScript | 适合做长期产品，支持 App Router、组件化、文件上传、仪表盘和流式 UI |
| UI 组件 | shadcn/ui + Tailwind CSS | 上手快，适合做清爽的学习工具界面 |
| 流式对话 | Server-Sent Events 或 WebSocket | Agent 回复、工具调用、导入进度都需要实时反馈 |
| 本地数据库 | SQLite | 本地优先、零部署、适合保存课程、文件、题库、做题记录、学习计划 |
| ORM | SQLModel 或 SQLAlchemy | Python 生态成熟，后续从 JSON 迁移到 SQLite 更稳 |
| 向量库 | LanceDB 或 Chroma | 都适合本地向量检索；LanceDB 更偏嵌入式数据表，Chroma 更偏 RAG 原型 |
| 图数据库 | Neo4j 可选 + local JSON fallback | Neo4j 适合复杂图谱查询，但本地 JSON fallback 继续保留，降低安装门槛 |
| 文档解析 | pypdf、python-docx、python-pptx、markitdown 可选 | 支持 PDF、Word、PPT、Markdown 等资料导入 |
| 后台任务 | FastAPI BackgroundTasks 起步，后续 Celery/RQ | 导入、解析、embedding、题库生成都不应阻塞请求 |
| 桌面封装 | Tauri 可选 | 如果未来要做桌面应用，Tauri 比 Electron 更轻，适合本地优先产品 |

### 16.2 为什么不是直接做大而全前端

当前项目的核心资产在 Python 后端：Agent、工具、RAG、图谱、记忆、Provider 抽象都已经存在。全栈化的第一步应该是“把已有能力服务化”，而不是重写成一个新 Web 项目。

正确顺序：

```text
1. FastAPI 包装现有 Agent 能力
2. 暴露知识库、题库、学习路线 API
3. Next.js 做 Web UI
4. 再考虑桌面端或移动端
```

### 16.3 后端 API 设计建议

建议新增：

```text
server/
  main.py              # FastAPI app
  deps.py              # 配置、路径、session 依赖
  routes/
    chat.py            # Agent 对话和流式输出
    knowledge.py       # 知识库导入、状态、搜索
    graph.py           # 图谱查询
    quiz.py            # 题库生成、做题、批改
    learning.py        # 学习路线、薄弱点分析
    files.py           # 文件上传和资料管理
  schemas/
    chat.py
    knowledge.py
    quiz.py
    learning.py
```

优先 API：

| API | 用途 |
|-----|------|
| `POST /api/chat/stream` | 流式 Agent 对话 |
| `POST /api/knowledge/import` | 导入文件、目录或 Obsidian vault |
| `GET /api/knowledge/status` | 查看知识库状态 |
| `POST /api/knowledge/search` | 本地 RAG 检索 |
| `POST /api/graph/query` | 知识图谱查询 |
| `POST /api/quiz/generate` | 生成题库 |
| `POST /api/quiz/submit` | 提交答案并批改 |
| `GET /api/quiz/review` | 获取错题和薄弱点 |
| `POST /api/learning/path` | 生成学习路线 |

### 16.4 前端页面规划

建议前端先做 5 个页面，不要一开始做复杂平台。

```text
web/
  app/
    chat/              # 对话页
    knowledge/         # 知识库管理
    quiz/              # 题库和练习
    graph/             # 知识图谱视图
    learning/          # 学习路线和复习计划
```

页面优先级：

1. `chat`：左侧资料/工具状态，右侧流式对话。
2. `knowledge`：上传资料、同步 Obsidian、查看导入报告。
3. `quiz`：生成题目、开始练习、查看错题。
4. `learning`：生成学习路线、每日任务、掌握度。
5. `graph`：查看概念关系，先做简单列表，后续再可视化。

### 16.5 本地数据存储升级路线

当前 `.knowledge/*.json` 适合 MVP，但全栈项目会遇到并发读写、分页、筛选、状态管理问题。建议逐步迁移到 SQLite。

第一阶段继续保留 JSON：

```text
.knowledge/rag_index.json
.knowledge/graph_store.json
.knowledge/question_bank.json
.knowledge/quiz_attempts.json
```

第二阶段新增 SQLite：

```text
.knowledge/bobodan.db
```

表建议：

- `documents`
- `chunks`
- `concepts`
- `relationships`
- `questions`
- `quiz_attempts`
- `mastery`
- `learning_plans`
- `import_jobs`

RAG 向量数据可以先继续放 LanceDB/Chroma，业务状态放 SQLite。

### 16.6 向量库选择建议

建议优先考虑两条路线：

#### 路线 A：LanceDB

适合目标：

- 本地优先
- 嵌入式
- 文件型存储
- 后续可能做更正式的数据表和向量检索

#### 路线 B：Chroma

适合目标：

- 快速 RAG 原型
- Python 文档多
- 学习成本低
- 社区示例多

我的建议：如果你想快速做出 Web 版学习助手，先用 Chroma；如果你想长期做成本地知识库产品，优先研究 LanceDB。

### 16.7 文件上传和解析建议

第一批支持：

- `.md`
- `.txt`
- `.pdf`
- Obsidian vault 目录

第二批支持：

- `.docx`
- `.pptx`
- 网页 URL

第三批支持：

- 图片 OCR
- 扫描版 PDF OCR
- B 站/YouTube 字幕导入

不要一开始就做 OCR。OCR 会引入大量额外依赖、准确率问题和性能问题，应该等文本资料闭环稳定后再加。

### 16.8 联网能力设计

联网搜索应该作为“外部补充”，不是默认知识库来源。

建议策略：

```text
默认回答：只用本地知识库
用户允许联网：搜索外部资料并标记来源
用户确认保存：再写入本地知识库
```

这样可以避免外部低质量内容污染个人知识库。

### 16.9 推荐开发顺序

#### Step 1：FastAPI 服务化

- 新增 `server/`
- 包装现有 `/kb status`、`rag_search`、`graph_query`
- 实现 `POST /api/chat/stream`
- 实现 `POST /api/files/upload`

#### Step 2：Next.js 最小 Web UI

- 对话页
- 知识库状态页
- 文件上传页
- 流式输出

#### Step 3：题库 API 和页面

- `quiz/` 模块
- 题库生成 API
- 题目列表
- 做题和批改

#### Step 4：学习路线 API 和页面

- `learning/` 模块
- 薄弱点分析
- 学习路线生成
- Obsidian 写回

#### Step 5：桌面化可选

- 用 Tauri 包装前端
- 后端仍然运行本地 Python 服务
- 适合非技术用户一键启动

### 16.10 不推荐的技术选择

| 技术/路线 | 暂不推荐原因 |
|----------|--------------|
| 一开始上 Kubernetes / Docker Compose 大编排 | 项目还在个人本地阶段，复杂度过高 |
| 一开始做 Electron | 桌面体积大；Tauri 更适合轻量本地工具 |
| 一开始做移动端 App | 文件管理、知识库构建、调试都不方便 |
| 一开始把数据放云端 | 会削弱“本地个人知识库”的差异化 |
| 一开始做多用户权限系统 | 会拖慢核心学习闭环 |
| 一开始做复杂知识图谱可视化 | 图谱数据质量还没稳定，先做列表和路径更实用 |

### 16.11 参考资料

- FastAPI 官方文档：`UploadFile`、后台任务、WebSocket 适合本项目的上传、导入和流式交互场景。https://fastapi.tiangolo.com/
- Next.js 官方文档：App Router 适合构建长期维护的 React 全栈前端。https://nextjs.org/docs
- Vercel AI SDK 文档：适合参考流式聊天 UI 和 LLM 前端交互模式。https://ai-sdk.dev/docs
- Chroma 官方文档：适合快速构建本地 RAG 原型。https://docs.trychroma.com/
- LanceDB 官方文档：适合本地嵌入式向量数据库方向。https://lancedb.github.io/lancedb/
- Neo4j GraphRAG 文档：适合后续增强图谱检索和 GraphRAG。https://neo4j.com/docs/neo4j-graphrag-python/current/
- Tauri 官方文档：适合后续把 Web UI 封装成本地桌面应用。https://tauri.app/
