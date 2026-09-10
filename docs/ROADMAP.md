# Bobodan 统一路线图

> 版本：v1.1（2026-09-08）
> 定位：**唯一的"下一步"文档。** 想知道现在做什么、接下来做什么，只看这里。
> 本文合并了以下来源并取代它们的前瞻部分（原文见 `docs/archive/`）：
> - [`archive/PRE_DESKTOP_ROADMAP.md`](archive/PRE_DESKTOP_ROADMAP.md)（openhanako v0.450 研究 → R0-R3 路线，R0 已完成）
> - `Bobodan参考项目调研报告.md` 第 3-10 章（DeepTutor / OpenMAIC / qiaomu 借鉴清单与 RAG 决策，**该报告保留为活文档**，是本文各条目的详细论据与源码索引）
> - [`archive/AGENT_OPTIMIZATION_PLAN.md`](archive/AGENT_OPTIMIZATION_PLAN.md) 遗留事项（该计划主体已于 2026-08-13 交付）
> - [`archive/experience_review_2026-08-01.md`](archive/experience_review_2026-08-01.md) 未决项（已核对部分已修复）
> - P5G.2 / P5G.3 剩余（PROJECT_GUIDE §P5G）

---

## 0. 当前状态快照（2026-09-08）

| 大轮次 | 状态 |
|---|---|
| P5C–P5F（Web 界面 / 资料库 / 设置中心 / 联网研究 / 个人知识库 / 知识地图） | ✅ 完成 |
| 2026-07-26 审查整改（旧系统退役、B1–B9 正确性修复） | ✅ 完成 |
| P5G.0 / P5G.1 / P5G.4 / P5G.5 / P5G.6 | ✅ 完成 |
| 整机优化计划（AG-0~3 / FE-1~4 / LB-1 主体） | ✅ 主体完成（遗留项已并入本文 W3/W4） |
| Library 重构 + 图谱编辑 + 体验轮（Modal/动效/品牌/增量图谱） | ✅ 完成 |
| R0 质量与调试基建（测试策略 / ScriptedProvider / e2e 冒烟化 / dev.py / diagnose / 持久化登记册） | ✅ 完成（`feat/r0-quality-infra`） |
| R0.7 数据 epoch 机制 | ⏳ 并入本文 W4 |
| P5G.2 Electron 桌面版 | ⏸ 推迟（门禁见 W5） |
| P5G.3 支撑页面 | ⏸ 按 C / E 批次拆分；复习提醒可先在 Web 交付 |

### 状态口径

路线项只使用以下状态，避免把“已有部分代码”误写成“已经交付”：

| 状态 | 含义 |
|---|---|
| `待核对` | 需求来自旧审查或调研，开工前必须先核对当前代码与测试，可能已经部分完成 |
| `未开始` | 已确认仍需要实施，尚无可验收交付 |
| `进行中` | 已有未完成改动或只完成部分验收 |
| `已验证` | 行为、测试和用户可见结果均满足验收条件 |
| `暂缓` | 方向保留，但当前批次不投入 |
| `取消` | 已被替代或不再符合产品边界 |

本表中的 P5 阶段状态是历史里程碑；W1-W5 是后续工作池。工作池条目在实施前默认视为 `待核对`，不能仅凭路线描述认定代码缺失。每次开工先记录现状证据，完成后至少留下测试、可复现步骤或用户可见结果之一。

贯穿性哲学（三个参考项目与 Bobodan 已有实践同构，**把已走对的路走完**）：
**模型负责语言，代码负责事实。** 证据门禁、确定性保存 source_ids、纯函数掌握度引擎、fail-closed 解析——一切新增机制都不得动摇这条线。

---

## 1. 工作流总览

五个工作流，编号 W1–W5。条目保留调研报告的原始编号（D/O/Q/F 前缀），细节与源码索引查 `Bobodan参考项目调研报告.md` 对应章节；体验审查遗留用 E 前缀；openhanako 路线用 H 前缀。

工作流是分类，不代表可以整组同时开工。当前只允许一个主交付批次和一个不互相阻塞的验证批次；新参考项目不能直接向 W1-W5 增项，必须先证明现有能力无法满足用户目标。

### W1 学习闭环升级（产品核心，最优先）

| # | 事项 | 动哪里 | 来源 |
|---|---|---|---|
| E1 | 会话内操作失败静默 → 全局错误位 + 可见反馈 | web/backend + ChatPage | 体验审查 P0-1 |
| E2 | 新建资料库路径体验：默认路径预填 + 目的解释 | LibrarySetupDialog | 体验审查 P0-2 |
| E3 | 错题变式死路回退链：无 chunk → 按概念重出 → 原题重练 + 失败原因上屏 | quiz_service | 体验审查 P0-3 |
| E4 | **ask_user 交互卡 + 交互生命周期持久化**（registered→awaiting→answered→graded，断线可恢复） | SSE 事件 + interactions 表 + 前端卡（联动 F11/F12） | D6；报告 P0-1 |
| E5 | **出题三阶段流式管线**：Explore→Plan→逐题生成，每题就绪即渲染；explanation 随题入库 | quiz_service | D8/D9；报告 P0-2 |
| E6 | **掌握度引擎纯函数化**：近 5 次加权 + 置信帽 {1:0.5,2:0.8} + 知识四分类 + next_objective 优先级（挂起问题>到期复习>第一个未掌握点）；agent 每轮先读引擎 | learning/ 新增 engine.py | D1/D2/D3；报告 P0-3；体验审查 P1-5 余项 |
| E7 | **划线最小闭环**：chunk 级划线（四元组锚）+ 托管区块同步到笔记 + ↩ 反链 flash 定位 | Reader + notes 服务 | Q1/Q2/Q3；报告 P0-4 |
| E8 | 导入进度 + 失败清单 + 取消 + 拖拽热区 | kb import 前后端 | 体验审查 P1-8 |
| E9 | 到期复习变式化 + 状态中文化 + "上次 X 天前" | learning_service + ReviewPage | 体验审查 P1-6/P2 |
| E10 | Socratic persona 技能（翻译 PERSONA.md + 优先级裁决：persona 管风格流程、不碰证据门禁） | skills/ 新增 | D10 |
| E11 | AgentLoop 单循环契约：无工具轮=finish、探索预算 + 3 轮结算期、截断续写 | core/agent_loop.py | D4 |
| E12 | prompt 具名块字节稳定 + KB seed 预检索进末尾 user 消息 | core/agent_loop.py | D5/D13 |
| E13 | 出题卡防绕过三道防线：服务端注入参数 / 纯文本收尾重定向 / 卡片数据从持久化重绑定 | Practice artifacts | D7 |
| E14 | 「问 AI」复用练习辅导会话，不再污染会话列表 | PracticePage | 体验审查 P1-9 |
| E15 | 简答三态判分与"学习中"映射核对（AnswerResult.verdict 已有三态，核对批改链路与展示一致性） | quiz_service | 体验审查 P1-10；O10 |
| E16 | 新确认概念返回坐标 + 前端高亮数秒 | concept_service + KnowledgeMap | 体验审查 P1-12 |

### W2 检索与 RAG（第十章决策落地）

> 现状：向量腿从未运行（`.knowledge/qdrant/` 为空），产品实际是 FTS5-only。2026-09-03 已拍板：**向量库不动（qdrant 本地模式）、不内置 ONNX 模型、embedding 走用户自配 API**。完整论证见调研报告第十章。

| # | 事项 | 动哪里 | 来源 |
|---|---|---|---|
| G1 | `EmbeddingProvider` 协议泛化（OpenAI 兼容适配器 + 保留 Ollama 为注册表一项）+ 预置模板（SiliconFlow bge-m3 免费标推荐 / DashScope / OpenAI）+ 设置页「向量模型」+ Library 状态卡升级为开通引导 | rag/embedding_service.py、config、设置页 | ch10 决策 3/5/6 |
| G2 | 防护三件：嵌入签名版本化（provider+model+dim 三元组，不匹配提示重建）+ 批次维度一致性校验 + 429 退避与断点续传 | rag/ | ch10 决策 4；D12 |
| G3 | 索引心跳守卫：600s 无进度报可行动错误（本地 embedding 黑洞连接是常态） | rag/ 索引管线 | ch10；D12；报告 P0-5 |
| G4 | 召回评测集（20–50 对问题→期望 chunk）跑 fts_only/vector/hybrid 三模式 hit@5+MRR，RRF 权重由数据决定，结果落 retrieval_runs | tests/eval + rag_design retrieval_runs | ch10 决策 7；O9 部分 |
| G5 | PDF 目录四级降级链（outline→heading→印刷目录文本匹配→粗体段）+ 扫描页判定 | rag/ PDF 导入 | Q4/Q6 |

### W3 前端体验第二批

**FE-P0（流式正确性，先做）**

| # | 事项 | 动哪里 |
|---|---|---|
| F1 | useChatStream 重构为纯 foldEvent reducer（lib/，seq 幂等），store 只暴露 applyEvent | hooks/useChatStream.ts |
| F3 | SSE 帧订阅表从事件常量派生 + 对账测试（漏订阅=静默丢帧） | lib/api.ts |
| F7 | 自动滚动升级：单写者 + overflow-anchor:none + MutationObserver 合帧 + 手势释放 + 「用户消息才回底」 | useStickyBottomScroll.ts |
| F14 | CJK 字体栈显式点名 + 语义 token 契约测试 + serif 正文 prose | globals.css / tailwind |

**FE-P1（体验质感）**

| # | 事项 | 动哪里 |
|---|---|---|
| F2 | narration/finish 元数据协议：过程文本靠标记事件从答案剔除，前端零启发式 | useChatStream |
| F6 | rAF 自适应打字机 + 单调 Simple→Rich markdown 分级渲染 | ChatPage 管线 |
| F8–F10 | 过程可视化升级：工具卡规则表（动词短语+chips+disclosure，测试对账）、工具组双时钟、thinking 预览/waiting 三点分离 | ProcessFoldBlock |
| F11 | ask_user 卡流序分段渲染 + 原位 resolved + 多题 tab（联动 E4） | artifacts/ |
| F13 | Quiz 流式卡：逐题出现 + chip 导航 + turnId 隔离 | PracticePage |
| F17 | Playwright mock SSE fixture（确定性事件串重放） | e2e/ |
| H-a | 消息操作条（悬停 复制/重答）+ 用户消息编辑重发 | ChatPage；openhanako MessageFooterActions |
| H-b | 会话内查找 Ctrl+F + 时间线导航条 | ChatPage；openhanako |
| H-c | Toast 通知系统 + 错误呈现器（人话一行+详情+错误码；与 E1 联动） | 全局；openhanako |
| H-d | @-mention 升级 inline 徽章（CodeMirror chip） | composer；openhanako |
| H-e | 文档版本 diff 视图（三栏：版本/版本/行级 diff，回滚前先看） | DocumentEditor；openhanako FileHistoryModal |
| H-f | motion spring 三档预设 + AnimatedList 布局动画（衔接现有 --dur token 体系） | ui/；openhanako |

**FE-P2（锦上添花）**：F4 断线恢复全家桶（Last-Event-ID 重放+caught_up+看门狗+命令 ACK）、F5 乐观负 id 对账、F15 空态三件套组件化、F16 组件外 -state.ts 纯函数模式 + 架构契约测试、F18 ProgressRing/LevelUp 庆祝动效、ContextRing 复习负载环（H）。
**体验审查 P2 杂项**：slash/@ 可发现性提示、连续复习多条错题、完成页逐题回顾、来源视图按来源分组、设置保存方式统一、流式不抢滚轮（F7 覆盖）、切资料库不强制跳聊天、空态用路由 Link。

### W4 运行时与数据底座

| # | 事项 | 来源 |
|---|---|---|
| H-R2.1 | **自主循环子系统 → 复习提醒/学习计划**：sessionId 键控循环轮次 + 单槽闹钟 + 预算/连续失败护栏 + 存活不变量；提醒交付 Web toast 先行（对应 P5G.3「复习自动化」，不依赖 Electron） | openhanako lib/loop |
| H-R2.2 | usage ledger 归因强化：start/finish/error 生命周期 + provider 级缓存 token 语义 + 来源归因 | openhanako |
| H-R2.3 | 后台任务统一抽象（deferred results）：持久化 + 投递意图 + 重试 + 唤醒父轮；统一 wiki run / 概念提取 / 整理任务的散装实现 | openhanako |
| H-R2.4 | 个人知识周期整理（Memory Dream / DeepTutor 三层记忆合并项：图章轨迹 / 脚注事实 / 四槽综合） | openhanako + D11 |
| H-R2.5 | 工具目录延迟装配：schema 出 KV 前缀 + BM25 工具搜索 + 桥接工具真实权限语义 | openhanako |
| H-R2.6 | 会话压缩升级：先做 O6 阈值式纯函数压缩（>30 条折叠、切点对齐 user 边界），再做比例预留 + 轮中压缩缝 | openhanako + O6 |
| H-R2.7 | 会话打开恢复三件套（健康尾扫 / 工具快照修复 / lineage 哈希）+ AG-1 JSONL 事件源切换（门禁：P5G 验收后） | openhanako + AG-1 |
| H-R0.7 | 数据 epoch 机制：破坏性 schema 变更走日志化检查点迁移，旧内核打不开新数据 | openhanako（R0 遗留项） |
| O7/O8 | SKILL.md 机器可校验约束 + 激活即转录；build-personal-skill 从错题/会话提炼画像技能卡 | OpenMAIC |

### W5 发布通道（P5G.2 / P5G.3）

**门禁**：W1 的 E1–E7 完成、W2 的 G1–G3 落地、W3 FE-P0 完成。桌面版调试测试难题已由 R0（契约测试替代浏览器 e2e、dev.py、diagnose）正面解决，启动时再吸收 openhanako 三条结论：

1. **sidecar 范式**：服务端独立进程 + stock runtime spawn（零 ABI 地狱）+ 启动心跳 + 崩溃诊断（契约测试保护）。
2. **release digest 生成器**：双语结构化发布说明作为数据（现在就可给 CHANGELOG 用，将来喂给更新 UI）。
3. **signed update trains**：签名清单 + pointer 通道 + 暂存激活回滚（研究不实现，桌面版启动时照抄）。

P5G.3 的产品能力不再整体等待 Electron：Roadmap、复习提醒和部分数据保护可在 Web 先交付；Memory Browser、Workbench 和桌面专属的数据恢复入口仍受 E 门禁约束。P5G 补充项（备份恢复 / 提醒交付 / 升级路径 / 卸载契约 / DPI 与性能预算）按 `PROJECT_GUIDE.md` 的发布验收执行。

---

## 2. 执行批次

大波次已经拆成可独立验收的小批次。每个批次完成后更新状态和证据，再进入下一批；不得把后续批次的“顺手重构”带入当前改动。

| 批次 | 范围 | 完成标准 |
|---|---|---|
| A0 现状核对（当前） | 逐项核对 E1-E7、G1-G3 与 FE-P0，标记已存在、部分存在和真实缺口 | 每项有代码 / 测试证据；删除重复或已被替代的任务 |
| A1 学习闭环正确性 | E1、E3、E4、E13、E15 | 错误可见；交互可恢复；练习卡不可绕过；三态判分前后端一致 |
| A2 学习推进 | E5、E6、E9、E14 | 题目可逐步就绪；掌握度由纯函数计算；复习状态清楚；题内问 AI 不污染会话列表 |
| A3 阅读与导入 | E2、E7、E8、E16 | 新建路径可理解；划线可回链；导入进度与失败可操作；新概念可定位 |
| B1 检索基线 | G4 的 FTS-only 基线、G5 | 有真实资料评测集和可重复指标；扫描页 / 目录失败不静默 |
| B2 可选向量检索 | G1-G3，再完成 G4 hybrid 对比 | 未配置时 FTS 正常；云端发送边界明确；签名、重建、限流和中断可恢复；数据证明 hybrid 有收益 |
| C1 前端正确性 | FE-P0、F2、F11、F17、H-c | SSE 不丢帧；滚动不抢用户；交互卡可测；错误反馈统一 |
| C2 体验增强 | 其余 FE-P1；只选当前用户高频路径实施 | 至少一次桌面、窄屏和移动端真实流程验收；不新增主导航 |
| D 运行时底座 | W4 中被上层需求实际阻塞的条目 | 每项由明确故障或发布门槛驱动，不以参考项目完整度为目标 |
| E 桌面发布 | W5 | A1-A3、B1-B2、C1 通过；安装、升级、卸载、备份恢复和崩溃诊断可验收 |

当前焦点是 A0。A0 完成前不应并行实现 A1 与 B2，因为现有代码已经包含部分确认状态、提取状态和检索记录，直接照路线开发可能造成重复实现。

排序原则：学习闭环正确性 > 可恢复性 > 检索质量证据 > 界面质感 > 通用运行时能力 > 发布包装。任何条目开工前先对齐 `PROJECT_GUIDE.md` 的产品边界四问。

### 单项完成定义

一项路线任务只有同时满足以下条件才能标记为 `已验证`：

1. 用户触发路径、成功结果、失败结果和恢复动作已经明确。
2. 服务端真相源与前端临时状态的边界明确，没有新增第二套业务状态。
3. 高风险逻辑有针对性测试；视觉改动至少检查桌面和移动端。
4. 用户可见文案不泄露内部实现、模型思维链、本地绝对路径或密钥。
5. `ROADMAP.md`、`PROJECT_GUIDE.md` 或专题真相源已同步，不保留相互矛盾的描述。

---

## 3. 已拍板决策（不再重复讨论）

| 决策 | 内容 | 依据 |
|---|---|---|
| RAG embedding | 向量库不动（qdrant 本地）；不内置 ONNX 模型（fastembed 搁置，+70~110MB 与 512 token 截断风险记录在案）；embedding 走用户自配 API（SiliconFlow bge-m3 免费标推荐）+ Ollama 可选离线档；fts_only 是一等公民形态不是降级 | 调研报告 ch10 |
| 桌面版推迟 | P5G.2 门禁化；先 R1/R2 主体；sidecar/server-info/契约测试三结论必须吸收 | PRE_DESKTOP + 本次确认 |
| 教学闭环哲学 | 模型管教学、引擎管算术；推进由已掌握内容计算，绝不用 stage counter | DeepTutor 对照 + Bobodan 证据门禁既有实践 |
| 动效体系 | 三档 token（120/160/220ms）+ 两条缓动；应用内减动效 = OS 级语义；不为动画引 motion 库 | DESIGN.md §11 + 2026-08-28 体验轮 |
| 测试政策 | 风险驱动分层；LLM 单缝 ScriptedProvider；浏览器只留冒烟；契约测试优先 | tests/README.md |

## 4. 明确不做（合并自三份来源，防止范围蔓延）

- 八引擎 RAG 矩阵、GraphRAG/LightRAG 等多引擎（FTS5+Qdrant+RRF 够用，新增手段须评测证明失败）
- LangGraph / Postgres 租约 / 多 worker durable runner / S3（单进程 + SQLite 即可；只取「事件先落盘再投递」与 interrupted/resumed 两个概念）
- 多用户 / IM 渠道 / subagent 商店 / 50+ provider 逐 issue 兼容层（收缩到 OpenAI 兼容协议 + 能力检测降级清单）
- TTS / 语音克隆 / 视频渲染 / i18n×10
- 思维链 / mood 展示（产品边界）；WS 传输层（SSE+seq 已覆盖）；会话分叉树
- CSS multicol 真分页（chunk 滚动阅读即可）；Obsidian 深耦合；11702 行单文件式实现
- framer-motion/motion 库引入；虚拟滚动库；Neo4j；PDF/DOCX 编辑
- 内置 ONNX embedding 模型（搁置，见 ch10.4）

## 5. 来源索引

- **调研报告**（`Bobodan参考项目调研报告.md`，活文档）：D1–D13 = §3.3、O1–O10 = §4.3、Q1–Q10 = §5.3、F1–F18 = §9.3、RAG 决策 = §10；各条目的机制精讲与源码行号在其对应章节，精读文件优先级见其附录。
- **归档文档**（`docs/archive/`，已完成或已被本文取代）：[`archive/AGENT_OPTIMIZATION_PLAN.md`](archive/AGENT_OPTIMIZATION_PLAN.md)（遗留已并入 W3/W4）、[`archive/PRE_DESKTOP_ROADMAP.md`](archive/PRE_DESKTOP_ROADMAP.md)（R0 完成，R1→W3、R2→W4、R3→W5）、[`archive/TASKS_LIBRARY_REWORK.md`](archive/TASKS_LIBRARY_REWORK.md)（已交付）、[`archive/knowledge_map_design.md`](archive/knowledge_map_design.md) 与 [`archive/knowledge_map_reliability_editing_design_2026-07-27.md`](archive/knowledge_map_reliability_editing_design_2026-07-27.md)（P5E.6 已交付，未竟项：跨文档候选/合并候选、evidence_level=cross 前端区分、提取计时 UI 核对 → 择机并入 W1/W3）、[`archive/project_review_2026-07-26.md`](archive/project_review_2026-07-26.md)（B1–B9 已整改）、[`archive/experience_review_2026-08-01.md`](archive/experience_review_2026-08-01.md)（未决项已并入 W1/W3）。
- **仍在体系内**：`PROJECT_GUIDE.md`（产品边界与阶段验收）、`DESIGN.md`（视觉硬约束）、`rag_design.md`（RAG 架构真相源）、`MCP.md`、`tools/skills.md`。
