# 2026-09-28 整改复审证据

适用版本：`4159f41`（功能提交 `ceb9cc2`，审查基线 `f6c3562`）。

本目录保存的是验收探针的失败证据，不是整改后的通过结果。探针使用临时资料库、测试 fixture 和 mock，不接触日常资料库或真实模型。业务源码没有修改。

## 文件

| 文件 | 内容 |
|---|---|
| backend-probes.txt | 最终 9 个后端验收探针全部失败的真实输出 |
| frontend-probes.txt | 最终 6 个前端验收探针失败、2 个既有控制用例通过的真实输出 |
| frontend-final.txt | 探针移出测试目录后，现有 24 个测试文件 / 127 个用例全部通过 |
| backend-probe-source.py.txt | 后端探针完整代码 |
| drafts-probe-source.tsx.txt | 草稿边界探针完整代码 |
| chat-probe-source.tsx.txt | 失败重试会话探针，含原异步设置控制用例 |
| practice-probe-source.tsx.txt | 练习重新挂载探针，含原连续提问控制用例 |

全套后端、lint、build、Playwright 和首次前端超时结果来自本次实际终端调用，汇总于主报告；本目录没有将摘要伪装为这些步骤的完整原始日志。早期 chat 探针曾因引用卸载前的输入框而超时，最终改为点击界面实际的“重新发送本轮”按钮，失败已收敛为明确的 session ID 断言，不把早期 harness 超时算作产品缺陷。

## 复跑方法

以下命令在项目根目录执行。先确认四个目标文件不存在，避免覆盖其他人的工作；这些文件名在本次审查结束时均已移出测试目录。

```powershell
Copy-Item docs/reviews/evidence/2026-09-28/backend-probe-source.py.txt tests/test_audit_review_probe.py
Copy-Item docs/reviews/evidence/2026-09-28/drafts-probe-source.tsx.txt web/frontend/src/pages/AuditReviewProbe.test.tsx
Copy-Item docs/reviews/evidence/2026-09-28/chat-probe-source.tsx.txt web/frontend/src/pages/AuditReviewChatProbe.test.tsx
Copy-Item docs/reviews/evidence/2026-09-28/practice-probe-source.tsx.txt web/frontend/src/pages/AuditReviewPracticeProbe.test.tsx
& ./.venv/Scripts/python.exe -m pytest tests/test_audit_review_probe.py -q --tb=short
Push-Location web/frontend
npx vitest run src/pages/AuditReviewProbe.test.tsx src/pages/AuditReviewChatProbe.test.tsx src/pages/AuditReviewPracticeProbe.test.tsx --reporter=verbose
Pop-Location
```

复跑后仅移除自己恢复的这四个探针文件，或者在修复阶段把它们整理成正式回归测试；不要通过删除失败断言来宣称验收通过。

## 证据边界

- 文件移动、索引错误和撤销覆盖：实际隔离文件系统/SQLite 路径，故障点按断言明确注入。
- 进程中止：检查第一次物理移动前是否存在持久计划；没有执行操作系统级强杀，不声明完成强杀恢复试验。
- pagehide：组件环境派发页面生命周期事件；需要进一步用真实浏览器验证刷新/退出窗口。
- 练习刷新：卸载、重新挂载相同 practiceSessionId 验证 ref 生命周期；未调用真实模型。
- chat 失败历史：经过实际 TestClient HTTP 创建/读取接口；AgentService.run_stream 使用可控失败替身，验证错误收尾持久化。
- 15 个失败断言在主报告中归为 10 组问题；其中历史缺陷与本轮新增问题已分别标记。
