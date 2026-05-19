# Agent 系统设计规格文档

> **项目：** Python Agent 系统（CLI 界面）
> **日期：** 2026-04-22
> **工作目录：** `project_class/`

---

## 1. 概述

**目标：** 构建一个基于 Python 的 Agent 系统，采用 ReAct 模式，支持多 LLM Provider（通过 Protocol + Factory 模式），提供 CLI REPL 交互界面，以及 Session 持久化功能。

**核心功能：**
- Agent Loop（ReAct 模式）
- 多 Provider LLM 支持（Deepseek、OpenAI 等）
- 5 个核心工具：read_file、write_file、list_dir、change_dir、stat_path
- Session 管理（内存 + 手动文件保存/加载）
- CLI REPL 界面

---

## 2. 架构

```
project_class/
├── config.yaml                    # 配置文件（LLM providers、agent 参数）
├── agent.py                        # CLI 入口点
├── core/
│   ├── __init__.py
│   ├── agent_loop.py               # ReAct Loop 实现
│   ├── session.py                  # Session 状态管理
│   └── llm.py                      # LLMProvider Protocol
├── tools/
│   ├── __init__.py
│   ├── base.py                    # 工具注册表和 Schema
│   ├── file_ops.py                # read_file、write_file
│   └── dir_ops.py                # list_dir、change_dir、stat_path
├── providers/
│   ├── __init__.py
│   ├── base.py                    # LLMProvider Protocol
│   ├── deepseek.py                # Deepseek 实现
│   └── factory.py                # Provider 工厂
└── cli/
    ├── __init__.py
    └── repl.py                    # REPL 界面
```

---

## 3. 模块规格

### 3.1 配置文件（config.yaml）

```yaml
llm:
  default_provider: "deepseek"
  providers:
    deepseek:
      type: "deepseek"
      base_url: "https://api.deepseek.com/v1"
      api_key_env: "DEEPSEEK_API_KEY"  # 引用环境变量
      model: "deepseek-chat"
    openai:
      type: "openai"
      base_url: "https://api.openai.com/v1"
      api_key_env: "OPENAI_API_KEY"
      model: "gpt-4"

agent:
  temperature: 0.7
  max_retries: 3
  timeout: 60

session:
  save_dir: ".session"
  max_messages: 100  # 内存中最大消息数
```

### 3.2 LLM Provider 协议（providers/base.py）

```python
from typing import Protocol

class LLMProvider(Protocol):
    """LLM Provider 接口。"""

    def complete(self, messages: list[dict]) -> str:
        """发送消息并返回完成文本。"""
        ...

    def get_name(self) -> str:
        """返回 Provider 名称。"""
        ...
```

### 3.3 Session（core/session.py）

**Session 数据结构：**
```python
@dataclass
class Session:
    session_id: str
    cwd: str
    messages: list[dict]  # OpenAI 格式消息
    created_at: datetime
    last_active: datetime
```

**操作：**
- `Session.new(cwd)` — 创建新 Session
- `add_message(role, content)` — 添加消息
- `save_to_file(path)` — 保存到 JSON 文件
- `load_from_file(path)` — 从 JSON 文件加载
- `list_sessions(save_dir)` — 列出已保存的 Session

### 3.4 工具 Schema 格式

工具使用 **Dict 格式**（保持与现有方法的兼容性）：

```python
TOOLS = [
    {
        "name": "read_file",
        "description": "读取文件内容",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"]
        }
    },
    # ... 其他工具
]
```

### 3.5 核心工具

| 工具 | 描述 | 参数 |
|------|------|------|
| `read_file` | 读取文件内容 | `path: str` |
| `write_file` | 写入内容到文件 | `path: str, content: str` |
| `list_dir` | 列出目录内容 | `path: str`（可选，默认为 cwd） |
| `change_dir` | 切换工作目录 | `path: str` |
| `stat_path` | 获取文件/目录信息 | `path: str` |

---

## 4. CLI REPL 界面

**交互流程：**
```
(project_class) > 你好
[Agent] 你好！有什么可以帮你的？

(project_class) > 读取 config.yaml
[Agent] 正在读取文件...
[Agent] 文件内容如下：
...

(project_class) > exit
保存 session? (y/n): y
Session 已保存到 .session/<id>.json
```

**命令：**
- `/exit` / `/quit` — 退出 CLI（提示保存 Session）
- `/session list` — 列出已保存的 Session
- `/session load <id>` — 加载指定 Session
- `/session save` — 保存当前 Session
- `/cwd` — 显示当前工作目录
- `/status` — 显示运行状态
- `/tools` — 列出可用工具
- `/help` — 显示帮助

---

## 5. Session 持久化

**文件格式：** JSON
**位置：** `.session/<session_id>.json`

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "cwd": "F:/claude projects/openclaw-main/project_class",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮你的？"}
  ],
  "created_at": "2026-04-22T15:00:00",
  "last_active": "2026-04-22T15:30:00"
}
```

---

## 6. Agent Loop 流程

```
1. 用户输入 → REPL
2. 添加用户消息到 session.messages
3. 使用 messages + tools schema 调用 LLM
4. 如果没有 tool_calls → 返回响应给用户
5. 如果有 tool_calls：
   a. 追加 assistant 消息（包含 tool_calls）到 messages
   b. 对每个 tool_call：
      - 执行工具函数
      - 追加工具结果到 messages
   c. 跳转到步骤 3（循环）
```

---

## 7. 实现说明

- API 密钥从环境变量读取，在 config.yaml 中引用
- 工作目录从 `project_class/` 开始
- Session 保存由用户手动触发，退出时提示
- 无自动 Session 持久化（用户控制）
- 工具相对于 agent 的 cwd 执行（由 change_dir 工具管理）
- 错误处理：工具执行错误返回给 LLM 进行重试/处理

---

## 8. 文件职责

| 文件 | 职责 |
|------|------|
| `agent.py` | CLI 入口，解析参数，启动 REPL |
| `core/agent_loop.py` | ReAct Loop 实现 |
| `core/session.py` | Session 状态管理 |
| `core/llm.py` | LLM 协议 + 工厂 |
| `providers/base.py` | LLMProvider Protocol |
| `providers/deepseek.py` | Deepseek 实现 |
| `providers/factory.py` | 根据配置创建 Provider |
| `tools/base.py` | 工具基类，Schema 注册表 |
| `tools/file_ops.py` | read_file、write_file |
| `tools/dir_ops.py` | list_dir、change_dir、stat_path |
| `cli/repl.py` | REPL 实现 |
| `config.yaml` | 配置文件 |