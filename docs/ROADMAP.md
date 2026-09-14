# Bobodan 统一路线图

> 版本：v1.2（2026-09-08）
> v1.2：路线审查补齐被遗漏的 F12，并记录 A0 完成状态。
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
| A0 现状核对（E1–E7 / G1–G3 / FE-P0，证据表见 §2） | ✅ 完成（2026-09-08） |
| A1 学习闭环正确性（E1 / E3 / E4 / E13 / E15） | ✅ 完成（2026-09-08，交付记录见 §2） |
| E18 题库 MVP（S1–S5） | ✅ 完成（2026-09-10，交付记录见 §2） |
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
| E3 | 错题变式死路回退链：无 chunk → 按概念重出 → 原题重练 + 失败原因上屏（A0：后端三级回退已存在，只做前端上屏） | quiz_service | 体验审查 P0-3 |
| E4 | **ask_user 交互卡 + 交互生命周期持久化**（registered→awaiting→answered→graded，断线可恢复）——**已交付（A1 + 2026-09-10 补齐轮）**；剩余 UI 细化见 F11/F12 | SSE 事件 + interactions 表 + 前端卡 | D6；报告 P0-1 |
| E5 | **出题三阶段流式管线**：Explore→Plan→逐题生成，每题就绪即渲染；explanation 随题入库（**口径**：这里的"入库"就是题库 D1 的入库，见 `QUESTION_BANK_DESIGN.md`） | quiz_service | D8/D9；报告 P0-2 |
| E6 | **掌握度引擎纯函数化**：近 5 次加权 + 置信帽 {1:0.5,2:0.8} + 知识四分类 + next_objective 优先级（挂起问题>到期复习>第一个未掌握点）；agent 每轮先读引擎 | learning/ 新增 engine.py | D1/D2/D3；报告 P0-3；体验审查 P1-5 余项 |
| E7 | **划线最小闭环**：chunk 级划线（四元组锚）+ 托管区块同步到笔记 + ↩ 反链 flash 定位 | Reader + notes 服务 | Q1/Q2/Q3；报告 P0-4 |
| E8 | 导入**流程**：进度 + 失败清单 + 取消 + 拖拽热区（边界见 E17，勿与其重复） | kb import 前后端 | 体验审查 P1-8 |
| E9 | 到期复习变式化 + 状态中文化 + "上次 X 天前"（**变式复用 E3 已交付的通道**，不要新建生成器） | learning_service + ReviewPage | 体验审查 P1-6/P2 |
| E10 | Socratic persona 技能（翻译 PERSONA.md + 优先级裁决：persona 管风格流程、不碰证据门禁） | skills/ 新增 | D10 |
| E11 | AgentLoop 单循环契约：无工具轮=finish、探索预算 + 3 轮结算期、截断续写 | core/agent_loop.py | D4 |
| E12 | prompt 具名块字节稳定 + KB seed 预检索进末尾 user 消息 | core/agent_loop.py | D5/D13 |
| E13 | 出题卡防绕过三道防线：服务端注入参数 / 纯文本收尾重定向 / 卡片数据从持久化重绑定（A0：重绑定已存在，缺前两道） | Practice artifacts | D7 |
| E14 | 「问 AI」复用练习辅导会话，不再污染会话列表 | PracticePage | 体验审查 P1-9 |
| E15 | 简答三态判分与"学习中"映射核对（AnswerResult.verdict 已有三态，核对批改链路与展示一致性） | quiz_service | 体验审查 P1-10；O10 |
| E16 | 新确认概念返回坐标 + 前端高亮数秒 | concept_service + KnowledgeMap | 体验审查 P1-12 |
| E17 | **资料库文件树：按真实文件夹呈现与建立资料库**（详见下方设计记录） | Library 前后端 + 受沙盒保护的资料库文件 API | 2026-09-10 设计确认（用户 E2E 反馈） |
| E18 | **题库**：浏览 / 筛选 / 收藏 / 一键练 / 对话引用 / 命名练习集 / 联网搜题 / 导出与备份（设计 D1–D9 见 [`QUESTION_BANK_DESIGN.md`](QUESTION_BANK_DESIGN.md)）——**S1–S7 全部交付（2026-09-10 立项 + 2026-09-11 收口）**；只剩「联网题新概念进候选」与「资料库整体备份」两件，分别属 D9 的候选钩子与 PROJECT_GUIDE 的数据保护专项 | quiz store + 练习页视图 + 复习页 + Chat 工具 | 2026-09-10 立项设计 |

#### E17 设计记录（2026-09-10）

**问题**（用户实测）：Library 把资料拍平成一行行，看不出文件在哪；同名资料出现两行。

- `documents` 表**有 `path`**（实测三层：`ai-agents-from-zero/`、`…/参考资料-2-LangChain入门/10-rag/docloads/assets/`、`raw/notes/`、`wiki/{sources,concepts,entities}/`），但 API 的 `DocumentSummary`（`web/frontend/src/types.ts:91-114`）**不返回任何路径字段** → 前端只能拍平。
- 实测该库 70 份 = **48 `course_document`（真实资料）+ 22 `obsidian_note`（AI 生成页）**；生成页住在 `wiki/*` 子目录，却与源文件并排显示 → 被误读成重复索引。**根因是"把生成物当资料展示"，不是索引 bug。**

**参考做法**（见 `REFERENCE_PROJECTS.md`）：

- DeepTutor 的 `obsidian` **连接型 KB**：KB 只是指向用户文件夹的**指针**，**完全不建索引**，由 capability 直接导航真实文件（`deeptutor/knowledge/kb_types.py:9-11`）。
- openhanako 的 **Desk**：native root dir，文件按**原始路径**附加而非 upload（`desktop/src/react/MainContent.tsx:121-136`、`deskBasePath`/`deskFiles`）。

**已定决策**：

1. **树建在真实文件系统上**（不是建在索引上）：浏览资料库文件夹本身，索引元数据（提取状态、chunk 数、是否 AI 生成页）作为徽章叠加。理由：Obsidian 的 vault 就是文件；与 `CLAUDE.md`「原始资料是事实来源」一致；同时天然消除"生成页与源文件并排"的困惑。
2. 写操作范围（建议）：**只读浏览 + 选择目标文件夹导入 + 新建文件夹**。**与 E8 的边界**：E8 负责导入**流程**（进度 / 失败清单 / 取消 / 拖拽热区），E17 负责**目标位置**（选文件夹 / 新建文件夹）；拖拽落点解析归 E8，落点确定之后的落库位置归 E17。

**硬约束（决定了什么不能顺手做）**：

> `document_id = _stable_hash(source)`（`obsidian/sync.py:281`），即**资料身份由路径派生**；概念证据、题目 `source_ids`、wiki `sources` 都引用它。**重命名/移动文件会改变身份并打断证据链。** 因此重命名/移动必须先设计"身份迁移"（内容型稳定 ID，或迁移 + 重新关联），**不得与展示层改造同期实施**。

**未决（实施前需定）**：

- 生成物在树里的归属：`wiki/` 作为普通子文件夹，还是单独的「AI 整理」区（决定用户会不会再次把它当资料）。
- 是否需要「仅已索引」筛选（未索引文件在树上可见但不可检索，需要一眼可辨）。
- 现有能力复用：编辑 `PUT /documents/{id}/content`、版本与回滚、AI 编辑提案、删除（**归档**到 `.bobodan/archive/raw/`）都已经存在，不要重做。

**归属批次**：与 A3（阅读与导入，E2/E7/E8/E16）同期或紧随其后。

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

**设计规格层已先重写（2026-09-14，见 §2「设计规格层重写」）**：复查后确认 `DESIGN.md` 的问题是「紧在禁令、松在规格」——颜色只有 1 档可用的边框、2 个被祝福的阴影、3 个字号级别，而 §14 全是绝对禁止没有配额，实现只能退到发丝线列表 + 只用主色。规格层已按实测重写（颜色面积预算 / 表面·边框·高度分档 / 字号硬下限 / 间距刻度 / 三档 spring / 反模式改配额），骨架层已落地，token 一致性与漂移棘轮由 `web/frontend/src/lib/designTokens.test.ts` 钉住。**下方 FE-P0 / FE-P1 的页面级工作按新规格分批执行**（Chat → Practice·Review → Library·Reader → 低频页），每落一批就把棘轮预算下调一次。

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
| F11 | ask_user 卡**剩余**部分：多题 tab + 自动跳题 + Other 草稿（**E4 已交付**：流序渲染 + 原位 resolved，勿重复实现） | artifacts/ |
| F12 | question 未答时接管 composer（编号问卷 + 键盘），answered 由 fold 派生（**E4 已交付**：答案经 tool result 回填、不产生用户气泡） | ChatPage composer |
| F13 | Quiz 流式卡：逐题出现 + chip 导航 + turnId 隔离 | PracticePage |
| F17 | Playwright mock SSE fixture（确定性事件串重放） | e2e/ |
| H-a | 消息操作条（悬停 复制/重答）+ 用户消息编辑重发 | ChatPage；openhanako MessageFooterActions |
| H-b | 会话内查找 Ctrl+F + 时间线导航条 | ChatPage；openhanako |
| H-c | Toast 通知系统 + 错误呈现器（人话一行+详情+错误码；与 E1 联动） | 全局；openhanako |
| H-d | @-mention 升级 inline 徽章（CodeMirror chip） | composer；openhanako |
| H-e | 文档版本 diff 视图（三栏：版本/版本/行级 diff，回滚前先看） | DocumentEditor；openhanako FileHistoryModal |
| H-f | motion spring 三档预设 + AnimatedList 布局动画（衔接现有 --dur token 体系）——**三档 spring 预设（CSS `linear()`）已在 2026-09-14 落地（`DESIGN.md` §11 / `styles.css`），`AnimatedList` 布局动画仍待做** | ui/；openhanako |
| F19 | 页面级规格收敛：字号 / 间距 / 交互四态 / 表面分档，按 Chat → Practice·Review → Library·Reader → 低频页 分批，每批同步下调 `designTokens.test.ts` 的棘轮预算（**四批全部完成，字号下限已收口到 0；间距与圆角的存量仍在棘轮上，见 §2「设计规格层重写」**） | 各页面 CSS；`DESIGN.md` §5–§7、§16 |

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
| A0 现状核对（完成） | 逐项核对 E1-E7、G1-G3 与 FE-P0，标记已存在、部分存在和真实缺口 | 每项有代码 / 测试证据；删除重复或已被替代的任务 → 结果见下方「A0 核对结果」 |
| A1 学习闭环正确性（完成） | E1、E3、E4、E13、E15 | 错误可见；交互可恢复；练习卡不可绕过；三态判分前后端一致 |
| A2 学习推进 | E5、E6、E9、E14 | 题目可逐步就绪；掌握度由纯函数计算；复习状态清楚；题内问 AI 不污染会话列表 |
| A3 阅读与导入 | E2、E7、E8、E16 | 新建路径可理解；划线可回链；导入进度与失败可操作；新概念可定位 |
| B1 检索基线 | G4 的 FTS-only 基线、G5 | 有真实资料评测集和可重复指标；扫描页 / 目录失败不静默 |
| B2 可选向量检索 | G1-G3，再完成 G4 hybrid 对比 | 未配置时 FTS 正常；云端发送边界明确；签名、重建、限流和中断可恢复；数据证明 hybrid 有收益 |
| C1 前端正确性 | FE-P0、F2、F11（剩余部分）、F12、F17、H-c | SSE 不丢帧；滚动不抢用户；交互卡可测；错误反馈统一。**注意**：F11/F12 只做 E4 未覆盖的部分；PracticePage 会被 E13 / F13 / E18 同时触及，批次内排开 |
| C2 体验增强 | 其余 FE-P1；只选当前用户高频路径实施 | 至少一次桌面、窄屏和移动端真实流程验收；不新增主导航 |
| D 运行时底座 | W4 中被上层需求实际阻塞的条目 | 每项由明确故障或发布门槛驱动，不以参考项目完整度为目标 |
| E 桌面发布 | W5 | A1-A3、B1-B2、C1 通过；安装、升级、卸载、备份恢复和崩溃诊断可验收 |

### A0 核对结果（2026-09-08 完成）

核对方式：逐项在代码与测试中查找产物。结论为「部分存在」的条目只补缺口，不再重写已有实现；结论为「后端已存在」的条目从批次中收缩为收尾项。

| 条目 | 核对结论 | 证据 | 批次内应做的部分 |
|---|---|---|---|
| E1 | 部分存在 | `ChatPage.tsx` 已有局部 `error` state + `ErrorNotice` + `toErrorMessage` + `BlockErrorBoundary` | 补 App 级全局错误位，收敛剩余静默 catch |
| E2 | 部分存在 | `LibrarySetupDialog.tsx` create 模式已预填 `~/Documents/Bobodan` | 补「目的解释」文案 |
| E3 | 后端已存在 | `service/quiz_service.py` `generate_wrong_answer_variant`：chunk → `concept_fallback` → `replay` 三级回退并返回 `mode` | 只做前端「失败原因上屏」+ 回归测试 |
| E4 | 未开始（真实缺口） | 全仓 `.py` 无 `ask_user` / `interaction`；可复用同类模式 `memory_confirmation` artifact 与 `/api/chat/memory/proposals/{id}/confirm` | 全量实施 |
| E5 | 未开始 | `quiz_service` 仅单发 `generate_questions`，无 plan / 逐题阶段 | 全量实施 |
| E6 | 未开始 | 无 `learning/engine.py`（现有 progress / workflow / scheduler / store / schema / path） | 全量实施 |
| E7 | 未开始 | Reader / Library 仅有跳转用 `highlightedChunk`，无用户划线锚存储与笔记同步 | 全量实施 |
| G1 | 未开始 | `rag/embedding_service.py` 仅为 Ollama 薄封装，无协议或适配器 | 全量实施 |
| G2 | 未开始 | `rag/` 无签名、维度校验或 429 退避 | 全量实施 |
| G3 | 未开始 | `rag/` 无心跳 / 无进度守卫 | 全量实施 |
| F1 | 未开始 | 无 `foldEvent`；归约逻辑仍在 `useChatStream` hook 内 | 全量实施 |
| F3 | 部分存在 | `lib/api.ts` 的 `ChatStreamEvent` union 是事件名唯一起源；`api.test.ts` 已覆盖解析、去重与坏帧 | 补「订阅表派生 + 漏订阅对账测试」 |
| F7 | 部分存在 | `useStickyBottomScroll.ts` 已有 rAF τ=85ms、>720px 瞬移、用户干预取消、ResizeObserver | 补单写者、`overflow-anchor:none`、MutationObserver 合帧、手势释放、「用户消息才回底」 |
| F14 | 部分存在 | `styles.css` 的 `--font-ui` / `--font-reading` 已显式点名 CJK 字体 | 补语义 token 契约测试与 serif 正文 prose |

顺带核对（属 A1 范围，提前确认）：

| 条目 | 核对结论 | 证据 | 应做的部分 |
|---|---|---|---|
| E13 | 部分存在 | `practice_ready` artifact（`tools/quiz_tools.py`）、按持久化重绑定（`web/backend/routers/chat.py`）、persist-once 测试（`tests/test_web_backend.py`）已存在 | 补「服务端注入参数」与「纯文本收尾重定向」两道防线 |
| E15 | 部分存在 | `quiz/evaluator.py` 已产出 `correct / partial / incorrect` 三态 | 只需核对批改链路与前端展示一致性 |

### A1 交付记录（2026-09-08 完成）

| 条目 | 状态 | 证据 |
|---|---|---|
| E1 | 已验证 | 新增 `noticeStore` + `NoticeCenter`（AppShell 全局挂载，跨页可见）；ChatPage 操作失败改走全局位，本地 `error` 只留会话加载与流式失败；AppShell 首次配置保存的静默 catch 已修；`noticeStore.test.ts` |
| E3 | 已验证 | `wrongAnswerFallbackNotice` 把后端 `mode` 映射为可见原因并接到全局提示位（导航后仍可见）；`wrongAnswerMode.test.ts`；后端三级回退链 A0 已确认存在 |
| E4 | 已验证（2026-09-10 补齐） | 首轮只交付了"持久化 + 恢复"，**漏了契约里的"暂停 + 回传"**，且注入 bug 让记录写进了错误的工作区（应答端点 404）。补齐后：`tools/ask_user.py` 声明 `workspace`/`chat_session_id` 由 `execute_tool` 注入（`core/agent_loop.py` 把 `tool_call_id` 戳进暂停载荷）；`ToolResult.pause_for_user` 让本轮以 `termination_reason="paused"` 干净结束并**故意不写 tool result**；`run_stream(resume_tool_call_id=...)` 把答案**回填成那条 tool 消息**再续跑（跳过 prompt/记忆重注入）；回填带继续指令；`/api/chat/runs` 接受 `resume_interaction_id`；新用户消息先用合成 tool result 关闭挂起（保证 provider 消息合法）；会话里最多一个 open interaction，7 天窗口只做数据清理。测试：`test_e4_interactions.py`（含走真实 `execute_tool` 的注入回归）、`test_e4_pause_resume.py`、`AskUserCard.test.tsx` |
| E13 | 已验证 | 防线①：web 白名单移除 `quiz_start`/`quiz_submit`，练习只能经服务端绑定的 `practice_ready` 卡片；防线②：`InlineQuestionPolicy` 检测纯文本选项收尾并重定向到 `question_generate`；防线③：卡片数据从持久化重绑定，`ask_user` 同样剥离正确答案；`test_e13_inline_question.py` |
| E15 | 已验证 | `quiz_attempts.verdict` 列 + 迁移；`partial` 映射为「学习中」（1 天间隔、ease 不惩罚）；逐题回顾显示三态；`test_e15_partial_verdict.py` |

分支验证：Python `1396 passed`、Vitest `57 passed`、前端 lint 与生产构建通过。

**E4 补齐轮（2026-09-10，`feat/e4-interaction-flow`）**：承接上面的口径问题——A1 把 E4 标成"已验证"时，契约的"暂停/回传"一半并不存在。补齐轮按参考项目的三家机制对比（见 `REFERENCE_PROJECTS.md` 案例 1）选了 **D+B**：挂起 tool result + 回合边界续跑 + 新助手消息。验证：Python `1402 passed`、Vitest `57 passed`、lint/tsc/生产构建通过。

### E18 交付记录（2026-09-10 完成）

范围是 `QUESTION_BANK_DESIGN.md` 的实现顺序 **S1–S5**（S6 联网搜题、S7 导出/备份、命名练习集、行内「问 AI」引用按设计留待后续）。E18 是用户 E2E 反馈驱动的独立小批次，不改变 A2 的在途顺序。

| 切片 | 状态 | 证据 |
|---|---|---|
| S1 数据层 | 已验证 | `questions.bookmarked_at`（沿用 `_ensure_db` 的 PRAGMA 迁移，幂等）；`list_bank_questions` / `count_bank_questions` / `bank_overview` / `set_bookmark`；状态由**最近一次作答**派生（`MAX(id)` 子查询），**不物化**；未作答题目不返回 `answer`/`explanation`；`tests/test_quiz.py` +9（含旧库迁移、"最新作答胜出"、分页筛选） |
| S2 服务 + API | 已验证 | `QuizService.get_bank` / `bookmark_question` / `start_bank_practice`；`GET /api/quiz/bank`、`POST /api/quiz/bank/bookmark`、`POST /api/quiz/bank/practice`；`tests/test_web_backend.py` +4 HTTP 契约（404 `question_not_found`、400 `bank_empty`） |
| S3 练习页视图 | 已验证 | `practice/bank` 静态路由（注册在 `practice/:practiceSessionId` 之前）+ `QuestionBankPage.tsx`：状态筛选、搜索、概念筛选、分页、收藏、一键重练；`e2e/question-bank.spec.ts` 在 desktop / 窄屏 / 移动三档各 2 条 |
| S4 复习衔接 | 已验证 | 「错题」在复习队列与题库里是同一个谓词：`get_wrong_answers` 改为**只取最近一次判定为 `incorrect`**，`partial` 不算错，`get_weakness_analysis` 同步排除 `partial`；`tests/test_learning_service.py` +2 交叉断言；Review 与练习小结都有进题库的入口 |
| S5 Chat 工具 | 已验证 | `tools/question_bank.py` 提供 `bank_overview` / `bank_list` / `bank_bookmark`，**只声明 `workspace`**（`execute_tool` 只注入声明过的参数——E4 的 404 就是这个坑）；只读 + 收藏、**不含起练**，因此不构成 E13 已封堵的"聊天文本练习"通道；`tests/test_question_bank_tools.py` +4 |

**有意为之的用户可见语义变更**：错题集从「所有答错的尝试」改为「最近一次仍答错」。答错后重练答对的题会同时从错题本和题库的错题筛选里消失；复习调度引擎不变，仍按 SM-2 独立计算。

**边界**：E18 未触碰 `document_id = _stable_hash(source)` 的路径派生（属 E17），也未改动已有 17 道题的任何数据。

分支验证：Python `1424 passed`、Vitest `57 passed`、前端 lint 与生产构建通过、Playwright `56 passed / 1 skipped`（workers=2）。

### E18 收口轮（2026-09-11 完成）

首轮 S1–S5 交付后，逐条对照 `QUESTION_BANK_DESIGN.md` §6 的验收条件发现四处「设计写了、实现没有」的缺口，连同 S6 / S7 分五批补齐；每批都有回归测试，UI 改动另有 Playwright 覆盖。

| 批次 | 状态 | 证据 |
|---|---|---|
| 第 1 批 筛选轴 + 复习窗口 | 已验证 | `difficulty` / `source` 打通 store → API → UI，题库页加题型 / 难度 / 资料三个下拉与「清除筛选」；批量练不再排除收藏并带上全部筛选；复习页返回题库真实错题总数 `wrong_total`（`get_review_queue` 窗口放宽到 200，路由上限 500），截断时给「在题库中查看全部」。**更正了 S4 被高估的「已交付」**——首版只统一了错题定义、20 条窗口还在 |
| 第 2 批 引用某一道题 | 已验证 | 题库行「问 AI」把 `question_id` 写进对话草稿；`bank_list(question_id=…)` 按 id 读回同一道题（走题库路径，未作答仍不返回答案）；`GET /api/quiz/bank?question_id=` 同源 |
| 第 3 批 命名练习集 + 测试隔离 | 已验证 | D8 两张小表（只存 id，有测试钉住列定义）+ 全套 REST + 题库页「练习集」区（按当前筛选建集 / 查看 / 练这集 / 改名 / 删除 / 逐题加入移出），列表新增 `set_id` 视图；agent 按 D4 不碰集合结构。同批查出并修掉：`test_learning.py` 与 `test_repl.py` 用当前目录当工作区，会写入**开发者真实 `.knowledge/bobodan.db`**；`tests/conftest.py` 加了会话结束的 tripwire |
| 第 4 批 S6 联网搜题 | 已验证 | 出题新增 `mode="search"`：只提取网页上已有的题目、来源页快照 + `attribution_kind=web` + 每条来源标 `third_party`；练习页加「让 Bobodan 出题 / 搜现成的题」切换。搜题模式**没有本地分支**，且有回归测试禁止它调用 `generate_from_query` |
| 第 5 批 S7 导出与备份 | 已验证 | 题库级备份 / 恢复（`bobodan-question-bank` 带版本号，覆盖题目 / 作答 / 收藏 / 练习集；删除顺序按外键逆序，测试抓出过这个 bug）+ 按筛选 / 练习集导出 Markdown（第三方题目默认排除、显式包含时逐条标注）；题库页加导出 / 备份 / 恢复三个入口 |

验证：Python `1450 passed`、Vitest `57 passed`、前端 lint 与生产构建通过、Playwright `74 passed / 1 skipped`（题库 e2e 由 6 条增至 24 条，覆盖三视口）。测试套件的 tripwire 确认全量运行前后真实工作区库的哈希与 mtime 不变。

**收口后仍不做**：① 联网题的新概念只进候选（D9 的硬边界「不进知识地图」一直成立，缺的是候选钩子）；② 资料库整体备份 / 恢复（PROJECT_GUIDE 的数据保护专项，题库这份届时并入）。

当前焦点仍是 A2（E5、E6、E9、E14）。A0/A1/E18 已确认的基础设施——全局错误位、交互生命周期、练习卡服务端绑定、题库真相源——在 A2 与后续批次中应复用，不要另起一套。

排序原则：学习闭环正确性 > 可恢复性 > 检索质量证据 > 界面质感 > 通用运行时能力 > 发布包装。任何条目开工前先对齐 `PROJECT_GUIDE.md` 的产品边界四问。

### 设计规格层重写（2026-09-14 完成）

用户实测反馈「前端 UI 还是不好看、不够丝滑」，复查 `DESIGN.md` 后确认问题不是「约束太紧」，而是**紧在禁令、松在规格**：三档纸色只差 2–4/255 等于一档、全站 31 条 `transition`、文档写「辅助 12–13px」而 494 条 `font-size` 里 233 条（47%）低于 12px、`--blue*` 被引用 188 次而 `--petal-wash` 只有 2 次。本轮先重写规格层再落地骨架层，页面级收敛按批次执行（W3 F19）。

| 层 | 状态 | 证据 |
|---|---|---|
| 规格层（`DESIGN.md`） | 已验证 | §4 颜色改**面积预算**（墨蓝不限、sage/clay 每屏 ≤1 整块、petal ≤2% 视口且须列调用点）；§4 token 表换成代码真实命名并成为唯一真相源；§5 字号下限（辅助 ≥12 / 标签 ≥13 / 正文 16–18）成硬约束；§6 新增间距刻度 4/8/12/16/24/32/48；§7 纸色三档拉开 + `--paper-sunken`、`--shadow-lift`、圆角 6/8/12/16、边框三档；§11 三档 spring（CSS `linear()`，不引 motion 库）+ `scale` 0.96–1.02 与 ≤220ms 布局动画；§14 拆「底线 / 配额」；新增 §16 组件规格与交互四态 |
| 骨架层（`styles.css`） | 已验证 | 侧栏 / 右栏改 `--paper-sunken`（三级结构第一次显形）、顶栏与右栏 tab active 走 `--shadow-lift`、导航与按钮补 hover 抬升与 spring 按压、圆角与间距开始走 token、shell 一层 10 处 10–11px 标签提到 12px、`--muted` / `--faint` 加深（正文对比度同时改善） |
| F19 批次 1（Chat 页） | 已验证 | 起点是实测的 8.8px 时间戳、9–11px 的 chip 与来源元数据、10px 的编排器下拉、12.5px 的选项 chip。收敛后 **Chat 页再无低于 12px 的文本**（71 个文本节点逐个取计算样式）：字号改走 §5 下限、间距与圆角改走 `--space-*` / `--radius-*`、`.assistant-message` 48→32 与 `.user-message-wrap` 34→24 收紧行距、下拉菜单的旧纸色写死值换成 `var(--paper-soft)`、chip 与菜单补齐 hover/按压/选中四态。回归：`e2e/interaction.spec.ts` 新增逐节点字号下限断言（未作答卡与已作答两态、三视口）。棘轮：<12px 226→208、裸 `ease` 16→15、脱轨圆角 73→69、裸毫秒 5→4 |
| F19 批次 2（Practice·Review 页） | 已验证 | 直击原始抱怨：参考答案 `.answer-feedback small` **原先没有字号**（跟着 `<small>` 缩到 0.8em）且用 `--muted`，现为 14px / `--ink` / 500；小结里的「你的答案」11→13px 并从 `--muted` 提到 `--ink`；批改意见与解析跟随 `var(--body-font-size)`；简答题输入框原先没有字号（继承容器），现 16px 且跟随阅读偏好。另扫尾 practice / review / page-heading 一层 10–11px 标签，圆角与间距全走 token，写死的旧纸色换成 `var(--paper-soft)`。复核：两页可见文本已无低于 12px 的元素。棘轮：<12px 196→195、脱轨圆角 69→65 |
| 停靠面回调（用户反馈） | 已验证 | 第一版停靠面 `#efeade` 比画布深 9–19/255 且 HSL 饱和度更高（0.35 > 0.29），侧栏与右栏渲染成饱和黄带。改用 Kami 同源三档（`#f0eee6` / `#f5f4ed` / `#faf9f5`），并把「不突兀」变成可执行约束：`designTokens.test.ts` 新增「纸张阶梯」——顺序固定、与画布每个通道差 ≤ 8/255、停靠面必须更灰，对每个纸色主题都跑。实测把 `#efeade` 改回去会同时报出通道超限与饱和度断言 |
| F19 批次 3（Library·Reader 页） | 已验证 | 资料列表是全站字号最失控的一页：50 行文档每行一个 9px 的状态 chip（`.document-extraction-state`）与 10px 的 meta。chip 9→12、标题 12→14、meta 10→12，阅读器的「资料片段」标记（单页 64 处）与眉标 10→12；表单 / 编辑器一族的 9–11px 辅助文字用一条按选择器前缀限定的脚本（先 dry-run 再 apply）统一提到 12–13px。回归：首次导入流程补「建库弹窗不得有低于 12px 的文字」。棘轮：<12px 195→167、脱轨圆角 65→60 |
| F19 批次 4（设置 / Wiki / 笔记 / 知识地图） | 已验证 | 设置页全部 8 个分区、Wiki 维护与编辑器、笔记列表与编辑器、知识地图三个视图、共用外壳（连接条 / 错误边界 / 快捷键 / 迁移预览）。用前缀限定的脚本先 dry-run 再 apply（123 条改动）：交互控件 13px、辅助文字 12px |
| F19 收口（全站字号下限） | 已验证 | 再跑一条「低于 12px 全部提到 12」的脚本，补齐此前未审计到的表面：composer 作用域、@ 提及、斜杠面板、过程折叠、消息引用、右栏上下文、移动端导航，以及多行写法的知识地图 / 侧栏标题。**494 条 `font-size` 声明里低于 12px 的归零**（起点 233）；棘轮转为门禁 0 |
| 防漂移 | 已验证 | 新增 `web/frontend/src/lib/designTokens.test.ts`：文档 ↔ 代码 token 一致性（含反向检查）+ 四条棘轮（<12px 字号 ≤226、裸 `ease` ≤16、脱轨圆角 ≤73、裸毫秒 ≤5），只允许下调；已实测能抓到人为漂移 |

验证：Python `1450 passed`（tripwire 确认真实工作区库未动）、Vitest `63 passed`、ESLint 与生产构建通过、Playwright `77 passed / 1 skipped`。

**F19 四个批次（Chat → Practice·Review → Library·Reader → 低频页）全部完成，字号下限已收口到 0**，见上表。仍未做：间距与圆角尚未全量收敛到 token（脱轨圆角 73 → 59，还有存量）；暗色主题——本轮只把 token 改成可换主题的形状，并补上文档里已预留但一直没实现的 `[data-theme]` 钩子。

### A4 止血轮（2026-09-14 立项）

外部审计产出 [`TECH_AUDIT_2026-09-14.md`](TECH_AUDIT_2026-09-14.md)（15 P0 / 36 P1 / 33 P2 / 12 测试盲区），三路并行静态审计 + ROADMAP 自认技术债交叉核对，全部结论可定位到文件与函数。审计的三条贯穿判断：**不缺架构缺接线**（hooks / 上下文压缩 / 事件重放实现完整但生产路径从未启用）、**写路径装了门而删路径与并发路径敞开**、**取消机制整体缺失**。

本轮按「先止血 → 再接线 → 横切原语单独立项」推进，P2 不排期。审计编号（`P0-x` / `P1-x`）成为稳定引用，提交信息一律带编号。

#### 批次一 · 止血（进行中）

| 条目 | 审计编号 | 动作 | 状态 |
|---|---|---|---|
| 静态托管路径穿越 | P0-4 | `spa_fallback` 加 resolve 包含性判断，越界 404 | 已验证 |
| 工具沙箱边界与写保护 | P0-5 + P0-6 | 派发前按签名白名单过滤、`workspace`/`cwd`/会话身份无条件覆盖；内部目录按路径段拒绝读写；trace 按凭据形态脱敏 | 已验证 |
| 中文 token 估算 | P0-7 | `core/token_budget.py` 唯一估算器：宽字符 ≥ `0x2E80` 记 1.2/字（实测 1.16），其余保留历史 1/4（实测 1/6，偏高即安全） | 已验证 |
| 删概念 500 | P0-11 | 在 store 层一个事务里先删关系与其证据、再删布局位置、最后删概念（对所有调用方生效） | 已验证 |
| 删除确认 | P0-12 | 连续两轮未扫到才判删 + 扫描报错一律不判删；vault 与 course 扫描器都不再静默吞错 | 已验证 |
| 原子写地基 | P0-13 + P1-8 | 新增 `core/atomic_io.py`（temp + fsync + replace + Windows `PermissionError` 退避 + 每次路径锁 + workspace 跨进程锁），会话 / 原文 / 版本 manifest 统一走它 | 已验证 |
| Qdrant 生命周期 | P0-15 | 新增 `shared_qdrant_store` 注册表（按 client 身份去重），检索管线与 `sync` 都从这里取；管线淘汰不再关闭共享 client，`clear_retrieval_cache` 负责关 | 已验证 |
| 读改写串行化 | P1-14 | preference patch 临界区加锁（读→校验→写）+ `core/db.py::begin_immediate` 原语，概念 upsert 的查重与写入改为同一写事务 | 已验证 |
| chunk_id 稳定性 | P1-21 | grep 命中 id 改用 `_stable_hash`，并加跨进程回归测试 | 已验证 |
| reset 一致性 | P1-28 | `/kb reset` 一并清理 `manifest.json`（派生索引，下次 sync 重建） | 已验证 |

#### 批次二 · 接线（已定方案，批次一完成后开始）

hooks 最小接线（✅ 结果上限落 `after_tool`、白名单门落 `before_tool`，记忆注入不动，加守护测试）→ 上下文压缩两级（L1 工具结果转可重取 marker、L2 确定性 checkpoint + turn 边界切点 + 序列化后配对兜底，无 checkpoint 不压缩）→ append-only 事件表 + `Last-Event-ID` 续传（含 P1-11 悬空 tool_call 与断线宽限取消）→ specialist 上 Web → 向量补建驱动 → grep 非文本可见降级。

#### 批次三 · 取消原语（先设计后动代码）

协作取消穿透 `AgentLoop` → provider 流 → 工具边界；每工具超时转结构化错误结果；取消后落盘已产出内容并标记 cancelled。

#### 明确不在本轮

- **P2 全部 33 条**：不排期，顺手时处理。
- **检索调优**（FTS 权重、RRF `k`、页码精度）：等 ROADMAP G4 评测集有基线之后再谈，避免无基线调参。
- **推理质量**（P1-1~P1-6）：归既有 E11 / E12 / H-R2.5，不重复立项。

#### 验收口径（本轮纪律）

每条先写**会失败的复现测试**再修；断线取消、Qdrant 双开、删除确认、向量补建四类必须用真实集成或故障注入而非 mock；CHANGELOG 记录「复现方式 + 失败信号」；每个批次末尾跑全量验证（pytest + vitest + Playwright + lint + build + `tests/conftest.py` 的真实库 tripwire）后才推送。

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
| 桌面版推迟 | P5G.2 门禁化；先 W3/W4（原 R1/R2）主体；sidecar/server-info/契约测试三结论必须吸收 | PRE_DESKTOP + 本次确认 |
| 教学闭环哲学 | 模型管教学、引擎管算术；推进由已掌握内容计算，绝不用 stage counter | DeepTutor 对照 + Bobodan 证据门禁既有实践 |
| 动效体系 | 三档 token（120/160/220ms）+ 两条缓动；2026-09-14 增三档 spring 预设（CSS `linear()` 近似、过冲 ≤2%）与 `scale` 0.96–1.02；应用内减动效 = OS 级语义；不为动画引 motion 库 | DESIGN.md §11 + 2026-08-28 体验轮 + 2026-09-14 设计规格轮 |
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
- **本地参考项目**（[`REFERENCE_PROJECTS.md`](REFERENCE_PROJECTS.md)，活文档）：`F:\claude projects\DeepTutor`（Apache-2.0）、`F:\claude projects\OpenMAIC`（MIT）、`F:\claude projects\openhanako-reference`（Apache-2.0）。**遇到 bug 或设计取舍先查这里**；已确认的同构案例（含 agent 提问/作答/续跑的三家机制对比）随进展追加。参考不产生排期。
- **仍在体系内**：`PROJECT_GUIDE.md`（产品边界与阶段验收）、`DESIGN.md`（视觉硬约束）、`rag_design.md`（RAG 架构真相源）、`MCP.md`、`tools/skills.md`。
