# 测试策略（Bobodan）

> 2026-08-28 起，借鉴 openhanako `tests/README.md` 的风险驱动测试政策。
> 测试的价值在于**保护契约与老用户数据安全**，不在于文件数量。

## 分层

| 层 | 位置 | 覆盖什么 | 不覆盖什么 |
|---|---|---|---|
| 单元 | `tests/test_*.py` | 纯函数、存储、服务逻辑；LLM 一律走 `tests/llm_fake.py` 的 `ScriptedProvider` | 网络、真实模型 |
| 路由契约 | `tests/test_web_backend.py` | 挂真实 FastAPI app + mock 服务依赖，断言状态码/错误信封/SSE 帧形状 | 浏览器渲染 |
| 前端单元 | `web/frontend/src/**/*.test.ts(x)` | 纯逻辑（selector、缓冲、折叠、命令路由）与小组件 | 跨页流程 |
| 冒烟 e2e | `web/frontend/e2e/smoke.spec.ts` | 2-4 条：应用可启动、主路由可渲染、核心交互（composer/设置）可用 | 业务深流程 |
| 专项 e2e | `web/frontend/e2e/app.spec.ts` | 仅保留**稳定且有独立价值**的流程用例（见下） | 依赖特定本地数据/环境状态的用例 |

## LLM mock 单缝（强制）

所有需要 LLM 的测试必须通过 `tests/conftest.py` 的 `scripted_provider` fixture
（`tests/llm_fake.py` 的 `ScriptedProvider`）：脚本化文本/工具调用/错误注入，
请求全量记录可断言。**不要再在测试文件里声明局部 FakeProvider/MockProvider**；
存量散装的允许暂留，碰到即迁移。

## 新增测试前自问

1. 这条测试锁的是**稳定契约**（错误码、事件名、关键数据形状）还是**易变实现/文案**？
   只锁文案的不要写。
2. 有没有路由契约或纯函数层能表达同样行为？优先下层——快 50 倍且不会陈旧。
3. 是否需要真实模型/网络/特定本地数据？需要就重设计，`ScriptedProvider` +
   tmp 工作区必须足够。

## 删除/合并测试的规则

出现以下任一情形，删除或合并（删除前跑一次 `pytest -q && npm run lint && cd web/frontend && npx tsc --noEmit && npm test -- --run`）：

- 只断言文案、间距、与实现耦合的选择器；
- mock 了被测对象的私有字段（公开 API 或服务契约能表达同样行为）;
- 依赖特定本地工作区数据、随机时序或外部服务，导致**在本机也会间歇失败**；
- 所测契约已由更下层的测试等价覆盖；
- 对应功能已删除（测试没有存续价值）。

## Playwright 政策（2026-08-28 收缩）

- 历史教训：`app.spec.ts` 曾积累 975+ 行浏览器用例，其中 12 条长期失败
  （依赖特定工作区状态 / 锁布局实现），且后端契约测试已覆盖同一契约。
- 现政策：浏览器只保留**冒烟**（启动、主路由渲染、composer/设置可用）与
  少数稳定流程；业务契约一律下沉到路由契约测试。
- 冒烟用例失败按最高优先级处理：它代表"应用打不开"级别的回归。

## 清理存量时的验证基线

```powershell
.venv\Scripts\python.exe -m pytest -q
cd web/frontend
npm run lint
npx tsc --noEmit
npm test -- --run
npm run build
npx playwright test --project=desktop
```
