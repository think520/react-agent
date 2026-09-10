# Bobodan 参考项目调研报告

> 调研日期：2026-09-02
> 调研方法：三个仓库已克隆到本地，逐文件阅读源码（非仅读 README）。
> 本地克隆路径：
> - `F:\claude projects\DeepTutor`（HKUDS/DeepTutor，Apache-2.0）
> - `F:\claude projects\OpenMAIC`（THU-MAIC/OpenMAIC，MIT）
> - `F:\claude projects\qiaomu-book-reader`（joeseesun/qiaomu-book-reader，MIT，elton-reader 的深度改造 fork）
>
> 结论先行：**三个项目都值得借鉴，且与你已有的产品哲学（来源边界、用户确认门禁、本地优先）高度同构。** DeepTutor 印证并细化了 Bobodan 的教学闭环设想，可直接增强 Chat / Practice / Review；OpenMAIC 提供了一套「单进程就能实现」的轻量多智能体范式，不要被它的云基础设施吓退；qiaomu 补上 Bobodan 最缺的一块——Library 阅读体验与划线批注体系。
>
> **2026-09-02 补充**：新增第九章「前端优化设计借鉴」专项调研——DeepTutor 与 OpenMAIC 的前端实现被逐文件深挖（流式渲染、过程可视化、交互卡、设计系统、工程化），全部映射到 Bobodan 的 `web/frontend`。
>
> **2026-09-03 补充**：新增第十章「RAG 向量化选型：调研与决策」——现状核查（向量腿从未真正运行过）、八引擎矩阵的取舍依据、三个参考项目 embedding/向量库的实际选型（结论出人意料）、三条 embedding 路线的体积实测，以及最终拍板的落地方案。
>
> **使用边界（2026-09-08）**：本文保留调研日的代码快照、机制比较和借鉴编号（D / O / Q / F / G），只作为论据与实现参考。P0 / P1 / P2、FE-P0 / P1 / P2 和第十章的方案均不能直接形成排期；当前工作批次、完成状态和取舍以 [`ROADMAP.md`](ROADMAP.md) 为准，RAG 运行事实以 [`rag_design.md`](rag_design.md) 为准。

---

## TL;DR（最重要的 8 个发现）

1. **DeepTutor 的核心设计宣言与你完全一致**：「模型管教学，引擎管算术」——掌握度门禁、复习调度、判分全部是**无 LLM 调用的纯函数引擎**，agent 每轮先调 `status` 工具读引擎、绝不自作主张推进。这正是 Bobodan「source_ids 确定性保存、模型不能伪造来源」的同一个思想的更完整形态。
2. **DeepTutor 的 Chat 是「单循环」而非多管线**：一轮对话 = 一个循环；调用工具的轮次默认是「过程叙述」，**停止调用工具的那一轮的文本才是最终答案**。探索预算用完后进入 3 轮「结算期」再强制无工具收尾。比「计划→执行→回答」三段式省一半 token，UI 也更简单。
3. **ask_user 是一等公民协议**（DeepTutor 与 OpenMAIC 都独立得出同样设计）：agent 提问即暂停本轮 run，用户下一条消息即答案，交互状态持久化（registered→awaiting_input→answered→graded），断线/崩溃可恢复。这是 Practice「跨轮判分确定性」的基础设施前提。
4. **防模型绕过的三道结构性防线**（DeepTutor mastery）：① 关键参数由服务端注入（模型永远不能填 path_id）；② 检测模型想用纯文本 A/B/C 结束回合时强制重定向回交互卡；③ 交互卡渲染数据**从持久化状态重绑定**而非信任模型输出，并结构化剥离 "(Recommended)" 这类答案暗示。Bobodan 的出题卡应照做，否则模型会在选项里泄答案。
5. **OpenMAIC 的多智能体是「轻 director + 单轮契约」**：每次请求只跑「director 选下一个 agent → 该 agent 执行一步」，多轮循环由客户端串行驱动，SSE 连接天然短、可打断。整张「图」只有两个节点一个条件边，Python 手写 ~100 行，**不需要 LangGraph**。
6. **qiaomu 的划线锚点四元组**：`{block 全局序号, occ 出现次数, pre/post 各 32 字符上下文}` 三级消歧——划线在重排版后仍能精确还原。映射到 Bobodan 即 `{chunk_id, offset, quote, prefix32, suffix32}`，offset 漂移时用前后文兜底。
7. **qiaomu 的「托管区块」同步模型**：划线自动全量重写书笔记的 `## 划线与批注` 区块（按 heading 边界替换，绝不碰用户其他内容），解决了 append 模式的重复与失同步两大顽疾。Bobodan 的「笔记关联资料」可直接套用。
8. **三家都把可靠性当产品功能**：qiaomu 的串行写队列 + 损坏文件「备份并锁定绝不带病覆盖」+ 每日救援目录；DeepTutor 的嵌入签名版本化索引（换 embedding 模型旧索引永不销毁）+ 索引心跳守卫（600s 无进度报可行动错误）。这些Bobodan 都该有。

---

## 一、三个项目速览

| | DeepTutor | OpenMAIC | qiaomu-book-reader |
|---|---|---|---|
| 定位 | 终身个性化 AI 家教（agent-native 学习工作台） | 把任意主题/文档变成「多智能体互动课堂」 | Obsidian 内的中文优先本地电子书阅读器 |
| 技术栈 | Python + FastAPI/WebSocket + Next.js，自研 provider 层，无 LangChain agent 框架 | Next.js 16 + React 19 + LangGraph（仅 2 节点）+ pi-agent-core | TypeScript Obsidian 插件（main.js 11702 行单文件） |
| 体量 | ~20 万行 | ~2800 文件 monorepo | 8 个源文件，核心 747KB |
| 许可证 | Apache-2.0 | MIT | MIT |
| 对 Bobodan | **最贴近愿景**：教学闭环的完整参照 | **优化智能体**：轻量多智能体范式 + eval 方法论 | **Library 阅读体验**：划线/批注/进度/反链的完整蓝图 |

---

## 二、Bobodan 现状基线（调研日快照）

本节描述 2026-09-02 调研时的出发点。功能是否已交付或随后调整，须回到 `ROADMAP.md`、`PROJECT_GUIDE.md` 和专题设计文档核对。

已有且不应被借鉴方案动摇的资产：

- **证据门禁**：知识型回答以 `library_search`/`rag_search` 的原始 chunk 为骨架；`service/evidence_policy.py` + AgentLoop 结束前验证。→ 三个项目都没做到这个强度，**这是 Bobodan 领先的地方，别丢**。
- **出题来源确定性**：模型只能选 `source_ids`，不能编造来源。
- **保守 SM-2** + 掌握度三态（mastered/learning/needs_review）。
- **概念图谱审查门禁**：候选必须用户确认才入图。
- **Skills（SKILL.md）**、SSE（状态/引用/artifact 结构化事件）、服务层 `{ok, code, error}` 契约。

因此下面的借鉴清单以「**增强现有模块**」为主，而不是引入新框架。

---

## 三、DeepTutor —— 教学闭环的完整参照（最重点）

### 3.1 定位与架构

「Lifelong Personalized Tutoring」：统一 Agent 运行时组织辅导/解题/出题/研究/可视化/掌握度练习/沉浸阅读。两层插件模型：

- **Level 1 Tools**：单函数工具，用户只开关 5 个，其余**按上下文自动挂载**（有 KB→挂 `rag`；有附件→挂 `read_source`），映射表在 `deeptutor/agents/_shared/tool_composition.py` L47-59。
- **Level 2 Capabilities**：接管整个 turn 的多阶段管线（chat/deep_solve/deep_question/deep_research/visualize/mastery）。

关键目录：`deeptutor/agents/chat/`（单循环 chat agent）、`deeptutor/learning/`（**纯教学引擎，无 LLM**）、`deeptutor/services/memory/`（三层记忆）、`deeptutor/services/prompt/`（prompts 外置为 `prompts/{en,zh}/*.yaml`）。

### 3.2 核心机制

**（a）单循环契约**（`deeptutor/agents/chat/agent_loop.py` L1-26）：
> 一轮 chat = 一个 agent 循环；调用工具的轮次默认是 narration（过程）；**不调用工具的轮次就是 finish，其文本即最终答案**。

配套：探索预算 + `MAX_SETTLEMENT_ROUNDS=3` 结算期（注入「不要开新搜索，只完成已开始的步骤」）；`finish_reason=length` 不算完成、保留可见前缀续写；空轮 nudge；上下文超预算时把旧工具结果替换为「[较早的工具结果已裁剪…如仍需要请再次调用]」——**只裁剪可再生内容**。

**（b）System prompt 具名块 + 字节稳定**（`prompt_blocks.py`）：system 拆成 `PromptBlock(name, content)` 序列；**检索结果（KB seed）放在末尾 user 消息**而不是 system，保证整个 turn 的 system prompt 字节级不变（prompt 缓存全命中）；日期只注入到「天」粒度，不破坏日内缓存。

**（c）Socratic 人格 = 预置 Persona，不是硬编码**（`deeptutor/services/persona/presets/teacher/PERSONA.md`，全文值得精读翻译）：
> 「Lead with a question. 先解释任何东西之前，先问一个能暴露学习者已有认知的问题。」
> 「Diagnose, don't lecture. 学习者答错时把它当线索：先复述他的推理，再问『如果关键假设变了会怎样』。」
> 「如果你的回复超过 ~200 字，你大概率已经停止教学了。」
> 「把最终答案告诉离答案只差一步的学习者」——列入 avoid。
> 每条回复以一个小追问或小结收尾。

人格优先级裁决（`prompts/zh/agentic_chat.yaml` L30-36）：persona 规定风格与流程优先，通用默认兜底；persona 不能覆盖安全与工具真实性。

**（d）Mastery Path = 硬门禁 + 引擎工具**（`deeptutor/capabilities/mastery/prompts/en/system.md`）：
> 「每个 objective 背后是 HARD mastery gate……每轮 FIRST 调用 `mastery_status`，永远信任引擎选择下一步，绝不猜测。」
> 「引擎未标记 mastered 的 objective，绝不能跳过。」
> 「每个干扰项必须编码一个具体的、合理的误解，且与正确项在长度/具体性/措辞上匹配。绝不给答案提示——选项上不许出现 '(Recommended)'。」
> 「`mastery_quiz` 必须传 `explanation`——它不出现在答题卡上，但随作答记录进题库，是复习错题时唯一的解释。」

**（e）掌握度引擎**（`deeptutor/learning/`，纯函数 + pydantic）：
- 知识点四分类：memory/procedure/concept/design（`models.py` L24-28）。
- memory/procedure 定量门 0.9（注释引 Alpha School "90% before you advance"）；concept/design 用 **Feynman 讲解定性判定**。
- 掌握度 = 近 5 次加权正确率，权重 (0.5,0.7,0.85,0.95,1.0)，**低置信上限 `{1:0.5, 2:0.8}`**——「一次幸运的正确无法宣布掌握」（`mastery.py` L17-37，docstring 说明换 IRT/BKT 只改这一个函数）。
- 复习按知识类型分序列（`scheduler.py`）：MEMORY `[0,1,3,7,14,30,60]`，CONCEPT `[3,7,14,30]`，PROCEDURE `[3,7,14]`，DESIGN `[14,28]`；连对 2 次跳 2 级、错 1 次退 1 级。
- `next_objective` 优先级（`policy.py` L206-288）：**挂起未答问题 > 到期复习 > 模块顺序第一个未掌握点 > 完成**；「门禁即游标」——**推进由已掌握内容计算得出，绝不用 stage counter 字段追踪**。
- 判分（`grading.py`）：choice 精确匹配；short 用 `SequenceMatcher ≥ 0.85`；open 用关键词命中率 ≥ 0.6。`expected_answer` **只存服务端、永不回传模型**；前端投影剥离 explanation/difficulty。

**（f）出题三阶段流式管线**（`deeptutor/agents/question/pipeline.py`）：Phase 1 Explore（带研究与弱项避重）→ Phase 2 Plan（单步输出 JSON 题目模板数组）→ Phase 3 每题独立小循环出题（严格 JSON + 一次 schema 修复重试）。**每题就绪即发 `quiz_question_emitted` 事件，前端立刻渲染**，不等整套完成。

**（g）题库独立于笔记**（`deeptutor/tools/question_bank.py`）：「笔记是学员保存的散文，题库条目是已判分的问题+答案+解析」；工具五动作 overview/list/organize/unfile/bookmark；**类目按名字寻址**（「学员说的是『我的错题集』，不是『类目 7』」）；所有错误返回模型可执行的句子而非异常。

**（h）三层记忆**（`deeptutor/services/memory/`）：L1 = append-only JSONL 轨迹，**只有图章没有正文**（安全、可随时调用）；L2 = 每面一份 Markdown，**脚注引用制**（`[^1]` 指回实体 id），LLM 只发 JSON ops（add/edit/delete + 删除原因枚举 contradicted/superseded/stale/low-signal），每条 ≤240 字符、**禁空话词表**（"mastered, expert, passionate, loves, always, never"）；L3 = 四槽跨面综合（recent/profile/scope/preferences）。`days_ago` 由代码预计算（「模型对 ISO 时间戳做日期算术有时会算错」）。

**（i）RAG 细节**：嵌入签名版本化——换 embedding 模型后按签名开新 `version-N` 目录，**旧索引永不销毁**，查询时返回 `needs_reindex` 提示（`rag/index_versioning.py`）；索引心跳守卫，600s 无进度报错而非永久挂起（`llamaindex/pipeline.py` L49-112，防本地模型黑洞连接）；**KB seed 预检索不替代工具**——进循环前先 hybrid 检索一次注入末尾 user 消息，并明示「可能不完整；不够就用 rag 继续检索」。

### 3.3 对 Bobodan 的借鉴清单

| # | 借鉴什么 | 对应 Bobodan 模块 | 怎么落地 | 参考源文件 |
|---|---|---|---|---|
| D1 | 掌握度「纯函数引擎」分层 | `learning/` + `service/learning_service.py` | 掌握度计算、`next_objective` 优先级（挂起问题>到期复习>第一个未掌握点）、判分做成无 LLM 的 `learning/engine.py`；agent 每轮先调 `learning_status` 工具读引擎 | `deeptutor/learning/policy.py`、`mastery.py` |
| D2 | 低置信上限 + 近因加权 | 掌握度可视化 | 近 5 次加权 + `{1:0.5, 2:0.8}` 置信帽；UI 显示「证据不足以宣布掌握」，防一次蒙对变绿 | `deeptutor/learning/mastery.py` |
| D3 | 知识类型四分类 + 类型化门禁 | Practice/Review | 题目/知识点加 `kind` 字段；concept 类走 Feynman 讲解定性判定而非对错 | `deeptutor/learning/models.py` L24-28、`policy.py` L32-45 |
| D4 | 单循环契约（无工具轮=答案） | `core/agent_loop.py` | 循环加探索预算 + 3 轮结算 + 强制无工具收尾；流式文本用 `call_role` 元数据区分 narration/finish | `deeptutor/agents/chat/agent_loop.py` |
| D5 | prompt 具名块 + KB seed 进末尾 user 消息 | `core/agent_loop.py` 的 prompt 组装 | system 拆具名块且全 turn 字节稳定；检索结果拼 `[Knowledge Base Context]` 到末尾 user 消息 + 「不够就继续检索」——省 token 且缓存友好 | `deeptutor/agents/chat/prompt_blocks.py` |
| D6 | ask_user 暂停/恢复 + 交互状态持久化 | Chat/Practice | 交互生命周期 registered→awaiting_input→answered→graded 落 SQLite；断线后可恢复作答 | `deeptutor/tools/ask_user.py`、`learning/models.py` L193-224 |
| D7 | 防模型绕过三道防线 | Practice 出题卡 | ① 服务端注入关键参数；② 纯文本 A/B/C 收尾检测重定向；③ 卡片数据从持久化状态重绑定 + 剥离 "(Recommended)" | `deeptutor/capabilities/mastery/loop.py` L39-241 |
| D8 | 出题三阶段流式管线 | `service/quiz_service.py` | Explore→Plan→逐题生成；每题就绪即经 SSE 渲染；每题带 explanation 入错题库 | `deeptutor/agents/question/pipeline.py` |
| D9 | 题库/错题库按名寻址 + explanation 随题入库 | quiz SQLite | 类目按名字建；错题必带 explanation（复习时唯一解释）；工具错误返回可执行句子 | `deeptutor/tools/question_bank.py` |
| D10 | Socratic persona 预设 | skills/（新增 `socratic-tutor` skill） | 翻译 `teacher/PERSONA.md` 为中文预设 + partner_turn_policy 优先级规则（persona 优先、通用兜底、不覆盖证据门禁） | `deeptutor/services/persona/presets/teacher/PERSONA.md` |
| D11 | 三层记忆 | `memory/personal_store.py` | L1 事件轨迹（只存图章）、L2 面级事实（脚注回链 + LLM 只发 JSON ops + 禁空话词表）、L3 综合 | `deeptutor/services/memory/` |
| D12 | 嵌入签名版本化 + 索引心跳守卫 | `rag/qdrant_store.py`、`rag/sqlite_store.py` | 换 embedding 时按签名建新目录不销毁旧索引；索引线程 600s 无进度报可行动错误 | `deeptutor/services/rag/index_versioning.py`、`pipelines/llamaindex/pipeline.py` |
| D13 | KB seed 预检索不替代工具 | Chat RAG 首跳 | 进循环前对用户消息先检索一次注入上下文，明示「不完整可继续检索」——解决冷启动检索质量 | `deeptutor/agents/chat/agentic_pipeline.py` L1282-1320 |

---

## 四、OpenMAIC —— 轻量多智能体范式（优化智能体）

### 4.1 定位与架构

**Open Multi-Agent Interactive Classroom**：把文档一键变成「AI 老师 + AI 同学」实时讲课、白板画图、出题、带 PBL 项目的课堂。两条产品线：经典模式（一次生成整门课，课堂多 agent 演出）+ Pro 工作台（chat-first 建课 agent，持久会话可恢复可插话）。

数据流（课堂模式）：浏览器 zustand store 持有全部状态 → 每轮把 `messages + storeState + directorState` 全量 POST → 服务端跑**一次** director→agent 单周期 → SSE 流回 → 客户端执行动作并决定是否发起下一轮。

### 4.2 核心机制

**（a）Director 模式 + 单轮契约**（`lib/orchestration/director-graph.ts`）：
- LangGraph 只有两个节点一个条件边：`START → director ─(next)→ agent_generate → END`。
- **每次 HTTP 请求最多跑一个 director→agent 周期**；多 agent 讨论由客户端串行发请求驱动（`lib/chat/agent-loop.ts` 的 while 循环：刷新状态 → POST → 消费 SSE → 退出条件 cue_user / director END / 连续 2 次空回复）。
- Director 决策：单 agent 场景纯代码零 LLM；多 agent 才让 LLM 输出 `{"next_agent": "<id>|USER|END"}`，解析失败默认 END（fail-closed）。
- Director 提示词注入：agent 列表（含 priority）、本轮已发言摘要、白板状态（**元素 >5 时警告「白板太挤，考虑路由给会整理的 agent」**）、学生画像。模板外置 `lib/prompts/templates/director/system.md`。

**（b）Agent 卡片，role 决定能力**（`lib/orchestration/registry/types.ts` L9-95）：
`AgentConfig { id, name, role, persona, avatar, color, allowedActions[], priority }`；`role ∈ {teacher, assistant, student}` 且 `ROLE_ACTIONS` 由 role 推导能力集。内置 6 个默认 agent 的 persona 写法值得逐字学（教学风格+语气+行为约束的紧凑系统提示词）。

**（c）Peer-context 防复读注入**（`lib/orchestration/summarizers/peer-context.ts`，全文仅 33 行）：每个发言者的提示词尾部注入「本轮已发言者 + 各自 300 字预览 + 5 条硬规则（不许重复问候/复述，必须新增价值、建设性质疑）」。**这是防「复读机式协作」的关键小件。**

**（d）确定性状态摘要器**：把 agent 做不好的检查用纯代码算好再喂回——白板冲突检测（bbox 重叠 ≥30%、线穿元素）生成「⚠ 必须先处理再新增」提示块（`summarizers/whiteboard-conflicts.ts`）；幻灯片状态压成单行（文本 60 字截断、代码行共享预算）。**思路对应 Bobodan：把 RAG 引用覆盖检查、概念图谱环检测做成 conflict summarizer 喂回 agent。**

**（e）SSE 事件协议**（`lib/types/chat.ts` L435-488）：判别联合 `agent_start / text_delta / action / thinking / cue_user / done / error`；`done` 事件把 director 累积状态回传客户端供下一轮携带；**每 15s 发 `:heartbeat` 注释帧防代理断连**（`app/api/chat/route.ts` L100-120）；错误也走流内 `error` 事件。

**（f）ask_user / cue_user**：agent 用 `ask_user` 提问即结束本轮 run（`lib/server/agent-runtime/ask-user.ts`），问题信封 `{question, options?, multiSelect?}`，用户下一条消息即答案——**刻意不做 answer 关联 id**（旧前端不认识该事件也无损，向后兼容）。运行中用户消息**先写持久日志再投递**（crash 不丢），空闲则排队驱动下一次 run。

**（g）阈值式纯函数记忆压缩**（`lib/pbl/v2/agents/instructor-memory.ts`，最轻量可移植）：>30 条触发，保留最近 16 条，旧半折叠为 ≤4500 字的结构化摘要（学习者画像：事实/卡点/偏好/进度 + 近期轨迹）；**切点必须对齐「user 消息结束」边界**，避免把一问一答劈开。纯函数无 LLM、成本恒定。

**（h）SKILL.md 三件套**（`lib/server/agent-runtime/skills.ts`）：
1. **按需加载**：只把 name/description/路径列进系统提示词，agent 需要时自己 `read` 正文——不全量注入；
2. **机器可校验约束文件**：技能可附带 JSON 约束（场景数范围、类型配比等），生成后硬校验，违规作为诊断返回由 agent 重规划；
3. **激活即转录**：用户选的技能被「综合成一次 read SKILL.md」写进持久事件日志，崩溃恢复后激活状态天然还原。
23 个内置技能含 `feynman-learning`、`spiral-curriculum`、`understanding-by-design` 等（`skills/agent-runtime/`），描述互相引用排他形成可路由技能图谱。

**（i）`build-personal-skill` 范式**：从用户自己的历史（做课记录）提炼专属可复用技能卡。Bobodan 有全量学习记录（错题/掌握度/笔记），条件更好。

**（j）eval 方法论**（`eval/`）：场景是带 case_id 的 JSON 夹具（含真实生产 bug 复现）；**能确定性判定就不用 LLM judge**；A/B 提示词变体（删规则 vs 原版各 N 采样）；API 错误样本剔除不计分；**评测 harness 与前端共享同一个 `runAgentLoop`**（评测即产品代码）；退出码可卡 CI。

### 4.3 对 Bobodan 的借鉴清单

| # | 借鉴什么 | 对应 Bobodan 模块 | 怎么落地 | 参考源文件 |
|---|---|---|---|---|
| O1 | Director 单轮契约 + 客户端/服务侧循环 | `core/agent_loop.py`、`web/backend/` | 多 agent 模式（若做）：每请求只跑「选人→执行一步」，`done` 事件回传累积状态；Python 手写两节点图，不引 LangGraph | `lib/orchestration/director-graph.ts`、`lib/chat/agent-loop.ts` |
| O2 | AgentConfig 卡片 + role→能力推导 | 未来多 persona 配置 | SQLite 一张 agents 表 `{id,name,role,persona,avatar,color,allowedActions,priority}` | `lib/orchestration/registry/types.ts`、`store.ts` DEFAULT_AGENTS |
| O3 | Peer-context 反复读注入 | 多 persona 讨论/辩论 | 每个发言者提示词尾部注入「已发言者 300 字预览 + 5 条硬规则」 | `lib/orchestration/summarizers/peer-context.ts` |
| O4 | 确定性冲突摘要器 | Chat 证据门禁 / Knowledge Map | RAG 引用覆盖检查、图谱环检测算成文本警告块注入 prompt | `lib/orchestration/summarizers/whiteboard-conflicts.ts` |
| O5 | SSE 心跳 + done 携带状态 + 流内 error | `web/backend/` SSE | 15s `:heartbeat` 注释帧；错误不甩 HTTP 状态码、走流内 error 事件 | `app/api/chat/route.ts` L96-182 |
| O6 | 阈值式会话压缩 | Chat 长会话 | >30 条折叠旧半为 ≤4500 字画像摘要，切点对齐 user 消息边界，保留 16 条；纯函数无 LLM | `lib/pbl/v2/agents/instructor-memory.ts` |
| O7 | SKILL.md 约束文件 + 激活即转录 | `skills/` | 出题类技能带 JSON 约束硬校验（题型配比/数量）；技能激活写进会话事件，重启还原 | `lib/server/agent-runtime/skills.ts`、`skill-preload.ts` |
| O8 | build-personal-skill | 个人知识 + Skills | 定期从错题/会话提炼「个人学习画像技能卡」落 SKILL.md | `skills/agent-runtime/build-personal-skill/SKILL.md` |
| O9 | eval 方法论 | tests/ 新增 eval/ | 证据门禁（引用命中率）、批改质量、路由正确性各建 runner；确定性判分优先；A/B 提示词 | `eval/orchestration/runner.ts`、`judge.ts` |
| O10 | Quiz 分级判分 | `service/quiz_service.py` | 选择/判断本地确定性判分，仅短答走 LLM 批改（Bobodan 已部分做到，可对照补齐） | `lib/quiz/grading.ts` L25-46 |

---

## 五、qiaomu-book-reader —— Library 阅读体验蓝图

### 5.1 定位与架构

Obsidian 内的 EPUB/FB2/PDF 阅读器，产品主张一句话：**「每本书一篇 Markdown 阅读笔记，进度、划线、批注全部沉淀为自己的笔记」**。AI 默认关闭、阅读完全离线、无遥测。

核心数据流：打开书 → 解析成统一 HTML → 构建目录 → 分页 → 恢复位置 → 重画划线。存储分两层：vault 内 `reading-progress.json` / `reading-highlights.json`（可同步层）+ data.json（本地日志/快照）。

### 5.2 核心机制

**（a）定位锚 = 段落全局序号 block index**：全 flow 的 `p,h1-h4` 全局序号是唯一锚——「手机和 PC 上存在同一条序列」，字号/栏数/屏宽变化都不影响；`currentBlockIndex` 二分查找。进度存 `{pct 浮点, block}`，**恢复优先 block 锚、pct 兜底**；恢复后目标段落 **flash 2.4 秒**「让眼睛找到落点」；大跳（≥15%）自动存历史点、面板可回滚。

**（b）划线四元组消歧**（`src/main.js:8908`）：
```js
hl = { id, color, text, block: 1234, occ: 0, pre: "前32字符", post: "后32字符", created, comment?, page?, chapter? }
```
跨块选区切成逐块 parts，每块算 occ（该文本在同段落内第几次出现）+ 前后文消歧。还原时三级降级：① 按出现次数直接定位 → ② pre/post 上下文消歧 → ③ 归一化映射（统一弯引号/破折号/NBSP）后模糊匹配。

**（c）托管区块同步**（`src/main.js:6819-6890`）：默认每次划线后**全量重写**书笔记的 `## 划线与批注` 区块（按 heading 边界算替换区间，用户在区块外写的内容一概不动），而非 append——解决重复与失同步两大顽疾；去重用归一化文本比对。引文格式自带 `↩` 反链（`obsidian://` 协议 + block 参数），从任何笔记都能点回原文，落地链 = 定位 → 滚动 → flash → 阅读器未就绪则轮询等待。

**（d）TOC 四级降级**（`src/main.js:5097-5205`）：PDF outline → H1-H3 标题 → **印刷目录页文本匹配**（解析「标题……页码」行，再在正文顺序匹配定位）→ 粗体短段落；每级配噪声过滤。无结构 PDF 也能做出可用目录。

**（e）可靠性工程**（`src/storage.js` 全文仅 57 行，是现成设计文档）：所有写走串行队列；JSON 损坏 → 备份 `.corrupt-<时间戳>.bak` + **锁定该文件拒绝再写** + 弹窗告知；划线写入前**重读磁盘最新副本再合并**（防多端互相覆盖）；划线 12 份快照、进度 30 个历史点、每日救援目录。

**（f）PDF 文本重建启发式**（`src/main.js:5270-5732`）：连字符合并、等宽字体检测判代码块、列表识别、CJK 标点修正；扫描页判定（单字符 token >70%）后降级为懒渲染页图。

**（g）AI 划词对话**（`src/main.js:3442-3507`）：system prompt 克制条款（「区分原文信息、你的解释和不确定推断；不要编造书中没有出现的内容」——与 Bobodan 证据门禁同向）；首轮消息注入 `书名 + 选段`；6 个内置快捷问题（解释/举例/关键思想/对我的用处/换角度/出题考我）可自定义；只发送被操作的选段，不发整章整本；回答可一键「存为笔记」。

**（h）书库筛选 chips 从真实数据推导**：「在读/未读/读完」由进度推导（≥98% 即读完），「筛选条只提供真正有结果的过滤器」；`continue-reading` 一键回到最近读的书。

### 5.3 对 Bobodan 的借鉴清单

| # | 借鉴什么 | 对应 Bobodan 模块 | 怎么落地 | 参考源文件 |
|---|---|---|---|---|
| Q1 | 划线锚四元组 | Library 阅读器 + Chat 引用 | 划线/引用统一存 `{chunk_id, start/end offset, quote, prefix32, suffix32}`；渲染走「精确 offset → 文本匹配 → 归一化模糊匹配」三级降级 | `src/main.js:8908, 5758-5853` |
| Q2 | 托管区块同步到笔记 | 笔记 ↔ 资料关联 | 资料阅读页划线自动同步到笔记的「来自本书的摘录」托管区块（heading 边界替换、归一化去重），区块外用户自由书写 | `src/main.js:6819-6890, 6712-6721` |
| Q3 | ↩ 反链 + flash 落点 | Chat 引用 / 笔记摘录 | 引用点击 → 定位 chunk → 滚动 → 目标段落 flash 2.4s；加载中轮询等待 | `src/main.js:8189-8210` |
| Q4 | TOC 降级链 | `rag/` PDF 导入 | 参考项目的 PyMuPDF outline → heading → 印刷目录文本匹配 → 粗体短段；Bobodan 当前使用 `pypdf`，若实施需按它的能力重新设计 | `src/main.js:5097-5205` |
| Q5 | 可靠性四件套 | SQLite 写入层 | 串行写队列；写前重读合并（多窗口并发）；快照滚动备份；损坏「备份+锁定，绝不带病覆盖」 | `src/storage.js:14-57` |
| Q6 | PDF 文本重建启发式 | PDF 解析 | 连字符合并、等宽字体判代码块、CJK 标点修正、扫描页判定降级 | `src/main.js:5270-5732` |
| Q7 | 阅读进度双层锚 | Library | 显示用 pct、恢复用内容锚（chunk/heading 路径）；翻页/滚动自动存；大跳存历史点可回滚 | `src/main.js:2510-2600, 8700-8732` |
| Q8 | AI 划词对话三件套 | Chat | 克制 system 条款；首轮注入书名+选段；快捷问题列表（含「出题考我」直达 Practice） | `src/main.js:3442-3507` |
| Q9 | 导出去重弹窗 | 笔记关联 UI | checkbox 列表、已存在条目标 already 并默认不选、「仅选新的」一键 | `src/main.js:7074-7174` |
| Q10 | 书库筛选从数据推导 | Library 首页 | 阅读状态 chips 由进度推导；continue-reading 命令 | `src/main.js:9081-9160` |

---

## 六、初始借鉴建议（2026-09-02 历史快照）

下表保留原始比较结论，便于追溯每一项的来源；其时间估算和优先级已被 `ROADMAP.md` 的 A–E 批次取代。实施前先核对相应路线项是否已经部分存在，再决定保留、拆分或取消。

### P0 — 直接增强现有模块，1-2 周级

| 项 | 做什么 | 动 Bobodan 哪里 | 参照 |
|---|---|---|---|
| 1 | **ask_user 交互卡 + 交互状态持久化**（Practice/Chat 通用基础设施） | `web/backend/` SSE 事件 + `web/frontend` 卡片组件 + 新增 interactions 表 | DeepTutor `ask_user.py` + OpenMAIC `ask-user.ts` |
| 2 | **出题改三阶段流式管线**：每题就绪即渲染；explanation 随题入库 | `service/quiz_service.py` | DeepTutor `agents/question/pipeline.py` |
| 3 | **掌握度引擎纯函数化**：近因加权 + 置信帽 + next_objective 优先级（挂起>复习>未掌握） | `learning/`、`service/learning_service.py` | DeepTutor `learning/policy.py`、`mastery.py` |
| 4 | **划线最小闭环**：chunk 级划线 + 托管区块同步到笔记 | `web/frontend` Library 阅读器 + notes 服务 | qiaomu `main.js:8810-8918, 6819-6890` |
| 5 | **RAG 索引心跳守卫**（本地 embedding 挂起是常态） | `rag/` 索引管线 | DeepTutor `pipelines/llamaindex/pipeline.py` L49-112 |

### P1 — 引入新机制，2-4 周级

| 项 | 做什么 | 动哪里 | 参照 |
|---|---|---|---|
| 6 | Socratic persona 技能（翻译 PERSONA.md + 优先级裁决规则） | `skills/` 新增 | DeepTutor persona |
| 7 | AgentLoop 单循环契约（无工具轮=finish、结算期、截断续写） | `core/agent_loop.py` | DeepTutor `agent_loop.py` |
| 8 | Prompt 具名块 + KB seed 进末尾 user 消息（缓存友好） | `core/agent_loop.py` | DeepTutor `prompt_blocks.py` |
| 9 | 会话阈值压缩（>30 条折叠、切点对齐 user 边界） | `core/session.py` | OpenMAIC `instructor-memory.ts` |
| 10 | 引用/划线统一锚协议（chunk_id+offset+pre/post 三级降级）+ flash 定位 | `rag/`、Chat 引用、Library | qiaomu |
| 11 | SKILL.md 机器可校验约束（出题技能硬校验）+ 激活即转录 | `skills/`、`core/` | OpenMAIC `skills.ts` |
| 12 | PDF 目录降级链 + 扫描页判定 | `rag/` PDF 导入 | qiaomu |
| 13 | 嵌入签名版本化索引 | `rag/qdrant_store.py` | DeepTutor `index_versioning.py` |

### P2 — 新形态试验

| 项 | 做什么 | 参照 |
|---|---|---|
| 14 | 多 persona「课堂/讨论」模式：轻 director + agent 卡片 + peer-context（Chat 主循环不动，做成可选 capability） | OpenMAIC director 模式 |
| 15 | eval 体系：证据门禁引用命中率、批改质量、路由正确性三个 runner；确定性判分优先；A/B 提示词 | OpenMAIC `eval/` |
| 16 | 三层记忆升级个人知识（L1 图章轨迹 / L2 脚注事实 / L3 综合） | DeepTutor `services/memory/` |
| 17 | build-personal-skill：从错题/会话提炼个人学习画像技能卡 | OpenMAIC |
| 18 | 阅读进度历史点、每日目标、streak（宽容设计：昨天读了今天没读不断签） | qiaomu |

> **补充（2026-09-03 历史建议）**：RAG embedding API 化与签名版本化是同一改造的两半。当前已被 `ROADMAP.md` 的 B1 / B2 拆分：先建立 FTS-only 评测基线，再决定是否交付可选向量检索。

---

## 七、不建议照搬清单

**DeepTutor：**
- 八引擎 RAG 矩阵（GraphRAG/LightRAG/WeKnora…）——学它的 pipeline 抽象接口，不学引擎数量；Bobodan 的 FTS5+Qdrant hybrid 已够。
- 多用户/Partner/IM 15 渠道（占仓库 1/4）；subagent/CLI-app/MCP 商店全家桶；DSML 文本协议兼容层与 50+ provider 逐 issue 补丁——Bobodan 收缩到 OpenAI 兼容协议 + 明确的「能力检测→降级」清单即可。
- 2000+ 行单文件管线（`question/pipeline.py` 2210 行、`agentic_pipeline.py` 1809 行）——拆小模块再抄。
- 枚举式 stage counter（它自己都是迁移遗迹）——从一开始就用「门禁计算推进」。

**OpenMAIC：**
- LangGraph/Postgres 租约/多 worker durable runner/S3 字节池——全是为云多实例部署设计的；Bobodan 单进程 + SQLite 用 sessions 表 + status 列 + 启动恢复即可。**只留两个概念：事件先落盘再投递（crash 不丢）、interrupted/resumed 生命周期。**
- pi-agent-core 双轨 director PoC——不要同时养两套。
- TTS/语音克隆/视频渲染/pptx 导入/i18n×10——与本地优先定位无关。

**qiaomu：**
- 11702 行单文件 main.js 与桌面/移动两份复制 UI——明确的反面教材。
- CSS multicol 真分页——坑极多（它自己用大量注释解释）；Bobodan 按 chunk 滚动阅读即可。若确要分页，只抄「步长由构造决定」和「高亮用 CSS Custom Highlight API 画、不插 DOM」两条。
- Obsidian 深耦合（frontmatter 双写、protocol handler、Templater、epubjs）——思想保留，实现用 SQLite + FastAPI 对应物。

---

## 八、一个贯穿性的观察

三个项目在同一个点上不约而同：**「模型负责语言，代码负责事实」**。

- DeepTutor：掌握度/调度/判分是纯函数引擎，模型每轮问引擎「下一步」，永远不能自己宣布掌握；expected_answer 只存服务端。
- OpenMAIC：白板冲突、状态摘要由确定性代码算好喂回提示词；director 解析失败默认 END（fail-closed）；动作白名单双重过滤，越权直接丢弃。
- qiaomu：进度/定位/去重/合并全是代码算术，模型只在划词时被请来解释一段话。

这与 Bobodan 已有的证据门禁、source_ids 确定性保存、候选审查是同一个哲学。**所以这三个项目的借鉴不是「改方向」，而是「把已经走对的路走完」**——尤其 DeepTutor，它几乎就是 Bobodan 设想的成熟版：单循环 Chat + 引擎驱动的掌握度闭环 + 来源可溯的题库 + 本地优先。建议把 `deeptutor/learning/`（约几百行纯函数）和 `deeptutor/agents/chat/agent_loop.py` 作为精读起点。

## 九、前端优化设计借鉴（专项补充）

> 调研范围：DeepTutor 的 `web/`（Next.js 16 + React 19 + Tailwind 3，自研 vanilla store + WebSocket turn 协议）与 OpenMAIC 的前端（`components/` + `lib/workbench/` + `lib/chat/`，Tailwind 4 + Zustand 5 + motion）。qiaomu 的阅读交互见第五章，本章只补前端工程视角。
> Bobodan 现状基线：`ChatPage.tsx` 1033 行（useChatStream 消费 SSE）、`LibraryPage.tsx` 1051 行、`ProcessFoldBlock` 过程折叠、`artifacts/` 结构化卡片、Zustand 5 + Tailwind 4 + react-markdown、Playwright e2e。

### 9.1 两套参考架构，一句话定位

- **DeepTutor 前端 = 「消息即事件流」的流式 UI 天花板**：assistant 消息 = `{content, events[]}`，一份事件流同时喂正文、过程折叠块、结构化卡片三种渲染；narration 与正式答案由元数据协议区分，前端零启发式。工程纪律极强——纯函数全部下沉 `lib/` 配单测，架构契约由测试强制。
- **OpenMAIC 前端 = 「UI 是事件日志的纯折叠」**：`foldEvent(state, event)` 纯 reducer 在 React 之外，UI = 事件前缀的纯函数，因此断线重放/刷新恢复天然正确（reattach at N ≡ 从 0 apply）。80 个测试文件，多个测试就是线上 bug 的墓碑。

两家独立得出同一结论：**流式 UI 的正确性来自「事件 → 纯函数 → 状态」的单向管线，而不是散落在组件里的 setState。**

### 9.2 核心机制精讲

**（a）流式渲染链路（对 Bobodan `useChatStream` 最重要）**
- DeepTutor 分层：`TurnRuntimeClient`（seq 排序/gap 缓冲/resume 游标/命令 ACK）→ `UnifiedTurnClient`（事件规整）→ `ChatStateAdapter` → 纯 reducer。事件带 `seq`，`appendEvent` 对 `seq <= lastSeq` 直接丢弃，天然幂等（`features/chat/store/reducer.ts:71-93`）。
- **narration/finish 元数据协议**（`web/lib/stream.ts`，80 行全文件值得精读）：只有 `call_kind` 白名单内的 content 才 append 进答案；round 结束的 `call_role:"narration"` 标记事件到达时，把已流入的过程文本**从答案中减掉**归还给 trace。增量 append、标记时校正——不是每个 chunk 都重算。
- OpenMAIC 的 fold（`lib/workbench/session-store.ts:913-1752`）：`if (event.id <= state.lastEventId) return state;` 开头一行保证幂等；`questionAnswered` 是折叠时派生的字段（「问题卡之后的首条非空用户消息」= 已回答），冷重放的历史问题卡第一次绘制就是已答态，不闪现可点按钮。
- **事件只当通知，不当正文载体**（`use-workbench-session.ts:10-14` 原则）：「事件只说『第 3 页落了』，不携带第 3 页」——正文走按 id 的 HTTP 拉取，浏览器永不持有两份不一致的数据。
- **断线恢复全家桶**：Last-Event-ID 重放 + `caught_up` 帧收口 + 20s 看门狗兜底 + backlog 压缩（token 级 delta 只留首尾帧，首帧带时间戳保证思考条时长重放后与直播一致）+ DeepTutor 的命令 ACK（cancel/submit 带(command_id)，重连后按 generation 重发——**停止和答题指令不因断线丢失**）。
- **乐观 id 对账**（`web/lib/turn-reconcile.ts`）：发送即插负 id 占位，turn 完成后原位换 id 并 remap 关联指针，替代「每轮 refetch 整个会话」——长会话卡顿的 O(n)→O(1) 修复。

**（b）打字机与 markdown 渲染**
- `web/hooks/useSmoothStreamText.ts`（141 行，零依赖可直接移植）：rAF 循环 reveal，每帧步长 `clamp(backlog/5, 2, 120)`——backlog 越大追得越快，2KB 突发不会打字半分钟；流结束 snap 全文；内容变短（regenerate）snap back。
- **单调 Simple→Rich 渲染器**（`MarkdownRenderer.tsx:14-58`）：正则探测 ``` / mermaid / HTML / math，触发后切 dynamic import 的全功能渲染器（KaTeX/高亮/mermaid 全部分包）且不回退；trace/过程文本永远走轻量路径。流式期每帧重解析 markdown，完成消息 memo 后不再解析。
- OpenMAIC 的对应原则：「ONE source of pacing」——SSE delta 先进 StreamBuffer 队列，固定 tick 逐字 reveal，聊天区与圆桌气泡消费**同一个节奏**，UI 层不再各自加动画（`lib/buffer/stream-buffer.ts:1-11`）。
- CJK 细节：若换渲染器，`remark-cjk-friendly` 必须排在 gfm 之前（CJK 全角标点旁的强调规则 bug）。

**（c）自动滚动（流式抖动的完整答案）**
DeepTutor `web/hooks/useChatAutoScroll.ts`（328 行，注释即设计文档）五条：① **唯一写者**——一个 useLayoutEffect 直接 `scrollTop = scrollHeight`，不用 smooth、不用节流，避免多写者竞争；② 滚动容器 `overflow-anchor: none`（禁用浏览器 scroll anchoring，否则代码块展开时 anchoring 与 pin 打架）；③ 流式期 MutationObserver + rAF 合帧捕捉子组件迟到高度（注释解释了为何 ResizeObserver 观察不到 scrollHeight 增长）；④ 用户意图检测——wheel 向上/触屏下拉立即释放，回到底部 80px 内自动重新武装；⑤ 流结束后观察窗延长 4s（标了 `data-chat-grow` 的重内容组件如 QuizViewer 可延至 12s），**ask_user 卡片出现时强制 re-arm 并滚底**。
OpenMAIC 补一条领域规则：**用户发消息才强制回底，agent 输出绝不拽走正在读上文的用户**；重放定位用 `instant` 防止从 16 分钟前的日志顶部长动画滚下来。

**（d）过程可视化（`ProcessFoldBlock` 的升级蓝图）**
- **工具卡 = 规则表**（OpenMAIC `tool-presentation.ts`，1002 行纯函数无 JSX）：每个工具一行 switch 产出 `{icon, label动词短语, subject, chips[], errorText}`，摘要**只从工具的结构化 details 生成、永不 parse 散文**；原始报文降级进 disclosure 不销毁；工具输出永不过 markdown（不可信文本）。配套测试把工具注册表对本规则表**对账**——新工具没写文案会 fail test，而不是把 wire 名漏到 UI。
- **工具组聚合 + 双时钟**（`tool-group-state.ts:18-32`）：连续工具调用共用「N 个工具调用」外框；settle 后 600ms 才收（让完成态被读到）但保底可见 1800ms（防快工具「刚展开就收起」的 twitch）；用户手动接管后永不自动收。折叠动画 `grid-rows 0fr→1fr` + `inert`，无需测高度。
- **thinking 条与 waiting 条严格分离**（OpenMAIC）：thinking 条只有存在 reasoning 文本才挂载，收起时显示**最新一行 200 字预览**（流式时预览在动，完成后是结论行）；时长冻结在**持久化 settle 帧**上——重放与直播一致。waiting 条是三个脉冲点，「没有标签、没有大脑图标、没有编造的想法」——这正是 Bobodan「不展示思维链」约束的现成 UI 落法。
- **StreamingStatus 状态头**（DeepTutor `TracePresentation.tsx:2223-2375`）：「DeepTutor Exploring… · 8s」→「responded · 10s」，turn 级单时钟只在流式期跑、结束后定格；呼吸动画只在活跃期，完成态静态降透明度。
- 每个工具的「中文动词 + 宾语 chip + 专属图标」大 switch（`TracePresentation.tsx:186-402`）是把工具调用变成一句中文（`检索资料 · "二项分布"`）的现成模板。

**（e）交互卡**
- **ask_user 卡**（DeepTutor `AskUserOptions.tsx`，991 行）：多题 tab（答过变 ✓）、单选自动跳下一未答、Other 自由文本草稿跨 tab 保留、批量提交；提交后**同容器原位变只读 Q&A 摘要**（默认折叠、显示 n/m answered），永不 unmount——历史里永远可回溯。最精妙的是 `extractMessageSegments`：把事件流切成 text/card/trace 段按流序渲染，**resume 后的文本渲染在卡片下方**（用户正看着的位置），不跳回顶部。
- **question 卡接管 composer**（OpenMAIC `question-form.tsx`）：未回答时输入框被编号问卷接管（键盘 1-9 选项、↑↓ 导航、Enter/Esc），时间线里的卡收成一行指针避免同屏两份。
- **Quiz 卡**（DeepTutor `QuizViewer.tsx`，1403 行）：逐题流式出现（`quiz_question_emitted` 事件增量收集，result 到达切权威数据）；题号 chip 颜色编码对错且**开放题不自动标红**；所有答题状态按 `turn_id` 而非会话隔离（防跨 quiz 串题，对应 issue #677）；AI 判卷是独立小协议 + 2 分钟 idle 超时 + cancel handle，判卷按钮流式时变 Stop。

**（f）状态管理与工程化**
- 组件外纯状态函数模式（OpenMAIC）：`thinking-bar-state.ts` / `tool-group-state.ts` / `question-form-state.ts` / `composer-send-state.ts` 都是「展开/锁定/发送态」的纯函数模块，可无 DOM 单测；`.ts`（状态）与 `.tsx`（视图）严格分离——workbench/chat 26 个文件最大 351 行。
- 架构契约测试（DeepTutor `tests/architecture-contracts.test.ts`）：localStorage 只许 shared/storage 用、裸 `fetch(` 只许 api client、页面组件不得互相 import——前端架构像后端一样 CI 强制。
- selector 引用稳定：模块级 `EMPTY_MESSAGES = []` 常量防空数组每次 render 新引用；会话缓存 LRU 20 条（只驱逐非活跃且非 running）。
- 全量重置工厂（OpenMAIC `createInitialSessionState`）：返回类型 = 完整 state 接口，漏字段编译失败 + 测试遍历 key 对账——「漏一个字段 = 无限 spinner」这类 bug 的根治法。
- **Playwright mock SSE**（`e2e/fixtures/mock-api.ts`）：`route.fulfill({headers: text/event-stream, body: 事件串})`——SSE 可确定性 mock，是过程 UI e2e 可测的关键，Bobodan 的 `test:e2e` 直接可用。
- counter 而非 flag：`libraryRevision` 用「刷新计数」而非「是否有 pending 刷新」——flag 不可精确重放，counter 可以。

**（g）设计系统**
- **语义 token + token 契约测试**（DeepTutor `app/globals.css:24-200` + `tests/design-token-parity.test.ts`）：四套主题全 CSS 变量（Cream 暖白赤陶 / dark / Snow 纯白蓝 / Glass），语义层含 success/warning/info 三元组 + `--overlay`（统一 modal scrim）+ `--motion-fast/base/slow`；一个 30 行测试断言每个主题发布全部 token + reduced-motion + focus-visible。
- **CJK 字体栈显式点名**（`tailwind.config.js:13-39`）：sans/serif 在拉丁字体后点名 PingFang/思源宋体等——不点名会导致标题拉丁用衬线、中文随机器乱 fallback；`.prose` 正文 serif 16px/1.75、标题 sans。**LibraryPage/ReaderPage 的阅读质感立刻受益。**
- scoped token + 类表（OpenMAIC `workbench-chat.css`）：`.wbchat { --wb-* }` 颜色全部映射回语义变量（暗色免费获得），动效分 base 160ms / fold 220ms（「折叠移动几何，比颜色换值给更长阅读时间」）；组件类集中进 `wbStyles` 常量表，一处分级全局生效。
- 状态点词汇表 `normalizeStatusDot`（所有状态词归一为 ok/error/running/suspended/idle，running 是小转圈**绝不用呼吸点**）；系统通知三档 tone 共用一个形状、技术原因藏 disclosure；相同通知连发折叠 ×N。
- 空态三件套：EmptyState（icon tile + 标题 + 描述 + action）/ Skeleton / 内联错误条带 Retry；进阶——手绘 SVG 装饰空态、「空则整节隐藏不画骨架」。

**（h）游戏化**
- `ProgressRing.tsx`（88 行）三条准则：环用 `--foreground`（墨）不用 primary、hairline 1.75px stroke、**只有「路径完成」这唯一时刻才点亮 primary**。
- `LevelUpCelebration.tsx`（328 行）：canvas 纸屑三炮交错、翻滚/飘摆/分裂阻力物理、portal 逃出 overflow-hidden、dpr≤2、reduced-motion 直接跳过——零粒子库依赖。

### 9.3 对 Bobodan 前端的借鉴清单（合并去重后 18 条）

| # | 借鉴什么 | Bobodan 落点 | 来源 |
|---|---|---|---|
| F1 | `useChatStream` 重构为「纯 foldEvent reducer（lib/）+ store 只暴露 applyEvent」；事件带 seq 幂等 | `src/hooks/useChatStream.ts`、新增 `src/lib/chatFold.ts` | OpenMAIC fold + DeepTutor reducer |
| F2 | narration/finish 元数据协议：过程文本靠标记事件从答案中剔除，前端零启发式 | useChatStream + ChatPage 消息渲染 | DeepTutor `lib/stream.ts` |
| F3 | 具名 SSE 帧订阅表从事件常量派生 + 对账测试（漏订阅 = 静默丢帧） | `src/lib/api.ts` 事件类型 | OpenMAIC |
| F4 | 断线恢复：Last-Event-ID 重放 + caught_up 帧 + 20s 看门狗 + 积压压缩 + 命令 ACK | useChatStream | 两家 |
| F5 | 乐观负 id 占位 + turn 完成原位对账（替代整会话 refetch） | ChatPage 会话流 | DeepTutor `turn-reconcile.ts` |
| F6 | rAF 平滑打字机（步长自适应）+ 单调 Simple→Rich markdown + trace 永远轻量 | ChatPage react-markdown 管线 | DeepTutor 两个 hook/组件 |
| F7 | 自动滚动：单写者 + overflow-anchor:none + MutationObserver 合帧 + 手势释放 + 「用户消息才回底」 | `useStickyBottomScroll.ts` 升级 | DeepTutor 主 + OpenMAIC 领域规则 |
| F8 | ProcessFoldBlock 升级为工具卡规则表（动词短语 + chips + disclosure），测试对账 | `ProcessFoldBlock.tsx` | OpenMAIC `tool-presentation.ts` |
| F9 | 工具组聚合双时钟（settle+600ms / minVisible 1800ms）+ 状态点词汇表 | ProcessFoldBlock | OpenMAIC |
| F10 | thinking 收起显示最新行预览、时长持久化帧冻结；waiting 三点无标签（思维链约束的 UI 落法） | ProcessFoldBlock | OpenMAIC |
| F11 | ask_user 卡：流序分段渲染 + 原位 resolved + 多题 tab/自动跳题/Other 草稿 | `artifacts/` 确认卡全家 | DeepTutor |
| F12 | question 未答时接管 composer（编号问卷 + 键盘）；answered 由 fold 派生 | ChatPage composer | OpenMAIC |
| F13 | Quiz 流式卡：逐题出现 + chip 导航（开放题不标红）+ turnId 隔离 + 判卷 cancel | PracticePage | DeepTutor QuizViewer |
| F14 | 语义 token 多主题 + token 契约测试 + CJK 字体栈点名 + serif 正文 prose | Tailwind 4 `@theme` + globals.css | DeepTutor |
| F15 | 空态三件套组件化 + 「空则整节隐藏」+ 手绘 SVG 装饰空态 | Library/Notes/KnowledgeMap | DeepTutor |
| F16 | 组件外 `-state.ts` 纯函数模式 + 架构契约测试 + bug 墓碑测试 | ChatPage 瘦身 + tests/ | OpenMAIC + DeepTutor |
| F17 | Playwright mock SSE fixture（确定性事件串重放） | `test:e2e` | OpenMAIC |
| F18 | ProgressRing 准则 + LevelUpCelebration 纸屑（掌握度/复习升级时刻） | ReviewPage/PracticePage | DeepTutor Learning Space |

### 9.4 前端建议映射（调研日快照）

FE-P0 / P1 / P2 是调研时的归类，不是当前执行顺序；当前以 `ROADMAP.md` 的 A0、C1、C2 批次为准。

- **FE-P0（流式正确性）**：F1 fold 重构、F3 订阅表测试、F7 自动滚动升级、F14 CJK 字体栈（半天级）。
- **FE-P1（体验质感）**：F2 narration 协议、F6 打字机 + markdown 分级、F8-F10 过程可视化升级、F11 交互卡、F17 e2e mock。
- **FE-P2（锦上添花）**：F4 断线全家桶、F5 乐观对账、F13 流式 Quiz、F15-F16 工程化、F18 游戏化。

### 9.5 前端不建议照搬

- DeepTutor 允许 2000+ 行编排组件（ChatWorkspace 2826 行）——学它的分层与纯函数下沉，不学文件尺寸；Bobodan 的 ChatPage 1033 行已经是瘦身对象。
- OpenMAIC 的 motion（framer-motion 后继）依赖——Bobodan 现有 CSS 动画路线（qiaomu/DeepTutor 都是 CSS keyframes 为主）更轻，别为一个动画引库。
- Next.js SSR/路由预算脚本/dependency-cruiser 全家桶——Vite 项目取其测试思想即可，`tsc --noEmit` + eslint 已覆盖大半。
- OpenMAIC 的 storeState 全量上送（客户端驱动循环专用）——Bobodan 的 SSE 单向流不需要。

---

## 十、RAG 向量化选型：调研与决策（2026-09-03）

> 本章回答四个问题：① Bobodan 的 FTS5+Qdrant 现在到底处于什么状态？② 要不要照搬 DeepTutor 的八引擎矩阵？③ 三个参考项目的 embedding 模型/向量库是怎么选的？④ 最终拍板的方案与落地清单。
>
> 本章的现场核查仍说明为什么 FTS-only 必须可用；但其中 API embedding 的实现尚未交付。当前 `EmbeddingService` 仅支持 Ollama，B2 的 API provider、签名、重建与评测门槛以 `ROADMAP.md` 和 `rag_design.md` 为准。

### 10.1 现状核查：向量腿从未真正运行过

实测证据（2026-09-03）：

- `.knowledge/qdrant/` 目录只有 `.lock` 和 34 字节的 `meta.json`——**没有任何 collection，向量索引从未建立**。
- 本机 11434 端口 Ollama 未运行，`rag/embedding_service.py` 的探测（3s 超时）失败 → `rag/hybrid.py` 静默降级 → `rag/retriever.py` 返回 `fts_only`。
- 所以当前产品实际是**纯 FTS5 检索**，「FTS5+Qdrant 组合」目前只存在于设计与配置中。

代码质量核查结论（不需要改动，只缺运行条件）：

- `rag/rrf.py` 的 RRF 实现是教科书级：`score = Σ weight/(k + rank + 1)`，k=60，vector/fts5 权重 1.0/1.0。RRF 的意义在于 BM25 分数与余弦相似度量纲不可比，RRF 只看排名位置，完全绕开归一化。
- `rag/hybrid.py` 先探测 embedding 可用性再检索、Qdrant 命中后回 SQLite 补文本（hydrate）、再 dedupe——链路设计正确。
- 组合本身评估：FTS5+CJK 2-gram 强在精确术语命中，弱在改述（「怎么安装」找不到「部署方法」）；向量检索正相反。学习场景概念型提问居多（「为什么是这样」），所以向量腿缺失对 Bobodan 的伤害比一般应用更大。

### 10.2 为什么不照搬 DeepTutor 的八引擎矩阵

DeepTutor 的八引擎（LlamaIndex/PageIndex/GraphRAG/LightRAG/WeKnora/Obsidian 直连等）是云端产品服务各类社区用户与文档生态的产物——每个引擎是一条 PR、一堆依赖、一套失败模式，提供的是同一对能力（词法+语义）的八种**实现**，不是八种新**能力**。Bobodan 的 FTS5（词法）+ Qdrant（语义）+ RRF（融合）已是业界标准 hybrid 形态。

真正值得借的是三件配套工程（已进路线图）：**嵌入签名版本化**（换模型重建索引、旧索引不混用）、**索引心跳守卫**（600s 无进度报可行动错误）、**检索评估集**（用数据决定要不要任何新引擎）。原则：只有当评测证明现有组合在某类查询上失败时，才考虑新增检索手段。

### 10.3 三个参考项目的实际选型（结论出人意料）

| | embedding 模型 | 向量库 | 检索形态 |
|---|---|---|---|
| DeepTutor | **无内置、无默认运行**——12 个用户自配 provider 注册表：openai（默认 `text-embedding-3-large` 3072d）、gemini、azure、cohere、jina、ollama（默认 `nomic-embed-text`）、vllm、**siliconflow（默认 `Qwen/Qwen3-Embedding-8B` 4096d，支持 bge-m3）**、**aliyun（`qwen3-vl-embedding` 2560d，支持多模态图片 embedding）**、custom OpenAI 兼容等 | **进程内 FAISS 文件**（`IndexFlatIP` 默认，大语料可选 HNSW，按 KB 持久化）；曾用 LlamaIndex SimpleVectorStore（JSON+纯 Python O(N) 扫描）因打满 CPU（issue #552）换掉；**从不跑向量库服务** | vector + BM25 → QueryFusionRetriever RRF 融合 + 可选 cross-encoder 重排 |
| OpenMAIC | **无**（全仓搜 embed/text-embedding/voyage/cohere 零命中） | **无** | 内存词法索引：Unicode 正则分词（汉字单 token）、NFC 归一、词重叠打分 + 精确短语加分（连 BM25 都不是）；底气是课程语料小而精、重活靠 LLM 直接读文档 |
| qiaomu | **无**（唯一的 "vector" 命中是 PDF.js 矢量绘图操作计数，与检索无关） | **无** | 纯文本查找 + CSS Highlight API 画高亮 |

四条启示：

1. **Bobodan 的 Qdrant 本地模式不需要动**。RAG 工程最重的 DeepTutor 用的也是进程内文件索引（FAISS），从不跑向量库服务；qdrant-client local mode 是同一档次，且多了 payload 过滤。真正的瓶颈从来不在向量库，在 embedding 一环。
2. **DeepTutor 的 provider 注册表是「API 自配」路线的现成蓝图**。spec 结构 `{label, default_api_base, default_model, default_dim, keywords, max_batch_items, multimodal}` 可直接照抄（`deeptutor/services/config/provider_runtime.py:156-261`）。
3. **fts_only 不是降级态，是一等公民形态**。OpenMAIC 和 qiaomu 证明：小而精的语料 + 好 LLM，纯词法检索就是完整产品。FTS5 永远在，向量是增强项。
4. DeepTutor 还有两个运维防护必须一并抄：**批次维度一致性校验**（同批返回向量维度不一致 → 直接报错要求重建索引）和签名版本化（binding+model+dim 三元组决定索引目录）。

### 10.4 embedding 三条路线对比与体积实测

| 路线 | 内容 | 优点 | 代价/风险 |
|---|---|---|---|
| A. 内置 ONNX 小模型（fastembed） | `pip install fastembed`，ONNX Runtime CPU 进程内推理，中文模型 `BAAI/bge-small-zh-v1.5`（官方支持列表确认，512 维 MIT） | 零配置、零 key、离线、私有 | 打包 +70~110MB；**512 token 上限 vs 1800 字符 chunk 会截断**；首次下载依赖 HF 可达性（中国网络） |
| B. 用户自配 API（DeepTutor 式） | OpenAI 兼容 `/v1/embeddings`，预置模板 | 复用现有 provider/key 体系；SiliconFlow bge-m3 **免费**；8192 token 装下 1800 字 chunk，无截断 | 需要用户有 key；chunk 正文上云（隐私边界要可见） |
| C. Ollama 本地（现状保留） | `localhost:11434` + `qwen3-embedding:0.6b` | 完全离线、模型质量好 | 用户需自装 Ollama，门槛最高 |

**体积实测（2026-09-03，在项目 venv 内通过 pip 依赖解析 + PyPI/HF 实测）**：

| 项目 | 体积 | 依据 |
|---|---|---|
| onnxruntime 1.29.0 win_amd64 wheel | **13.4 MB** | 实测 PyPI |
| fastembed 全部依赖合计下载 | **约 22 MB** | 实测（tokenizers 2.7 + hf-xet 3.8 + hub 0.8 + 其余小件） |
| 依赖解压后 | 约 60-80 MB | 按 2-2.5x 估算 |
| bge-small-zh-v1.5 模型（fp32） | **91.4 MB** | 实测 safetensors 95,827,648 字节（24M 参数） |
| 模型压缩进安装包 | 约 45-55 MB | ONNX 对 zip 类压缩约砍半 |
| **安装包总增量** | **约 70~110 MB** | — |
| 运行时内存 | 不触发向量则 0；索引/查询时约 200~300MB（懒加载） | 估算 |
| 向量磁盘 | 512 维 float32 = 2KB/chunk，1 万 chunk 约 20MB | 计算 |

路线 A 的两个遗留风险：① 512 token 截断需把 embedding 切块与 FTS 切块解耦（向量索引二次细切到 500 字符级，命中后回链标准 chunk）；② int8 量化可到约 24MB 但中文质量需评测验证。

### 10.5 最终决策（2026-09-03 拍板）

这是一项已确认的**目标方案**，不是已上线能力：当前仍是 FTS5 默认可用、Ollama 为唯一可选 embedding 适配器；用户自配 API embedding 必须通过 B2 的隐私边界、索引安全和真实资料评测验收后才能交付。

1. **向量库不动**：继续 qdrant-client 本地模式（10.3 启示 1）。
2. **不内置本地 ONNX 模型**：fastembed 路线（方案 A）搁置，体积账与截断风险记录在案，未来若用户调研显示大量零 key 用户再重启。
3. **embedding = DeepTutor 式用户自配 API**（方案 B 为主）：
   - 预置模板：**SiliconFlow `BAAI/bge-m3`（免费，标推荐）**、DashScope `text-embedding-v4`（与本地 qwen3-embedding 同家族，可讲成连贯故事）、OpenAI `text-embedding-3-small`；spec 结构照抄 DeepTutor 注册表。
   - **Ollama 保留为可选离线档**（现有 `OllamaEmbeddingClient` 降格为注册表里的一个 provider，零成本保留）；「不内置本地模型」的准确表述是「不内置 ONNX 模型」。
   - 自动降级链：`auto = API key 已配 → 用 API；Ollama 在运行 → 可切换；都没有 → fts_only`（界面照常显示状态）。
4. **必配防护**：嵌入签名版本化 + 重索引提示（provider+model+dim 三元组存 collection 元数据，检测不匹配提示重建，绝不混用向量空间）；批次维度一致性校验；429 限流退避 + 断点续传（sync 大资料库时）。
5. **DeepSeek 用户断层处理**：DeepSeek 无 embedding API——设置页预置模板 + Library 的 fts_only 状态卡从「降级提示」升级为「一键去开通」引导（选模型 + 贴 key），主推免费档 SiliconFlow。
6. **隐私边界**：用户主动选择云端向量模型 = 明确授权（与联网研究授权门禁同模式）；Library 持续显示「hybrid · bge-m3（云端）」让边界可见。
7. **验证闭环**：召回评测集（20~50 对「问题 → 期望 chunk/文档」，真实资料出品）跑 fts_only / vector_only / hybrid 三模式对比 hit@5 与 MRR，结果落 `rag_design.md` 已有的 `retrieval_runs` 表；RRF 权重（vector 是否提到 1.2~1.5）由数据决定。

**决策理由**：对已配置云端 Provider 的用户，API embedding 可以复用既有账户；但本地 Ollama 和零 key 用户也必须完整使用 FTS-only 检索，不能把云端 key 当作产品前提。免费档 bge-m3 可在用户明确选择后降低接入门槛；不内置 fastembed 则避免安装包体积和截断风险。实现仍需完成四件事：① `rag/embedding_service.py` 泛化为 EmbeddingProvider 协议（OpenAI 兼容适配器 + 保留 Ollama 适配器）；② config.yaml / provider.json 加 embedding 槽位与预置模板；③ 设置页「向量模型」选择 + Library 状态卡引导；④ 签名版本化 + 重索引提示。

---

## 附录：精读文件索引（按优先级）

1. `DeepTutor/deeptutor/learning/policy.py` — 门禁与 next_objective 引擎（纯函数）
2. `DeepTutor/deeptutor/learning/mastery.py` — 40 行掌握度数学
3. `DeepTutor/deeptutor/agents/chat/agent_loop.py` — 单循环契约
4. `DeepTutor/deeptutor/services/persona/presets/teacher/PERSONA.md` — Socratic 人格全文
5. `DeepTutor/deeptutor/capabilities/mastery/prompts/en/system.md` — 19 行门禁提示词全文
6. `DeepTutor/deeptutor/agents/question/pipeline.py` — 三阶段出题（注意只学结构，勿抄 2210 行实现）
7. `DeepTutor/deeptutor/tools/ask_user.py` + `DeepTutor/web/components/chat/home/AskUserOptions.tsx` — 交互卡协议
8. `OpenMAIC/lib/orchestration/director-graph.ts` + `lib/chat/agent-loop.ts` — 轻编排
9. `OpenMAIC/lib/pbl/v2/agents/instructor-memory.ts` — 最轻量会话压缩
10. `OpenMAIC/lib/server/agent-runtime/skills.ts` — SKILL.md 三件套
11. `OpenMAIC/eval/` — eval 方法论
12. `qiaomu-book-reader/src/storage.js` — 57 行可靠性设计文档
13. `qiaomu-book-reader/src/main.js:8810-8918, 6819-6890, 5097-5205` — 划线/托管区块/目录降级

**前端专项：**

14. `DeepTutor/web/lib/stream.ts` — 80 行 narration/finish 元数据协议全文件
15. `DeepTutor/web/hooks/useChatAutoScroll.ts` — 328 行自动滚动设计文档（注释即规范）
16. `DeepTutor/web/hooks/useSmoothStreamText.ts` — 141 行零依赖打字机
17. `DeepTutor/web/components/common/MarkdownRenderer.tsx` — 单调 Simple→Rich 渲染器
18. `DeepTutor/web/components/chat/home/AskUserOptions.tsx:198-377, 894-991` — 流序分段 + 原位 resolved
19. `DeepTutor/web/components/quiz/QuizViewer.tsx` — 流式 Quiz 卡（只学结构，1403 行实现勿整抄）
20. `DeepTutor/web/tests/design-token-parity.test.ts` + `tests/architecture-contracts.test.ts` — 前端架构契约测试
21. `OpenMAIC/lib/workbench/session-store.ts:3-23, 913-1752` — foldEvent 纯 reducer 与设计宣言注释
22. `OpenMAIC/lib/workbench/use-workbench-session.ts:9-255` — 订阅表血泪注释 + 重放 + 看门狗
23. `OpenMAIC/components/workbench/chat/tool-presentation.ts` — 工具卡规则表（1002 行纯函数）
24. `OpenMAIC/components/workbench/chat/tool-group-state.ts` + `thinking-bar-state.ts` — 组件外纯状态函数范式
25. `OpenMAIC/e2e/fixtures/mock-api.ts` — Playwright 确定性 mock SSE

**RAG 向量化选型专项（第十章）：**

26. `DeepTutor/deeptutor/services/config/provider_runtime.py:156-261` — EMBEDDING_PROVIDERS 注册表（spec 结构直接照抄）
27. `DeepTutor/deeptutor/services/rag/pipelines/llamaindex/vector_store.py` — FAISS 接缝文件头注释（进程内向量库的完整论证 + issue #552 教训）
28. `DeepTutor/deeptutor/services/embedding/client.py` — 批次维度一致性校验与批量钳制
29. `DeepTutor/deeptutor/services/rag/index_versioning.py` — EmbeddingSignature（binding+model+dim）版本化
30. `OpenMAIC/lib/rag/providers/in-memory-lexical-index.ts` — 「无向量 RAG」的实证（词法索引够用的边界案例）
31. Bobodan 自查：`rag/rrf.py`、`rag/hybrid.py`、`rag/embedding_service.py`、`config.yaml`（rag 段）— 决策的现状依据
