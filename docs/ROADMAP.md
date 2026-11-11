# Bobodan 路线图

> **v2.0（2026-11-11，GOV-01 重写）** · 基线：分支 `feat/qa-live-gate`（基于 `main` `ac9bb17`）· 后端 1906 passed / 前端 vitest 353 passed / mock e2e 0 failed
>
> **这是唯一的"现在做什么"文档，控制在两屏。** 只写四件事：当前基线、当前批次、下一批候选、发布阻塞项。交付经过写进 [`../CHANGELOG.md`](../CHANGELOG.md)；v1.5 及以前的完整路线（W1–W5 交付长表、A0–A4、E1–E18、G1–G5 的复测记录）原样归档在 [`archive/delivery/ROADMAP_HISTORY_2026-09_11.md`](archive/delivery/ROADMAP_HISTORY_2026-09_11.md)，只用于追溯。

---

## 1. 当前基线（唯一状态表）

只列**未关闭**或**本轮刚关闭**的条目。已关闭的旧条目不在这里重复——要追溯去看 CHANGELOG 或归档。

| ID | 工作流 | 事项 | 状态 | 证据 / 下一步 |
|---|---|---|---|---|
| W1-E6.2 | W1 学习闭环 | 掌握度统一消费契约（事实 / 估计 / 调度三分） | `已验证` | `learning/contract.py`；`tests/test_mastery_contract.py` 23 条；已合入 main |
| QA-LIVE-01 | 横贯 | 真实后端核心闭环门禁（只替换模型） | `已验证`（第一版） | `tests/test_live_core_loop.py` 12 条：导入→检索→出题→作答→复习→重启、批改失败、跨库隔离、引用链路、预检索范围。**余项**：资料移动撤销冲突、整体备份恢复（并入 W4-RESTORE-01） |
| W2-EVID-01 | W2 检索 | 引用校验第一阶段：确定性引用标签 + 运行时引用门禁 | `已验证` | `rag/citations.py`、`CitationPolicy`；`tests/test_citation_policy.py` 12 条 + 真实链路 5 条。**真实模型未抽查**（标签是否被照抄）——见 §2 |
| W2-EVID-02 | W2 检索 | 引用支持度：引用真实但结论与原文矛盾时给风险信号 | `未开始` | 评审原始复现（原文「非负权」→ 回答「支持负权」+ 真实标签）**现在仍会通过**。规则/模型辅助 + 人工抽样，结果只作风险信号 |
| GOV-01 | 治理 | 单一状态表、历史归档、Wiki 边界决策记录 | `已验证` | 本文即单一状态表；历史已归档；D-WIKI 已拍板（§5）；CHANGELOG 已切 0.13 / 0.14 / 0.15 |
| W1-RES | W1 | 残留：练习页课程选择器；划线只能同步进正在编辑的笔记 | `未开始` | 无依赖，体验改进 |
| W1-QUALITY-01 | W1 | 题目 / 批改人工审阅集 + 模型评测记录 | `未开始` | 依赖 E6.2（已满足）；预算上限 + 人工复核 |
| W2-G4.2 | W2 | 召回评测扩充：人工集、去 basename 歧义、片段级指标、冻结判据 | `未开始` | 现有 G4 基线见 [`RAG_EVAL.md`](RAG_EVAL.md) |
| W2-G5 | W2 | PDF 四级降级链（outline→heading→印刷目录→粗体） | `暂缓` | 真实库没有 PDF；有失败样本再谈 |
| W3-TODAY-01 | W3 | Chat 起始态「今日任务」与短首次路径 | `未开始` | 依赖 E6.2 稳定语义（已满足） |
| W3-PERF | W3 | 前端性能与一致性（审查 2026-11-11 余项，见 §3） | `进行中` | 已做：流式不再重解析历史、全局快捷键避开输入框、未定义 CSS 变量清零、「读取失败」不再显示成「空 / 尚未练习」 |
| AUDIT-P1 | 横贯 | 2026-11-11 审查 P1 首批：CLI 证据门禁、检索不列全库、按 id 直接打开会话、失败与空分开 | `已验证` | `service/turn_policy.py`；`KBService.search` 300 份资料 48.9ms → 13.1ms；回归均在旧代码上先红 |
| W4-RESTORE-01 | W4 | 整体备份 / 恢复与迁移失败演练 | `未开始` | **发布硬门禁** |
| W5-RC-01 | W5 | 锁定发布依赖；安装 / 升级 / 退出 / 卸载验收 | `未开始` | **发布硬门禁**；依赖 W4-RESTORE-01 |

## 2. 当前批次

同一时间只有**一个主交付批次 + 一个不互相阻塞的验证批次**。

- **主批次：审查余项（§3 的 P1）**。完成标准：§3 P1 全部关闭或明确降级。
- **验证批次：真实模型抽查引用标签**。用真实模型问 3–5 个基于资料的问题，确认回答带 `[Sxxxxxx]` 且门禁不误伤；不照抄就改提示位置，而不是放宽门禁。

## 3. 下一批候选（按依赖排序）

来自 2026-11-11 全项目审查（前端 / 后端 / 工程卫生三份结论汇总在 CHANGELOG 同日条目）。已在本分支修掉的不再列。

| 优先级 | 候选 | 为什么 | 粗估 |
|---|---|---|---|
| P1 | `QuizStore` 构造不再每次执行回填写事务（读请求也在抢写锁；`KBSQLiteStore` 已改为按库只迁移一次） | 并发时 busy 等待，表越大越慢 | S |
| P1 | 知识图谱画布颜色跟随主题 | 暗色下节点标签是浅色贴片 | S–M |
| P1 | AppShell 拆出导入、健康检查、外观同步 hooks；Outlet context 稳定化 | 每次 resize / 健康检查让所有页面重渲染 | L（可分步） |
| P2 | 增量同步按 `(mtime, size)` 短路，不再每次读全文件算哈希 | 资料库越大同步越慢 | M |
| P2 | 测试 fake 迁移到 `ScriptedProvider`（存量 27 文件 / 56 处） | 接口一变要改几十处 | M |
| P2 | `kb_service.py` 拆出 Wiki 维护与资料文件管理；`app.css` 先清死选择器与重复规则再按页拆分 | 降低误改风险；先清后拆 | L |
| P2 | 服务层高频错误补结构化 code（会话不存在 / 损坏 / 有歧义 …） | 前端只能显示笼统错误 | M |

## 4. 发布阻塞项

进入 Windows Prerelease 之前必须全部 `已验证`：

1. **W4-RESTORE-01** 整体备份 / 恢复：干净目录恢复后关键记录与引用可核对；迁移失败可回滚。
2. **W5-RC-01** 干净机器安装、sidecar 生命周期、升级 / 退出 / 卸载契约（细则见 `PROJECT_GUIDE.md` 发布验收）。
3. **W2-EVID-01 真实模型抽查**通过（§2 验证批次）。
4. 核心 P0（E6.2、QA-LIVE-01、EVID-01）保持绿灯。

---

## 5. 已拍板决策（不再重复讨论）

| 决策 | 内容 | 依据 |
|---|---|---|
| RAG embedding | 向量库 qdrant 本地；不内置 ONNX 模型；embedding 走用户自配 API + Ollama 可选离线档；`fts_only` 是一等公民形态 | 调研报告 ch10 |
| 桌面版推迟 | P5G.2 门禁化；sidecar / server-info / 契约测试三结论必须吸收 | PRE_DESKTOP |
| 教学闭环 | 模型管教学、引擎管算术；推进由已掌握内容计算，不用 stage counter | DeepTutor 对照 |
| 掌握度 | 事实（`mastery_attempts`）→ 估计（`learning.contract`）→ 调度（SM-2 只写 `next_review`）；保留 SM-2 是刻意的 | E6.2（2026-11-05） |
| D-WIKI Wiki 边界 | ① 旧 Wiki 数据只读保留（文件树隐藏、不进检索）② 允许新生成，但只作为高级维护入口（对话 `/wiki plan` · `/wiki update` · `/wiki generate` 与设置页），不进一级导航 ③ Wiki 编排底座继续服务 AI 资料整理 ④ Wiki 页**不能**作为回答或出题证据——证据只认 `rag_search` 原文（`collection="material"`，预检索同口径） | 路线评审 §4.2 四问；2026-11-11 负责人确认 |
| 引用 | 确定性标签 `[Sxxxxxx]` + 运行时门禁只核对「引用真实」；「引用支持结论」单列 EVID-02，结果只作风险信号 | EVID-01（2026-11-11） |
| 动效 | 三档 token + 两条缓动 + 三档 spring；Motion 受限使用（复杂弹窗 / 抽屉 / 消息出现 / 布局变化 / 拖拽），`LazyMotion` + `m` 按需加载 | `DESIGN.md` §11 |
| 测试政策 | 风险驱动分层；LLM 单缝 `ScriptedProvider`；真实后端闭环门禁只替换模型；浏览器只留冒烟与稳定流程 | `tests/README.md` |
| Lint | Python 只开抓真 bug 的规则（`ruff.toml`）；未用 import 存量单独一批清 | 2026-11-11 |

## 6. 明确不做

- 八引擎 RAG 矩阵、GraphRAG / LightRAG（FTS5 + Qdrant + RRF 够用，新增手段须评测证明失败）
- LangGraph / Postgres 租约 / 多 worker durable runner / S3
- 多用户 / IM 渠道 / subagent 商店 / 50+ provider 兼容层
- TTS / 语音克隆 / 视频渲染 / i18n×10
- 思维链 / mood 展示；WS 传输层；会话分叉树
- CSS multicol 真分页；Obsidian 深耦合；Neo4j；PDF / DOCX 编辑；虚拟滚动库
- Motion 全站动画化；内置 ONNX embedding 模型
- 移动端验收（当前发布目标是 Windows 桌面端）

## 7. 状态口径与完成定义

状态只用：`待核对`（开工前先核对代码）· `未开始` · `进行中` · `已验证` · `暂缓` · `取消`。

一项只有同时满足以下条件才能标 `已验证`：

1. 用户触发路径、成功结果、失败结果和恢复动作明确。
2. 服务端真相源与前端临时状态边界明确，没有第二套业务状态。
3. 高风险逻辑有针对性测试（核心闭环优先进 `tests/test_live_core_loop.py`）。
4. 用户可见文案不泄露内部实现、思维链、本地绝对路径或密钥。
5. 本文、`PROJECT_GUIDE.md` 或专题真相源已同步，不留相互矛盾的描述。

同一时间只允许一个主交付批次和一个验证批次；参考项目不能直接往本文增项，必须先证明现有能力无法满足用户目标。**模型负责语言，代码负责事实**——新增机制都不得动摇这条线。

## 8. 来源索引

- 交付经过：[`../CHANGELOG.md`](../CHANGELOG.md)；v1.5 及以前完整路线：[`archive/delivery/ROADMAP_HISTORY_2026-09_11.md`](archive/delivery/ROADMAP_HISTORY_2026-09_11.md)
- 评审：[`reviews/2026-10-20-roadmap-review.md`](reviews/2026-10-20-roadmap-review.md)（本版 P0 批次与 GOV-01 的来源）
- 工作池细项（H-R2.x、FE-P1/P2、O7/O8 等未关闭的长尾）：保留在归档版 §1 的 W3 / W4 表里，重新启用前按 §7 先 `待核对`
- 专题真相源：[`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) · [`DESIGN.md`](DESIGN.md) · [`FRONTEND_UPGRADE_PLAN.md`](FRONTEND_UPGRADE_PLAN.md) · [`rag_design.md`](rag_design.md) · [`RAG_EVAL.md`](RAG_EVAL.md) · [`LIBRARY_TREE_DESIGN.md`](LIBRARY_TREE_DESIGN.md) · [`QUESTION_BANK_DESIGN.md`](QUESTION_BANK_DESIGN.md) · [`CANCELLATION_DESIGN.md`](CANCELLATION_DESIGN.md)
- 参考：[`REFERENCE_PROJECTS.md`](REFERENCE_PROJECTS.md) → [`Bobodan参考项目调研报告.md`](Bobodan参考项目调研报告.md)（2026-09-02 快照，历史参考）
