---
name: course-learning
description: Use RAG and knowledge graph tools to answer course-learning questions with sources and related concepts.
---

# Course Learning Assistant

Use this skill when the user asks about course materials, Obsidian notes, concepts, prerequisites, or learning order.

## Tool choice

- For "是什么", definitions, explanations, summaries, or "在哪里出现过", call `rag_search` first.
- For "和谁有关", tags, source notes, course/chapter placement, or concept relationships, call `graph_query` first.
- For mixed questions, call both `rag_search` and `graph_query`, then separate textual evidence from graph relationships.
- If the user says they added or changed notes, call `obsidian_sync` before searching.

## Answer style

- Always cite sources from `rag_search` when using retrieved text.
- When graph and retrieved text disagree, state the difference instead of forcing one answer.
- Keep answers study-oriented: define the concept, show where it appears, then list related concepts or next steps.
