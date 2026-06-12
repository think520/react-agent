---
name: obsidian-workspace
description: 管理 Bobodan 的 Obsidian / 本地知识库工作区：同步资料、检查知识库状态、搜索知识库、查询知识图谱、导出学习计划或做题总结、生成或检查 wiki。当用户说"同步资料"、"导入 Obsidian"、"知识库状态"、"整理笔记"、"导出到 Obsidian"、"导出学习计划"、"导出做题总结"、"生成 wiki"、"检查 wiki"时使用。不要用于普通概念解释；那类请求使用 course-learning。不要用于每日学习流程；那类请求使用 study-loop。
---

# Obsidian Workspace

管理用户的本地学习资料、知识库索引和 Obsidian 输出。这个 skill 负责"资料进来、结构整理、结果导出"。

## 边界

- 用户要解释概念、查资料出处、看相关概念：使用 `course-learning`。
- 用户要开始学习、继续计划、今天学什么：使用 `study-loop`。
- 用户要考前冲刺、薄弱点训练：使用 `exam-prep`。
- 用户要同步、检查、导出、整理 wiki：使用本 skill。

## 常用流程

### 检查知识库

当用户说"知识库状态"、"现在同步了吗"：

1. 调用 `knowledge_status`
2. 如果没有知识库，提示用户提供 Obsidian vault 或课程资料路径
3. 如果有错误文件，只列前几个关键错误，并建议重新同步或检查路径

### 同步资料

当用户说"同步资料"、"导入 Obsidian"：

1. 确认 vault 路径；如果有课程资料目录，也一并确认
2. 调用 `obsidian_sync`
3. 返回扫描文件数、更新文件数、chunk 数和图谱关系数
4. 不要假设任意路径可访问；如果工具拒绝路径，向用户说明需要 workspace 内路径

### 搜索和图谱检查

当用户想确认资料是否进库：

1. 用 `rag_search` 搜一个用户关心的关键词
2. 用 `graph_query` 查核心概念关系
3. 明确区分"检索片段"和"图谱关系"

### 导出到 Obsidian

当用户说"导出学习计划"：

1. 确认 `plan_id` 和 vault 路径
2. 调用 `obsidian_export_plan`
3. 返回实际写入路径

当用户说"导出做题总结"：

1. 确认 vault 路径和可选 course
2. 调用 `obsidian_export_quiz_summary`
3. 返回实际写入路径

### Wiki 整理

当用户说"生成 wiki"、"整理成 wiki"：

1. 调用 `wiki_ingest`
2. 之后可调用 `wiki_lint` 检查 orphan、broken links、missing pages
3. 不要把 wiki 生成和普通 RAG 搜索混为一谈

## 输出风格

- 用中文说明结果，路径和工具名保留英文
- 输出具体文件路径、数量、错误摘要
- 不要一次性执行破坏性操作；重置或覆盖前先确认
