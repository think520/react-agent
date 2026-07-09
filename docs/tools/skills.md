# Skills 系统

Skills 是 Bobodan 的扩展指令系统。每个 skill 是一组针对特定任务的专业说明，agent 可以在需要时读取并遵循。

## 目录结构

```text
skills/
  study-loop/
    SKILL.md
  exam-prep/
    SKILL.md
  obsidian-workspace/
    SKILL.md
```

## SKILL.md 格式

每个 skill 必须包含一个 `SKILL.md` 文件，格式为 YAML frontmatter + Markdown body：

```yaml
---
name: study-loop
description: "引导学习闭环：同步资料、制定计划、练习、复习和导出。"
---

# Study Loop

当用户想学习一门课、准备考试、整理资料或安排复习时，优先检查知识库状态，再推动学习闭环。
```

必填字段：

| 字段 | 说明 |
|---|---|
| `name` | skill 名称，用于 `/skill` 命令 |
| `description` | 一句话描述，用于模型判断何时使用 |

## 工作机制

1. 启动时扫描 `skills/` 目录。
2. 解析每个 `SKILL.md` 的 frontmatter。
3. 将 skill 目录注入 system prompt。
4. 模型根据任务选择是否读取完整 skill。
5. `/skill run <name>` 可以手动运行某个 skill。

## 产品边界

Skills 是内部任务策略，不是一等产品入口。

在未来 Web UI 中，普通用户不应该看到“运行 skill”这类工程概念。它们应该被包装成学习动作，例如：

- 开始学习。
- 考前冲刺。
- 整理 Obsidian 工作区。
- 生成练习。
- 今日复习。

## 当前内置 skills

| Skill | 用途 |
|---|---|
| `study-loop` | 学习闭环：资料同步、计划、练习、复习、进度 |
| `exam-prep` | 考前冲刺和薄弱点训练 |
| `obsidian-workspace` | Obsidian / 本地知识库工作区管理 |
| `course-learning` | 课程学习问答 |
| `aihot` | AI 热点信息 |
