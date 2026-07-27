# 波波蛋（Bobodan）

Bobodan 是一个本地优先的 AI 学习工作区。它以 React + FastAPI 提供面向桌面浏览器的学习界面，把资料阅读、基于原文的对话、练习、复习、个人知识和知识地图放在同一条学习流程中。

当前主流程是：

```text
Library 导入与阅读资料
  → Chat 基于原文检索与提问
  → Practice 生成和完成练习
  → Review 按掌握度安排复习
```

## 当前能力

- **资料库**：管理多个本地资料库，导入 Markdown、TXT、PDF、DOCX、PPTX 等学习资料，并在 Library 中阅读和定位原文。
- **可信对话**：ReAct Agent 调用资料检索、知识地图和个人知识工具；知识型回答以原始资料证据为骨架，明确区分本地资料、联网来源与通用知识。
- **本地 RAG**：使用 SQLite `knowledge.db` 保存文档与 chunk 元数据，采用 heading-aware 切分、中文友好的 CJK 2-gram FTS5，并可结合 Qdrant 做混合检索。
- **知识地图**：使用 `concept_graph.db` 保存用户已经审查确认的概念、关系与证据。候选概念不会直接参与回答。
- **个人知识**：使用结构化 SQLite 保存已确认的偏好、目标、学习策略和课程洞见；旧 Markdown 记忆只用于显式迁移，不再由正常运行时读写。
- **学习闭环**：支持题目生成、自动批改、错题变体、掌握度追踪和保守的 SM-2 间隔复习。
- **可信联网**：本地资料不足时，可在用户授权边界内搜索、选择并保存网页证据快照。
- **高级维护**：历史 Wiki 整理能力保留为只读历史与高级维护入口，不是资料导入或 Chat RAG 的必经层。
- **扩展能力**：支持 DeepSeek、MiniMax、OpenAI 及其他 OpenAI-compatible Provider，另有 Skills、MCP 和 specialist 编排能力。

> 当前发布形态仍是 Vite + FastAPI 两个开发进程；Windows 桌面安装包尚未完成。

## 快速开始

最近一次验证环境为 Python 3.13 和 Node.js 24。

### 1. 安装后端

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填写至少一个 Provider 的 API key，例如：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

启动 FastAPI：

```powershell
python -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

### 2. 安装并启动前端

```powershell
Set-Location web\frontend
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。前端开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

### 3. 可选：使用 CLI

```powershell
python agent.py
python agent.py --session-id my-session
python agent.py -v
```

资料库也可以通过 CLI 初始化和同步：

```powershell
python agent.py library init <path> --name <name>
python agent.py library sync <path>
python agent.py library list
```

## 配置

- `.env`：只保存 API key，不提交到 Git。
- `config.yaml`：配置 Provider、模型、RAG、MCP 和 specialist。
- 默认 Provider 是 DeepSeek；也可使用 MiniMax、OpenAI、通义、硅基流动、OpenRouter 等 OpenAI-compatible 接口。
- Qdrant 默认使用本地模式；未配置可用向量模型时，FTS5 检索仍可独立工作。

## 数据与迁移边界

Bobodan 只保留一个正常运行的真相源，旧数据不会被静默删除：

| 数据 | 当前真相源 | 旧数据处理 |
|---|---|---|
| 原始资料与 RAG | 资料库文件 + `.bobodan/knowledge.db`，可选 Qdrant | 旧工作区使用 `.knowledge/`；旧 JSON / sparse RAG 不参与正常检索 |
| 知识地图 | `.bobodan/concept_graph.db` | 旧工作区使用 `.knowledge/`；`graph_store.json` 仅在“设置 → 数据迁移”中检测、预览和确认迁移 |
| 个人知识 | 全局 `personal-knowledge.db` + 资料库 `.bobodan/bobodan.db` | `.bobodan/memory/*.md` 与 daily 文件只读预览、显式导入 |
| Wiki | 高级维护 / 历史整理 | 不作为默认 RAG 证据，不自动生成或强制维护 |

旧图谱迁移会先生成预览；Concept 与语义关系进入候选审查，Memory 不会混入概念图谱。只有迁移写入、数量与校验值验证成功后，旧 JSON 才会被归档。

## 项目结构

```text
agent.py             CLI 入口
core/                AgentLoop、Session、数据库与通用运行时
providers/           LLM Provider 与统一错误契约
rag/                 SQLite / Qdrant 检索、切分与引用
graph/               已审查概念图谱 SQLite
memory/              个人知识存储与旧记忆只读适配
quiz/ learning/      练习、批改、掌握度与复习
service/             Web 与 CLI 共用的业务服务
web/backend/         FastAPI API 与 SSE 适配
web/frontend/        React + TypeScript + Vite 界面
wiki/                高级维护与历史整理工作流
tests/               Python 测试
docs/                项目指南、设计规范与审查记录
```

## 常用 CLI 命令

| 命令 | 用途 |
|---|---|
| `/kb sync/status/search/graph/reset` | 同步、检索与维护知识库 |
| `/quiz generate/start/wrong/weak/stats` | 生成练习、答题和查看错题 |
| `/learning plan/progress/review/mark/plans/today` | 学习计划、掌握度和复习 |
| `/memory list/show/search/forget/legacy/review/stats` | 管理个人知识与检查旧记忆 |
| `/wiki init/lint/status` | 高级 Wiki 维护；已无 ingest 命令 |
| `/model list/use` | 查看或切换 Provider |
| `/session list/save/resume/load` | 会话管理 |
| `/mcp status/restart/tools/reload` | MCP 管理 |
| `/specialists status/tools` | specialist 状态与工具 |

## 验证

```powershell
# Python
python -m pytest

# Frontend
Set-Location web\frontend
npm run lint
npm run build
npm test
```

最近一次全量整改验证：Python `1160 passed`，前端 lint 与生产构建通过，Vitest `19 passed`。

## 文档

- [项目文档索引](docs/README.md)
- [项目主指南](docs/PROJECT_GUIDE.md)
- [2026-07-26 项目审查与整改记录](docs/project_review_2026-07-26.md)
- [更新日志](CHANGELOG.md)
