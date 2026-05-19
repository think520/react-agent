# 波波蛋 (Bobodan)

Python ReAct Agent，支持多 LLM Provider、工具调用、Session 持久化、Skills 注入、持久化记忆系统、本地知识库（RAG + 知识图谱）、题库系统（生成/练习/批改/错题分析）、学习路线与复习计划、CLI REPL 交互。

## 运行

```bash
# 1. 激活虚拟环境
# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

# 2. 配置 API key
cp .env.example .env
# 编辑 .env，填入 API key（如 MINIMAX_API_KEY=xxx）

# 3. 启动
python agent.py

# 指定 session 恢复上下文
python agent.py --session-id my-session
```

## 项目结构

```
agent.py            # CLI 入口
config.yaml         # Provider / Agent / Session / Skills / Memory 配置
.env.example        # API key 模板
core/
  session.py        # Session 持久化 + 消息裁剪
  agent_loop.py     # ReAct 推理循环（支持 skills + memory 注入）
  skills.py         # Skills 加载与 prompt 格式化
  memory.py         # 持久化记忆系统（MemoryManager + MemoryEntry）
providers/
  types.py          # 统一内部类型（ToolCall、LLMResponse）
  base.py           # LLMProvider 协议
  openai_compat.py  # OpenAI 兼容 API 基类
  factory.py        # Provider 工厂
  deepseek.py       # Deepseek Provider
  minimax.py        # MiniMax Provider
tools/
  base.py           # 工具注册表 + ToolResult + workspace 安全边界
  file_ops.py       # read_file、write_file（带大小限制、二进制检测、覆盖保护）
  dir_ops.py        # list_dir、change_dir、stat_path
  http_req.py       # http_request（HTTP 请求工具）
  obsidian_tool.py  # obsidian_sync：同步 Obsidian/课程资料到知识库
  rag_search.py     # rag_search：本地 RAG 检索
  graph_query.py    # graph_query：知识图谱关系查询
  memory_tools.py   # memory_save、memory_recall：跨会话持久化记忆
  knowledge_status.py # knowledge_status：知识库状态查询
  quiz_tools.py     # question_generate、quiz_start、quiz_submit：题库工具
knowledge/          # 知识库管理
  documents.py      # DocumentRecord：按文件追踪导入状态
  manifest.py       # .knowledge/manifest.json 读写
  import_report.py  # ImportReport：同步后导入报告
  library.py        # LibrarySummary：课程、chunk、图谱聚合统计
quiz/               # 题库系统（SQLite-backed）
  schema.py         # Question、QuizSession、QuizAttempt 数据模型
  store.py          # QuizStore：SQLite CRUD
  generator.py      # QuestionGenerator：基于 RAG 的 LLM 出题
  evaluator.py      # QuizEvaluator：自动批改（选择/判断）+ LLM 批改（简答）
  review.py         # QuizReviewer：错题本和薄弱点分析
learning/           # 学习路线与进度追踪
  schema.py         # Mastery、LearningPlan 数据模型
  store.py          # LearningStore：SQLite（mastery、learning_plans 表）
  scheduler.py      # ReviewScheduler：简单间隔重复（1/3/7/14天）
  progress.py       # ProgressTracker：掌握度概览、自动推断
  path.py           # LearningPathGenerator：基于 LLM 的个性化学习计划
obsidian/           # Obsidian vault 扫描、frontmatter/双链/tag 解析
rag/                # 文档导入、文本切块、本地轻量向量索引、检索
graph/              # 知识图谱 schema、本地 JSON store、可选 Neo4j adapter
.bobodan/           # 记忆系统运行时数据（.gitignore 已排除）
  memory/           # 单独记忆文件（Markdown + YAML frontmatter）
  MEMORY.md         # 自动生成的记忆索引
  memory_index.json # 向量索引
.knowledge/         # 知识库运行时数据（.gitignore 已排除）
  rag_index.json    # RAG 向量索引
  graph_store.json  # 本地图谱
  sync_state.json   # 增量同步 hash
  manifest.json     # 知识库清单（文档记录）
  import_report.json # 最近一次导入报告
  bobodan.db        # 题库 SQLite 数据库
cli/
  repl.py           # REPL 交互界面（/kb、/quiz、/skill、/memory、/session、/status 等命令）
skills/             # Skills 定义目录
  course-learning/  # 课程学习助手 skill
  weather/          # 示例：天气查询 skill
tests/              # 单元测试
```

## REPL 命令

```
/help               # 显示帮助
/status             # 运行时状态
/cwd                # 当前工作目录
/tools              # 可用工具列表
/kb status          # 本地知识库状态（课程、chunk、错误、图谱统计）
/kb sync <vault>    # 同步 Obsidian vault
/kb search <query>  # 本地 RAG 检索
/kb graph <concept> # 知识图谱关系查询
/kb reset --yes     # 删除生成的知识库索引
/quiz generate <topic>  # 基于知识库生成练习题
/quiz start [count]     # 开始一轮练习
/quiz wrong         # 错题本
/quiz weak          # 薄弱点分析
/quiz stats         # 题库统计
/learning plan <目标>  # 生成学习计划
/learning progress    # 掌握度概览
/learning review      # 今日复习清单
/learning mark <概念> <状态> # 手动设置掌握度
/learning plans       # 列出已保存的学习计划
/memory list        # 列出所有记忆
/memory show <name> # 查看记忆详情
/memory search <q>  # 语义搜索记忆
/memory forget <n>  # 删除记忆
/memory stats       # 记忆统计
/skill list         # 列出所有 skill
/skill <name>       # 查看 skill 内容
/skill run <name>   # 执行 skill
/ui tools on|off    # 切换工具调用显示
/session list       # 列出已保存的 session（名称、ID、时间）
/session save [name] # 保存当前 session（可选命名）
/session resume     # 交互式选择 session 恢复
/session load <id>  # 按 ID、前缀或名称加载 session
/exit, /quit        # 退出
```

安装 `prompt_toolkit` 后，输入 `/` 会实时显示可用命令候选；如果当前终端不支持实时提示，输入 `/` 回车会显示精简命令面板。

启动页和知识库命令使用 Rich 渲染：启动信息会显示为不会错位的面板；`/kb status`、`/kb search` 会使用 Rich 面板和表格展示。Agent 流式回复使用打字机效果逐字符输出，支持标题、代码块、表格、列表、引用等内联 Markdown 渲染；thinking 动画使用旋转 braille 字符（`⠋ thinking`），文字到来时无缝消失。

## 课程学习助手 MVP

这个功能把学习资料分成两层能力：

- **RAG 检索**：回答“是什么、在哪里出现过、原文怎么说”，来源写入 `.knowledge/rag_index.json`。
- **知识图谱**：回答“和谁有关、属于哪门课/章节、被哪些标签标记”，来源写入 `.knowledge/graph_store.json`。

本地运行数据统一放在 `.knowledge/`，该目录已加入 `.gitignore`，可以删除后重新同步。Neo4j 是可选能力：设置 `NEO4J_URI`、`NEO4J_USERNAME`、`NEO4J_PASSWORD` 后会优先尝试 Neo4j；没有配置或连接失败时自动使用本地 JSON 图谱。

### 快速演示

在项目目录下准备一个 Obsidian 风格的 vault：

```powershell
mkdir demo_vault
notepad demo_vault\Dijkstra.md
```

示例笔记：

```markdown
---
course: 数据结构
chapter: 图
aliases: [单源最短路]
tags: [algorithm]
---

# Dijkstra 算法

Dijkstra 用于求解非负权图中的单源最短路径。

相关知识：[[图]]、[[贪心算法]]、[[优先队列]]
```

启动 Agent 后先用 `/kb` 命令同步和检查，不需要消耗模型调用：

```text
/kb sync demo_vault
/kb status
/kb search Dijkstra 算法
/kb graph Dijkstra 算法
```

也可以继续用自然语言提问，让 Agent 自己选择 `rag_search` 或 `graph_query`：

```text
Dijkstra 算法是什么？
Dijkstra 算法和哪些知识点有关？
```

对应工具：

| 工具 | 用途 |
|------|------|
| `obsidian_sync` | 扫描 Obsidian vault，可选同步课程资料目录，生成 `.knowledge/` 数据 |
| `rag_search` | 检索课程资料和 Obsidian 笔记，返回片段、来源、分数、metadata |
| `graph_query` | 查询概念相关关系、tag、出现位置、课程/章节 |

常用 `/kb` 命令：

| 命令 | 用途 |
|------|------|
| `/kb sync <vault> [course_dir] [--full]` | 同步 Obsidian vault 和可选课程资料目录 |
| `/kb status` | 查看文件数、chunk 数、节点数、关系数 |
| `/kb search <query> [--course name] [--top-k n]` | 直接检索本地 RAG 索引 |
| `/kb graph <concept> [--intent related] [--limit n]` | 直接查询知识图谱 |
| `/kb reset --yes` | 删除生成的 `.knowledge/` 索引 |

更多细节见 `docs/RAG_KNOWLEDGE_GRAPH_MVP.md`。

## 题库系统

题库系统实现"生成题目 → 做题 → 批改 → 错题记录 → 薄弱点分析"的学习闭环。

### 功能

- **题目生成**：基于本地知识库 RAG 检索相关内容，LLM 生成题目（单选、判断、简答）
- **交互练习**：`/quiz start` 或 Agent 对话中 `quiz_start`，一题一题作答
- **自动批改**：选择题和判断题自动批改，简答题 LLM 批改
- **错题本**：记录每次错误，按知识点聚合薄弱环节
- **来源绑定**：每道题关联知识库来源，可追溯

### 数据存储

题库数据存储在 `.knowledge/bobodan.db`（SQLite），包含三张表：
- `questions` — 题目（类型、选项、答案、解析、知识点、难度、来源）
- `quiz_sessions` — 练习 session（题目列表、时间）
- `quiz_attempts` — 做题记录（用户答案、是否正确、反馈）

### Agent 工具

| 工具 | 用途 |
|------|------|
| `question_generate` | 基于主题从知识库生成题目 |
| `quiz_start` | 创建练习 session，返回题目（不含答案） |
| `quiz_submit` | 提交答案，返回批改结果和反馈 |

### REPL 命令

| 命令 | 用途 |
|------|------|
| `/quiz generate <topic>` | 生成题目 |
| `/quiz start [count]` | 开始练习 |
| `/quiz wrong` | 查看错题本 |
| `/quiz weak` | 薄弱点分析 |
| `/quiz stats` | 题库统计 |

## 学习路线

学习路线系统把知识库、题库和掌握度串联成完整学习闭环。

### 功能

- **学习计划生成**：根据学习目标、截止日期、课程资料和做题记录，生成个性化每日学习计划
- **掌握度追踪**：自动从做题记录推断知识点掌握度（连续正确 2 次 → 已掌握），也支持手动覆盖
- **间隔复习**：简单间隔重复算法（1/3/7/14天），到期自动提醒复习
- **Obsidian 写回**（计划中）：学习计划可导出为 Obsidian Markdown

### 数据优先级

学习路线的数据来源按优先级排列：
1. 做题记录（反映真实掌握度）
2. 用户目标（想学什么）
3. 图谱关系（前置知识）
4. 课程资料结构（章节顺序）

### Agent 工具

| 工具 | 用途 |
|------|------|
| `learning_path` | 生成个性化学习计划 |
| `learning_progress` | 查询掌握度概览或单个知识点详情 |
| `learning_review` | 获取今日复习清单 |

### REPL 命令

| 命令 | 用途 |
|------|------|
| `/learning plan <目标>` | 生成学习计划 |
| `/learning progress` | 掌握度概览 |
| `/learning review` | 今日复习清单 |
| `/learning mark <概念> <状态>` | 手动设置掌握度 |
| `/learning plans` | 列出已保存的计划 |

### 数据存储

学习数据存储在 `.knowledge/bobodan.db`（SQLite），新增两张表：
- `mastery` — 知识点掌握度（概念、状态、分数、复习次数、连续正确、下次复习时间）
- `learning_plans` — 学习计划（标题、目标、步骤 JSON、课程、截止日期）

## Skills

Agent 启动时自动加载 `skills/` 目录下的 skill。模型根据用户输入自主判断是否需要某个 skill，通过 `read_file` 读取完整 SKILL.md 内容并遵循指令。

创建新 skill：在 `skills/` 下新建子目录，放入 `SKILL.md`（YAML frontmatter + Markdown 指令）。详见 `docs/tools/skills.md`。

## 记忆系统

Agent 支持跨会话持久化记忆。记忆以单独 Markdown 文件存储在 `.bobodan/memory/`，自动维护 `MEMORY.md` 索引和向量索引。启动时记忆内容注入 system prompt，让 Agent 在新会话中也能记住用户偏好和上下文。

四种记忆类型：`user`（用户画像）、`feedback`（纠正/确认）、`project`（项目上下文）、`reference`（外部资源指针）。

Agent 工具：
- `memory_save` — 保存记忆（name, description, content, type）
- `memory_recall` — 语义搜索记忆

REPL 命令：
- `/memory list` — 列出所有记忆
- `/memory show <name>` — 查看详情
- `/memory search <query>` — 语义搜索
- `/memory forget <name>` — 删除
- `/memory stats` — 统计信息

配置（`config.yaml`）：
```yaml
memory:
  enabled: true
  dir: ".bobodan"
```

## Provider

支持三种 Provider 类型（在 `config.yaml` 中切换）：

| 类型 | 类 | 说明 |
|------|------|------|
| `minimax` | `MiniMaxProvider` | 原始 httpx，refusal 检测 |
| `deepseek` | `DeepseekProvider` | 继承 `OpenAICompatibleProvider` |
| `openai` | `OpenAICompatibleProvider` | OpenAI 兼容 API |

所有 provider 返回统一的 `LLMResponse(content, tool_calls)` 类型。

## 工具安全

- **Workspace 边界**：工具只能访问项目根目录内路径
- **拒绝列表**：`.env`、`.git`、`.session`、`__pycache__`、`.venv` 默认不可读写
- **`write_file`**：默认拒绝覆盖已有文件，需传 `overwrite=true`
- **`read_file`**：1 MB 大小限制 + 二进制文件检测
- **`change_dir`**：不能切出 workspace root

## 测试

```bash
pytest tests/ -v
```

当前测试数量以 `pytest tests/ -v` 的实际输出为准。
