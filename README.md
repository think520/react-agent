# 波波蛋 (Bobodan)

Python ReAct Agent，支持多 LLM Provider、工具调用、Session 持久化、Skills 注入、持久化记忆、本地知识库（RAG + 知识图谱）、题库系统、学习路线与复习、MCP 客户端、多 agent 编排、CLI REPL 交互。

## 快速开始

```powershell
# 1. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 2. 安装依赖
python -m pip install -r requirements.txt

# 3. 复制并填写环境变量
Copy-Item .env.example .env
notepad .env

# 4. 启动
python agent.py
python agent.py --session-id my-session  # 恢复 session
python agent.py -v                       # 调试模式
```

Linux / macOS 激活虚拟环境使用：

```bash
source .venv/bin/activate
```

## 配置说明

Bobodan 的配置分两层：

- `.env`：只放 API key，不提交到 Git。
- `config.yaml`：选择 provider、模型、RAG、MCP、specialist 等行为。

### 1. 配置 LLM Provider

默认 provider 在 `config.yaml` 中配置：

```yaml
llm:
  default_provider: "deepseek"
```

默认使用 DeepSeek，因此 `.env` 至少需要填写：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

也可以切换到 MiniMax 或 OpenAI：

```yaml
llm:
  default_provider: "openai"   # deepseek | minimax | openai
```

对应 `.env`：

```env
MINIMAX_API_KEY=your_minimax_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

REPL 启动后也可以临时切换：

```text
/model list
/model use openai
```

### 2. 配置本地知识库 / RAG

默认 RAG embedding 后端是 `auto`：

```yaml
rag:
  embedding_backend: auto      # auto | local | ollama
  ollama_url: "http://localhost:11434"
  ollama_model: "qwen3-embedding:0.6b"
```

- 不装 Ollama 也能用：会走本地 sparse/local 检索。
- 想用 Ollama dense embedding：先启动 Ollama，并准备 `qwen3-embedding:0.6b`。
- 想强制不用 Ollama：把 `embedding_backend` 改成 `local`。

同步资料到知识库：

```text
/kb sync <你的 Obsidian vault 路径>
/kb status
/kb search <问题>
```

### 3. 配置 MCP（可选）

MCP 默认关闭：

```yaml
mcp:
  enabled: false
  servers: {}
```

需要接入外部 MCP server 时再打开，例如：

```yaml
mcp:
  enabled: true
  servers:
    context7:
      command: uvx
      args: ["context7-mcp"]
```

启动后可用：

```text
/mcp status
/mcp tools
/mcp reload
```

### 4. Specialist 配置（通常不用改）

Bobodan 默认启用 3 个 specialist：

- `doc_reader`：读文档和总结。
- `triage`：任务分流。
- `planner`：学习计划。

配置在 `config.yaml` 的 `specialists:` 下。v1 只允许覆盖 Python 已定义 specialist 的行为，不支持只靠 YAML 新增 specialist。

### 5. 运行时数据

运行后会产生这些本地目录，已被 `.gitignore` 排除：

- `.session/`：会话存档。
- `.bobodan/`：记忆、每日记忆、trace。
- `.knowledge/`：RAG 索引、图谱、题库 SQLite。

## 项目结构

```
agent.py / config.yaml / .env.example    # 入口 + 配置
core/          # AgentLoop、Session、Skills、Memory 核心
cli/           # REPL 交互界面
providers/     # LLM Provider（Deepseek / MiniMax / OpenAI 兼容）
tools/         # Agent 工具注册（文件、目录、RAG、图谱、记忆、题库、MCP、specialist）
agents/        # 多 agent 编排（doc_reader / triage / planner）
mcp_client/    # MCP 客户端（stdio / SSE / streamable_http）
knowledge/     # 知识库管理（文档追踪、清单、报告）
quiz/          # 题库系统（生成/练习/批改/错题分析）
learning/      # 学习路线与掌握度追踪
memory/        # 每日记忆 + FTS5 检索 + 晋升机制
obsidian/      # Obsidian vault 扫描与解析
rag/           # 文档导入、切块、向量索引、检索路由
graph/         # 知识图谱（本地 JSON + 可选 Neo4j）
wiki/          # LLM Wiki 编译层
skills/        # Skills 定义目录
tests/         # 单元测试（994+）
```

## 核心功能

### 学习闭环

```
/kb sync <vault>     → 同步学习资料到知识库
/quiz start          → 从知识库出题练习
quiz_submit          → 自动批改 + 写记忆 + 更新掌握度
/learning progress   → 查看掌握度概览
/learning review     → 今日复习清单
```

掌握度规则：连续答对 2 次 → mastered，答错 → needs_review。间隔复习 1/3/7/14 天。

### Obsidian 写回

学习计划和做题总结可导出为 Obsidian Markdown：

- `obsidian_export_plan` — 学习计划导出为 checkbox 任务 + `[[双链]]` 知识点引用
- `obsidian_export_quiz_summary` — 做题总结导出为错题本 + 薄弱点分析 + 掌握度概览

对话中直接说"把学习计划导出到 Obsidian"即可触发。

### 知识库

- **RAG 检索**：回答"是什么、在哪出现过"。支持 sparse（本地）和 dense（Ollama）两种向量后端。
- **知识图谱**：回答"和谁有关、属于哪门课"。本地 JSON 存储，可选 Neo4j。
- **Wiki 编译**：LLM 读资料 → 生成结构化 wiki 页面，`/wiki ingest`。

### 记忆系统

- **永久记忆**（`.bobodan/memory/`）：跨 session 持久化，FTS5 全文检索。
- **每日记忆**（`.bobodan/daily/`）：做题结果自动写入，启动时注入 system prompt。
- **晋升**：每日记忆通过评分公式（频率 0.4 + 做题 0.4 + 时间 0.2）升级为永久记忆。

### MCP 客户端

接入外部 MCP server，工具自动注入 agent loop。三种传输：stdio / streamable_http / SSE。

```yaml
# config.yaml
mcp:
  enabled: true
  servers:
    context7:
      command: uvx
      args: ["context7-mcp"]
```

### 多 Agent 编排

主 agent 将任务委派给 specialist（`doc_reader` / `triage` / `planner`），隔离上下文和工具权限。

## REPL 命令速查

| 命令 | 用途 |
|------|------|
| `/kb sync/status/search/graph/reset` | 知识库操作 |
| `/quiz generate/start/wrong/weak/stats` | 题库操作 |
| `/learning plan/progress/review/mark/plans` | 学习路线 |
| `/memory list/show/search/forget/daily/promote/stats` | 记忆管理 |
| `/skill list/<name>/run` | Skills |
| `/wiki init/ingest/lint/status` | Wiki 编译 |
| `/mcp/status/restart/tools/reload` | MCP 管理 |
| `/specialists/status/tools` | 多 agent |
| `/model/list/use` | Provider 切换 |
| `/session/list/save/resume/load` | Session 管理 |
| `/ui tools on\|off` | 工具显示开关 |
| `/status` | 运行时状态 |

## Provider

| 类型 | 说明 |
|------|------|
| `minimax` | 原始 httpx，refusal 检测 |
| `deepseek` | OpenAI 兼容 |
| `openai` | OpenAI 兼容 API |

所有 provider 返回统一 `LLMResponse(content, tool_calls)`。

## 测试

```bash
pytest tests/ -v
```

## 文档

项目主指南见 [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md)。文档索引见 [`docs/README.md`](docs/README.md)。
