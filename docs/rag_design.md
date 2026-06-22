# Bobodan Full RAG Design

## 1. 目标

Bobodan 的知识库检索升级为完整 RAG 基础设施，支持四种检索方式：

1. **向量检索**：语义相似度检索（Qdrant + Ollama embedding）。
2. **FTS5 检索**：关键词、术语、原文匹配（SQLite FTS5 / BM25）。
3. **目录索引检索**：文档级路由，根据标题、摘要、关键词 + chunk 聚合判断相关文档。
4. **grep/rg 检索**：在候选文档中做精确文本搜索，返回原文上下文。

默认检索模式：

```text
Vector + FTS5 -> RRF 融合排序 -> chunk-level results
Directory Index -> 文档级路由 -> document-level results
directory_grep -> Directory 选文档 -> grep 搜原文 -> evidence results
```

本设计是完整知识库检索层，为 CLI、tools、FastAPI、未来 Web UI 共用。

## 2. 当前问题

当前项目已有：

- `rag/vector_store.py`：本地 sparse vector JSON（纯 TF，无 IDF）。
- `rag/dense_store.py`：Ollama dense embedding JSON（线性扫描）。
- `rag/router.py`：dense/sparse 路由和 fallback。
- `rag/chunker.py`：段落感知切块，1000 chars，无 heading 感知。
- `memory/search.py`：记忆系统已有 SQLite FTS5。
- `service/kb_service.py`：知识库 service 层入口。
- `graph/`：知识图谱，概念关系存储。

现有 RAG 缺：

- 没有统一知识库数据库（SQLite）。
- 没有正经向量数据库（Qdrant）。
- 没有知识库 FTS5 索引。
- 没有 Vector + FTS5 的 RRF 融合。
- 没有文档级目录索引（Directory Retriever）。
- 没有 grep/rg 原文检索和上下文扩展。
- 没有 heading-aware chunking。
- 没有多格式（PDF/PPT/Word）统一解析。
- 没有 FastAPI KB search endpoint。

## 3. 技术选型

| 层 | 选型 | 用途 |
|---|---|---|
| 元数据数据库 | SQLite | documents、chunks、directory entries、retrieval logs |
| 全文检索 | SQLite FTS5 | BM25/rank 关键词检索 |
| 向量数据库 | Qdrant | dense vector search（HNSW 索引） |
| embedding 模型 | Ollama `qwen3-embedding:0.6b` | 本地语义向量 |
| 精确搜索 | `rg` 优先，Python fallback | 原文定位和上下文扩展 |
| 融合排序 | RRF | 合并 Vector 和 FTS5 排名 |
| 多格式解析 | python-docx / python-pptx / pymupdf | PDF/Word/PPT 统一解析 |
| API | FastAPI | 给未来 Web UI 使用 |

参考：

- SQLite FTS5: https://sqlite.org/fts5.html
- Qdrant: https://qdrant.tech/documentation/quickstart/
- Qdrant Python client: https://github.com/qdrant/qdrant-client
- RRF: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
- ripgrep: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md

## 4. 存储结构

知识库目录：

```text
.knowledge/
  knowledge.db          # SQLite: metadata + FTS5
  qdrant/               # Qdrant local persistent storage
  manifest.json         # 文档清单
  sync_state.json       # 增量同步 content_hash 跟踪
  import_report.json    # 最近一次同步报告
```

### 4.1 SQLite

`knowledge.db` 保存结构化数据和 FTS5 索引。

核心表：

```sql
-- 文档元数据
CREATE TABLE documents (
    id TEXT PRIMARY KEY,            -- stable hash(source)
    source TEXT NOT NULL UNIQUE,    -- "course/deep-learning/ch03.md"
    path TEXT,
    kind TEXT,                      -- "obsidian_note" | "course_document"
    title TEXT,
    course TEXT,
    tags_json TEXT,                 -- JSON array
    summary TEXT,                   -- 规则摘要（前 300-500 字）
    content_hash TEXT,              -- 文件内容 hash
    vector_status TEXT DEFAULT 'pending',  -- pending | indexed | error
    vector_indexed_hash TEXT,       -- Qdrant 索引对应的内容 hash
    vector_error TEXT,              -- Qdrant 写入失败的错误信息
    updated_at TEXT
);

-- 文本块
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,            -- deterministic hash(source:index:text)
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    chunk_index INTEGER,
    text TEXT NOT NULL,
    heading_path_json TEXT,         -- JSON: ["深度学习", "激活函数", "ReLU"]
    heading_text TEXT,              -- "深度学习 > 激活函数 > ReLU"
    heading_level INTEGER,
    section_id TEXT,                -- "deep-learning/activation-functions/relu"
    chunk_index_in_section INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    slide_start INTEGER,
    slide_end INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    metadata_json TEXT              -- 其余 metadata
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text, title, heading_text, source, course,
    content='chunks',
    content_rowid='rowid'
);

-- FTS5 同步触发器
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, title, heading_text, source, course)
    VALUES (new.rowid, new.text,
            (SELECT title FROM documents WHERE id = new.document_id),
            new.heading_text, new.source,
            (SELECT course FROM documents WHERE id = new.document_id));
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title, heading_text, source, course)
    VALUES ('delete', old.rowid, old.text,
            (SELECT title FROM documents WHERE id = old.document_id),
            old.heading_text, old.source,
            (SELECT course FROM documents WHERE id = old.document_id));
END;

-- 文档目录索引
CREATE TABLE directory_entries (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT,
    summary TEXT,
    keywords_json TEXT,             -- JSON: ["ReLU", "Sigmoid", "激活函数"]
    source TEXT,
    path TEXT,
    course TEXT,
    chunk_count INTEGER
);

-- 检索日志
CREATE TABLE retrieval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT,
    mode TEXT,
    result_count INTEGER,
    created_at TEXT
);
```

### 4.2 Qdrant

使用 Qdrant local persistent 模式：

```text
.knowledge/qdrant/
```

Collection：

```text
bobodan_chunks
```

Payload：

```json
{
    "chunk_id": "a1b2c3d4e5f6g7h8",
    "document_id": "stable_hash_of_source",
    "source": "course/deep-learning/ch03.md",
    "title": "神经网络基础",
    "course": "深度学习",
    "heading_path": ["深度学习", "激活函数", "ReLU"],
    "heading_text": "深度学习 > 激活函数 > ReLU",
    "section_id": "deep-learning/activation-functions/relu",
    "chunk_index_in_section": 0,
    "page_start": 18,
    "page_end": 20
}
```

后续可从 local mode 切到 server mode：

```yaml
rag:
  vector_db:
    mode: server
    url: "http://localhost:6333"
```

### 4.3 document_id 稳定性

`document_id` 必须稳定，不随文档内容变化：

```python
document_id = stable_hash(source)  # source 路径的 hash
content_hash = hash(file_content)  # 文件内容的 hash
```

这样文档修改后 `document_id` 不变，才能正确删除旧 vectors 再插入新的。

### 4.4 旧索引清理

旧 JSON 索引是 legacy artifact，不再使用：

```text
.knowledge/rag_index.json       # legacy，不再写入/读取
.knowledge/rag_index_dense.json  # legacy，不再写入/读取
```

处理策略：

- 不读取、不更新、不作为 fallback。
- full reindex 成功后自动删除。
- `/kb reset` 会自然清理。
- 如果只有旧索引没有新索引，提示用户重新 sync。

## 5. 多格式解析与切块

### 5.1 统一中间结构

所有文件类型先解析成 `SourceSection`，再切块：

```text
PDF / PPT / Word / Markdown / TXT
        ↓
    SourceSection
        ↓
    heading-aware chunking
        ↓
    TextChunk
        ↓
  SQLite + Qdrant
```

```python
@dataclass
class SourceSection:
    source: str                    # "course/ch03.pdf"
    doc_title: str                 # "神经网络基础"
    unit_type: str                 # "page" | "slide" | "heading" | "paragraph"
    unit_range: str                # "p12-p14" | "slide 5-7"
    heading_path: list[str]        # ["第三章", "激活函数"]
    text: str
    metadata: dict                 # file_type, page_start, slide_start 等
```

### 5.2 按文件类型解析

| 文件类型 | 切 section 策略 | 依赖 |
|---|---|---|
| Markdown | 按 `#`/`##`/`###` heading 切 | 内置 |
| Word (.docx) | 按 Heading 1/2/3 样式切 | `python-docx` |
| PDF | 按 page 提取，尝试识别标题 | `pymupdf` |
| PPT (.pptx) | 按 slide 提取，按章节合并 | `python-pptx` |
| TXT | 按段落 fallback | 内置 |

**Markdown**：heading-aware，和现有 `obsidian/parser.py` 配合。

**Word**：读取 Heading 1/2/3 样式作为 section 边界，section 内按段落二次切分。

**PDF**：

- 文字型 PDF：按 page 提取文本，尝试识别标题/章节。
- 扫描型 PDF：检测到空文本 → 标记 `needs_ocr`，不强行 OCR，提示用户。
- metadata 带 `page_start` / `page_end`。

**PPT**：

- 按 slide 提取：title、bullet text、speaker notes、shape text。
- 1-3 页 slide 合成一个 chunk。
- metadata 带 `slide_start` / `slide_end`。

### 5.3 Section-Aware Adaptive Chunking

```yaml
chunking:
  strategy: heading_aware
  target_chars: 1800
  max_chars: 2600
  overlap_chars: 350
  min_chars: 400

  pdf:
    page_aware: true
    max_pages_per_chunk: 3

  ppt:
    slide_aware: true
    max_slides_per_chunk: 3
```

切块流程：

1. 按 Markdown heading / Word heading 样式 / PDF page / PPT slide 切成 sections。
2. section 内按段落切 chunk，chunk 继承 `heading_path`。
3. 长 section（> max_chars）二次切分，每个子 chunk 保留同一 `heading_path`。
4. 短 section（< min_chars）与相邻 section 合并，避免碎片。
5. overlap 在 chunk 边界提供上下文连续性。

### 5.4 TextChunk Schema

```python
@dataclass
class TextChunk:
    id: str                         # deterministic hash(source:index:text)
    text: str                       # chunk 正文
    source: str                     # "course/deep-learning/ch03.md"
    metadata: dict                  # 包含以下所有字段

    # 结构信息
    # metadata["doc_title"]: str
    # metadata["heading_path"]: list[str]  ["深度学习", "激活函数", "ReLU"]
    # metadata["heading_text"]: str        "深度学习 > 激活函数 > ReLU"
    # metadata["heading_level"]: int
    # metadata["section_id"]: str
    # metadata["chunk_index_in_section"]: int

    # 来源定位
    # metadata["page_start"]: int | None
    # metadata["page_end"]: int | None
    # metadata["slide_start"]: int | None
    # metadata["slide_end"]: int | None
    # metadata["char_start"]: int | None
    # metadata["char_end"]: int | None
    # metadata["file_type"]: str  "md" | "pdf" | "docx" | "pptx" | "txt"
```

### 5.5 Embedding Text 注入 Heading Context

embedding 和 FTS5 索引的 text 不只存正文，要注入 heading 上下文：

```text
文档：神经网络基础
章节：深度学习 > 激活函数 > ReLU

正文：
ReLU 是一种常见的非线性激活函数……
```

但返回给 LLM 的 `RetrievalHit.text` 保持正文为主，heading 信息在独立字段里。

这样用户搜"激活函数"时，即使 chunk 正文主要讲"ReLU 的梯度"，向量和 FTS5 也能知道它属于"激活函数"章节。

## 6. 检索方式

### 6.1 统一结果 Schema

```python
@dataclass
class RetrievalHit:
    # 核心标识
    chunk_id: str
    document_id: str
    source: str                     # "course/deep-learning/ch03.md"

    # 内容
    text: str                       # chunk 正文
    heading_path: list[str]         # ["深度学习", "激活函数", "ReLU"]
    heading_text: str               # "深度学习 > 激活函数 > ReLU"

    # 来源定位
    page_start: int | None = None
    page_end: int | None = None
    slide_start: int | None = None
    slide_end: int | None = None
    char_start: int | None = None
    char_end: int | None = None

    # 检索信息
    score: float = 0.0
    retrievers: list[str]           # ["vector", "fts5"]
    debug: dict                     # {"vector_rank": 2, "fts_rank": 5, "rrf_score": 0.032}

    # grep 特有
    match_context: str | None = None

@dataclass
class DocumentHit:
    document_id: str
    source: str
    title: str
    course: str | None
    heading_path: list[str]
    score: float
    reason: str                     # "chunks matched '激活函数', 'ReLU'"
    chunk_count: int
    top_chunks: list[RetrievalHit]
    debug: dict                     # {"metadata_score": 0.42, "chunk_aggregate_score": 0.68}

@dataclass
class RetrievalResult:
    hits: list[RetrievalHit]
    document_hits: list[DocumentHit] | None  # directory 模式时有值
    mode: str                       # 实际使用的检索模式
    confidence: str                 # "high" | "medium" | "low"
    fallback_from: str | None       # 从哪个 mode 降级来的
    debug: dict
```

`TextChunk` 是切块阶段产物，`RetrievalHit` 是检索阶段产物。切块时产生 `TextChunk`，存入 SQLite + Qdrant；检索时从两个库查出来组装成 `RetrievalHit`。

### 6.2 Vector Retriever

用途：

- 语义问题："解释一下……"
- 概念理解："这个概念和什么有关？"
- 用户问题和原文不完全同词。

数据来源：

- Qdrant collection `bobodan_chunks`
- embedding 来自 Ollama

失败降级：

- Ollama 不可用时，vector retriever 返回空。
- 其他 retriever 继续工作。

结果校验：

- Qdrant 返回的 chunk_id 必须回 SQLite hydrate 验证。
- 如果 SQLite 找不到该 chunk（可能残留旧 vector），丢弃该 hit。

### 6.3 FTS5 Retriever

用途：

- 精确术语："ReLU"、"Transformer"、"Adam optimizer"。
- 英文缩写、人名、模型名、文件名。
- 课程原文中的关键词。

排序：

- 使用 SQLite FTS5 `rank` / BM25。
- 结果转成统一 `RetrievalHit`。

FTS5 索引字段：

```sql
chunks_fts(text, title, heading_text, source, course)
```

### 6.4 Directory Retriever

**定位：文档级路由，不是元数据过滤，不是语义检索。**

职责：找"哪些文档可能相关"，不直接回答用户问题。

三种检索模式对比：

```text
Hybrid Retriever = 找"哪些 chunk 能回答问题"
Directory Retriever = 找"哪些文档可能相关"
Grep Retriever = 找"原文在哪里出现"
```

**第一版能力：**

1. **metadata lexical search**：在 title / summary / keywords / tags / course / path 上做 FTS5/BM25 或 LIKE 匹配。
2. **chunk hybrid result aggregation**：消费 Hybrid Retriever 的中间结果，按 document_id 聚合，得到相关文档列表。
3. **document-level ranking**：合并 metadata score + chunk aggregate score，返回排序后的文档列表。
4. **可解释原因**：返回为什么相关——命中了 title、summary、keyword，还是某几个 chunk 命中。

**接口：**

```python
class DirectoryRetriever:
    def search(
        self,
        query: str,
        chunk_hits: list[RetrievalHit] | None = None,
        top_k: int = 8,
        top_chunks_per_doc: int = 3,
    ) -> list[DocumentHit]:
        ...
```

**评分公式：**

```python
document_score = metadata_score * metadata_weight + chunk_aggregate_score * chunk_weight

# 默认权重
metadata_weight = 0.4
chunk_aggregate_weight = 0.6
```

**返回结构：**

```json
{
    "document_id": "...",
    "source": "course/deep-learning/ch03.md",
    "title": "神经网络基础",
    "course": "深度学习",
    "score": 0.72,
    "reason": "chunks matched '激活函数', 'ReLU', 'sigmoid'",
    "chunk_count": 8,
    "top_chunks": ["..."],
    "debug": {
        "metadata_score": 0.42,
        "chunk_aggregate_score": 0.68,
        "matched_fields": ["title", "heading_text"],
        "matched_terms": ["激活函数", "ReLU"]
    }
}
```

**关键约束：DirectoryRetriever 不调用 HybridRetriever。** chunk_hits 由 Orchestrator 传入。

第一版不依赖 LLM 生成摘要：

- title 来自 frontmatter 或文件名。
- summary 取文档前 300-500 字清洗文本。
- keywords 来自 tags、标题词、frontmatter、高频词。
- 后续可以增加 LLM summary。

### 6.5 Grep Retriever

用途：

- "在哪里提到 X？"
- "原文怎么说？"
- "包含这个词的上下文给我看。"
- hybrid 结果不足时补证据。

**两种任务意图：**

| intent | 场景 | evidence 判断 |
|---|---|---|
| exact_lookup | "在哪里提到 ReLU？" "原文里 softmax 怎么定义的？" | 看有没有强匹配（exact phrase / all_terms + context >= 300 chars） |
| coverage | "激活函数讲了哪些内容？" "哪些资料提到优化？" | 看覆盖面（多个 docs / 多个 sections 命中） |

**扩展阶梯：**

```text
directory top 8 docs, window=500 chars
  -> evidence thin: top 8, window=1000 chars
  -> still thin: top 15, window=1000 chars
  -> still thin: return available results, confidence=low
```

**不再继续扩展。** top 15 文档搜不到说明 query 和知识库不匹配，或者需要走 vector/semantic。

**evidence thin 判断：**

```python
def is_evidence_thin(
    matches: list[GrepMatch],
    total_context_chars: int,
    intent: str,  # "exact_lookup" | "coverage"
) -> bool:
    if not matches:
        return True
    if total_context_chars < 300:
        return True

    strong_matches = [
        m for m in matches
        if m.match_type in {"exact_phrase", "all_terms"}
        and m.context_chars >= 300
    ]

    if intent == "exact_lookup":
        return len(strong_matches) == 0

    # coverage
    unique_docs = {m.document_id for m in matches}
    unique_sections = {m.heading_text for m in matches if m.heading_text}
    if len(matches) < 2:
        return True
    if len(unique_docs) < 2 and len(unique_sections) < 2:
        return True

    return False
```

**confidence 标记：**

| confidence | 条件 |
|---|---|
| high | exact_lookup 有 strong match；coverage 有多个 docs/sections 命中 |
| medium | 有匹配但覆盖面一般 |
| low | 扩到 top 15 + 1000 chars 后仍 thin；或只有 partial matches |

**返回结构：**

```json
{
    "results": ["..."],
    "confidence": "high",
    "expanded": false,
    "window_chars": 500,
    "candidate_docs": 8,
    "reason": null
}
```

**rg fallback**：`rg` 不可用时使用 Python 文件扫描 fallback。

## 7. Hybrid Retriever（RRF 融合）

默认模式：

```text
query
  -> vector top 30
  -> fts5 top 30
  -> RRF rerank
  -> dedupe
  -> top_k
```

**RRF 只融合 vector + FTS5，不融合 directory 和 grep。**

原因：RRF 适合融合同一粒度的不同排序列表（都是 chunk-level）。directory 是 document-level，grep 是 evidence-level，粒度不同不适合混入 RRF。

**RRF 公式：**

```text
rrf_score = sum(weight[source] / (rrf_k + rank))
```

默认配置：

```yaml
rag:
  retrieval:
    rrf:
      k: 60
      weights:
        vector: 1.0
        fts5: 1.0
```

vector 和 fts5 默认权重相等：

- 没有评测集前，调权重是拍脑袋。
- RRF 只看排名不看分数，相等权重是最稳 baseline。
- FTS5 强：英文缩写、人名、模型名、术语。
- vector 强：中文解释性问题、同义表达、概念理解。
- 后续用真实查询样本再决定是否加 lexical/semantic profile。

**去重规则：**

```text
优先 chunk_id
其次 source + chunk_index
最后 source + text hash
```

**HybridRetriever 中间结果结构：**

```python
@dataclass
class HybridResult:
    top_chunks: list[RetrievalHit]      # 最终 top_k 结果
    all_chunk_hits: list[RetrievalHit]  # RRF 后的全部候选（给 Directory 消费）
    vector_hits: list[RetrievalHit]     # 原始 vector 结果
    fts_hits: list[RetrievalHit]        # 原始 fts5 结果
```

## 8. Query Routing

### 8.1 RetrievalOrchestrator

**核心约束：Hybrid 是 chunk 候选生成器；Directory 是文档级聚合器；Orchestrator 负责共享 Hybrid 结果，禁止 Directory 内部自己调用 Hybrid。**

```python
class RetrievalOrchestrator:
    def search(self, query: str, mode: str = "auto", top_k: int = 5) -> RetrievalResult:
        resolved_mode = self.router.route(query) if mode == "auto" else mode

        if resolved_mode == "hybrid":
            result = self._search_hybrid(query, top_k)
            # auto 模式下 hybrid 空结果自动 fallback
            if not result.hits and mode == "auto":
                fallback = self._search_directory_grep(query, top_k)
                fallback.fallback_from = "hybrid"
                return fallback
            return result

        if resolved_mode == "directory":
            return self._search_directory(query, top_k)

        if resolved_mode == "directory_grep":
            return self._search_directory_grep(query, top_k)

    def _search_hybrid(self, query, top_k):
        hybrid = self.hybrid.search(query, top_k=top_k, candidate_k=30)
        return RetrievalResult(hits=hybrid.top_chunks, mode="hybrid", ...)

    def _search_directory(self, query, top_k):
        hybrid = self.hybrid.search(query, top_k=top_k, candidate_k=50)
        docs = self.directory.search(query, chunk_hits=hybrid.all_chunk_hits)
        return RetrievalResult(hits=[], document_hits=docs, mode="directory", ...)

    def _search_directory_grep(self, query, top_k):
        hybrid = self.hybrid.search(query, top_k=top_k, candidate_k=50)
        docs = self.directory.search(query, chunk_hits=hybrid.all_chunk_hits)
        grep_results = self.grep.search(query, documents=docs)
        return RetrievalResult(hits=grep_results, mode="directory_grep", ...)
```

**三种模式的 chunk search 只跑一次：**

| mode | 流程 | fallback |
|---|---|---|
| hybrid | vector + fts5 → RRF → top_k | auto 模式空结果 → directory_grep |
| directory | hybrid broad search → directory metadata + chunk aggregation → document results | 无 |
| directory_grep | hybrid broad search → directory → grep evidence | 无 |

**显式指定 mode 时不自动 fallback，保持行为可预测。**

### 8.2 Query Router（规则匹配）

第一版不用 LLM router，用规则 router：

```python
def auto_route(query: str) -> str:
    q = query.strip()

    directory_grep_patterns = [
        r"在哪里提到", r"哪里提到", r"在哪.*提到",
        r"原文怎么说", r"原文", r"引用", r"出处", r"来源",
        r"包含.*上下文", r"包含.*原文", r"查找.*出现",
    ]
    directory_patterns = [
        r"哪些文档", r"哪一章", r"哪些资料", r"文档列表",
        r"资料列表", r"目录", r"应该看哪些", r"看哪.*资料",
    ]

    for pattern in directory_grep_patterns:
        if re.search(pattern, q):
            return "directory_grep"
    for pattern in directory_patterns:
        if re.search(pattern, q):
            return "directory"
    return "hybrid"
```

优先级：directory_grep > directory > hybrid。"原文/出处/在哪里"更具体，优先匹配。

### 8.3 Routing 规则总结

| 用户问题 | 检索模式 |
|---|---|
| 普通问答 | hybrid |
| 解释、理解、为什么 | hybrid |
| 包含、提到、在哪里 | directory_grep |
| 哪些文档、哪一章 | directory |
| 原文、引用、出处 | directory_grep |
| hybrid 无结果（auto 模式） | directory_grep fallback |

## 9. 对外接口

### 9.1 KBService

保持兼容，新增 mode 参数：

```python
KBService.search(
    query: str,
    course: str | None = None,
    top_k: int = 5,
    mode: str = "auto",          # auto | hybrid | directory | directory_grep
    config: dict | None = None,
)
```

KBService 不做 fallback 逻辑，fallback 由 Orchestrator 处理。

返回：

```json
{
    "ok": true,
    "results": [
        {
            "text": "...",
            "source": "course/deep-learning/ch03.md",
            "heading_text": "深度学习 > 激活函数 > ReLU",
            "score": 0.032,
            "method": "hybrid",
            "retrievers": ["vector", "fts5"],
            "page_start": 18,
            "page_end": 20,
            "debug": {
                "vector_rank": 2,
                "fts_rank": 5,
                "rrf_score": 0.032
            }
        }
    ],
    "mode": "hybrid",
    "confidence": "high",
    "fallback_from": null
}
```

### 9.2 Tool

`rag_search` tool schema 新增 optional mode：

```json
{
    "query": "string",
    "course": "string?",
    "top_k": "integer?",
    "mode": "string?"
}
```

mode 可选值：`auto`（默认）、`hybrid`、`directory`、`directory_grep`。

tool description：

```text
mode is optional. Use auto by default.
Use directory_grep for exact source/context lookup.
Use directory for document-level routing.
Use hybrid for normal semantic Q&A.
```

不破坏现有 skills 和 specialists。

### 9.3 FastAPI

新增：

```text
GET  /api/kb/status
POST /api/kb/sync
POST /api/kb/search
POST /api/kb/reindex
GET  /api/kb/documents
GET  /api/kb/documents/{document_id}
```

`POST /api/kb/search` 请求：

```json
{
    "query": "...",
    "course": null,
    "top_k": 5,
    "mode": "auto"
}
```

mode 可选值与 tool 一致：`auto | hybrid | directory | directory_grep`。

## 10. 知识图谱

知识图谱在第一版保持独立，不纳入 RetrievalOrchestrator。

```text
Graph = 独立概念关系查询层
RAG = 原文证据和文档检索层
```

- sync pipeline 继续构建 `graph_store.json`。
- `graph_query` tool 继续独立注册，Agent 自主决定何时调用。
- Orchestrator 不调用 `graph_query`，不融合 graph results。

原因：

- 图谱查询的是 concept node / relationship edge，和 chunk/document 不是同一粒度。
- 概念关系查询（"学 X 之前要先学什么"）vs 原文证据查询（"课件里怎么解释 X"）是不同场景。
- `graph_query` 已经独立工作，不需要重写。
- 第一版目标已经够大，不增加额外复杂度。

后续可考虑 Graph as RAG enhancement（query expansion / answer structuring），但不是当前阶段。

## 11. 配置

```yaml
rag:
  embedding_backend: auto
  ollama_url: "http://localhost:11434"
  ollama_model: "qwen3-embedding:0.6b"
  probe_timeout: 3
  request_timeout: 10

  storage:
    metadata_db: sqlite
    sqlite_path: ".knowledge/knowledge.db"

  vector_db:
    backend: qdrant
    mode: local
    local_path: ".knowledge/qdrant"
    url: "http://localhost:6333"
    collection: "bobodan_chunks"
    distance: cosine

  chunking:
    strategy: heading_aware
    target_chars: 1800
    max_chars: 2600
    overlap_chars: 350
    min_chars: 400
    pdf:
      page_aware: true
      max_pages_per_chunk: 3
    ppt:
      slide_aware: true
      max_slides_per_chunk: 3

  retrieval:
    default_mode: hybrid
    rrf:
      k: 60
      weights:
        vector: 1.0
        fts5: 1.0
    vector_top_k: 30
    fts_top_k: 30
    directory_top_k: 8
    directory_top_chunks: 3
    directory:
      metadata_weight: 0.4
      chunk_aggregate_weight: 0.6
    grep:
      window_chars: 500
      expand_chars: 1000
      max_candidate_docs: 15
    max_context_chars: 6000
```

## 12. 文件规划

新增：

```text
rag/schema.py                    # RetrievalHit, DocumentHit, RetrievalResult, HybridResult
rag/sqlite_store.py              # SQLite + FTS5 存储层
rag/qdrant_store.py              # Qdrant 向量存储层
rag/rrf.py                       # RRF 融合排序
rag/hybrid.py                    # HybridRetriever
rag/directory.py                 # DirectoryRetriever
rag/grep_retriever.py            # GrepRetriever
rag/orchestrator.py              # RetrievalOrchestrator
rag/query_router.py              # QueryRouter（规则匹配）
rag/source_section.py            # SourceSection 中间结构
rag/chunker_v2.py                # heading-aware adaptive chunking
rag/parsers/
  __init__.py
  markdown_parser.py             # Markdown heading-aware 解析
  pdf_parser.py                  # PDF page-aware 解析
  pptx_parser.py                 # PPT slide-aware 解析
  docx_parser.py                 # Word heading-style 解析
web/backend/routers/kb.py        # FastAPI KB endpoints
tests/test_rag_sqlite_store.py
tests/test_rag_qdrant_store.py
tests/test_rag_retrievers.py
tests/test_rag_hybrid.py
tests/test_rag_orchestrator.py
tests/test_rag_query_router.py
tests/test_rag_chunker_v2.py
tests/test_rag_parsers.py
tests/test_kb_api.py
```

修改：

```text
obsidian/sync.py                 # 改用新 chunking + SQLite + Qdrant 写入
rag/retriever.py                 # 改用 Orchestrator 作为入口
rag/chunker.py                   # 保留旧实现作为 fallback，新版在 chunker_v2.py
service/kb_service.py            # 新增 mode 参数
tools/rag_search.py              # 新增 mode 参数
config.yaml
requirements.txt
```

保留但标记 legacy：

```text
rag/vector_store.py              # legacy，新链路不调用
rag/dense_store.py               # legacy，新链路不调用
rag/router.py                    # legacy，新链路不调用
```

## 13. 迁移策略

### 13.1 旧索引处理

旧 JSON 索引是 legacy artifact，不进入新架构：

- 不读取、不更新、不作为 fallback。
- full reindex 成功后可清理旧 JSON。
- `/kb reset` 会自然删除。

### 13.2 Incremental Sync

```python
def incremental_sync(workspace, vault_path, course_dir):
    current = scan_all(vault_path, course_dir)
    previous = load_sync_state(workspace)

    changed = [f for f in current if f.hash != previous.get(f.source)]
    deleted = [s for s in previous if s not in {f.source for f in current}]

    for doc in changed:
        sections = parse_document(doc)
        chunks = chunk_sections(sections)

        # SQLite 事务：主数据 + FTS5 增量更新
        with sqlite.transaction():
            sqlite.upsert_document(doc, vector_status="pending")
            sqlite.delete_chunks_by_document(doc.document_id)
            sqlite.insert_chunks(chunks)
            sqlite.upsert_directory_entry(doc, chunks)
            # FTS5 通过触发器自动同步

        # Qdrant：先删旧 vectors，再插新的
        try:
            qdrant.delete_by_filter(document_id=doc.document_id)
            qdrant.upsert(chunks)
            sqlite.mark_vector_indexed(
                document_id=doc.document_id,
                content_hash=doc.content_hash,
            )
        except Exception as e:
            sqlite.mark_vector_error(
                document_id=doc.document_id,
                error=str(e),
            )

    for source in deleted:
        doc_id = sqlite.get_document_id(source)
        if not doc_id:
            continue
        with sqlite.transaction():
            sqlite.delete_document(doc_id)
            # chunks, fts, directory entries cascade/delete
        try:
            qdrant.delete_by_filter(document_id=doc_id)
        except Exception:
            pass  # stale qdrant hits 由 SQLite hydrate 过滤

    save_sync_state(workspace, current)
```

### 13.3 Full Sync

full sync 完全重建 SQLite + Qdrant：

- 清空 SQLite 所有表。
- 清空 Qdrant collection。
- 重新扫描、解析、chunk、写入。
- 重建 FTS5（通过触发器自动完成）。
- 重建 directory_entries。
- 清理旧 JSON 索引文件。

### 13.4 SQLite 是 Truth Source

- SQLite 始终完整，Qdrant 失败不回滚 SQLite。
- `documents.vector_status` 跟踪 Qdrant 索引状态：`pending | indexed | error`。
- 下次 sync/reindex 可以补 `vector_status != indexed` 的文档。
- 检索时 Qdrant hit 必须回 SQLite hydrate，防止旧 vector 污染。

### 13.5 FTS5 策略

- incremental sync：FTS5 增量更新（触发器自动同步）。
- full sync / repair：rebuild FTS5。

## 14. 测试计划

1. SQLite store
   - 建库
   - documents/chunks 写入和级联删除
   - FTS5 增量搜索
   - course filter
   - vector_status 更新
   - directory_entries 写入

2. Qdrant store
   - local path 初始化
   - collection 创建
   - upsert vectors
   - search vectors
   - delete by document_id filter

3. RRF
   - 单来源排序
   - vector + fts5 融合
   - 重复 chunk 去重
   - 权重生效

4. Chunker v2
   - Markdown heading-aware 切分
   - heading_path 继承
   - 长 section 二次切分
   - 短 section 合并
   - embedding text 注入 heading context

5. Parsers
   - PDF page-aware 解析
   - PPT slide-aware 解析
   - Word heading-style 解析
   - 扫描 PDF 标记 needs_ocr

6. Retrievers
   - vector retriever + SQLite hydrate
   - fts retriever
   - directory retriever（metadata + chunk aggregation）
   - grep retriever（exact_lookup / coverage intent）
   - rg 不可用 fallback
   - evidence thin 判断 + 扩展阶梯

7. Orchestrator
   - hybrid mode
   - directory mode
   - directory_grep mode
   - auto mode 路由
   - hybrid 空结果 fallback to directory_grep
   - 显式 mode 不 fallback

8. Query Router
   - directory_grep 模式匹配
   - directory 模式匹配
   - 默认 hybrid
   - 优先级：directory_grep > directory > hybrid

9. KBService
   - 旧 search 调用不破坏（mode 默认 auto）
   - mode 参数生效
   - 无索引错误
   - 空 query 错误

10. Incremental Sync
    - 变更文档更新 SQLite + Qdrant
    - 删除文档级联清理
    - Qdrant 失败记录 vector_status=error
    - Qdrant 残留数据由 SQLite hydrate 过滤

11. FastAPI
    - `/api/kb/status`
    - `/api/kb/search`（含 mode 参数）
    - `/api/kb/documents`

验证命令：

```bash
pytest tests/test_rag_sqlite_store.py -v
pytest tests/test_rag_qdrant_store.py -v
pytest tests/test_rag_chunker_v2.py tests/test_rag_parsers.py -v
pytest tests/test_rag_retrievers.py tests/test_rag_hybrid.py -v
pytest tests/test_rag_orchestrator.py tests/test_rag_query_router.py -v
pytest tests/test_kb_service.py tests/test_knowledge_tools.py -v
pytest
```

## 15. 完成标准

完成后应满足：

- `obsidian_sync` 后生成 SQLite + Qdrant 索引（无旧 JSON 索引）。
- `rag_search` 默认走 hybrid（auto mode）。
- exact keyword 查询由 FTS5 命中。
- semantic 查询由 Qdrant vector 命中。
- "在哪里提到"类问题走 directory_grep。
- "哪些文档"类问题走 directory。
- hybrid 无结果时 auto 模式 fallback 到 directory_grep。
- heading-aware chunking 生效，检索结果带 heading_path。
- PDF/PPT/Word 能正确解析并索引，引用带页码/slide 号。
- Qdrant 失败时 FTS5/directory/grep 仍可用。
- Qdrant 残留旧数据由 SQLite hydrate 过滤。
- 没有 Ollama 时，FTS5 / directory / grep 仍可用。
- 没有 `rg` 时，Python fallback 仍可用。
- CLI、tool、KBService、FastAPI 都使用同一套检索逻辑（Orchestrator）。
- 全量测试通过。

## 16. 不做事项

本阶段不做：

- React Web UI。
- LLM query router。
- LLM 生成 directory summary。
- 多用户权限。
- 云端 Qdrant 部署。
- LangChain / LangGraph 重写。
- OCR（扫描 PDF 标记 needs_ocr，不自动 OCR）。
- 知识图谱纳入 Orchestrator。
- 动态 RRF weight profile（lexical/semantic）。
- 旧 JSON 索引作为 runtime fallback。

这些可以在 RAG 核心稳定后再做。
