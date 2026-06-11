# 波波蛋 (Bobodan)

Python ReAct Agent，支持多 LLM Provider、工具调用、Session 持久化、Skills 注入、持久化记忆、本地知识库（RAG + 知识图谱）、题库系统、学习路线与复习、MCP 客户端、多 agent 编排、CLI REPL 交互。

## 运行

```bash
# 1. 激活虚拟环境
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# 2. 配置 API key
cp .env.example .env

# 3. 启动
python agent.py
python agent.py --session-id my-session  # 恢复 session
python agent.py -v                       # 调试模式
```

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
tests/         # 单元测试（716+）
```

运行时数据（`.gitignore` 已排除）：
- `.bobodan/` — 记忆文件、每日记忆、SQLite 索引
- `.knowledge/` — RAG 索引、图谱、题库 SQLite

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

详见 [`docs/README.md`](docs/README.md) 文档索引。视觉设计参考 [`docs/DESIGN.md`](docs/DESIGN.md)。
