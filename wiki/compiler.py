"""Wiki compiler — reads source documents, LLM extracts entities/concepts, writes wiki pages.

This is the 'compilation layer' that transforms raw source documents into
structured, interlinked wiki pages. It is NOT a parallel knowledge base —
wiki pages are LLM-generated 'compiled results' from source materials.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

import yaml

from .schema import (
    WikiPage, CompileResult, WikiConfig,
    load_wiki_state, save_wiki_state,
    PAGE_TYPES, FM_SOURCE_HASH,
)

logger = logging.getLogger(__name__)

# LLM prompt for extracting entities and concepts from source documents
EXTRACT_PROMPT = """你是一个知识库编辑。请阅读以下资料，提取关键信息。

资料标题：{title}
资料路径：{path}
资料内容：
{content}

请提取并返回 JSON 格式：
{{
  "entities": [
    {{
      "name": "实体名称",
      "description": "2-3句简要说明",
      "tags": ["标签1", "标签2"],
      "related": ["相关概念1", "相关概念2"]
    }}
  ],
  "concepts": [
    {{
      "name": "概念名称",
      "description": "2-3句简要说明",
      "tags": ["标签1", "标签2"],
      "related": ["相关概念1", "相关概念2"]
    }}
  ],
  "summary": "200字以内的核心要点摘要"
}}

要求：
- 实体是具体事物（人物、算法、工具、系统、数据结构等）
- 概念是抽象主题（理论、方法论、设计模式、原则等）
- 每个实体和概念都要有相关关系（用名称列表表示）
- 标签用小写英文或中文
- 只返回 JSON，不要其他文字"""


def _content_hash(content: str) -> str:
    """SHA-256 hash of file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _safe_filename(name: str) -> str:
    """Convert a title to a safe filename."""
    # Remove or replace unsafe characters
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe = safe.strip('. ')
    return safe[:100] if safe else "untitled"


def _parse_llm_json(text: str) -> dict | None:
    """Extract JSON from LLM response. Handles markdown fences and extra text."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown fences
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    start = text.find("{")
    if start == -1:
        return None

    # Bracket-depth tracking
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class WikiCompiler:
    """Compiles source documents into structured wiki pages using LLM."""

    def __init__(self, workspace: str, vault_path: str,
                 llm_provider=None, config: WikiConfig | None = None):
        self.workspace = workspace
        self.vault_path = vault_path
        self.config = config or WikiConfig()
        self.llm = llm_provider

    def _ensure_dirs(self) -> None:
        """Create wiki directory structure if it doesn't exist."""
        for path in [
            self.config.entities_path(self.vault_path),
            self.config.concepts_path(self.vault_path),
        ]:
            os.makedirs(path, exist_ok=True)

    def _get_llm(self):
        """Get LLM provider, lazy-loading from config if needed."""
        if self.llm:
            return self.llm
        try:
            from providers.factory import ProviderFactory
            self.llm = ProviderFactory.create_from_config()
            return self.llm
        except Exception as e:
            logger.warning("Could not load LLM provider: %s", e)
            return None

    def _call_llm(self, prompt: str) -> str:
        """Call LLM and return response content."""
        llm = self._get_llm()
        if not llm:
            return ""
        try:
            response = llm.complete([{"role": "user", "content": prompt}])
            return response.content or ""
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return ""

    def compile_source(self, source_path: str, force: bool = False) -> CompileResult:
        """Compile a single source file into wiki pages.

        Args:
            source_path: Path to source file (absolute or relative to workspace).
            force: If True, recompile even if source hasn't changed.

        Returns:
            CompileResult with generated pages.
        """
        result = CompileResult()
        self._ensure_dirs()

        # Resolve and read source file
        if not os.path.isabs(source_path):
            source_path = os.path.join(self.workspace, source_path)
        if not os.path.exists(source_path):
            result.errors.append({"source": source_path, "error": "File not found"})
            return result

        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

        hash_val = _content_hash(content)

        # Check if source has changed (incremental)
        state = load_wiki_state(self.vault_path, self.config)
        if not force and state.get("sources", {}).get(source_path) == hash_val:
            result.skipped.append(source_path)
            return result

        # Parse source
        try:
            from obsidian.parser import parse_markdown_note
            note = parse_markdown_note(content, source_path)
            title = note.title or os.path.basename(source_path)
        except Exception:
            title = os.path.basename(source_path)
            note = None

        # Call LLM to extract entities and concepts
        body = note.body if note else content
        prompt = EXTRACT_PROMPT.format(
            title=title,
            path=source_path,
            content=body[:4000],  # Cap content length
        )
        llm_response = self._call_llm(prompt)

        if not llm_response:
            # No LLM — track source in registry only, no wiki pages
            result.sources_count += 1
            return result

        # Parse LLM response
        extracted = _parse_llm_json(llm_response)
        if not extracted:
            logger.warning("Failed to parse LLM response as JSON")
            result.sources_count += 1
            return result

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Generate entity pages
        for entity in extracted.get("entities", []):
            name = entity.get("name", "").strip()
            if not name:
                continue
            desc = entity.get("description", "")
            tags = entity.get("tags", [])
            related = entity.get("related", [])

            links_section = ""
            if related:
                links_section = "\n\n## 相关概念\n" + "\n".join(f"- [[{r}]]" for r in related)

            page = WikiPage(
                title=name,
                page_type="wiki_entity",
                content=f"{desc}{links_section}",
                tags=tags,
                sources=[source_path],
                links=related,
                source_hash=hash_val,
                created=now,
            )
            result.pages.append(page)
            result.entities_count += 1

        # Generate concept pages
        for concept in extracted.get("concepts", []):
            name = concept.get("name", "").strip()
            if not name:
                continue
            desc = concept.get("description", "")
            tags = concept.get("tags", [])
            related = concept.get("related", [])

            links_section = ""
            if related:
                links_section = "\n\n## 相关概念\n" + "\n".join(f"- [[{r}]]" for r in related)

            page = WikiPage(
                title=name,
                page_type="wiki_concept",
                content=f"{desc}{links_section}",
                tags=tags,
                sources=[source_path],
                links=related,
                source_hash=hash_val,
                created=now,
            )
            result.pages.append(page)
            result.concepts_count += 1

        result.sources_count += 1
        return result

    def write_pages(self, result: CompileResult) -> list[str]:
        """Write compiled wiki pages to vault directory.

        Returns list of written file paths.
        """
        self._ensure_dirs()
        written = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for page in result.pages:
            if page.page_type == "wiki_entity":
                dir_path = self.config.entities_path(self.vault_path)
            elif page.page_type == "wiki_concept":
                dir_path = self.config.concepts_path(self.vault_path)
            else:
                continue  # skip unknown types

            filename = _safe_filename(page.title) + ".md"
            filepath = os.path.join(dir_path, filename)

            # Check if page already exists — preserve created date
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        existing = f.read()
                    if existing.startswith("---"):
                        end = existing.find("---", 3)
                        if end != -1:
                            meta = yaml.safe_load(existing[3:end])
                            if meta and meta.get("created"):
                                page.created = meta["created"]
                except Exception:
                    pass

            page.updated = now
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(page.to_markdown())
            written.append(filepath)

        return written

    def update_state(self, result: CompileResult) -> None:
        """Update wiki state with new source hashes."""
        state = load_wiki_state(self.vault_path, self.config)
        if "sources" not in state:
            state["sources"] = {}

        for page in result.pages:
            for source in page.sources:
                if page.source_hash:
                    state["sources"][source] = page.source_hash

        state["last_compile"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_wiki_state(self.vault_path, state, self.config)

    def update_registry(self, source_path: str, hash_val: str, result: CompileResult) -> None:
        """Update source registry with compiled source info."""
        from .schema import load_source_registry, save_source_registry
        registry = load_source_registry(self.vault_path, self.config)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        page_titles = [p.title for p in result.pages]
        registry[source_path] = {
            "hash": hash_val,
            "pages": page_titles,
            "entities": result.entities_count,
            "concepts": result.concepts_count,
            "updated": now,
        }
        save_source_registry(self.vault_path, registry, self.config)

    def compile_and_write(self, source_path: str, force: bool = False) -> CompileResult:
        """Full pipeline: compile source → write pages → update state → update index/log."""
        result = self.compile_source(source_path, force=force)

        # Update registry regardless of whether pages were generated
        if result.sources_count > 0:
            hash_val = ""
            for page in result.pages:
                if page.source_hash:
                    hash_val = page.source_hash
                    break
            if not hash_val and os.path.exists(source_path):
                with open(source_path, "r", encoding="utf-8") as f:
                    hash_val = _content_hash(f.read())
            self.update_registry(source_path, hash_val, result)

        if result.pages:
            self.write_pages(result)
            self.update_state(result)

            # Update index and log
            try:
                from .index import WikiIndexer
                indexer = WikiIndexer(self.vault_path, self.config)
                indexer.update_index(result.pages)
                indexer.append_log("ingest", source_path, result)
            except Exception as e:
                logger.warning("Failed to update wiki index/log: %s", e)

        return result

    def compile_batch(self, source_paths: list[str], force: bool = False) -> CompileResult:
        """Compile multiple source files."""
        combined = CompileResult()
        for path in source_paths:
            result = self.compile_and_write(path, force=force)
            combined.pages.extend(result.pages)
            combined.entities_count += result.entities_count
            combined.concepts_count += result.concepts_count
            combined.sources_count += result.sources_count
            combined.errors.extend(result.errors)
            combined.skipped.extend(result.skipped)
        return combined
