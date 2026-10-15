# Bobodan 人格（persona）载体与优先级裁决

（W1 E10，2026-09-30。核对结论：此前产品里**没有 persona 系统** —— `assistant.display_name` 只是名字。）

## 载体

persona 不再新造一套机制，直接落在既有的 skills 通道上：

| 环节 | 位置 |
| --- | --- |
| 发现 | `skills/<name>/SKILL.md`（`core/skills.py::load_skills_from_dir`） |
| 注入 | `build_skills_system_prompt()` 把**启用的**技能作为目录写进 system prompt；模型按需 `read_file` 读 SKILL.md |
| 过滤 | 偏好 `preferences.skills.enabled_names` |
| Web 可见性 | `web/backend/capabilities.py::WEB_SKILL_NAMES`（不在白名单里的技能在 Web 设置里看不见） |

当前 persona 技能：`skills/socratic-persona/SKILL.md`。

## 优先级（从高到低，冲突时永远让路）

1. **证据门禁** —— `service/evidence_policy.py` 的策略与 AgentLoop 收尾校验。persona 不能放宽它，
   也不能要求"先别管证据、先问我"。
2. **来源绑定与资料库边界** —— 练习必须经服务端绑定的练习卡；不跨资料库读取或引用。
3. **persona 的风格与流程** —— 先问后讲、一次一个问题、语气与节奏。

## 边界（persona 不做什么）

- 不改工具白名单，不改判分，不改调度。
- 不绕过练习卡（纯文本发题会被防线②重定向回 `question_generate`）。
- 不因为"带学风格"而省略证据或来源。
- 不决定"讲什么"：内容来自原文检索与已审查图谱。

## 怎么加一个新 persona

1. 新建 `skills/<name>/SKILL.md`，frontmatter 里写 `name` 与 `description`（描述要说明**何时使用**，
   而不是介绍它多好）。
2. 若要在 Web 上可见，加进 `WEB_SKILL_NAMES`。
3. 正文必须显式写出上面的**优先级裁决**，否则不算 persona。
4. `tests/test_e10_persona_skill.py` 会检查：能加载、在 Web 白名单里、启用后进 system prompt、
   正文含裁决与练习卡边界。
