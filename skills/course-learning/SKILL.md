---
name: course-learning
description: Use RAG and knowledge graph tools to answer course-learning questions with sources and related concepts.
---

# Course Learning Assistant

Use this skill when the user asks about course materials, Obsidian notes, concepts, prerequisites, or learning order.

## Tool choice

- For "是什么", definitions, explanations, summaries, or "在哪里出现过", call `rag_search` first.
- For "和谁有关" or concept relationships, call `concept_map_query` (reviewed concept map only) — it adds structure but is never source evidence.
- For mixed questions, call both `rag_search` and `concept_map_query`, then separate textual evidence from map relationships.
- If the user says they added or changed notes, call `obsidian_sync` before searching.

## Answer style

- Cite retrieved text with the `[Sxxxxxx]` label shown at the start of each result, copied exactly; never invent labels (a runtime gate rejects unknown ones).
- When the concept map and retrieved text disagree, state the difference instead of forcing one answer.
- Keep answers study-oriented: define the concept, show where it appears, then list related concepts or next steps.
