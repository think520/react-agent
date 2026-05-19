"""Skills discovery, loading, and prompt formatting."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"


@dataclass
class Skill:
    name: str
    description: str
    file_path: str   # absolute path to SKILL.md
    base_dir: str     # skill directory


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter delimited by --- lines."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def load_skills_from_dir(skills_dir: str) -> list[Skill]:
    """Scan a directory for skill subdirectories containing SKILL.md files."""
    skills = []
    if not os.path.isdir(skills_dir):
        return skills

    for entry in sorted(os.listdir(skills_dir)):
        entry_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith(".") or entry == "__pycache__":
            continue

        skill_md = os.path.join(entry_path, SKILL_FILENAME)
        if not os.path.isfile(skill_md):
            continue

        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            logger.warning("Failed to read %s", skill_md)
            continue

        frontmatter = parse_frontmatter(content)
        name = (frontmatter.get("name") or "").strip()
        description = (frontmatter.get("description") or "").strip()
        if not name or not description:
            logger.warning("Skipping %s: missing name or description in frontmatter", skill_md)
            continue

        skills.append(Skill(
            name=name,
            description=description,
            file_path=os.path.abspath(skill_md),
            base_dir=os.path.abspath(entry_path),
        ))

    return skills


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Format skills as an XML catalog for injection into the system prompt."""
    if not skills:
        return ""

    lines = [
        "",
        "The following skills provide specialized instructions for specific tasks.",
        "Use the read_file tool to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory.",
        "",
        "<available_skills>",
    ]
    for skill in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{_escape_xml(skill.name)}</name>")
        lines.append(f"    <description>{_escape_xml(skill.description)}</description>")
        lines.append(f"    <location>{_escape_xml(skill.file_path)}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


SKILLS_PROMPT_MARKER = "<!-- [skills_prompt] -->"


def build_skills_system_prompt(skills_dir: str) -> Optional[str]:
    """Load skills and return a complete system prompt string, or None if no skills."""
    skills = load_skills_from_dir(skills_dir)
    if not skills:
        return None

    catalog = format_skills_for_prompt(skills)
    return (
        SKILLS_PROMPT_MARKER + "\n"
        "Before replying: scan the <available_skills> <description> entries.\n"
        "- If exactly one skill clearly applies: read its SKILL.md at <location> with read_file, then follow it.\n"
        "- If multiple could apply: choose the most specific one, then read/follow it.\n"
        "- If none clearly apply: do not read any SKILL.md.\n"
        "Constraints: never read more than one skill up front; only read after selecting.\n"
        + catalog
    )


def list_skills(skills_dir: str) -> list[Skill]:
    """Public API to list available skills."""
    return load_skills_from_dir(skills_dir)


def find_skill_by_name(skills_dir: str, name: str) -> Optional[Skill]:
    """Find a skill by name."""
    for skill in load_skills_from_dir(skills_dir):
        if skill.name == name:
            return skill
    return None
