# Ollama RAG 嵌入接入方案

> **状态**: ✅ 已实现 (2026-05-21)
> 新增文件：`rag/ollama.py`、`rag/dense_store.py`、`rag/router.py`
> 修改文件：`config.yaml`、`rag/retriever.py`、`obsidian/sync.py`、`tools/rag_search.py`、`tools/obsidian_tool.py`、`cli/repl.py`
> 测试文件：`tests/test_ollama_embedding.py` (38 tests)

## 1. 目标

把本地 Ollama embedding 模型接入 Bobodan 的 RAG 体系，用于文本向量化、知识检索和后续的学习系统，但不破坏当前已有功能。

核心原则：

- 不替换原有 RAG 逻辑
- 不影响聊天、工具调用、记忆、题库、学习路径
- Ollama 可用时优先使用本地 embedding
- Ollama 不可用时自动回退到现有本地 embedding 方案

## 2. 当前状态

Bobodan 现在已经有这些能力：

- `rag/embeddings.py`：本地稀疏 embedding
- `rag/vector_store.py`：本地向量索引
- `rag/search.py` / `tools/rag_search.py`：检索入口
- `core/memory.py`：记忆搜索，已接入 FTS5 + vector fallback
- `cli/repl.py`：`/kb search`、`/kb sync` 等交互入口

因此，Ollama 的接入应该只作为“新的 embedding 后端”，而不是重写整套系统。

## 3. 接入范围

本次只处理 RAG 相关的 embedding 层：

- 文本切块后的向量化
- 知识检索的向量搜索
- 后续可复用到记忆检索

暂不改动：

- 聊天模型 Provider
- ReAct 主循环
- 工具系统
- 题库系统
- 学习路径系统

## 4. 运行逻辑

推荐采用自动选择模式：

```text
启动时探测 Ollama
  ├─ 可用且 embedding 模型可请求成功 → 使用 Ollama embedding
  └─ 不可用 / 模型不支持 / 请求失败 → 回退现有本地 embedding
```

这样做的好处：

- 不需要用户手动切换
- 不影响原来功能
- Docker 容器停了也能继续用

## 5. Ollama 可用性判断

判断标准分三层：

1. 服务可达
   - `http://localhost:11434/api/tags`
   - `http://localhost:11434/api/show`

2. 模型能力
   - `api/show` 返回 `capabilities` 包含 `embedding`

3. 实际可用
   - `POST /api/embed` 成功返回 `embeddings`

最终标准以第 3 条为准。

## 6. 推荐模型

优先使用专门的 embedding 模型，例如：

- `qwen3-embedding:0.6b`
- `nomic-embed-text`
- `embeddinggemma`

不建议把普通聊天模型直接当 embedding 模型用。

## 7. 数据结构建议

不要把两种向量格式混在一个索引里。

建议分开：

- 现有本地稀疏索引：保留
- Ollama dense 索引：新建

原因：

- 现有 `LocalEmbeddingProvider` 产出的是稀疏 dict
- Ollama 产出的是 dense float array
- 两者不能直接共用同一份 vector schema

## 8. 兼容性策略

必须保证以下行为不变：

- Ollama 关闭时，Bobodan 仍能正常聊天
- Ollama 关闭时，`/kb search` 仍能使用旧检索
- Ollama 关闭时，记忆、题库、学习路径不受影响
- Ollama 模型不支持 embedding 时自动回退

## 9. 配置建议

后续可增加这些配置项：

```yaml
rag:
  embedding_backend: auto   # auto | local | ollama
  ollama_url: "http://localhost:11434"
  ollama_model: "qwen3-embedding:0.6b"
```

说明：

- `auto`：默认，优先 Ollama，失败回退本地
- `local`：强制使用现有本地 embedding
- `ollama`：强制使用 Ollama

## 10. 代码落点建议

后续实现时，优先改这些位置：

- `rag/embeddings.py`
- `rag/vector_store.py`
- `rag/search.py`
- `tools/rag_search.py`
- `config.yaml`

如果要复用到记忆系统，再扩展：

- `core/memory.py`
- `memory/search.py`

## 11. 不做的事

这次不要做：

- 不删除原有本地 embedding
- 不改聊天 Provider
- 不把 Ollama 和原始索引强行合并
- 不让 Ollama 失败影响主流程

## 12. 验收标准

满足以下条件就算接入成功：

- Ollama 启动时，RAG 自动走 Ollama embedding
- Ollama 停止时，RAG 自动回退本地 embedding
- `kb search` 行为可用
- 旧功能全部保持正常
- 测试能覆盖“可用 / 不可用 / 回退”三种情况

## 13. 建议实施顺序

1. 先做配置与探活
2. 再加 Ollama embedding provider
3. 再做索引后端切换
4. 最后补测试

这份方案的目标不是“更换原系统”，而是“给 Bobodan 增加一个可切换的本地嵌入能力”。
