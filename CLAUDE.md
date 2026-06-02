# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview 

波波蛋 (Bobodan) is a Python-based ReAct agent with multiple LLM provider support, session persistence, a skills system, a persistent memory system with daily memory and FTS5 search, a local knowledge base with RAG and knowledge graph, a wiki compilation layer, a quiz system, a learning path system, and a CLI REPL interface. Users chat with the agent which reasons and calls tools (read_file, write_file, list_dir, change_dir, stat_path, memory_save, memory_recall, memory_daily_save, memory_daily_read, memory_promote, knowledge_status, question_generate, quiz_start, quiz_submit, learning_path, learning_progress, learning_review, wiki_ingest, wiki_lint) in a loop until it produces a response.

## Commands

### Run the agent
```bash
python agent.py
python agent.py -c config.yaml
python agent.py --session-id <id>  # resume saved session
python agent.py -v                 # verbose logging (DEBUG level)
```

### Install dependencies
```bash
pip install -r requirements.txt          # runtime only
pip install -r requirements-dev.txt      # with pytest
```

### REPL commands
```
/skill list         # list available skills
/skill <name>       # show skill content
/skill run <name>   # run skill as agent task
/kb sync <vault> [course_dir] [--full]   # sync Obsidian vault to knowledge base
/kb status          # show knowledge base stats (courses, chunks, errors, graph)
/kb search <query> [--course name] [--top-k n]  # local RAG search
/kb graph <concept> [--intent related] [--limit n]  # knowledge graph query
/kb reset --yes     # delete generated .knowledge/ indexes
/quiz generate <topic> [--count n] [--course name]  # generate quiz questions
/quiz start [count] [--course name]  # start a quiz practice session
/quiz wrong         # show wrong answer book
/quiz weak          # show weakness analysis by concept
/quiz stats         # show quiz question counts by type
/learning plan <goal> [--course name] [--deadline date]  # generate learning plan
/learning progress [concept]  # show mastery overview or concept detail
/learning review    # show today's review list
/learning mark <concept> mastered|learning|needs_review  # manually set mastery
/learning plans     # list saved learning plans
/memory list        # list saved memories
/memory show <name> # show memory details
/memory search <query>  # search memories (FTS5 + vector)
/memory forget <name>   # delete a memory
/memory daily [content] # write/view today's daily memory
/memory daily YYYY-MM-DD  # view specific date's memory
/memory promote     # check and execute daily→permanent promotion
/memory review      # show today's review list (from learning module)
/memory stats       # show memory statistics (includes FTS5 stats)
/wiki init <vault>  # initialize wiki directory structure
/wiki ingest <source> [--vault path] [--force]  # compile sources into wiki pages
/wiki lint [vault]  # wiki health check (orphans, broken links, stale)
/wiki status [vault]  # wiki statistics
/ui                 # show UI settings
/ui tools on|off    # toggle tool call display during streaming
/session list                 # list saved sessions (name, id, time)
/session save [name]          # save session with optional name
/session resume               # interactive session picker
/session load <id|name>       # load by id, prefix, or name
/status             # show runtime status
```

### Run tests
```bash
pytest
pytest tests/test_session.py        # single test file
pytest tests/ -v                     # verbose
```

### Environment setup
```bash
cp .env.example .env                 # then edit .env with API keys
```

## Architecture

```
agent.py          # CLI entry point, parses args, starts REPL
config.yaml       # Provider, agent, session, skills, memory configuration
.env              # API keys (copy from .env.example)
core/
  session.py      # Session dataclass, message history, save/load to JSON
  agent_loop.py   # ReAct loop: calls LLM, parses tool calls, executes tools
  skills.py       # Skills discovery, frontmatter parsing, XML prompt formatting
  memory.py       # Memory system: MemoryManager, MemoryEntry, MEMORY.md index
cli/
  repl.py         # REPL class: handles input, commands, streaming feedback
  markdown_render.py  # Rich-based terminal rendering (panels, tables, markdown)
providers/
  types.py        # ToolCall and LLMResponse dataclasses (unified internal types)
  base.py         # LLMProvider protocol (complete, get_name)
  openai_compat.py # OpenAICompatibleProvider base class (raw httpx, shared logic)
  factory.py      # ProviderFactory: creates providers from config.yaml
  deepseek.py     # DeepseekProvider (inherits OpenAICompatibleProvider)
  minimax.py      # MiniMaxProvider (raw httpx, refusal detection)
tools/
  base.py         # Tool registry, ToolResult, workspace security (DENY_READ_PATTERNS)
  file_ops.py     # read_file, write_file tools (with size limit, binary check, overwrite guard)
  dir_ops.py      # list_dir, change_dir, stat_path tools
  http_req.py     # http_request tool (GET/POST/etc.)
  obsidian_tool.py # obsidian_sync tool (syncs vault to .knowledge/)
  rag_search.py   # rag_search tool (local RAG retrieval)
  graph_query.py  # graph_query tool (knowledge graph relationships)
  memory_tools.py # memory_save, memory_recall, memory_daily_save, memory_daily_read, memory_promote
  knowledge_status.py # knowledge_status tool (knowledge base overview)
  quiz_tools.py   # question_generate, quiz_start, quiz_submit tools
knowledge/        # Knowledge base management
  documents.py    # DocumentRecord, build_document_records (per-file import tracking)
  manifest.py     # .knowledge/manifest.json read/write
  import_report.py # ImportReport: post-sync error and summary reports
  library.py      # LibrarySummary: aggregate stats across courses, graph, and chunks
quiz/             # Quiz system (SQLite-backed)
  schema.py       # Question, QuizSession, QuizAttempt dataclasses
  store.py        # QuizStore: SQLite CRUD for questions, sessions, attempts
  generator.py    # QuestionGenerator: LLM-based question generation from RAG chunks
  evaluator.py    # QuizEvaluator: auto-grade choice/T-F, LLM-grade short answer
  review.py       # QuizReviewer: wrong answer book and weakness analysis
learning/         # Learning path and progress tracking
  schema.py       # Mastery, LearningPlan dataclasses
  store.py        # LearningStore: SQLite tables for mastery and learning plans
  scheduler.py    # ReviewScheduler: simple spaced repetition (1/3/7/14 days)
  progress.py     # ProgressTracker: mastery overview, auto-infer from quiz
  path.py         # LearningPathGenerator: LLM-based personalized learning plans
memory/           # Memory upgrade: daily memory, FTS5 index, promotion
  store.py        # MemoryIndexStore: SQLite + FTS5 full-text search (chunks, recall_log, promotion_log)
  daily.py        # DailyMemoryManager: daily memory files in .bobodan/daily/
  search.py       # MemorySearcher: FTS5 primary + vector fallback
  promotion.py    # PromotionEngine: daily→permanent promotion scoring
mcp_client/       # MCP (Model Context Protocol) client integration
  config.py       # YAML loading + ${ENV_VAR} substitution
  event_loop.py   # AsyncEventLoop: background thread bridge for async MCP SDK
  manager.py      # MCPManager: per-server state, lazy connect, reload
  naming.py       # build_safe_tool_name: server__tool format with sanitization
  catalog.py      # build_mcp_tool_specs: enumerate tools across servers
  tool_wrapper.py # make_mcp_tool_func: wrap as Bobodan ToolResult
  prompt.py       # build_mcp_status_prompt: system prompt segment
  transport_base.py    # Transport abstract base
  transport_stdio.py   # stdio transport (subprocess + SDK)
  transport_sse.py     # SSE transport (legacy HTTP+SSE)
  transport_http.py    # streamable_http transport (modern HTTP)
rag/              # Document ingestion, chunking, embeddings, vector stores, retrieval router
  chunker.py      # TextChunk, chunk_text (paragraph-aware sliding window)
  embeddings.py   # LocalEmbeddingProvider: sparse TF+L2 vectors
  vector_store.py # LocalVectorStore: JSON-backed sparse vector index
  dense_store.py  # DenseVectorStore: JSON-backed dense vector index (Ollama)
  ollama.py       # OllamaEmbeddingClient: probe, embed, cache availability
  router.py       # VectorStoreRouter: auto/local/ollama backend selection + dual-write
  retriever.py    # search_index: thin search wrapper
  ingest.py       # Document loading (md/txt/pdf)
  citations.py    # format_search_results
wiki/             # LLM wiki compilation layer (Karpathy pattern)
  schema.py       # WikiPage, CompileResult, WikiConfig, source registry
  compiler.py     # WikiCompiler: LLM-based source→wiki page compilation
  index.py        # WikiIndexer: index.md catalog + log.md chronicle
  lint.py         # WikiLinter: orphan/broken link/stale page detection
tools/
  mcp.py          # register_mcp_tools: REPL integration entry point for MCP
skills/           # Skills directory (configurable via config.yaml)
  weather/        # Example skill: weather queries via wttr.in
    SKILL.md      # YAML frontmatter (name, description) + Markdown instructions
```

## Knowledge assistant modules

RAG and knowledge graph features are additive modules. Keep the existing Agent loop,
provider abstraction, session model, and REPL stable unless a change is explicitly
needed for tool integration.

```
obsidian/        # Obsidian vault scanning and Markdown/frontmatter/link/tag parsing
rag/             # Document ingestion, chunking, embeddings, vector stores, retrieval router
graph/           # Knowledge graph schema, local JSON store, optional Neo4j adapter
tools/           # Agent-facing wrappers for sync, RAG search, and graph query
.knowledge/      # Runtime indexes and sync state; generated locally and not tracked by git
```

### Knowledge data rules

- `.knowledge/` is generated runtime state. Do not commit it, and it may be safely
  deleted when rebuilding indexes from source notes/documents.
- Knowledge tools must keep workspace boundary checks. They should not scan or
  index paths outside the current workspace unless a future explicit allow-list is
  added first.
- Prefer local, deterministic fallbacks for MVP behavior. Neo4j is optional: when
  `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` are missing or the driver is
  unavailable, graph operations must continue through the local JSON graph store.
- Keep RAG storage behind adapter-style modules so the lightweight local index can
  later be replaced by real embedding providers or vector databases without
  changing Agent tool contracts.

### Key patterns

**Provider creation**: `ProviderFactory.create_from_config(config.yaml)` reads `llm.default_provider` from config and instantiates the matching provider class.

**Provider types**: All providers return `LLMResponse(content: str, tool_calls: list[ToolCall])`. `ToolCall` has `id`, `name`, `arguments` fields. `LLMProvider` protocol: `complete(messages, tools=None) -> LLMResponse`. Providers also implement `complete_stream()` returning `Iterator[LLMStreamChunk]` for streaming; `AgentLoop._complete_with_events()` auto-detects streaming support via `getattr(self.llm, "complete_stream")`.

**Tool registration**: Tools auto-register at import time — `tools/__init__.py` imports all tool modules, each of which calls `register_tool()` at module level. Adding a new tool: create the file, call `register_tool()`, add the import to `tools/__init__.py`.

**Tool execution**: Tools are registered via `register_tool(name, description, params_schema, func)`. `execute_tool(name, args, session)` returns `ToolResult(ok: bool, content: str, data: dict)`. Tools enforce workspace root boundary (`_is_within_workspace`) and deny list (`_is_denied_path` for `.env`, `.git`, etc.). `content` goes to the LLM, `data` is for programmatic use (e.g., `change_dir` sets `data["cwd"]`).

**Session persistence**: Sessions save to `.session/<id>.json` (configurable). The cwd is stored in the session and used by all tools as the workspace root.

**ReAct loop**: `AgentLoop.run_stream(user_input)` (or the convenience wrapper `run()`) adds the user message, calls the LLM, executes each `ToolCall`, and loops until the LLM returns text instead of tool calls (max 8 iterations). The REPL calls `run_stream()` in a background thread and renders events (`assistant_delta`, `tool_start`, `tool_end`, `assistant_done`) in real time. Message ordering is always: `user → assistant(tool_calls) → tool → assistant`. The REPL deep-copies the session before each turn so timeouts don't pollute state.

**Skills system**: Skills are loaded from `skills/` directory (configurable). Each skill is a subdirectory containing a `SKILL.md` file with YAML frontmatter (`name`, `description`) and Markdown body (instructions). At startup, `build_skills_system_prompt()` scans the directory, parses frontmatter, and formats an XML catalog into a system message. The model reads the catalog and autonomously decides which skill to load via `read_file`. `/skill run <name>` strips frontmatter and sends the body as a user message prefixed with `[Skill: name]`. A stable `SKILLS_PROMPT_MARKER` in the injected system message prevents duplicate injection on session restore. System messages are protected from trimming in `_trim_messages()`.

**Memory system**: Two-tier memory with lifecycle management.

Permanent memories (`.bobodan/memory/*.md`): YAML frontmatter (`name`, `description`, `type`, `created`, `updated`). Four types: `user` (profile), `feedback` (corrections), `project` (context), `reference` (external pointers). Auto-generated `MEMORY.md` index.

Daily memories (`.bobodan/daily/YYYY-MM-DD.md`): Timestamped entries with YAML frontmatter (`date`, `tags`). Used as buffer for learning notes, quiz results, and transient context. Today + yesterday injected into system prompt automatically.

Storage: `.bobodan/memory.db` (SQLite) with FTS5 full-text search for fast keyword retrieval. `memory_index.json` (vector store) kept as fallback. FTS5 triggers auto-sync with chunks table.

Search: `MemorySearcher` uses FTS5 as primary, `LocalVectorStore` vector similarity as fallback.

Promotion: `PromotionEngine` evaluates daily memories for promotion to permanent. Score = 0.4×frequency + 0.4×quiz_association + 0.2×recency (30-day half-life). Threshold: score ≥ 0.6 and recall_count ≥ 2. Triggered by `/memory promote` or `memory_promote` tool.

Tools: `memory_save`, `memory_recall` (FTS5 search), `memory_daily_save`, `memory_daily_read`, `memory_promote`. REPL: `/memory list|show|search|forget|daily|promote|review|stats`.

## RAG Embedding System

Two vector store backends with automatic routing:

- **Sparse** (`rag/vector_store.py`): TF + L2 normalization, dict-based vectors. Zero dependencies, always available.
- **Dense** (`rag/dense_store.py`): Ollama embedding models, float arrays. Better semantic matching, requires local Ollama.

Routing (`rag/router.py`): `VectorStoreRouter` selects backend based on `config.yaml` `rag.embedding_backend`:
- `auto` (default): probe Ollama at startup → use dense if available, sparse as fallback. Dual-writes both indices on `/kb sync`.
- `local`: force sparse only.
- `ollama`: force dense, fail if unavailable.

Ollama client (`rag/ollama.py`): `OllamaEmbeddingClient` probes Ollama health + model capability + real embed request. Caches availability. Config: `rag.ollama_url`, `rag.ollama_model`, `rag.probe_timeout`, `rag.request_timeout`.

Index files: `.knowledge/rag_index.json` (sparse), `.knowledge/rag_index_dense.json` (dense). Dense index stores model name + embedding dim for model change detection.

## MCP (Model Context Protocol) Client

Bobodan can connect to external MCP servers and expose their tools to the LLM agent. Three transports: stdio (subprocess), streamable_http, SSE. All backed by the official `mcp` Python SDK 1.19+.

**Architecture** (`mcp_client/`):
- `event_loop.py` — `AsyncEventLoop` singleton: background daemon thread runs asyncio, `run_sync(coro, timeout)` bridges sync→async via `run_coroutine_threadsafe`
- `manager.py` — `MCPManager`: per-server state (config, transport, connected/error, tools), lazy connect on first tool call, `reload()` diffs config and adds/removes/reconnects
- `config.py` — config loader; supports both `transport` and `type` field names; substitutes `${ENV_VAR}` in any string field (fail-fast on missing); validates stdio needs `command`, http needs `url` with `http(s)://`
- `naming.py` — `build_safe_tool_name(server, tool, reserved)`: sanitizes special chars to `-`, truncates server to 30 chars and combined to 64, appends `-2`/`-3` on collision against reserved names
- `catalog.py` — `build_mcp_tool_specs(mgr, reserved)`: connects to each enabled server and returns a list of `{safe_name, server, tool_name, description, inputSchema}` dicts
- `tool_wrapper.py` — `make_mcp_tool_func(server, tool, mgr)`: returns a function that calls `mgr.call()` and converts the MCP result to a `ToolResult(ok, content, data)`
- `prompt.py` — `build_mcp_status_prompt(mgr)`: returns the `## MCP Servers` segment for the system prompt; lists each enabled server's connection state and tool count

**Transports** (`mcp_client/transport_*.py`): all three implement the same `Transport` ABC (`connect / disconnect / list_tools / call_tool / is_connected`). They wrap the corresponding SDK context manager and `mcp.ClientSession`. The call_tool result conversion uses `btype` to disambiguate text/image/resource blocks.

**REPL integration** (`tools/mcp.py` + `cli/repl.py`):
- `tools/mcp.register_mcp_tools(config)` is called once at REPL startup, before `AgentLoop` is constructed. It builds the catalog and calls `register_tool()` for each MCP tool. Per-server connect failures are isolated: a server that can't connect is logged and skipped, others register.
- `core/agent_loop.py` takes a new `mcp_prompt` parameter and injects it as a system message on first turn (HTML comment marker for idempotency).
- `/mcp` command group: `list` (default), `status`, `restart [name]`, `tools <name>`, `reload`. See `cli/repl.py`.
- Startup panel shows `mcp: <connected>/<total> connected, N tools`.

**Config schema** (`config.yaml`):
```yaml
mcp:
  enabled: true
  connection_timeout: 30
  tool_call_timeout: 60
  servers:
    github:        # stdio (auto-inferred from `command`)
      command: uvx
      args: ["mcp-server-git"]
    amap:          # streamable_http
      transport: streamable_http
      url: "https://mcp.example.com/mcp"
      headers:
        Authorization: "Bearer ${GITHUB_TOKEN}"
    legacy:        # sse (default for url without explicit transport)
      transport: sse
      url: "https://mcp.example.com/sse"
```

**Security model**: trust-first. Any server in `config.yaml` is fully trusted; all its tools are auto-available. No per-tool approval gate (that's Phase 2 per the harness plan).

**Testing**: `tests/test_mcp_*.py` covers config, event loop, manager, naming, catalog, prompt, all three transports (SDK-mocked), and the REPL commands — 76 tests total.

## Provider API

Providers must implement `LLMProvider` protocol:
- `complete(messages: list[dict], tools: list[dict] | None = None) -> LLMResponse`
- `get_name() -> str`

**`OpenAICompatibleProvider`** (`providers/openai_compat.py`) is the base class for OpenAI-compatible APIs. Handles message conversion (`_convert_messages`), HTTP requests, and response parsing (`_parse_response`). Deepseek and OpenAI providers inherit from it.

**MiniMax provider** (`providers/minimax.py`) uses raw httpx with its own message conversion and refusal detection (skips tool_calls when content contains refusal language).
