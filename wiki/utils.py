"""Small shared helpers used by the maintained Wiki workflows."""

import re

from core.llm_json import parse_llm_object


def safe_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")
    return safe[:100] if safe else "untitled"


def parse_wiki_json(text: str) -> dict | None:
    return parse_llm_object(text)
