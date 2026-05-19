# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview 

波波蛋 (Bobodan) is a Python-based ReAct agent with multiple LLM provider support, session persistence, a skills system, a persistent memory system, a local knowledge base with RAG and knowledge graph, a quiz system, a learning path system, and a CLI REPL interface. Users chat with the agent which reasons and calls tools (read_file, write_file, list_dir, change_dir, stat_path, memory_save, memory_recall, knowledge_status, question_generate, quiz_start, quiz_submit, learning_path, learning_progress, learning_review) in a loop until it produces a response.

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
/memory search <query>  # search memories by semantic similarity
/memory forget <name>   # delete a memory
/memory stats       # show memory statistics
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
  memory_tools.py # memory_save, memory_recall tools (persistent memory)
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
rag/             # Document ingestion, chunking, local embeddings, vector index, retrieval
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

**Memory system**: Persistent memories are stored as individual Markdown files in `.bobodan/memory/` with YAML frontmatter (`name`, `description`, `type`, `created`, `updated`). An auto-generated `MEMORY.md` index provides a table overview. The `MemoryManager` class (`core/memory.py`) handles CRUD operations and vector indexing via `LocalVectorStore`. Two Agent tools are registered: `memory_save` (save/update) and `memory_recall` (semantic search). At startup, `build_memory_prompt()` builds an XML-structured system prompt fragment with a `MEMORY_MARKER` for idempotent injection (same pattern as skills). Memory types: `user` (profile/preferences), `feedback` (corrections/confirmations), `project` (context), `reference` (external pointers). REPL provides `/memory list|show|search|forget|stats` commands.

## Provider API

Providers must implement `LLMProvider` protocol:
- `complete(messages: list[dict], tools: list[dict] | None = None) -> LLMResponse`
- `get_name() -> str`

**`OpenAICompatibleProvider`** (`providers/openai_compat.py`) is the base class for OpenAI-compatible APIs. Handles message conversion (`_convert_messages`), HTTP requests, and response parsing (`_parse_response`). Deepseek and OpenAI providers inherit from it.

**MiniMax provider** (`providers/minimax.py`) uses raw httpx with its own message conversion and refusal detection (skips tool_calls when content contains refusal language).
