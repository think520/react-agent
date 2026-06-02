# 记忆系统升级计划

> **状态**: ✅ Phase 4.5 已实现 (2026-05-20)
> 实现文件：`memory/store.py`、`memory/daily.py`、`memory/search.py`、`memory/promotion.py`
> 改造文件：`core/memory.py`、`tools/memory_tools.py`、`cli/repl.py`、`tools/__init__.py`
> 测试文件：`tests/test_memory_upgrade.py` (34 tests)
> 待完成：做题结束自动写每日记忆（quiz_submit 集成）

## 1. 目标

在现有记忆系统基础上，增加每日记忆、FTS5 全文检索、向量检索降级、晋升机制，让记忆从"静态存储"升级为"有生命周期的学习记忆"。

## 2. 设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| 每日记忆定位 | 方案 C：缓冲 + 学习日志 + 晋升 | 学习助手需要临时缓冲（减少噪音）和日志（回顾今天学了什么） |
| FTS5 与向量的关系 | 方案 3：FTS5 为主，向量为辅 | 现有稀疏向量是 bag-of-words，和 FTS5 高度重叠；FTS5 零依赖、支持中文 |
| 晋升评分维度 | 出现次数(0.4) + 做题关联(0.4) + 时间衰减(0.2) | 学习助手独有优势——做题数据可以驱动记忆晋升 |
| 每日记忆写入时机 | 方案 C：做题结束 + 用户手动 + 特定场景 | 只在有价值时写入，避免噪音 |
| 晋升调度 | 方案 D：启动时轻量检查 + `/memory promote` 手动兜底 | Bobodan 是 CLI 工具，没有常驻进程 |
| 存储格式 | 方案 C：Markdown 文件 + SQLite 只做索引 | 保持人可读、易备份、与现有架构一致 |

## 3. 记忆生命周期

```
对话/做题
   │
   ▼
每日缓冲 (daily/YYYY-MM-DD.md)  ←── FTS5 索引
   │
   │  晋升评分 ≥ 0.6 且出现次数 ≥ 2
   ▼
永久记忆 (.bobodan/memory/*.md)  ←── FTS5 索引 + 向量辅助
   │
   │  连续 7 天未提及且正确率 < 50%
   ▼
待复习 (status: stale)  ←── 不注入 prompt，用户主动查看
```

## 4. 文件结构

```text
.bobodan/
  memory/               # 永久记忆（现有，不改）
    xingke_basic_info.md
    bobodan_identity.md
  daily/                # 每日记忆（新增）
    2026-05-19.md
    2026-05-20.md
  memory.db             # SQLite 索引（新增）
    chunks              # 所有记忆的文本块
    chunks_fts          # FTS5 虚拟表
    promotion_log       # 晋升记录
  MEMORY.md             # 索引表（现有，扩展）
```

## 5. 模块设计

### 5.1 `memory/daily.py` — 每日记忆管理

```python
class DailyMemoryManager:
    def append(date, content, tags)    # append 到当天文件
    def read(date) -> str              # 读取某天的记忆
    def list_recent(days=7) -> list    # 列出最近 N 天的文件
    def get_today() -> str             # 读取今天的内容
    def get_yesterday() -> str         # 读取昨天的内容
```

文件格式（`daily/YYYY-MM-DD.md`）：
```markdown
---
date: 2026-05-19
tags: [quiz, regex, learning]
---

## 14:30 正则表达式练习
- 做了 5 道题，对 3 道
- 薄弱点：贪婪匹配、转义符
- 下次复习：量词范围

## 16:00 学习笔记
- 理解了 Dijkstra 算法的贪心策略
```

### 5.2 `memory/store.py` — SQLite 索引

```python
class MemoryIndexStore:
    def __init__(workspace)            # 初始化 SQLite，建 FTS5 表
    def index_chunk(chunk_id, path, source, text, date)  # 索引一块文本
    def remove_by_path(path)           # 删除某文件的所有索引
    def search_fts(query, limit)       # FTS5 关键词搜索
    def get_promotion_candidates()     # 获取待晋升的每日记忆
    def record_recall(chunk_id)        # 记录一次搜索命中
    def get_recall_stats(chunk_id)     # 获取命中统计
```

SQLite schema：
```sql
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,           -- 文件路径
    source TEXT NOT NULL,         -- 'daily' 或 'permanent'
    text TEXT NOT NULL,
    date TEXT,                    -- YYYY-MM-DD（每日记忆用）
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, path, source,
    content='chunks',
    content_rowid='rowid',
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS recall_log (
    chunk_id TEXT NOT NULL,
    recalled_at TEXT NOT NULL,
    query_hash TEXT
);

CREATE TABLE IF NOT EXISTS promotion_log (
    daily_path TEXT NOT NULL,
    promoted_at TEXT NOT NULL,
    score REAL NOT NULL,
    details TEXT                  -- JSON: {frequency, quiz_score, recency}
);
```

### 5.3 `memory/promotion.py` — 晋升机制

```python
class PromotionEngine:
    def score(daily_path) -> float     # 计算晋升分数
    def promote(daily_path)            # 执行晋升：提取内容写入永久记忆
    def check_stale() -> list          # 检查待复习的永久记忆
    def run_promotion_check()          # 批量检查所有待晋升项
```

评分公式：
```
score = 0.4 * frequency_score + 0.4 * quiz_score + 0.2 * recency_score

frequency_score = min(1.0, recall_count / 5)      # 命中 5 次得满分
quiz_score = related_concept_accuracy              # 关联知识点的做题正确率
recency_score = exp(-0.1 * age_in_days)            # 30 天半衰期
```

晋升阈值：score ≥ 0.6 且 recall_count ≥ 2

### 5.4 `memory/search.py` — 混合检索

```python
class MemorySearcher:
    def search(query, limit=5) -> list  # FTS5 主检索
    def search_vector(query, limit=5)   # 向量辅助检索
    def search_hybrid(query, limit=5)   # 混合检索（FTS5 为主）
```

FTS5 检索（主）：`SELECT * FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank`

向量检索（辅）：现有 `LocalVectorStore.search()`，仅在 FTS5 无结果时 fallback

### 5.5 每日记忆写入触发

| 场景 | 触发方式 | 写入内容 |
|------|----------|----------|
| 做题结束 | `quiz_submit` 完成后自动 | 做题结果、正确率、薄弱知识点 |
| 用户说"记住" | Agent 调用 `memory_daily_save` | 用户指定的内容 |
| 对话超过 10 轮 | Agent 判断 | 本轮对话的关键要点 |
| 手动 | `/memory daily <content>` | 用户指定的内容 |

### 5.6 晋升触发

| 场景 | 触发方式 |
|------|----------|
| 启动时 | 检查是否有超过 3 天的未晋升每日文件，提示用户 |
| 手动 | `/memory promote` 执行晋升 |
| 做题结束后 | 顺带检查（可选） |

### 5.7 prompt 注入策略

| 记忆类型 | 注入时机 | 注入方式 |
|----------|----------|----------|
| 永久记忆 | 每次对话 | 现有 `build_memory_prompt()`，全部注入 |
| 今日记忆 | 每次对话 | 注入今天 + 昨天的每日文件内容 |
| 待复习记忆 | 不注入 | 用户通过 `/memory review` 主动查看 |

## 6. Agent 工具

| 工具 | 用途 |
|------|------|
| `memory_daily_save` | 写入每日记忆 |
| `memory_daily_read` | 读取某天的记忆 |
| `memory_promote` | 执行晋升检查 |
| `memory_search`（改造） | FTS5 搜索，覆盖每日 + 永久 |

## 7. REPL 命令

| 命令 | 用途 |
|------|------|
| `/memory daily [content]` | 写入今日记忆或查看今日内容 |
| `/memory daily 2026-05-19` | 查看指定日期的记忆 |
| `/memory promote` | 执行晋升检查 |
| `/memory search <query>` | FTS5 搜索（改造现有命令） |
| `/memory review` | 查看待复习的记忆 |

## 8. 实现顺序

1. `memory/store.py` — SQLite schema + FTS5 索引
2. `memory/daily.py` — 每日文件管理
3. `memory/search.py` — FTS5 检索（替换现有向量检索）
4. `memory/promotion.py` — 晋升评分和执行
5. 改造 `core/memory.py` — 集成 FTS5 索引、每日记忆注入
6. 新增 Agent 工具 + REPL 命令
7. 测试

## 9. 与现有系统的关系

- **永久记忆**（`core/memory.py`）：保持不变，只是搜索从向量改为 FTS5
- **向量检索**（`rag/vector_store.py`）：保留，降级为 FTS5 无结果时的 fallback
- **学习系统**（`learning/`）：晋升评分读取 quiz 做题数据
- **做题工具**（`tools/quiz_tools.py`）：做题结束后自动写每日记忆
