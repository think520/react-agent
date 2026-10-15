# 审查证据说明

这些证据对应 `../../2026-09-25-project-review.md`。全部来自隔离的审查资料库及合成数据，不代表真实模型的教学质量评测。

- `review_pytest_20260925.txt`：后端完整测试，1633 passed、9 warnings。
- `review_e2e_20260925.txt`：桌面及窄桌面 E2E，59 passed、12 skipped、1 failed。
- `review_e2e_retry_20260925.txt`：单独重跑窄桌面目录操作，仍因面板遮挡而失败。
- `review_stream_probe_20260925.txt`：两个临时流式异常用例的失败输出；临时测试已移除。
- `api-probes.json`：格式导入、文档与笔记等接口探针。
- `memory-disabled-note.json`：关闭记忆时手动笔记写入的返回结果。
- `failed-chat-sse.txt`：不可达测试提供商导致的真实 SSE 失败事件。
- `scale-integrity.json`：300 份合成资料的同步、接口计时、移动身份与跨库隔离探针。

前端 lint、构建和 111 个单元测试通过的结果来自本次终端执行；未单独归档该次完整日志。不能把临时异常用例的两个失败与这 111 个既有通过用例混成一次运行。

截图位于 `../../assets/2026-09-25/`。报告中的代码风险若未实测，均已明确标注；本次没有提供修复提交。
