# Bobodan 技术缺陷审计报告

> 审计日期：2026-09-14
> 审计方式：三路并行静态代码审计（agent 运行时与 provider / 数据层与一致性 / web 后端与前端）+ 项目 ROADMAP 自认技术债交叉核对
> 审计范围：`core/`、`providers/`、`tools/`、`agents/`、`rag/`、`graph/`、`memory/`、`service/`、`knowledge/`、`web/backend/`、`web/frontend/src/`、`cli/`
> 可信度说明：全部结论可定位到文件与函数。标注「待验证」的条目需运行时确认。
> 用途：优化 backlog。按主题归并，非按审计来源归并；同一问题被多份报告独立命中时标注「多路印证」。

---

## 0. 统计与总览

| 严重度 | 数量 | 说明 |
|---|---|---|
| 严重（P0） | 15 | 影响用户数据、安全边界或核心可用性 |
| 中等（P1） | 36 | 性能、并发、健壮性、契约一致性 |
| 轻微（P2） | 33 | 工程卫生、死代码、增长债 |
| 测试盲区 | 12 | 关键路径无测试，导致缺陷长期潜伏 |

### 三条贯穿性判断

**判断一：不缺架构，缺"接线"。**
好几套为优化而写的机制（hooks、上下文压缩、事件重放、权限门）**实现完整、单元测试通过，但生产路径从未启用**。测试给了"已完成"的错觉，用户实际享受不到。这是本审计最值得警惕的一类问题——它不会报错，只会让投入白费。

**判断二：写路径装了很多门，"删路径"和"并发路径"几乎是敞开的。**
项目对"写入事实"非常克制（证据门禁、确认卡、检查点、10 版快照），但对删除（外键、孤儿数据、级联）和并发（多标签页、多线程、多进程写同一份数据）几乎没有防护。

**判断三：取消机制整体缺失。**
从 CLI 到 Web，从工具到 specialist，没有一条完整的取消传播链。用户看到的"停止生成"在服务端基本无感，token 会继续烧，后台任务会继续写状态。

---

## 1. 严重缺陷（P0，15 条）

### A 组：取消与中断（3 条）

**P0-1 客户端断线不取消 LLM 运行，token 继续烧**
- 位置：`web/backend/routers/chat.py::create_run` 的 `event_stream()`、`web/backend/sse.py::iterate_on_stream_lane`
- 触发：关闭标签页、网络断开、点"停止生成"（前端 `ChatPage.tsx:1048` 只 `abortRef.current?.abort()`）
- 影响：全仓无取消令牌（grep `cancel|stop_event|should_stop` 无命中）；`iterate_on_stream_lane` 未 try/finally 关闭底层同步生成器；`event_stream` 的 `finally` 只做 `persist_session()` + `emitter.clear()`，**从不 `close()` 掉 run_stream 生成器**。停止依赖 GC 时机，`anyio.to_thread.run_sync` 默认 `abandon_on_cancel=False`，正在跑的 provider HTTP 调用不会中断。多标签页会各留一个僵尸 run。
- 修法：给 AgentLoop 传 cancel event，`finally` 显式 `events.close()`，`to_thread` 用 `abandon_on_cancel=True`。
- 多路印证（web 审计 + 运行时审计 + ROADMAP H-R2 方向）

**P0-2 specialist 超时无法真正取消，后台继续跑并写状态**
- 位置：`agents/runner.py::run_specialist`
- 触发：超过 `cfg.timeout_seconds`（doc_reader 60s / planner 120s）
- 影响：`Future.cancel()` 对已开始执行的任务无效，线程照跑。父级已收到 timeout 结果并可能换路，后台旧任务仍在发 LLM 请求、仍执行工具（planner 会写 learning store），产生重复副作用；多个 specialist 并发时争抢同一 SQLite 库。**超时语义是假的**。
- 修法：协作式取消（cancel event 贯穿）或子进程隔离。

**P0-3 无统一取消链路（工具 / 线程池 / CLI 同病）**
- 位置：`settings.py::test_provider`/`test_search_provider`、`chat.py::generate_session_title`、`cli/repl.py::run_agent`
- 触发：任何超时或 Ctrl+C
- 影响：`executor.shutdown(wait=False, cancel_futures=True)` 无法取消已在执行的任务，线程跑到自身超时（**线程泄漏**）；CLI 的 agent 跑在 daemon 线程，超时/Ctrl+C 只跳出消费循环，**真线程继续烧 token**。
- 修法：统一取消原语，穿透到 provider 层。

### B 组：安全边界（3 条）

**P0-4 静态托管路径穿越，可读本机任意文件**
- 位置：`web/backend/static.py::spa_fallback`
- 触发：`GET /C:/Windows/win.ini`（Windows 上 `Path(dist) / "C:/..."` 整体替换为绝对路径）；`GET /..%2f..%2f<file>`（uvicorn 默认不归一化）
- 影响：绕过 dist 边界读取任意文件；`tests/test_static_hosting.py` 无穿越用例。
- 修法：`candidate.resolve()` 必须位于 `dist.resolve()` 之内，否则 404（三行改动）。
- **已由本次审计实测代码确认。**

**P0-5 工具入参无 schema 校验，模型可覆盖 `workspace` 实现沙箱逃逸**
- 位置：`tools/base.py::execute_tool`（`call_args = dict(args)` + `setdefault("workspace", ...)`）；`tools/file_ops.py`、`tools/dir_ops.py` 等均接受 `workspace` 形参
- 触发：模型在 tool call 里带额外 `workspace` 键（schema 未声明但 `execute_tool` 不校验、照单全收，`setdefault` 只填缺省）
- 影响：`read_file(path="C:/Windows/win.ini", workspace="C:/")` 可读任意文件，`write_file` 同理可写任意路径。**沙箱的根不该靠模型自觉**。
- 修法：参数白名单过滤（只接受 schema 声明的键）+ 注入参数覆盖模型值。

**P0-6 写保护缺失 + trace 明文泄露凭证**
- 位置：`tools/file_ops.py::write_file`（workspace 内任意路径可覆盖，无确认/白名单）；`tools/base.py::DENY_READ_PATTERNS`（只比 basename，`.git/config`、`.session/<id>.json` 内部文件不拦）；`core/trace.py::_redact_obj`（只按字段名匹配）
- 触发：模型调 `write_file` 覆盖 `.knowledge/knowledge.db`、会话文件、资料原文；`http_request` 带 `Authorization` header → header 值进 `args`，trace 里 `headers` 不是敏感字段名，**明文落盘**
- 修法：写路径白名单 + 敏感值按内容模式脱敏（Bearer/token 形态）。

### C 组：上下文与 token 管理（4 条）

**P0-7 中文 token 估算系统性低估约 4 倍**
- 位置：`core/session_compactor.py::estimate_tokens`（`CHARS_PER_TOKEN = 4`）、`core/memory_injector.py::estimate_tokens`（同样 4）
- 触发：任何中文长会话或中文个人知识注入
- 影响：中文约 1 字≈1 token，按 1 字=0.25 token 估 → `should_compact` 永远迟钝；**1500 token 的记忆预算实际能塞进约 6000 token**。对中文优先的学习助手，会直接撞 provider 上下文上限报 400。
- 修法：按字符类型分档估算（CJK 按 1:1，ASCII 按 1:4）。

**P0-8 上下文压缩是死代码；真触发时会切断 tool 配对**
- 位置：`core/agent_loop.py::AgentLoop.__init__`/`_build_context`；调用方 `service/agent_service.py::run_stream`、`cli/repl.py` 都不传 `context_window`；`core/session_compactor.py::project_context`
- 触发：任意长会话
- 影响：三重问题。① 压缩永不发生，长会话只能靠 `max_messages` 条数硬删（默认 `None`，很多路径没设）→ 死代码。② 即便传了，`checkpoint` 默认 `None`，`project_context` 丢掉中段历史且**不留任何摘要**，静默丢失上下文。③ `project_context` 用 `rest[-tail:]` 切尾，落脚点可能是 `role=tool` 消息，配对的 `assistant(tool_calls)` 被切掉 → 严格 provider 直接 400。
- 修法：接线上 context_window；切点对齐 turn 边界；无 checkpoint 时不允许压缩。
- 多路印证（运行时审计 + ROADMAP H-R2.6）

**P0-9 工具结果全量回填 session，无大小上限**
- 位置：`core/agent_loop.py::_execute_tool_calls` → `session.add_tool_message(tc.id, result.content)`；唯一有上限的是 `tools/file_ops.py::read_file`（1MB）
- 触发：`rag_search`（同一批 chunk 正文在 JSON 与格式化文本里**重复序列化两遍**）、`list_dir`（大目录逐条列 size）
- 影响：单条 tool 结果可达上万字符直接进上下文；结合 P0-7 会很快击穿真实窗口。trace 有 500 字符上限，会话里没有。
- 修法：per-tool 结果上限 + 超限摘要；rag_search 去掉重复序列化。

**P0-10 无总请求/总回合超时，只有 per-read 超时**
- 位置：`providers/openai_compat.py`（`httpx.Client(timeout=...)`）；`core/agent_loop.py` 的 `max_iterations` 只限轮次不限墙钟；`web/backend/routers/chat.py::event_stream` 无服务端上限
- 触发：provider 以"滴灌"方式持续发小 chunk
- 影响：只要不断有字节就不超时，一个回合可无限拖；客户端网络抖动也拿不到兜底。
- 修法：overall deadline（墙钟）+ 回合级预算。

### D 组：数据一致性与破坏不可逆（5 条）

**P0-11 删除有关联的概念会撞外键，接口 500**
- 位置：`graph/concept_store.py::delete_concept`、`service/concept_service.py::delete_concept`（无 try/except）
- 触发：`DELETE /graph/concepts/{id}`，只要该概念在 `relationships` 里出现过（确认过候选、手动建过关系必然产生）
- 影响：`relationships.from_id/to_id REFERENCES concepts(concept_id)` 未声明 `ON DELETE`，默认 NO ACTION；`open_connection` 又强制 `PRAGMA foreign_keys=ON` → `FOREIGN KEY constraint failed` → 用户侧 500，**概念删不掉**。测试只覆盖了"无关系概念删除"，恰好避开失败路径。
- 修法：表加级联，或服务层先删关系（代价最小）。

**P0-12 变更检测把"扫描不到的源"一律判为已删除**
- 位置：`obsidian/sync.py::sync_sources`（`deleted_sources = [s for s in old_state if s not in new_state]`，扫描用 `os.walk` 静默吞错）
- 触发：网络盘/外接盘瞬时断开、权限变化、符号链接失效、扫描中途异常
- 影响：该文档的 `documents`/`chunks`/`directory_entries` 被级联删除、Qdrant 向量被清、概念证据标 stale。文件还在时下次 sync 能重建索引，但**概念证据修复依赖 excerpt 精确匹配**，匹配不上就永久 stale。静默数据抖动。
- 修法：删除确认（连续两轮未扫到才判删）或容错重扫。

**P0-13 用户原始资料是非原子写入**
- 位置：`service/document_edit_service.py::_write_file`、`_record_version`（均 `open(path,"w")` 直写）；`service/document_proposal_service.py::_write_new_document`
- 触发：编辑/回滚/应用 AI 提案期间崩溃、断电、磁盘写满
- 影响：`raw/` 被定位为"不可变证据层"，直写可能把用户原文截断/写坏；快照写一半则回滚源也不完整。项目里已有 `wiki.reliability.atomic_text`（临时文件 + replace），**这里没用**。
- 修法：复用 atomic_text。

**P0-14 同步无事务边界，SQLite 与 Qdrant 双写无一致性保障**
- 位置：`obsidian/sync.py` 主循环（各步独立 commit，之后才写 Qdrant，`_save_state` 最后落盘）
- 触发：循环中途异常/崩溃；或 `qdrant.delete_by_filter` 成功而 `upsert` 失败
- 影响：出现"文档行在、chunks 为空/半量"或"向量集合与 SQLite 不一致"。最坏情况 `_save_state` 已写而内容未落库 → 下一轮判为未变化，**损坏长期留存且不自愈**。
- 修法：单文档事务边界 + 跨存储补偿记录。

**P0-15 Qdrant local 模式进程内单实例锁冲突**
- 位置：`rag/qdrant_store.py::_get_client`（local 模式 `QdrantClient(path=...)`）、`rag/retriever.py::_retrieval_pipeline`（按 workspace 缓存长期存活 client）、`obsidian/sync.py`（自建独立 QdrantStore，非取自缓存）
- 触发：向量可用时，Web 检索管线已持有某 workspace 的本地 client，此时后台导入/编辑触发 sync，sync 又对同一路径开第二个 client
- 影响：qdrant-client local 模式禁止同路径多实例 → 抛异常，同步或检索失败；缓存只在少数入口清理，`sync` 不调 `clear_retrieval_cache`。表现为偶发"检索不可用/导入失败"。
- 修法：统一 Qdrant 生命周期（sync 复用缓存管线）。

---

## 2. 中等缺陷（P1，36 条）

### 上下文与推理
- **P1-1 ReAct 无规划/无回溯/迭代硬截断**：`core/agent_loop.py`，`max_iterations=8` 超限即返回"工具调用次数过多"。ROADMAP E11（单循环契约：无工具轮=finish、探索预算 + 3 轮结算期、截断续写）已立项未做。
- **P1-2 工具无路由，20+ 工具全量喂模型**：选错率随工具数上升。ROADMAP H-R2.5（工具目录延迟装配 + BM25 工具搜索）未做。
- **P1-3 prompt 缓存友好性未完成**：ROADMAP E12（具名块字节稳定 + KB seed 预检索进末尾 user 消息）未做。
- **P1-4 只读工具白名单过窄**：`core/agent_loop.py:READ_ONLY_TOOLS` 仅 4 个（rag_search / concept_map_query / concept_map_status / knowledge_status）；`read_file`、`list_dir`、`learning_progress` 等明明只读却串行。
- **P1-5 并行度硬编码**：`MAX_PARALLEL_TOOLS = 2`，不可配置。
- **P1-6 并行等待用顺序遍历 + 异常会中断整批**：`for future in futures: future.result()`（非 `as_completed`），且 `future.result()` 抛异常会丢掉整批工具结果。

### 取消与并发
- **P1-7 并行去重缓存竞态 + 测试假绿**：`core/agent_loop.py::_run_single_tool`（查缓存 → 执行 → 写缓存三步非原子），同批重复只读调用会各自 miss 各自执行；`test_read_only_tool_dedup` 靠线程调度侥幸通过。
- **P1-8 会话文件并发读改写竞态 + 非原子写**：`core/session.py::save_to_file`（`open(path,"w")` 直写，无锁）。两标签页/两请求操作同一 session → 后写覆盖先写、或读到半截 JSON 崩掉。**项目里 preference/library 都用了 `_atomic_json + os.replace`，唯独会话是裸 JSON**。
- **P1-9 长任务无超时/不可取消**：`kb.py::sync`、`libraries.py::sync_library`、`chat.py` wiki 系列、`graph.py` 抽取、`settings.py::fetch_provider_models` 均为同步路由无请求级超时。
- **P1-10 ThreadPoolExecutor 线程泄漏**：`settings.py::test_provider`、`chat.py::generate_session_title` 每请求新建 executor，超时无法取消已在执行的任务。
- **P1-11 悬空 tool_call 无修复路径**：`core/agent_loop.py::run_stream`（`_execute_tool_calls` 抛异常时）；pause 路径故意不给 ask_user 留 tool result。用户不 resume 而直接发下一条 → session 里 `assistant(tool_calls)` 无配对 tool 消息 → 严格 provider 400。
- **P1-12 跨 scope 记忆确认非原子**：`memory/personal_store.py::confirm_candidate`（create + delete + 回写候选三段独立事务），崩溃窗口产生重复或丢失。
- **P1-13 一次作答跨子系统写入非原子且失败被吞**：`service/quiz_service.py::submit_answer`（attempt → learning_event → mastery → summary 各自连接；掌握度/事件失败只 `logger.warning`）。错题簿与掌握度会漂移。
- **P1-14 `preference_service.patch` lost update 窗口**：读 revision → 写无锁，两并发都通过检查后各自写。

### 死代码与未接线
- **P1-15 hooks 体系生产零注册**：`core/hooks.py` 全套；grep `register_hook(` 只出现在 `tests/`。文档宣称承载权限检查、记忆注入、结果消毒等，**运行时一个都没生效**（记忆走 memory_injector 直调）。真正生效的权限只有 `allowed_tool_names` 与 specialist 工具过滤。
- **P1-16 specialist 只在 CLI 可用**：`tools/agents.py::register_delegate_tools` 只在 `cli/repl.py:238` 调用，**Web 后端未注册** → 浏览器里用不到三个子 agent。能力两端不对等。
- **P1-17 事件重放端到端不存在**：`web/backend/routers/chat.py::replay_stream` + `StreamStore` + 前端 `streamChat` 的 seq 去重是**死路径**（前端全量 grep 无调用）；且 `finally` 每次 run 结束（含断线）就 `emitter.clear()`，**清除时机与重放目的相反**。PROJECT_GUIDE 承诺的"断线续传"实际不可用。

### 检索质量
- **P1-18 向量腿长期缺位且无补建入口**：`obsidian/sync.py`（只有 `changed_sources` 走向量写入）；`rag/sqlite_store.py::get_pending_vector_documents` 除测试外无调用方。导入时 Ollama 没启动 → 记 pending，之后启动再 sync 因内容未变永不出向量 → **语义检索永久缺失**。
- **P1-19 检索质量不可评测**：无评测集/召回指标/query 改写/rerank；`rag/rrf.py` 的 `k=60`、weights 1.0/1.0 是经验值。ROADMAP G4 已立项未做。
- **P1-20 FTS5 索引膨胀 + 排序污染**：`rag/sqlite_store.py::_search_text`（整段 normalized 文本 + CJK 2-gram 都存进 `search_text` 列，`chunks` 体积约翻倍）；`_build_fts_query` 全 token OR 化（召回宽精度低）；`search_fts5` 用 `ORDER BY rank`，`source`/`course`/`title` 与正文等权。
- **P1-21 grep 命中 chunk_id 用 Python `hash()`，跨进程不稳定**：`rag/grep_retriever.py::_matches_to_hits`。`PYTHONHASHSEED` 随机化 → 重启后 id 全变 → 错题变式按 chunk_id 找原文失败。
- **P1-22 grep 检索对 PDF/DOCX/PPTX 静默失效**：`rag/grep_retriever.py::_grep_file`（按文本读，PDF 是二进制）。"原文定位"对占大头的 PDF/PPT/Word 形同虚设，且不报错不给降级提示。
- **P1-23 PDF 页范围失真**：`rag/parsers/pdf_parser.py::_merge_pages`（最多 3 页共享 page 区间）+ `rag/chunker_v2.py::_split_section`（每 chunk 复制整段区间）+ `_merge_short_chunks`（只改 char_end 不动 page_end）。引用页码可能是它并未占据的范围。
- **P1-24 嵌入签名/维度校验/429 退避未做**：ROADMAP G2。无签名版本化 → 换 embedding 后旧向量静默不匹配。
- **P1-25 索引心跳守卫缺失**：ROADMAP G3。本地 embedding 连接黑洞时无进度反馈。

### 数据一致性
- **P1-26 删除文档不清概念候选与抽取运行记录**：`obsidian/sync.py` 删除分支只调 `mark_document_evidence_stale`；已删文档的候选仍可被确认 → 生成引用不存在文档的概念；`concept_extraction_runs` 残留 → `list_extraction_statuses` 报幽灵文档。
- **P1-27 概念删除留孤儿位置；证据永栈 stale 不清理**：`concept_positions` 无外键无清理；`evidence` 无 document 外键 → `concept_graph.db` 单调增长。
- **P1-28 `/kb reset` 不清 manifest.json，也不动概念图谱/research**：`service/kb_service.py::reset` 删除列表不含 `manifest.json` → reset 后 `build_library_summary` 从陈旧 manifest 读出非零 total_files，而 `list_documents` 为空，**状态自相矛盾**。
- **P1-29 个人知识 500 硬上限静默截断**：`memory/personal_store.py::list_by_reference`/`overview`/`export_markdown` 均 500。超 500 条后 `knowledge_count` 永远封顶、关联笔记漏项、导出不完整，都不报错。
- **P1-30 provider 默认值不一致**：`providers/factory.py::_build_minimax`（`MiniMax-Text-01`）vs `providers/minimax.py`（`MiniMax-M2.7`）vs `providers/catalog.py`（`MiniMax-Text-01`）；`agents/specialists/triage.py::default_model` 为 `deepseek-v4-flash`（**待验证是否为真实模型**）。同一 provider 三处默认不同。
- **P1-31 MiniMax 把所有 system 消息合并到最前**：`providers/minimax.py::_convert_messages`。中途注入的 `request_prompt`、guard 纠正消息被上提，位置语义丢失，同一对话在 deepseek 与 minimax 下模型看到的结构不同。

### provider 与可观测性
- **P1-32 流式/非流式解析对畸形 chunk 不健壮**：`providers/openai_compat.py::_parse_stream_chunk`（choices 为 `[]` 时 IndexError）、`_parse_response`（KeyError）；`json.loads` 失败抛裸 `JSONDecodeError`；`data:` 无空格帧被静默丢弃；`httpx.ReadError`/`RemoteProtocolError` 未被归类为 `ProviderError`。
- **P1-33 重试可能重复副作用 + 失败前多睡一次**：`providers/openai_compat.py`（非流式 `complete` 重试不幂等）、`providers/retry.py::retry_delay`（最后一次尝试后仍 `sleep(2**attempt)`，白等 1~4s）。
- **P1-34 `retry_delay` 无上限无 jitter**：`providers/retry.py`，`2**attempt`；多请求重试会同时打上去（thundering herd）。
- **P1-35 specialist 结果渲染误导模型且丢字段**：`agents/runner.py::CONTENT_CAP_SPECIALIST`（截断提示"full result in data.result"，但父模型只看得到 content）；`agents/specialists/doc_reader.py::data_to_content` 只挑 3 个字段，违反 `agents/base.py` 自己的"必须渲染"规则。
- **P1-36 可观测性不足**：`core/trace.py::TraceWriter.write` 不写 `usage_records`/`request_id`，`tool_start` 的 args 不截断（大 write_file 会写爆 trace）；`core/agent_loop.py::run_stream` 安全策略终止仍标 `termination_reason="max_iter"`（监控误分类）；错误事件只有 `str(exc)` 无上下文。

---

## 3. 轻微缺陷（P2，33 条）

### 运行时与 provider
- **P2-1** `core/session.py::_trim_messages` 每次 `add_message` 全量重新分组，长会话 O(n²)；单组超预算时可能把最新一组也丢弃。
- **P2-2** `tools/base.py::_is_within_workspace` 用 `startswith`（大小写敏感），Windows 大小写不敏感文件系统下理论可绕过（`C:\Foo` vs `c:\foo`）。
- **P2-3** `core/agent_loop.py::_run_single_tool` 缓存 key 用注入前原始 args，session 级注入参数（如 `document_ids`）变化时可能命中陈旧结果。
- **P2-4** `agents/runner.py::assert_invariants` 用 `assert`，`python -O` 下被剥离。
- **P2-5** `providers/minimax.py` refusal 检测流式用 `casefold()`、非流式用原文（口径不一致）；词表含 `unable`/`sorry`，正常解释中出现会误丢合法 tool call。
- **P2-6** `core/agent_loop.py::_complete_with_events` 在 tool_call 缺 id 时合成 `call_{index}_{name}`，与后续 tool 消息 id 匹配依赖巧合。
- **P2-7** `tools/rag_search.py::_config_cache` 进程级全局永不失效，用户改配置后仍用旧配置。
- **P2-8** `core/event_bus.py::_matching_ids` 每次 publish 重建两个集合（热路径分配偏多）。
- **P2-9** `providers/factory.py` 与 `agents/specialists/*` 默认模型/超时分散在多处，缺单一真相源。

### web / 前端
- **P2-10** `cli/repl.py::run_agent`：agent 跑在 daemon 线程，超时/Ctrl+C 不停止线程内 run_stream。
- **P2-11** `cli/web_serve.py::find_free_port`：测试占用后关闭再交给 uvicorn，存在端口 TOCTOU 竞态。
- **P2-12** `pages/KnowledgeMapPage.tsx`：`positionsSaveTimer`（800ms）卸载时未 clearTimeout，离页后仍发一次保存请求。
- **P2-13** `components/AppShell.tsx` 健康检查 effect：30s interval 与失败重试链可能并存多条，`timer` 只记录最后一条。
- **P2-14** `web/backend/events.py::to_web_events` 白名单投影，未知 artifact type / SPECIALIST_EVENT / MESSAGE_END 静默丢弃，新增类型到不了前端。
- **P2-15** `schemas.py::ChatRunRequest.web_enabled` 后端从不读取，死字段。
- **P2-16** SSE 响应头缺 `Cache-Control: no-cache` / `X-Accel-Buffering: no`（反代下会被缓冲）。
- **P2-17** `settings.py::_public_settings` 把每个 provider 的 `base_url` 返回前端（可能是内网地址）；api key 未泄漏（这点是对的）。
- **P2-18** `kb_service.py::import_files` 未处理 Windows 保留名（`CON`/`NUL`）与全空名边界。
- **P2-19** `stores/handoffStore.ts` 的 `practiceTopic`/`chatDraft` 持久化后未消费时跨会话残留。
- **P2-20** 前端消息列表**完全没有 `React.memo`**（全 src grep 无命中）：`useChatStream.ts::updateLastMessage` 用 `map` 生成新数组，33ms flush 一次就重渲染整列表 + ReactMarkdown 重解析所有历史回答，长会话流式开销随消息数增长。
- **P2-21** `components/AppShell.tsx` 内联构造 `context={{...}}`，每次重渲染换新对象 → 所有 `useOutletContext` 页面重渲染（同文件 `showKnowledgeContext` 已专门 ref 化，说明知道这个坑但只补一处）。
- **P2-22** `ChatPage.tsx` 会话加载 effect 依赖 `settings.default_provider`/`resolveModelRef`，流式期间 `refreshSettings()` 会重跑 effect → `setMessages(session.messages)` 用磁盘快照**盖掉正在流式的内容**。
- **P2-23** `Session.list_session_summaries` 逐个 `json.load` 完整会话（含整个 messages）只为算 message_count，且 `refreshSessions()` 前端多处频繁触发 → 侧栏卡顿。
- **P2-24** `app.py::resolve_library` 中间件每请求读两遍库注册表 + 每库 `Path.is_dir()` + YAML 解析，无缓存。
- **P2-25** `app.py::lifespan` 对每库串行 `migrate_unnamed_sessions`（O(会话数) 文件遍历）+ 恢复任务，库多时启动慢。
- **P2-26** `StreamStore._buffers` 以 stream_id 为 key 无限增长，只靠 finally 清理。
- **P2-27** `ChatPage.tsx` slash/mention 面板无 `aria-activedescendant`（屏幕阅读器无法播报高亮项）；`role="tablist"` 缺 `aria-controls`/tabpanel 关联。
- **P2-28** `GraphCanvas.tsx`（sigma/WebGL canvas）节点边不可键盘聚焦，知识地图核心交互是鼠标专属。
- **P2-29** `NoticeCenter` 无自动消失计时，错误提示可能长期占屏。
- **P2-30** `create_run` 前置重活（会话加载、KB 列文档、记忆检索、概念状态、技能 prompt 读文件）跑在共享 40 线程池，专用 SSE lane 保护不到。

### 数据层
- **P2-31** FTS 触发器隐患：`rag/sqlite_store.py::insert_chunks` 用 `INSERT OR REPLACE`，`recursive_triggers=off` 时 REPLACE 的删除不触发 `chunks_ad` → FTS5 残留旧 rowid。当前主路径"先删后插"侥幸避开。
- **P2-32** `rag/chunker_v2.py::_merge_short_chunks` 合并后不再校验 `max_chars`（可超上限）；合并保留下游 chunk id，id 与内容不再对应。
- **P2-33** `rag/parsers/__init__.py` 把 `.txt` 映射到 `markdown_parser.parse`，`parse_txt` 是死代码；docstring 与实际标题层级行为不符。
- **P2-34** 存储无限增长：`retrieval_runs`（每次检索一行）、`usage.db`、`.knowledge/research.db`（存整页正文快照）、`.bobodan/traces/*.jsonl`、`.bobodan/wiki/checkpoints`（每次 apply 整目录 copytree）、`.bobodan/proposals/*.json`。全部无清理策略（文档编辑快照的 10 版上限是唯一好例子）。
- **P2-35** 删除策略不一致：`kb_service.delete_document` 便携库归档到 archive，旧工作区走 `os.remove` 永久删除不可撤销。
- **P2-36** 便携库根目录设计为"往这里扔文件"，但 `delete_document` 只允许删 `raw/inbox` 内文件 → 根目录文件"可索引但不可删"。
- **P2-37** 多处 `_ensure`/`_init_schema`/`_ensure_db`/`_init_db` 每次实例化都建表 + PRAGMA；`MemoryService._personal_store()` 每次调用新建 store（`personalization_context` 一次调两次）。
- **P2-38** 迁移不可回滚：各处只用"存在性判断 + ADD COLUMN"，无版本表无 downgrade。`rag/sqlite_store.py::init_db` 以 `"search_text" not in fts_columns` 判断是否重建 FTS，若在 ADD COLUMN 与 rebuild 之间崩溃 → 下次认为无需重建 → FTS 与 chunks 长期脱节。
- **P2-39** `service/library_service.py::initialize` 的 `BOBODAN_LIBRARY.yaml` 用 `write_text` 非原子；`migrate` 异常时只回滚注册表，不回滚已创建目录。
- **P2-40** `rag/rrf.py::rrf_fuse` 每结果两趟线性 `any()`，O(n·m)。
- **P2-41** course 过滤路径不一致：FTS 侧 SQL JOIN 过滤，向量侧逐条 `get_document`；文档已删而向量残留时静默丢弃该命中。
- **P2-42** LOD / 大列表：资料列表、会话列表均无分页（见 P1 分页项）。

---

## 4. 测试盲区（12 条）

1. **并行只读工具无真实并发测试**：`test_read_only_tool_dedup` 依赖线程调度侥幸通过（对应 P1-7）。
2. **provider 健壮性无回归**：缺"choices 为空 / 非 JSON 行 / `data:` 无空格 / 首 chunk 后断流 / httpx.ReadError"用例（对应 P1-32、P1-33）。
3. **中文 token 与压缩端到端缺失**：`test_session_compactor.py` 只用英文小样本（正好掩盖 P0-7 的量纲错误）；无"压缩后 tool 配对是否合法"断言（对应 P0-8）。
4. **无沙箱逃逸负向测试**：没有"模型传 `workspace`/`cwd` 越权"用例（对应 P0-5）。
5. **无悬空 tool_call 恢复测试**：pause 后不 resume、异常中断后的 session 一致性无人测（对应 P1-11）。
6. **无 specialist 超时后子线程仍执行的观测测试**（对应 P0-2）。
7. **无 hooks 生产接线守护测试**：没有断言"生产入口应注册哪些 hook"，所以 hooks 悄悄变死代码没人发现（对应 P1-15）。
8. **无多会话/多线程下 registry 与 session 隔离测试**（对应 P1-16）。
9. **无断线取消测试**：grep `tests/` 无 `ClientDisconnect|is_disconnected`（对应 P0-1）。
10. **无静态托管路径穿越测试**：`test_static_hosting.py` 无穿越用例（对应 P0-4）。
11. **无同 session 并发写测试**（对应 P1-8）；无"删除有关系的概念"测试（正好是 P0-11）。
12. **无真实向量端到端**：向量测试全用 `MagicMock(spec=OllamaEmbeddingClient)`，没有真实 Ollama + Qdrant 回归 → P0-15 这类双 client 冲突在 CI 里永不暴露；无 grep 哈希稳定性测试（对应 P1-21）。

---

## 5. 优化路线建议（分四批）

### 批次 1：止血（代价最小、后果不可逆，建议立即做）
| 条目 | 动作 |
|---|---|
| P0-4 路径穿越 | `spa_fallback` 加 resolve containment（三行） |
| P0-11 删概念 500 | 表加级联，或服务层先删关系 |
| P0-13 原文非原子写 | 复用 `wiki.reliability.atomic_text` |
| P1-8 会话原子写 | 临时文件 + `os.replace` + 每 session 锁 |
| P0-7 中文 token | 按字符类型分档估算 |
| P0-5 沙箱逃逸 | 参数白名单过滤（只接受 schema 声明键） |

### 批次 2：正确性（影响核心可用性）
| 条目 | 动作 |
|---|---|
| P0-1 / P0-2 / P0-3 取消链路 | 引入统一 cancel event，穿透 provider / specialist / CLI |
| P0-8 压缩接线 + 切点对齐 | 传 `context_window`；切点对齐 turn 边界；无 checkpoint 不压缩 |
| P0-9 工具结果上限 | per-tool 截断 + 摘要；rag_search 去重复序列化 |
| P0-12 / P0-14 同步一致性 | 删除确认 + 单文档事务边界 |
| P0-15 Qdrant 生命周期 | sync 复用缓存管线 |
| P1-11 悬空 tool_call | 补桩/清理逻辑 |

### 批次 3：接线与质量（把已写的机制真正通电）
| 条目 | 动作 |
|---|---|
| P1-15 hooks 接线 | 生产入口注册 hook，或用它替换硬编码逻辑 |
| P1-16 specialist 上 Web | web 后端注册 delegate 工具 |
| P1-17 事件重放 | 二选一：接上前端重放并改 clear 时机；或删除整套死代码 |
| P1-18 向量补建 | 加 pending 重试驱动器 |
| P1-19 检索评测集 | 按 ROADMAP G4 建基线 |
| P1-20/21/22/23 检索质量 | FTS 权重、稳定 chunk_id、非文本 grep、页码精度 |

### 批次 4：性能与工程卫生
| 条目 | 动作 |
|---|---|
| P2-20 / P2-21 / P2-22 前端渲染 | memo 化 + context 稳定 + effect 依赖收敛 |
| P2-23 / P2-24 / P2-25 | 会话索引、注册表缓存、启动异步化 |
| P2-34 存储增长 | 各 store 加保留策略 |
| P2-38 迁移版本化 | 引入 schema version + 检查点迁移（ROADMAP H-R0.7） |
| 其余 P2 | 按触碰频率择机 |

---

## 6. 附：项目自认技术债（ROADMAP 对照）

以下条目在 `docs/ROADMAP.md` 中已立项但未实施，与本次审计相互印证：

| ROADMAP 编号 | 内容 | 本次审计对应 |
|---|---|---|
| E11 | AgentLoop 单循环契约（无工具轮=finish、探索预算、截断续写） | P1-1 |
| E12 | prompt 具名块字节稳定 + KB seed 预检索 | P1-3 |
| G1–G3 | embedding 协议泛化 / 签名维度校验 / 索引心跳 | P1-24、P1-25 |
| G4 | 召回评测集（hit@5 + MRR） | P1-19 |
| G5 | PDF 目录四级降级链 | P1-23 相关 |
| H-R0.7 | 数据 epoch 机制（日志化检查点迁移） | P2-38 |
| H-R2.3 | 后台任务统一抽象（deferred results） | P1-13 相关 |
| H-R2.5 | 工具目录延迟装配 + BM25 工具搜索 | P1-2 |
| H-R2.6 | 会话压缩升级（阈值式纯函数压缩、轮中压缩缝） | P0-8 |
| H-R2.7 | 会话打开恢复三件套 + AG-1 JSONL 事件源 | P1-8 相关 |
| F1 / F3 / F4 / F5 | 前端流式正确性（foldEvent reducer、订阅表派生、断线恢复、乐观对账） | P1-17、P2-20 相关 |
| E17 | 资料库文件树（身份迁移约束：`document_id = _stable_hash(source)`） | 未在本次前三份审计覆盖，见 PROJECT_GUIDE §P5G |

> 关键结构约束（ROADMAP 已标注）：`document_id = _stable_hash(source)`，资料身份由路径派生。**重命名/移动文件会改变身份并打断概念证据、题目 source_ids、wiki 来源的整条证据链**。任何展示层改造不得与该约束同期实施。

---

## 7. 一句话总结

**这个项目对"如何写入事实"极度克制（证据门禁、确认卡、检查点），对"如何中止、如何并发、如何删除"却几乎没有防护；同时若干已完成的优化机制停留在测试里，没有接到生产路径。优化的第一原则应该是：先把写了的东西通电，再补上中止、并发与删除这三条腿。**
