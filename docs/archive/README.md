# 文档归档

本目录存放**已完成、已交付或已被取代**的方案、任务书、交付记录和审计报告。它们不再是当前路线或规范依据：

- 当前路线看 [`../ROADMAP.md`](../ROADMAP.md)。
- 产品边界看 [`../PROJECT_GUIDE.md`](../PROJECT_GUIDE.md)。
- 视觉规范看 [`../DESIGN.md`](../DESIGN.md)；前端实施顺序看 [`../FRONTEND_UPGRADE_PLAN.md`](../FRONTEND_UPGRADE_PLAN.md)。

归档文档保留当时的行号、测试数量、分支状态和产品名称，用于追溯决策；这些数字不自动代表当前代码或当前验收结果。

## 目录

| 目录 | 内容 | 阅读方式 |
|---|---|---|
| [`frontend/`](frontend) | 前端优化、视觉系统评估底稿、设置重构、逐页视觉审计与打包前验收 | 追溯 M1–M6 与前端决策时 |
| [`delivery/`](delivery) | 已完成工作流的交付清单 | 追溯 W1 交付范围与当时门禁时 |
| [`audits/`](audits) | 已收口的技术缺陷审计 | 追溯 2026-09-14 审计条目来源时 |
| [`prototypes/`](prototypes) | 早期静态视觉原型 | 仅作历史参考 |

## 历史任务与路线

| 文档 | 状态 | 去向 |
|---|---|---|
| `AGENT_OPTIMIZATION_PLAN.md` | 主体 2026-08-13 交付 | **部分遗留没有落点**：上滑分页 / TailFade / 顶层 reconcile / CardParser / 动效配方 4–5 / forceAtlas2 六项在 W3、W4 两表里都查不到（2026-10-28 核对）；需要时按 ROADMAP §1「新参考项目不能直接增项」重新论证 |
| `PRE_DESKTOP_ROADMAP.md` | R0 于 2026-08-28 交付（**不含 R0.7**） | R0.7 数据 epoch 已并入 ROADMAP W4（H-R0.7）；R1→W3、R2→W4、R3→W5 |
| `TASKS_LIBRARY_REWORK.md` | 2026-08-13 交付 | — |
| `knowledge_map_design.md` | P5E.6 已交付 | 未竟项（跨文档候选/合并候选、`evidence_level=cross` 前端区分、提取计时 UI）**尚未并入任何工作池**，只是「择机」（仅 ROADMAP §5 复述一句） |
| `knowledge_map_reliability_editing_design_2026-07-27.md` | 图谱编辑已交付 | 同上（未竟项同样没有落点） |
| `project_review_2026-07-26.md` | B1–B9 已整改 | — |
| `experience_review_2026-08-01.md` | 未决项已并入 ROADMAP W1/W3（W1 来源列有 11 处「体验审查 P0-x/P1-x」） | — |
| `prototypes/bobodan-study-workspace.html` + `prototypes/bobodan-study-workspace-preview.png` | 2026-07-10 静态视觉原型 | 已被实际 React 页面取代 |

## 前端与交付

| 文档 | 状态 | 为什么归档 |
|---|---|---|
| `frontend/FRONTEND_OPTIMIZATION.md` | M1–M6 已完成 | 保留实测过程、里程碑与验收依据；后续视觉工作看 `FRONTEND_UPGRADE_PLAN.md` |
| `frontend/FRONTEND_OPTIMIZATION_V2.md` | W-F1 / W-F2 / W-F6 / W-F7 已完成 | 保留 store 化与页面拆分的过程记录 |
| `frontend/VISUAL_SYSTEM_PLAN.md` | 评估底稿，已被取代（2026-10-21 拍板） | 内嵌 `@import` 方案等判断已被 M1 证明错误；实施依据看 `FRONTEND_UPGRADE_PLAN.md`，硬约束看 `DESIGN.md` |
| `frontend/SETTINGS_V2.md` | S1–S5 已完成 | 保留设置区重构决策与实施记录 |
| `frontend/UI_AUDIT.md` | 2026-10-17 逐页修复已验收 | 保留逐页修复与遗留观察结论 |
| `frontend/M6_ACCEPTANCE.md` | 打包前前端验收已完成 | 发布相关结论继续以 `ROADMAP.md` 和当前 `DESIGN.md` 为准 |
| `delivery/W1_DELIVERY.md` | E1–E16 已交付 | 保留交付范围与当时门禁；当前状态看 `ROADMAP.md` |
| `audits/TECH_AUDIT_2026-09-14.md` | P0 主体已收口 | 保留缺陷来源与审计证据；未决项看 `ROADMAP.md` |

如需追溯某个决策的完整论证，本目录、[`../reviews/`](../reviews/) 与 `git log -- docs/` 足够。
