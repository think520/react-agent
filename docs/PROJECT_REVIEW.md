# 项目重度使用视角评审与迭代建议

> **历史快照（2026-05-06）**：本文档记录了项目早期评审结果。所有 17 项评审问题已全部修复（见 CHANGELOG.md）。当前项目状态：167 个测试通过，已新增持久化记忆系统、课程学习助手（RAG + 知识图谱）、流式 REPL 等能力。本文档保留作为历史参考。

本文档用于后续修改迭代。它不是一次性重构方案，而是从”长期高频使用这个 Agent”的角度，整理当前项目里最容易踩坑的结构问题、潜在 bug、体验问题和推荐修复顺序。

评审日期：2026-05-06
项目定位：Python CLI ReAct Agent，支持多 LLM Provider、工具调用、Session 持久化、Skills 注入。

## 完成状态

- [x] **Phase 1** — 项目可安全使用（P0 全部完成）
- [x] **Phase 2** — 稳定抽象边界（P1 全部完成）
- [x] **Phase 3** — 提升工具可靠性（P2 全部完成）
- [x] **Phase 4** — 改善 CLI 和 Skills 体验（完成：超时控制、日志系统、配置校验、依赖清单）

当前测试：80 passed。所有 17 项评审问题已修复。

## 当前状态快照

当前主路径已经具备基本骨架：

- `agent.py`：CLI 入口。
- `cli/repl.py`：交互命令、启动信息、Session 命令、Skill 命令。
- `core/agent_loop.py`：ReAct 循环，调用 LLM，执行 tool calls。
- `core/session.py`：会话状态和 JSON 保存/恢复。
- `providers/`：Deepseek、MiniMax、OpenAI 兼容配置入口。
- `tools/`：文件和目录工具注册。
- `skills/`：通过 `SKILL.md` 提供额外任务指令。
- `tests/`：已有较完整的单元测试。

我运行了：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
48 passed, 2 failed
```

失败集中在 `tests/test_repl.py`，原因是测试断言的 REPL 输出文案和当前实际输出不一致。这不是最危险的问题，但说明“CLI 输出契约”和测试已经漂移。

## 优先级说明

- P0：高频使用中很可能造成错误结果、API 调用失败、数据泄露或破坏文件。
- P1：结构债务，会拖慢后续扩展，或在接入新 Provider / 新工具时放大问题。
- P2：体验、可维护性、测试覆盖和工程卫生问题。

## P0 问题

### 1. 项目存在大量乱码文本，已经影响工具描述、文档和 CLI [已完成]

涉及文件：

- `README.md`
- `CHANGELOG.md`
- `docs/tools/skills.md`
- `cli/repl.py`
- `tools/file_ops.py`
- `tools/dir_ops.py`
- `core/agent_loop.py`
- 部分测试文件

现象：

- 很多中文显示为类似 `娉㈡尝铔?`、`宸插垏鎹㈠埌`、`鏂囦欢` 的乱码。
- 这些乱码不仅影响人读，也会传给模型作为 tool description。
- 模型依赖工具描述来决定是否调用工具，所以乱码会降低工具选择准确性。
- `core/agent_loop.py` 里通过乱码前缀识别 `change_dir` 结果，如果只修一边，会导致 cwd 同步失效。

建议：

- 统一把源码、文档、测试恢复为 UTF-8 正确中文或直接改成英文。
- 不要只修 README，要连同 tool schema、错误消息、CLI 输出、测试断言一起修。
- 把工具返回值中用于程序判断的文本替换为结构化结果，至少不要依赖中文前缀。

验收标准：

- `README.md`、`CHANGELOG.md`、CLI 启动画面、工具描述均无乱码。
- `pytest` 全部通过。
- `change_dir` 的 cwd 同步不依赖乱码字符串。

### 2. tool call 消息顺序不符合 OpenAI 风格协议 [已完成]

涉及文件：

- `core/agent_loop.py`
- `providers/minimax.py`
- `providers/deepseek.py`

当前 `AgentLoop.run()` 的流程是：

1. 收到模型返回的 tool calls。
2. 立刻执行工具。
3. 先把 `tool` message 加入 session。
4. 再把带 `tool_calls` 的 `assistant` message 加入 session。

这会形成：

```text
user -> tool -> assistant(tool_calls)
```

但标准顺序应该是：

```text
user -> assistant(tool_calls) -> tool -> assistant(final)
```

`providers/minimax.py` 里现在做了 provider 层的重排修补，但这属于“在出口补锅”。Session 内部保存的历史本身仍然是不规范的，其他 provider 不一定能容忍。

风险：

- Deepseek / OpenAI 兼容 provider 可能报 tool_call_id 无法关联。
- Session 保存后再恢复，历史顺序仍然错误。
- 后续新增 provider 时很容易重复踩坑。

建议：

- 在 `AgentLoop` 层修正顺序：先追加 `assistant(tool_calls)`，再执行工具并追加 `tool` message。
- Provider 层只负责格式转换，不负责修复核心历史顺序。
- 增加测试断言 session message 顺序。

验收标准：

- tool call turn 的 session 历史始终是 `assistant(tool_calls)` 在 `tool` 前。
- MiniMax provider 不再需要靠 swap 修复正常路径。
- Deepseek / OpenAI 兼容格式测试覆盖多轮 tool calls。

### 3. 文件工具没有安全边界，Agent 可以读写任意绝对路径 [已完成]

涉及文件：

- `tools/file_ops.py`
- `tools/dir_ops.py`
- `tools/base.py`
- `core/session.py`

当前工具允许：

- `read_file` 读取任意绝对路径。
- `write_file` 覆盖任意绝对路径。
- `change_dir` 切到任意目录。
- `list_dir` 和 `stat_path` 探查任意目录。

这对本地 Agent 来说很危险，尤其是模型自主调用工具时。

风险：

- 误读 `.env`、SSH key、系统配置等敏感文件。
- 误覆盖项目外文件。
- Session 中保存了工具返回内容，可能把敏感文件内容持久化到 `.session/`。

建议：

- 引入 `workspace_root`，默认限制工具只能访问项目根目录内。
- 对绝对路径访问增加配置开关，默认关闭。
- 对覆盖写入增加保护，例如 `write_file` 默认拒绝覆盖，新增 `overwrite: true` 才允许。
- 增加 `dry_run` 或写入前 diff。
- 至少把 `.env`、`.session`、`.git`、`.venv` 加入默认拒读列表。

验收标准：

- 默认不能读取或写入项目根目录外路径。
- 默认不能读取 `.env`。
- 写入已存在文件时有明确策略。

### 4. 缺少 `.gitignore`，敏感文件和运行产物容易进入版本库 [已完成]

当前工作区存在：

- `.env`
- `.session/`
- `__pycache__/`
- `.venv/`

但项目根目录没有 `.gitignore`。

风险：

- API key 被误提交。
- Session 历史泄露用户输入、工具输出、文件内容。
- 依赖环境和缓存污染版本库。

建议：

新增 `.gitignore`，至少包含：

```gitignore
.env
.session/
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

验收标准：

- `git status --short` 不再显示运行产物。
- `.env` 永不进入 git。

### 5. Session 裁剪可能破坏 tool call 消息组 [已完成]

涉及文件：

- `core/session.py`

当前 `_trim_messages()` 只保留开头 system message，然后用 `deque(maxlen=budget)` 裁剪剩余消息。这可能把一组 tool call 消息裁断：

```text
assistant(tool_calls) -> tool
```

可能被裁成只剩 `tool`，或者只剩 `assistant(tool_calls)`。

风险：

- Provider 看到孤立 `tool` message 后报错。
- 模型拿到残缺上下文，无法理解工具结果。
- Session 恢复后更容易出错。

建议：

- 按“对话 turn”或“tool call group”裁剪，而不是按单条 message 裁剪。
- 保证 `assistant(tool_calls)` 和对应 `tool` message 要么一起保留，要么一起移除。
- 对 `tool_call_id` 做一致性校验。

验收标准：

- 裁剪后不存在孤立 `tool` message。
- 裁剪后不存在没有结果的 `assistant(tool_calls)`。
- 增加专门测试覆盖多轮工具调用后的裁剪。

## P1 问题

### 6. Provider 协议定义和真实实现不一致 [已完成]

涉及文件：

- `providers/base.py`
- `providers/deepseek.py`
- `providers/minimax.py`
- `providers/factory.py`
- `tests/test_providers.py`

`LLMProvider` 协议目前是：

```python
def complete(self, messages: list[dict]) -> str
```

但真实调用是：

```python
self.llm.complete(self.session.messages, tools=self.tools_schema)
```

真实返回也不是 `str`，而是带 `.content` 和 `.tool_calls` 的对象。

风险：

- mock provider 和真实 provider 的接口不一致。
- 新 provider 按协议实现后会在 `AgentLoop` 中报 `unexpected keyword argument 'tools'`。
- 类型提示无法帮助发现问题。

建议：

- 定义统一响应类型，例如 `LLMResponse(content: str, tool_calls: list[ToolCall])`。
- 协议改为 `complete(messages: list[dict], tools: list[dict] | None = None) -> LLMResponse`。
- 所有 provider 都转换成同一种内部响应对象。
- 测试 mock 也按真实协议实现。

验收标准：

- `AgentLoop` 不再依赖 `hasattr(response, "tool_calls")`。
- 所有 provider 返回同一种内部类型。
- `tests/test_providers.py` 能覆盖 tools 参数。

### 7. OpenAI provider 当前复用了 `DeepseekProvider`，命名和职责混乱 [已完成]

涉及文件：

- `providers/factory.py`
- `providers/deepseek.py`

当前 `type: openai` 分支返回的是 `DeepseekProvider(provider_name="openai")`。

这在技术上可能因为 OpenAI-compatible API 暂时能跑，但结构上不清晰：

- `DeepseekProvider` 实际变成了“LangChain OpenAI-compatible Provider”。
- Deepseek 和 OpenAI 的 provider-specific 行为未来会混在一起。
- 日后接入其他兼容 API 时难以命名和测试。

建议：

- 抽出 `OpenAICompatibleProvider`。
- Deepseek、OpenAI、其他兼容服务通过配置复用它。
- MiniMax 如果仍需特殊格式，可以单独保留。

验收标准：

- `ProviderFactory` 中 provider type 和 class 名称一致或有明确抽象。
- OpenAI 分支不再返回 `DeepseekProvider`。

### 8. Deepseek provider 只恢复第一个历史 tool call [已完成]

涉及文件：

- `providers/deepseek.py`

在把 session 中的 `assistant(tool_calls)` 转成 LangChain `AIMessage` 时，代码只取：

```python
tc = tool_calls_data[0]
```

如果模型一次返回多个工具调用，历史里只有第一个会被转换，其他 tool calls 会丢失。

风险：

- 多工具并行调用历史不完整。
- 后续 provider 调用时 tool_call_id 无法匹配。
- 只有单工具测试时不容易发现。

建议：

- 完整遍历 `tool_calls_data`。
- 增加多 tool call 的 provider message conversion 测试。

验收标准：

- 一次 assistant message 中多个 tool calls 能完整转换。
- 多个对应 tool messages 都能被 provider 接收。

### 9. MiniMax provider 的 `max_retries` 配置没有实际生效 [已完成]

涉及文件：

- `providers/minimax.py`
- `config.yaml`

`MiniMaxProvider.__init__()` 接收 `max_retries`，但 raw `httpx.Client.post()` 没有重试逻辑。

风险：

- 网络抖动时直接失败。
- 配置项给用户造成“已经有重试”的错觉。

建议：

- 实现显式 retry，覆盖连接错误、超时、5xx、429。
- 对不可重试的 4xx 给出清晰错误。
- 可以统一 provider 错误类型。

验收标准：

- 测试覆盖 500 后重试成功。
- 测试覆盖 401 不重试并返回清晰错误。

### 10. Skills 注入和已有 system message 的关系不稳定 [已完成]

涉及文件：

- `core/agent_loop.py`
- `core/skills.py`
- `cli/repl.py`

当前 `_inject_skills_prompt()` 如果发现 session 中已经有任意 system message，就不会注入 skills prompt。

风险：

- 恢复旧 session 时，skills 可能不会生效。
- 未来如果增加主系统提示词，skills 会被跳过。
- 多个 system message 的管理缺少明确策略。

建议：

- 明确 system prompt 结构，例如：
  - base system prompt
  - skills catalog system prompt
  - runtime policy system prompt
- 用 metadata 或稳定标记识别 skills prompt，而不是“是否存在 system message”。

验收标准：

- 存在 base system prompt 时，skills 仍能注入。
- 重复运行不会重复注入 skills。

### 11. CLI 使用线程运行 Agent，但没有真正取消和超时控制 [已完成]

涉及文件：

- `cli/repl.py`

`run_agent()` 在后台线程里执行 LLM 请求，主线程显示 thinking 动画。用户按 `Ctrl+C` 时，主循环能捕获，但已经运行的 LLM 线程无法被真正取消。

风险：

- 请求卡住时 CLI 无法干净停止。
- 后台线程可能继续写 session。
- 用户连续输入时状态可能混乱。

建议：

- 在 provider 层支持 timeout 和取消。
- CLI 中明确“一次只能运行一个请求”。
- 出错或超时后不写入不完整 session。

验收标准：

- 模拟 provider 卡住时，REPL 能超时返回。
- 超时后 session 不包含半截 tool call 组。

## P2 问题

### 12. 测试和当前输出契约漂移 [已完成]

涉及文件：

- `tests/test_repl.py`
- `cli/repl.py`

当前失败测试：

- `test_repl_initialize_renders_rich_startup`
- `test_repl_status_output`

原因：

- 测试期望 `Python Agent System`、`Runtime status:` 等旧文案。
- 当前实现输出不同文案，并且包含 ANSI 颜色和乱码。

建议：

- 先决定 REPL 输出使用英文还是中文。
- 测试不要过度绑定整段样式，可以断言关键字段：session id、provider、model、save dir、tools。
- 对 ANSI 输出做 strip 后再测。

验收标准：

- `pytest` 全部通过。
- 修改颜色或边框不导致无关测试失败。

### 13. 缺少依赖清单，环境不可复现 [已完成]

当前项目有 `.venv/`，但未看到 `requirements.txt` 或 `pyproject.toml`。

风险：

- 新机器无法稳定复现运行环境。
- provider 依赖版本变化后，`ChatOpenAI.invoke()` 行为可能变。

建议：

- 新增 `pyproject.toml` 或 `requirements.txt`。
- 固定核心依赖大版本。
- 记录 Python 版本。

验收标准：

- 清空环境后能按文档一步安装并跑测试。

### 14. 工具返回值是纯文本，程序逻辑依赖文本解析 [已完成]

涉及文件：

- `tools/file_ops.py`
- `tools/dir_ops.py`
- `core/agent_loop.py`

当前工具返回纯字符串。`change_dir` 后，`AgentLoop` 通过字符串前缀更新 `session.cwd`。

风险：

- 文案修改会破坏逻辑。
- 多语言输出难维护。
- 错误和成功状态不易机器判断。

建议：

- 内部工具返回 `ToolResult(ok: bool, content: str, data: dict)`。
- 给 LLM 的 tool message 仍可用 `content` 字符串。
- 程序逻辑用 `ok` 和 `data` 更新状态。

验收标准：

- 修改 `change_dir` 展示文案不会影响 cwd 更新。

### 15. `write_file` 默认覆盖文件，重度使用风险较高 [已完成]

涉及文件：

- `tools/file_ops.py`

当前 `write_file` 会直接覆盖已有文件。

建议：

- 增加 `overwrite` 参数，默认 `false`。
- 如果文件存在，返回错误并建议用户显式确认。
- 后续新增 `edit_file`，按 patch 修改文件，而不是整文件覆盖。

验收标准：

- 未传 `overwrite: true` 时不会覆盖已有文件。
- 测试覆盖已有文件写入场景。

### 16. 配置缺少校验和默认值说明 [已完成]

涉及文件：

- `config.yaml`
- `providers/factory.py`

当前配置读取后直接使用。

风险：

- 拼错 provider 名称时错误信息有限。
- 缺少字段时可能在更深层才报错。

建议：

- 新增 config schema 校验。
- 启动时打印有效配置摘要。
- 对模型名、base_url、api_key_env 做清晰校验。

验收标准：

- 无效 provider、缺少 model、缺少 api_key_env 都有清楚错误。

### 17. 日志系统不完整 [已完成]

涉及文件：

- `core/agent_loop.py`
- `providers/minimax.py`

当前有 `logging.getLogger()`，但没有统一 logging 配置。

建议：

- 增加 `--verbose` 或 config 中的 log level。
- 日志中记录 provider、tool name、duration、错误摘要。
- 不记录完整 API key、`.env` 内容或敏感工具输出。

验收标准：

- 调试 provider/tool 问题时不需要临时加 print。

## 推荐迭代顺序

### 第一阶段：先让项目“可安全使用”

1. 新增 `.gitignore`，排除 `.env`、`.session/`、`.venv/`、缓存。
2. 修复乱码，统一 UTF-8 文案。
3. 修正 `AgentLoop` 的 tool call 消息顺序。
4. 修复 session 裁剪，保证 tool call 组不被拆开。
5. 跑通全部测试。

这一阶段的目标是：不泄露、不乱码、不保存错误格式的消息历史。

### 第二阶段：稳定抽象边界

1. 定义统一 `LLMResponse` 和 `ToolCall` 内部类型。
2. 修正 `LLMProvider` 协议签名。
3. 重构 provider message conversion。
4. 抽出 `OpenAICompatibleProvider`。
5. 补齐 Deepseek / MiniMax / OpenAI 兼容格式测试。

这一阶段的目标是：新增 provider 时不用碰 AgentLoop。

### 第三阶段：提升工具可靠性

1. 给工具增加 workspace root 安全边界。
2. `write_file` 默认不覆盖。
3. 工具返回结构化结果。
4. 给 `read_file` 增加大小限制和二进制文件检测。
5. 增加文件操作测试和危险路径测试。

这一阶段的目标是：Agent 可以长期在真实项目里跑，而不是只适合 demo。

### 第四阶段：改善 CLI 和 Skills 体验

1. 修复 REPL 输出测试。
2. 增加请求超时和取消能力。
3. 明确 system prompt / skills prompt 注入策略。
4. 增加 `/session current`、`/session delete`、`/config` 等命令。
5. Skills 支持 aliases、assets、脚本路径解析。

这一阶段的目标是：使用起来顺手，出现问题时容易诊断。

## 建议新增测试清单

- `AgentLoop` 生成的消息顺序必须是 `assistant(tool_calls)` 在 `tool` 前。
- 多个 tool calls 同时返回时，所有 tool call 都能执行并保存。
- `max_messages` 裁剪后不出现孤立 `tool` message。
- `read_file` 默认拒绝读取 `.env`。
- `write_file` 默认拒绝覆盖已有文件。
- `change_dir` 不能切出 workspace root。
- MiniMax 500/429 重试。
- OpenAI-compatible provider 格式转换测试。
- Skills prompt 在已有 system message 时仍能正确注入。
- ANSI 输出 strip 后的 REPL 状态测试。

## 总结

这个项目的基础方向是对的：CLI、AgentLoop、Provider、Tools、Session、Skills 分层已经成型。真正需要优先处理的不是加更多功能，而是把几个核心契约收紧：

1. 消息历史格式必须正确。
2. Provider 接口必须统一。
3. 工具访问必须有安全边界。
4. Session 裁剪不能破坏协议。
5. 文案和编码必须恢复正常。

先把这些打牢，再继续加搜索工具、代码编辑工具、更多 skills 或 Web UI，后面的迭代会轻很多。
