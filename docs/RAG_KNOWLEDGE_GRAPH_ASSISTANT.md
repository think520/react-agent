# Neo4j + RAG 课程知识图谱学习助手设计文档

## 1. 项目定位

本项目可以从通用 ReAct Agent 进一步演进为一个面向学习场景的垂直型 Agent：

> 基于 Neo4j + RAG + Obsidian 的课程知识图谱学习助手。

它的核心目标不是只回答“某个文档里有什么”，而是帮助用户把课程资料、PDF、PPT、实验文档、课堂笔记、Obsidian 个人知识库整理成一个可检索、可关联、可规划学习路径的知识系统。

系统应该能够回答以下类型的问题：

- 某个知识点是什么？
- 这个知识点出现在我的哪些课程资料或笔记中？
- 它和哪些知识点有关？
- 它依赖哪些前置知识？
- 我应该按什么顺序学习一门课？
- 我的 Obsidian 笔记和课程资料里有哪些内容在讲同一个主题？
- 某个实验文档需要哪些理论基础？

## 2. 为什么适合当前 Agent 项目

当前项目已经具备一个 Agent 框架的基础能力：

- CLI 交互入口；
- ReAct 循环；
- 工具调用机制；
- Provider 抽象；
- Session 管理；
- Skill 加载机制；
- 文件、目录、HTTP 等工具能力。

这些能力适合作为学习助手的调度层。RAG、Neo4j 和 Obsidian 不应该被硬塞进 Agent 循环本身，而应该作为 Agent 可调用的能力模块。

推荐定位如下：

```text
现有 Agent = 调度层 / 推理层 / 工具编排层
RAG        = 文档语义检索层
Neo4j      = 知识关系与学习路径层
Obsidian   = 用户个人知识来源与输出目标
```

## 3. 总体架构

```text
课程 PDF / PPT / 实验文档 / Markdown / Obsidian Vault
        |
        v
文档解析与清洗
        |
        v
文本切块 + 元数据提取
        |
        +----------------------+
        |                      |
        v                      v
向量数据库 / Embedding       Neo4j 知识图谱
        |                      |
        v                      v
RAG 语义检索                 图谱关系查询
        |                      |
        +----------+-----------+
                   |
                   v
             Agent 工具调用
                   |
                   v
       问答 / 关系解释 / 学习路径 / 笔记整理
```

## 4. 核心数据来源

### 4.1 课程资料

包括：

- PDF 教材；
- PPT 课件；
- 实验文档；
- Markdown 笔记；
- 课堂资料；
- 习题、复习提纲、考试范围。

这些资料主要进入 RAG 系统，用于回答定义、解释、引用来源、内容总结类问题。

### 4.2 Obsidian 个人知识库

Obsidian 是非常适合本项目的数据源，因为它天然包含结构化关系：

- Markdown 正文；
- `[[双链]]`；
- `#标签`；
- 文件夹层级；
- frontmatter 元数据；
- 用户自己的理解、总结、疑问和学习痕迹。

Obsidian 不仅可以作为输入，也可以作为输出目标。例如 Agent 可以把学习总结、知识点卡片、错题分析、学习路径写回 Obsidian。

## 5. Obsidian 融合方式

Obsidian Vault 可以被解析成两类数据。

### 5.1 进入 RAG 的内容

每篇 Markdown 笔记可以被切块并向量化：

```text
文件路径
标题
正文段落
标签
课程名
章节名
更新时间
双链上下文
```

这些内容用于语义检索。例如：

> 我之前关于 Dijkstra 算法的笔记在哪里？

### 5.2 进入 Neo4j 的关系

Obsidian 的结构可以转成图谱：

```text
[[Dijkstra 算法]] -> RELATED_TO -> [[图]]
[[Dijkstra 算法]] -> USES -> [[优先队列]]
[[Dijkstra 算法]] -> USES -> [[贪心算法]]
#数据结构 -> TAG_OF -> Dijkstra 算法
文件夹 数据结构/图论 -> BELONGS_TO -> 课程章节
```

示例笔记：

```markdown
---
course: 数据结构
chapter: 图
difficulty: medium
---

# Dijkstra 算法

Dijkstra 用于求解单源最短路径。

相关知识：[[图]]、[[贪心算法]]、[[优先队列]]
```

可转成：

```text
(Dijkstra算法)-[:BELONGS_TO]->(数据结构)
(Dijkstra算法)-[:IN_CHAPTER]->(图)
(Dijkstra算法)-[:RELATED_TO]->(图)
(Dijkstra算法)-[:USES]->(贪心算法)
(Dijkstra算法)-[:USES]->(优先队列)
```

## 6. 推荐模块设计

建议在当前项目中新增以下模块：

```text
rag/
  ingest.py          # 导入 PDF、PPT、Markdown、实验文档
  chunker.py         # 文本切块
  embeddings.py      # 向量化接口
  vector_store.py    # 向量库适配
  retriever.py       # 检索逻辑
  citations.py       # 引用来源整理

graph/
  schema.py          # Neo4j 节点和关系定义
  extractor.py       # 从文本中抽取知识点和关系
  neo4j_store.py     # Neo4j 写入和查询
  learning_path.py   # 学习路径生成

obsidian/
  vault.py           # 扫描 Obsidian Vault
  parser.py          # 解析 Markdown、双链、tag、frontmatter
  sync.py            # 同步到 RAG 和 Neo4j

tools/
  rag_search.py      # Agent 可调用的 RAG 检索工具
  graph_query.py     # Agent 可调用的图谱查询工具
  obsidian_tool.py   # Agent 可调用的 Obsidian 工具

skills/
  course-learning/
    SKILL.md         # 学习助手技能说明
```

## 7. Neo4j 图谱模型初版

第一版不要设计得过重，先支持学习场景中最常用的节点和关系。

### 7.1 节点类型

```text
Course        课程
Chapter       章节
Concept       知识点
Document      文档
Note          Obsidian 笔记
Experiment    实验
Question      问题或习题
Tag           标签
```

### 7.2 关系类型

```text
BELONGS_TO      属于某门课
IN_CHAPTER      位于某章节
MENTIONED_IN    出现在某文档或笔记中
RELATED_TO      相关知识点
PREREQUISITE_OF 前置知识
USES            使用某个概念或方法
SIMILAR_TO      相似或容易混淆
TAGGED_AS       被某标签标记
DERIVED_FROM    从某资料抽取而来
```

### 7.3 典型查询

查询某知识点相关内容：

```cypher
MATCH (c:Concept {name: $name})-[r]-(n)
RETURN c, r, n
LIMIT 50
```

查询学习前置路径：

```cypher
MATCH path = (pre:Concept)-[:PREREQUISITE_OF*1..5]->(target:Concept {name: $name})
RETURN path
```

查询某门课的知识结构：

```cypher
MATCH (course:Course {name: $course})<-[:BELONGS_TO]-(concept:Concept)
OPTIONAL MATCH (concept)-[r:RELATED_TO|PREREQUISITE_OF|USES]-(other:Concept)
RETURN course, concept, r, other
```

## 8. Agent 工具设计

建议新增以下工具，让 Agent 可以根据用户意图选择能力。

### 8.1 rag_search

用途：

- 语义检索课程资料；
- 查找相关笔记；
- 回答定义、解释、总结类问题；
- 给出引用来源。

输入示例：

```json
{
  "query": "Dijkstra 算法是什么？",
  "course": "数据结构",
  "top_k": 5
}
```

输出示例：

```json
{
  "results": [
    {
      "text": "Dijkstra 算法用于求解带非负权边图中的单源最短路径...",
      "source": "数据结构/图论/Dijkstra.md",
      "score": 0.87
    }
  ]
}
```

### 8.2 graph_query

用途：

- 查询知识点关系；
- 查询前置知识；
- 生成学习路径；
- 找相似或易混淆知识点。

输入示例：

```json
{
  "concept": "Dijkstra 算法",
  "intent": "prerequisites"
}
```

### 8.3 obsidian_sync

用途：

- 扫描 Obsidian Vault；
- 解析 Markdown、双链、tag、frontmatter；
- 同步到 RAG 和 Neo4j；
- 可选地写回学习总结。

输入示例：

```json
{
  "vault_path": "D:/Obsidian/MyVault",
  "mode": "incremental"
}
```

### 8.4 learning_path

用途：

- 根据目标知识点生成学习顺序；
- 结合前置知识、相关资料、用户笔记生成计划；
- 标记薄弱环节。

输入示例：

```json
{
  "target": "操作系统",
  "level": "beginner",
  "use_obsidian_notes": true
}
```

## 9. 推荐 MVP

第一版建议控制范围，先证明方向成立。

### 9.1 MVP 功能

必须包含：

- 导入 Obsidian Markdown；
- 导入 PDF 或 Markdown 课程资料；
- 文本切块；
- 向量检索；
- 从 Obsidian 双链和 tag 生成 Neo4j 图谱；
- 支持 `rag_search` 工具；
- 支持 `graph_query` 工具；
- 支持“知识点解释”和“相关知识点查询”两类问答。

暂时不要做：

- 复杂自动知识抽取；
- 完整 Web UI；
- 过度复杂的学习计划系统；
- 多用户权限；
- 大规模分布式索引。

### 9.2 MVP 用户流程

```text
1. 用户配置 Obsidian Vault 路径
2. 用户导入课程资料目录
3. 系统解析 Markdown / PDF
4. 系统生成向量索引
5. 系统把双链、标签、课程结构写入 Neo4j
6. 用户在 CLI 中提问
7. Agent 判断使用 RAG、Neo4j 或二者结合
8. 系统返回答案、来源和相关知识点
```

## 10. 分阶段迭代计划

### 阶段一：本地知识库接入

目标：

- 支持 Obsidian Vault 扫描；
- 支持 Markdown 解析；
- 支持 PDF 文本抽取；
- 支持基础向量检索；
- 支持 Neo4j 写入基础节点和关系。

验收标准：

- 能找到某个知识点出现在几篇笔记或资料中；
- 能查出 Obsidian 双链关系；
- 能基于检索内容回答问题并带来源。

### 阶段二：Agent 工具集成

目标：

- 新增 RAG 工具；
- 新增图谱查询工具；
- 让 Agent 根据问题类型选择工具；
- 增加 course-learning skill。

验收标准：

- 问“是什么”时优先走 RAG；
- 问“和谁有关”时优先走 Neo4j；
- 问“怎么学”时结合 Neo4j 路径和 RAG 资料。

### 阶段三：知识抽取增强

目标：

- 使用 LLM 从 PDF/PPT 中抽取知识点；
- 抽取定义、前置知识、相关概念、易混淆概念；
- 将抽取结果写入 Neo4j；
- 增加人工确认机制，避免错误关系污染图谱。

验收标准：

- 新导入资料后能自动发现知识点；
- 自动生成的关系可追溯到原文来源；
- 用户可以确认、拒绝或修正抽取结果。

### 阶段四：学习路径与复习系统

目标：

- 根据目标课程生成学习路线；
- 根据用户笔记和问答记录判断薄弱点；
- 自动生成复习清单；
- 可将学习计划写回 Obsidian。

验收标准：

- 能生成带前置关系的学习路径；
- 能指出需要补的基础知识；
- 能输出 Obsidian Markdown 格式的学习计划。

## 11. 关键技术选择建议

### 11.1 Neo4j

适合存储：

- 知识点关系；
- 课程章节结构；
- 前置依赖；
- Obsidian 双链；
- 文档和知识点的来源关系。

### 11.2 向量数据库

MVP 可以优先选择本地方案：

- Chroma；
- FAISS；
- SQLite + 向量扩展；
- 或先用简单本地 JSON/SQLite 做原型。

第一版重点是接口抽象，不要过早绑定复杂基础设施。

### 11.3 Embedding

建议做成可插拔接口：

```text
LocalEmbeddingProvider
OpenAICompatibleEmbeddingProvider
MiniMaxEmbeddingProvider
FakeEmbeddingProvider for tests
```

这样既方便本地测试，也方便后续接入不同模型。

### 11.4 文档解析

建议优先支持：

- Markdown；
- PDF；
- TXT。

PPT 可以作为第二阶段支持，因为 PPT 的结构解析、图片文字、表格和版式会带来更多复杂度。

## 12. 潜在风险

### 12.1 图谱关系污染

LLM 自动抽取关系时可能产生错误边。例如把“相关”误判成“前置知识”。

建议：

- 每条自动关系保留来源；
- 增加置信度；
- 支持人工确认；
- 未确认关系和确认关系分开存储。

### 12.2 RAG 与图谱答案冲突

RAG 检索到的文本和 Neo4j 中的关系可能不一致。

建议：

- 回答中区分“资料原文依据”和“图谱关系推断”；
- 保留引用来源；
- 对冲突结果提示用户。

### 12.3 Obsidian 笔记结构不统一

用户的笔记可能存在命名混乱、同义词、重复概念等问题。

建议：

- 增加概念归一化；
- 支持 alias；
- 支持 frontmatter 中声明 canonical name；
- 对重复概念给出合并建议。

### 12.4 大量资料导入后的性能问题

文档数量变多后，解析、向量化、图谱写入都可能变慢。

建议：

- 使用增量同步；
- 根据文件 hash 判断是否变化；
- 向量索引分批更新；
- Neo4j 写入使用批处理。

## 13. 当前项目的改造建议

建议不要一开始大规模重构当前 Agent，而是采用增量方式。

第一批新增内容：

```text
rag/
obsidian/
graph/
tools/rag_search.py
tools/graph_query.py
skills/course-learning/SKILL.md
docs/RAG_KNOWLEDGE_GRAPH_ASSISTANT.md
```

当前 Agent 的核心循环、Provider、Session、CLI 可以先保持稳定。新增能力通过工具系统接入，降低对已有架构的冲击。

## 14. 项目差异化价值

这个方向相比通用 Agent 更有辨识度。

通用 Agent 通常强调：

- 工具调用；
- 文件操作；
- 浏览器或 HTTP 请求；
- 任务自动化。

本项目可以强调：

- 面向课程学习；
- 个人知识库融合；
- RAG 语义检索；
- Neo4j 知识关系；
- 学习路径规划；
- Obsidian 双向同步。

一句话定位：

> 一个能把课程资料和个人 Obsidian 笔记融合起来，并基于 RAG 与知识图谱帮助用户理解、关联和规划学习的 Agent。

## 15. 下一步建议

建议从最小闭环开始：

```text
Obsidian Markdown 解析
        |
        v
双链 / tag / frontmatter 提取
        |
        +-------> Neo4j
        |
        v
文本切块 + 向量索引
        |
        v
Agent 通过工具检索和回答
```

第一阶段完成后，这个项目就已经不只是一个普通 Agent，而是一个有明确使用场景、数据资产和长期演进空间的学习系统。
