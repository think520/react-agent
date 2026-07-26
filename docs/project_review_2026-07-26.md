# Bobodan 全项目深度体验与改进建议

日期：2026-07-26 · 基于分支 `feat/p5e6-knowledge-map`（commit 7432c6a）
方法：通读 PROJECT_GUIDE / CLAUDE.md → 5 个方向逐文件代码审查（core+CLI、service+web 后端、rag/graph/wiki、quiz/learning/memory、React 前端）→ 实际启动后端走完一轮真实学习闭环（Chat → 检索 → 出题 → 答题 → 复习）→ 跑全量测试。

---

## 0. 结论先行

**产品方向和分层设计是对的，最大的问题是"旧系统没死透"和"几个巨型文件把边界冲垮了"。**

- 测试实测 `1238 passed`（2 分 19 秒），学习闭环真实可用：出题质量好、批改解释准确、来源归因结构化、SSE 事件协议干净。这在个人项目里是罕见的完成度。
- 但代码里同时存在 **三套并行的"新旧系统"**（记忆、图谱、RAG legacy）和 **四个失控的巨型文件**（repl.py 2859 行、kb_service.py 1791 行、chat.py router 1460 行、ChatPage.tsx 1064 行），每加一个功能都在给旧债付利息。
- 找到了 **9 个真实 bug**，其中 3 个直接破坏产品核心承诺（间隔复习失效、批改解析失败判错、SSE 断线丢会话）。
- 各区域健康度：core/CLI **6/10**、service/web 后端 **6/10**、rag/graph/wiki **5.5/10**、quiz/learning/memory **5.5/10**、前端 **5.5/10**。

进入 P5G 发布收尾之前，建议先花 1-2 周做一轮"还债"，否则 Electron 打包只是把这些债封进安装包。

---

## 1. 实际体验记录

我用真实资料库（68 个文件、1863 chunks）走了一遍主流程，好的和坏的都记录在这：

| 体验点 | 结果 |
|---|---|
| Chat SSE 流式问答 | ✅ 事件协议干净：`run_started → personalization → status → citation → message_delta`，状态文案是中文（"正在查找你的资料"），符合渐进披露设计 |
| 引用相关性 | ⚠️ 问"什么是 RAG"，返回的 citation 却来自《13 - 提示词与消息模板》的 JSON 加载章节——检索命中了字面 "RAG" 相近内容但语义跑偏（无 Ollama 时 hybrid 静默降级为纯 FTS5） |
| 关键词检索 | ✅ `/api/kb/search` 查 "RAG" 命中准确 |
| 语义检索降级 | ❌ 查"贪心算法为什么正确"返回 **0 条结果**，且响应里没有任何"当前处于关键词模式/未启用向量检索"的提示——用户只会以为自己的资料里没有 |
| 出题 | ✅ 质量高：单选干扰项合理、attribution 精确到 chunk + heading、`local_extension` 标注诚实 |
| 答题批改 | ✅ 判对、解释具体（逐个排除错误选项）、掌握度联动 |
| 复习队列 | ⚠️ 9 个概念里 6 个 score 0.0 / needs_review——结合下文 bug #3，间隔复习机制实际是坏的 |
| 知识地图 | ⚠️ concept graph 27 概念 / 9 关系，同库旧图谱却有 114 节点 / 146 关系——两套图并存，用户看到的地图远小于系统已知的知识结构 |
| API 一致性 | ⚠️ CLI 出题参数叫 `topic`，Web API 叫 `query`；响应信封有三种形态（带 ok / 剥掉 ok / 无 ok） |

**API 面积**：123 个路径，其中 Wiki 相关约 40 个。对一个单用户本地应用，这个面积已经在产生维护税（P5E.6 已把 Wiki 收进"高级维护"，但后端端点没有随之收敛）。

---

## 2. 真实 Bug 清单（按用户影响排序）

这些都有具体代码证据，不是风格意见。前 3 个直接破坏产品对用户的核心承诺。

### B1. 间隔复习实际只有 2 次——"mastered" 永久退出复习循环
`learning/scheduler.py:41-42` + `learning/store.py:158-160`
连对 2 次 → status 置为 `mastered`，但 `get_due_reviews` 的 SQL 是 `WHERE status IN ('learning','needs_review')`。`next_review` 虽然写了 7 天后，**但 mastered 概念永远不会再出现在到期列表里**。1/3/7/14 的后两档间隔不可达，"间隔重复"退化为"答对两次即毕业"——与遗忘曲线目标背道而驰。
**修法**：`get_due_reviews` 纳入 `mastered`，补一条"答对 3 次后仍会到期"的测试。一行 SQL。

### B2. 简答批改解析失败 = 判学生答错
`quiz/evaluator.py:20-39`
LLM 批改响应解析失败时直接返回 `(False, "批改解析失败，请重试。")`——**解析失败被当成"答错"**，会污染掌握度（-0.2、触发 needs_review）和错题本。而 generator 有重试 + 纠正提示，evaluator 没有，不对称。
**修法**：解析失败重试一次；仍失败则返回"无法判定"，不写 mastery、不进错题本。

### B3. SSE 流末尾才保存会话——断线丢整轮对话
`web/backend/routers/chat.py:1356-1460`
`save_session` 和记忆巩固调度写在流式生成器的末尾。浏览器中途断开 → `GeneratorExit` → 整轮对话（用户消息+AI 回复）不落盘，`except Exception` 接不住。这与 PROJECT_GUIDE"流式回答支持断线恢复已完成内容"的承诺直接冲突。
**修法**：保存逻辑移入 `finally`，或在产出 `run_completed` 前先落盘。

### B4. Wiki 后台线程吞掉所有异常，run 永久卡在 planning
`service/kb_service.py:808-841`
worker 里 `except Exception: return`——LLM 失败/磁盘错误后状态不更新、无日志，前端永久轮询。`cancel_wiki_run` 也救不了。
**修法**：异常时 `store.update(run_id, status="failed", error=...)` + `logger.exception`。

### B5. repl.py 引用未定义的 `logger` —— 降级路径变成必死路径
`cli/repl.py:226, 241, 250`
全文件没有 `import logging`，但 MCP/specialist 注册失败的三处 except 分支引用 `logger.warning(...)`。一旦触发 → `NameError` → 外层 except → `sys.exit(1)`，**本该优雅降级的场景变成 REPL 直接退出**。说明这条错误路径从未被测试覆盖。

### B6. 流式重试导致回答内容重复输出
`providers/openai_compat.py:220-256`
`complete_stream` 的重试循环包住了 `yield`：流中途超时后 sleep 重连，**从头重新 yield 全部内容**，用户看到回答重复一遍，session 里也拼接重复。
**修法**：yield 过第一个 chunk 后不再重试，中途失败直接 raise。

### B7. 学习计划的"弱点分析"整条链路是死的（三个 bug 叠加被裸 except 吞掉）
`learning/path.py:104-119`
① 把 DB 路径当 workspace 传给 QuizStore（Windows 反斜杠下退化为 `QuizStore(".")`，还会在错误位置创建空 db）；② 调 `get_weakness_analysis(course=...)` 但该方法不接受参数，必然 TypeError；③ 读 `item['accuracy']` 但字段实际叫 `error_rate`。整段被 `except Exception: return ""` 掩盖——**"薄弱知识点优先安排"这个核心卖点从未生效过**。

### B8. 知识地图空图时 SQL 语法崩溃
`graph/concept_store.py:731-737`
`concept_ids` 为空集时生成 `IN ()` → SQLite syntax error。新建资料库第一次打开知识地图就可能触发。旁边的 `get_subgraph`（794-800 行）做了防护，唯独这里漏了。

### B9. SQLite 连接泄漏：`with sqlite3.connect(...)` 不会 close
`service/usage_service.py:89,110,125`、`research/store.py:32`、`wiki/orchestration.py:52` 等
`sqlite3.Connection` 作为上下文管理器只提交事务不关连接。每条 usage 记录新建连接靠 GC 兜底，Windows + WAL 下会残留文件句柄。`graph/concept_store.py:122-135` 的 `_connect()` contextmanager 是正确范本，照抄即可。

**次级 bug（顺手修）**：工具参数 JSON 解析失败静默变空参数（`core/agent_loop.py:231-234`，应回写错误让模型自纠）；`http_request` 的 result summary 读 `"status"` 写 `"status_code"` 永远为 None（`core/agent_loop.py:29` vs `tools/http_req.py:125`）；判断题 answer 未归一化，LLM 生成"对/错"而非 "true/false" 时用户怎么答都错（`quiz/evaluator.py:86`）；`/api/memory/promote` 的 `dry_run` 参数接受了但强制为 True（`web/backend/routers/memory.py:122-124`）；前端 SSE `parseFrame` 无 try/catch，一个坏帧中断整个流（`web/frontend/src/lib/api.ts:484-493`）。

---

## 3. 重构建议一：杀死并行系统（最高优先级）

这是全项目最大的债。同一职责有两套甚至三套实现在同时运行：

### 3.1 记忆系统：旧系统仍在活跃写入（≈1350 行债）

P5F.1 的新个人学习知识库（`memory/personal_store.py`，质量很高：乐观锁、指纹去重、CJK 2-gram 分词、job 队列）已经上线，但旧系统三个写入口全部在线：

- `tools/memory_tools.py:58,98,241,281`（agent 工具）
- `cli/repl.py:1305,1311`（/memory daily、promote 命令）
- `web/backend/routers/memory.py:90-125`（POST 端点）

且旧 FTS5 用 `tokenize='unicode61'`（`memory/store.py:72-74`）**不分中文**，整段汉字是一个 token → recall 计数长期为 0 → promotion 的 frequency_score 恒 0 → **晋升机制从未有效工作过**。新系统专门做了 CJK 2-gram（`personal_store.py:64-71`），说明你知道这个问题，但没回补旧系统——那就别补了，删。

**退役路径**（两步，不能一刀切）：
1. 立即删：`memory/promotion.py` 整个、vector 双写（`core/memory.py` 的 `_update_vector_store` 等）、`memory/search.py` 的 vector fallback、各处死方法 ≈ 700 行，无用户可见影响。
2. 把 system prompt 注入从 `core/memory.py:build_memory_prompt`（目前无长度上限，全量塞入，token 成本随记忆线性上涨）切到 personal_store 读取（带 max_chars，`personalization_context` 已有 2000 上限的范本）；daily 写入改落 `learning_events`。之后 `core/memory.py`、`memory/daily.py`、`memory/store.py`、`memory/search.py` 全部退役，`memory_service.py` 前 190 行随之删除，只留 legacy 只读迁移一个版本周期。

顺带解决架构环：`core/memory.py` 反向 import `memory/` 5 处，`memory/promotion.py` 又反向 import `core.memory`——core ↔ memory 双向依赖成环，退役后自然消失。

### 3.2 RAG legacy：CLAUDE.md 说"retained but not used"是不成立的

`rag/__init__.py:3-10` eager import 全部 legacy 模块；`core/memory.py` 的向量索引**至今建立在 legacy `LocalVectorStore` + `chunk_text` 上**；`cli/repl.py:208-210` 启动时还实例化 legacy `VectorStoreRouter`；`service/kb_service.py:1693` 搜索时还会合并 legacy 索引结果。

做完 3.1 后可净删 `rag/{dense_store,embeddings,router,vector_store,chunker,ingest}.py` + 对应测试 ≈ **1300 行**，并修正 CLAUDE.md（文档与现实不符是比死代码更贵的债——AI 和人都会被它误导）。

### 3.3 图谱：两套互不相通的图模型

`graph/local_store.py`+`neo4j_store.py`（旧 JSON 图，obsidian sync 写入，114 节点）与 `graph/concept_store.py`（P5E.6 新概念图，27 概念）并存。用户在知识地图里看到的比系统已知的少得多。P5E.6 的产品决策是对的（概念图 = 用户确认的知识），但旧图数据应该：要么作为概念提取的候选来源喂给新图，要么明确退役 Neo4j 适配层（PROJECT_GUIDE 已把"Neo4j 深度产品化"列为暂不做——那 137 行 neo4j_store 现在就可以删）。

### 3.4 Wiki：三代管线并存

`compiler.py`(383 行，旧单文件编译，仅 repl 一处还在用) → `workflow.py`(729) → `orchestration.py`(952)。页面渲染和目标路径推导在 workflow 与 orchestration 里逐字重复（`workflow.py:313-329` vs `orchestration.py:740-756`）。且 `compiler.py:207-211` 解析失败被静默记为"已编译"。
**建议**：repl 那一处改走 workflow，废弃 compiler 编译路径；抽共享的 `render_page_markdown()` / `resolve_target_path()`。

---

## 4. 重构建议二：拆掉四个巨型文件

### 4.1 `cli/repl.py`（2859 行 → 目标 800 行内）
- 80+ 方法的 god class；`run_agent_streaming` 单函数 370 行，3 个嵌套闭包通过 nonlocal 捕获 8 个可变变量 + 6 个 `self._active_*` 字段。
- 命令分发是 17 个 if 分支 + 手工切片，每个子命令 handler 又复制一遍 parse→if/elif→help 结构；帮助文案在 COMMAND_HINTS / print_help / 9 个 print_*_help 三处维护，已经开始漂移（`/quiz generate` 的参数描述三处不一致）。
- 死代码 ≈150 行（`build_thinking_prompt`、readline 补全器、`_terminal_cell_width`、旧渲染路径等，grep 确认无调用点）。
- **拆法**：① 渲染状态机抽 `StreamRenderer` 类（`cli/tool_display.py` 已是同层正面样板——纯函数+状态机+可测，照它的思路走完）；② 命令改注册表 `{"kb": {"sync": (fn, help), ...}}`，补全器、/help、子命令 help 全部从注册表渲染，单一数据源。

### 4.2 `service/kb_service.py`（1791 行）
一个类混 5 个职责：Wiki 页面 CRUD、Wiki 运行编排+预算估算（`estimate_wiki_run` 单方法 108 行）、源目录同步、文档查询、RAG 搜索排序。**拆为** `WikiPageService` / `WikiRunService` / `KBSyncService` / `KBQueryService`。

### 4.3 `web/backend/routers/chat.py`（1460 行）
Router 里写满了业务：基于中文关键词的证据策略路由（344-417）、6 个 prompt 组装函数、memory proposal 的 create-vs-update 决策（833-893）、还直接调 KBService 的私有方法 `_wiki_scope_documents`（277 行）破坏封装。会话加载/保存/artifact 查找样板在 chat/settings/research 三个 router 里复制三份。
**拆法**：新建 `service/chat_run_service.py` 承接 prompt 组装与策略；`MemoryService` 增加 `resolve_proposal()`；抽 `service/chat_session_service.py` 收编三份会话样板。目标：router 只留 DTO 转换，300 行内。

### 4.4 前端 `AppShell.tsx`（790 行，33 个 useState）+ `ChatPage.tsx`（1064 行）
- AppShell 是 33 个 useState 的上帝组件，通过 26 字段的 outlet context 整包下发（ChatPage 一次解构 15 个）；**跨页通信靠 localStorage 当消息总线**（`bobodan:practice-topic`、`bobodan:wiki-scope` 等 15 个 key、47 处读写删，无类型无过期）。
- ChatPage 的 `send()` 单函数 170 行，混合 slash 路由、web 搜索分流、设置意图嗅探、SSE 归约、导航副作用；`artifactSurface()` 用 90 行 if 链内联渲染 10 种 artifact 卡片。
- **引入 zustand 的信号已齐**：拆 `useLibraryStore` / `useSessionStore` / `useUiStore` 三个 store，localStorage 交给 persist 中间件；10 种 artifact 卡片各自抽成 `components/artifacts/*.tsx`（参照已有 WikiPlanCard 模式）；SSE→messages 归约抽 `useChatStream` hook——抽的过程自然产出可单测的纯函数。

---

## 5. 重构建议三：统一横切模式

### 5.1 SQLite 访问层
现状：**8 个独立 SQLite 库 × 4 种连接风格 × 2 种迁移模式**，FTS5 external-content + 三触发器的样板被逐字复制 3 遍（`rag/sqlite_store.py:565-580`、`memory/store.py:66-95`、`personal_store.py:182-201`）。最危险的是 `bobodan.db` 被 quiz/learning/personal 三个 store 共写却互不知晓 schema，且都没设 `busy_timeout`——Web 请求 + 后台 consolidation 线程并发写可能 `database is locked`。
**不需要合库，只需要合模板**：新建 `core/db.py`（~150 行）提供 `connect()`（统一 PRAGMA/WAL/busy_timeout/row_factory）、`ensure_columns()`、`create_fts5_mirror()`，逐个 store 迁移。顺带修复 B9 泄漏。
另：`QuizStore._ensure_db` 的迁移（含 2 个全表 UPDATE）在每次构造时执行，而 QuizService 每请求新建 store——**每个请求都在跑迁移**，纯浪费。

### 5.2 Provider 契约
- `LLMProvider` Protocol 没有 `complete_stream/name/model`，AgentLoop 只能 `getattr` 鸭子探测——接口形同虚设。
- `complete` 与 `complete_stream` 的 retry/backoff 逻辑逐行重复；MiniMax 的 refusal 检测只覆盖非流式路径，而 AgentLoop 优先走流式 → **那段逻辑是死代码**；DeepseekProvider 是只换默认参数的空壳子类，factory 里又把默认值重复一遍。
- 异常全是裸 `raise Exception(...)`，调用方无法区分可重试与配置错误。
- **改法**：Protocol 补全方法；抽 `_with_retries()` helper；定义 `ProviderError/ProviderTimeout`；factory 改注册表。这样以后加 provider 不再复制 90 行样板。

### 5.3 服务层返回信封与错误码
`_ok/_err` 帮助函数复制了 6 份；错误映射靠字符串匹配（`kb.py:520` `409 if "read-only" in message else 404`）；响应信封三种形态并存（原样带 ok / 手动剥 ok / 无 ok）。**改法**：服务层返回结构化错误码 `{"ok": False, "code": "...", "message": "..."}`，`unwrap_service_result` 按 code 映射 HTTP；`_ok/_err` 抽 `service/_result.py`。前端对应的 `reason instanceof Error ? message : 兜底` 三元式复制了 60 次，抽一个 `toErrorMessage()`。

### 5.4 LLM JSON 解析
项目里有 **4 份**近似重复的"剥代码块 + 括号匹配 + 尾逗号修复"解析器（`quiz/generator.py`、`learning/path.py:197-237`、`wiki/compiler.py:75-107`、`wiki/extractor.py:286-301`，`memory_consolidation.py` 还有第 5 份 `_parse_array`）。quiz/generator 的那份质量最好（有重试+纠正提示+失败分类），抽成 `core/llm_json.py` 公共 util，其余全部替换。

### 5.5 掌握度口径
"掌握"的判定散落 6 处、有两个互相矛盾的口径（mastery.status vs quiz error_rate）。收敛到 scheduler 一个 domain 函数，其余处调用。

---

## 6. 功能与体验建议

按 PROJECT_GUIDE 第 9 章的判断标准（是否改善学习闭环）排序：

### 6.1 检索降级必须可见（直接改善信任）
实测无 Ollama 时语义查询返回 0 条且无任何提示。按你自己的交互原则"反馈引导行动"，响应应携带 `retrieval_mode: "fts_only"` 之类的结构化字段，前端显示"当前为关键词检索，未匹配到资料。试试更具体的关键词，或启用向量检索"。这和 P5G.0 的"提取完整性报告"是同一个哲学：**静默的空结果比错误更伤信任**。工作量小（service 层已知道 embedding 是否可用），建议并入 P5G.0。

### 6.2 RAG 主库的中文检索质量
FTS5 对长中文短语命中率低的问题不只在旧记忆库。`personal_store.py` 的 CJK 2-gram 方案已被验证，建议评估把它应用到 `rag/sqlite_store.py` 的 chunks_fts（需要重建索引，`.knowledge/` 本来就是可重建的）。这是对"基于用户资料回答"这个核心价值最直接的改善。

### 6.3 间隔重复升级到 SM-2（修完 B1 之后）
现在是固定 1/3/7/14 + 线性 score 夹逼。SM-2 约 30 行代码，schema 只需加 `ease_factor`、`interval` 两列，`scheduler.py` 的 docstring 自己已经写了 upgrade path。这直接决定"复习"页面的长期价值——固定 14 天封顶意味着半年后用户的到期队列会堆积失真。

### 6.4 错题重练走模型出题（对应你之前的反馈）
备忘中记录过：quiz start 太僵硬、错题复习应走模型出题。现在 Review 聚合了错题但"继续生成针对性练习"仍是按概念重新出题。建议：错题重练时把原题 + 用户的错误答案喂给 generator，生成"针对同一概念、不同问法"的变式题——这才是错题本的价值，也是和刷题 App 的差异点。

### 6.5 CLI 渲染 `**` 符号问题（对应你之前的反馈）
模型输出的 Markdown 粗体符号在终端未渲染。修复位置在 `cli/repl.py` 的流式渲染路径——流式 delta 逐段输出无法等完整 Markdown，建议维持一个轻量的行级状态机（成对 `**` 转 ANSI bold）。这也是抽 `StreamRenderer` 的顺手收益。

### 6.6 文案语言统一
用户可见文案中英文严重混杂：同一个 `/memory` 命令里 "Saved memories:" 和"今日暂无每日记忆"并存；`agent_loop.py` 达到迭代上限是中文、工具被禁用是英文；`/exit` 是 "Goodbye!"。产品定位是中文用户，**统一中文**，一次 grep 扫过去即可。前端 2.5 万+ 中文字符硬编码可接受（本地中文工具），但 `SETTINGS_PHRASES` 这种"文案即逻辑"（40 个中文短语当意图识别规则，`ChatPage.tsx:36-40`）必须和展示文案分离，否则未来改文案就会破坏功能。

### 6.7 知识地图冷启动
新图只有用户确认的 27 个概念，旧图谱 114 个节点的信息没有利用。建议：概念提取时把旧 graph 的 Concept/RELATED_TO 数据作为候选来源之一（标注"来自早期索引"），让用户批量审查——比让用户从每份资料重新提取快得多，也符合 P5E.6"候选→审查→写入"的既定流程。

### 6.8 P5G 顺序确认
PROJECT_GUIDE 定的 P5G.0（提取完整性）→ P5G.1（单进程）→ P5G.2（Electron）顺序是对的，不用改。唯一建议：**把本文档第 2 节的 B1-B4 和第 3.1 节旧记忆退役排在 P5G.0 之前**——发布前修正确性 bug 的成本远低于发布后。

---

## 7. 工程质量建议

1. **Python 没有任何 lint 配置**（无 pyproject.toml/ruff），前端**没有 ESLint**（代码里却出现了 `eslint-disable` 注释，说明想有）。B5 那种 NameError 和前端 effect 依赖缺失正是 lint 一秒能拦的。建议：`ruff`（含 F821 未定义名称、自动 import 排序）+ 前端 `eslint + react-hooks` 插件，半天工作量。
2. **错误路径测试缺失**。1238 个测试基本都是 happy path + 边界，B5（logger NameError）、B1（mastered 复习路径）、B6（流中断重试）都属于"一条针对性测试就能拦住"的类别。建议每修一个第 2 节的 bug 都附带一条回归测试。
3. **前端单测约等于零**（2 文件 5 case，vs 巨型组件 1000 行裸奔）。不必追覆盖率，优先给这几个纯逻辑补 20-30 个 case：SSE 分帧归约、`looksLikeSettingsChange`（会劫持用户消息的启发式）、@mention 解析、日期分组。第 4.4 的组件拆分会自然产出这些可测函数。
4. **路由层加 ErrorBoundary**（当前任何渲染异常 = 白屏整个 app）。
5. **性能低垂果实**：每次搜索重建全套 RAG 对象并重跑 105 行 DDL + 重新 probe Ollama（最多 6 秒超时，`rag/retriever.py:48-76`）→ service 层按 workspace 缓存 Orchestrator；`_hydrate_texts` N+1 查询改 `WHERE id IN (...)`；wiki 文档批量读取 N+1 开库（500 文档 = 500 次 init_db）加批量方法。
6. **每轮对话 deepcopy 整个 session**（`cli/repl.py:684-700`）长会话下是 O(全部历史)；且超时后 daemon 线程仍在执行工具，文件副作用照常发生，"Session not modified" 提示有误导性——至少把提示改诚实。

---

## 8. 建议执行顺序

```text
第一批（1-2 天）：修正确性 bug
  B1 复习循环（1 行 SQL + 测试）
  B2 批改解析失败不判错
  B3 SSE 保存移入 finally
  B4 wiki worker 异常落状态
  B5 repl logger（1 行 import）
  B8 空图 SQL 短路
  + ruff / eslint 上线（拦住下一批 B5）

第二批（3-5 天）：还最大的债
  旧记忆系统退役第一步（删 promotion + vector 双写，~700 行）
  RAG legacy 切断依赖并删码（~1300 行）
  core/db.py 统一连接模板（顺带修 B9）
  修正 CLAUDE.md 与现实的偏差

第三批（1 周）：拆巨型文件
  chat.py router → chat_run_service（顺带修 B3 的架构根因）
  kb_service 四拆
  repl.py：StreamRenderer + 命令注册表（顺带修 6.5 的 ** 渲染）
  前端 zustand 三 store + ChatPage 肢解 + 纯函数单测

第四批：回到 PROJECT_GUIDE 主线
  P5G.0 提取完整性（并入 6.1 检索降级可见性）
  6.2 RAG 中文分词 / 6.3 SM-2 / 6.4 错题变式重练
  → P5G.1 / P5G.2 发布
```

第一批和第二批加起来约一周，删掉约 2000-2700 行代码、修掉全部正确性 bug。**这是进入 P5G 发布前性价比最高的一周。**

---

## 9. 值得保留和表扬的部分

避免只报忧：这些设计不要在重构中弄丢。

- `Attribution + SourceRef` 统一归因贯穿 Chat/Practice/Review，前端不从自然语言猜引用——这是全项目最好的架构决策。
- `memory/personal_store.py`：乐观锁 revision、指纹去重、CJK 2-gram、带 BEGIN IMMEDIATE 抢占的 job 队列——新代码的质量标杆，退役旧系统时以它为范本。
- `cli/tool_display.py`：纯函数 + 状态机 + 专为可测性抽出，repl.py 拆分照它做。
- `tools/http_req.py` 的 SSRF 防护（重定向逐跳复查）、`core/trace.py` 的脱敏、路径穿越防护（`_is_within_workspace` 用 commonpath）——安全基本功扎实，审查未发现注入或密钥泄漏。
- 前端 SSE 分帧（残帧回填 + 跨 chunk 测试）是前端质量最高的一段。
- 出题的 attribution 确定性保留（不让 LLM 编 source 字段）、`local_extension` 诚实标注——正是 PROJECT_GUIDE"不把 AI 常识伪装成用户资料"的正确落地。
- Playwright 75 case 认真覆盖了桌面/窄屏/移动端。
