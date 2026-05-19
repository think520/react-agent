import os
import tempfile
import pytest
from core.skills import (
    parse_frontmatter,
    load_skills_from_dir,
    format_skills_for_prompt,
    build_skills_system_prompt,
    SKILLS_PROMPT_MARKER,
    Skill,
)
from core.agent_loop import AgentLoop
from core.session import Session


class MockProvider:
    def complete(self, messages, tools=None):
        from providers.types import LLMResponse
        return LLMResponse(content="ok")

    def get_name(self):
        return "mock"


# --- parse_frontmatter ---

def test_parse_frontmatter_basic():
    content = "---\nname: test\ndescription: desc\n---\nBody here"
    result = parse_frontmatter(content)
    assert result["name"] == "test"
    assert result["description"] == "desc"


def test_parse_frontmatter_no_frontmatter():
    result = parse_frontmatter("No frontmatter here")
    assert result == {}


def test_parse_frontmatter_malformed():
    result = parse_frontmatter("---\nname: test\n")
    assert result == {}


def test_parse_frontmatter_empty():
    result = parse_frontmatter("")
    assert result == {}


# --- load_skills_from_dir ---

def _create_skill(tmpdir, name, description, body="# Skill\nInstructions"):
    skill_dir = os.path.join(tmpdir, name)
    os.makedirs(skill_dir)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {name}\ndescription: \"{description}\"\n---\n\n{body}")
    return skill_dir


def test_load_skills_from_dir_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills = load_skills_from_dir(tmpdir)
        assert skills == []


def test_load_skills_from_dir_nonexistent():
    skills = load_skills_from_dir("/nonexistent/path")
    assert skills == []


def test_load_skills_from_dir_one_skill():
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "weather", "查询天气")
        skills = load_skills_from_dir(tmpdir)
        assert len(skills) == 1
        assert skills[0].name == "weather"
        assert skills[0].description == "查询天气"
        assert skills[0].file_path.endswith("SKILL.md")


def test_load_skills_from_dir_multiple():
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "alpha", "Alpha skill")
        _create_skill(tmpdir, "beta", "Beta skill")
        skills = load_skills_from_dir(tmpdir)
        assert len(skills) == 2
        names = [s.name for s in skills]
        assert names == sorted(names)  # should be sorted


def test_load_skills_skips_missing_frontmatter():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "bad")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("# No frontmatter\nJust body")
        skills = load_skills_from_dir(tmpdir)
        assert skills == []


def test_load_skills_skips_missing_description():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "bad")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\nname: bad\n---\nBody")
        skills = load_skills_from_dir(tmpdir)
        assert skills == []


def test_load_skills_skips_dot_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, ".hidden", "Hidden")
        _create_skill(tmpdir, "visible", "Visible")
        skills = load_skills_from_dir(tmpdir)
        assert len(skills) == 1
        assert skills[0].name == "visible"


def test_load_skills_skips_no_skill_md():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "noskill"))
        with open(os.path.join(tmpdir, "noskill", "readme.txt"), "w") as f:
            f.write("not a skill")
        skills = load_skills_from_dir(tmpdir)
        assert skills == []


# --- format_skills_for_prompt ---

def test_format_skills_empty():
    assert format_skills_for_prompt([]) == ""


def test_format_skills_single():
    skills = [Skill(name="weather", description="查询天气", file_path="/path/SKILL.md", base_dir="/path")]
    result = format_skills_for_prompt(skills)
    assert "<available_skills>" in result
    assert "<name>weather</name>" in result
    assert "<description>查询天气</description>" in result
    assert "<location>/path/SKILL.md</location>" in result
    assert "</available_skills>" in result


def test_format_skills_escapes_xml():
    skills = [Skill(name="a&b", description='c<d "e"', file_path="/p", base_dir="/p")]
    result = format_skills_for_prompt(skills)
    assert "a&amp;b" in result
    assert "c&lt;d &quot;e&quot;" in result


def test_format_skills_multiple():
    skills = [
        Skill(name="a", description="A", file_path="/a/SKILL.md", base_dir="/a"),
        Skill(name="b", description="B", file_path="/b/SKILL.md", base_dir="/b"),
    ]
    result = format_skills_for_prompt(skills)
    assert result.count("<skill>") == 2
    assert result.count("</skill>") == 2


# --- build_skills_system_prompt ---

def test_build_skills_system_prompt_no_skills():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = build_skills_system_prompt(tmpdir)
        assert result is None


def test_build_skills_system_prompt_with_skills():
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "test", "Test skill")
        result = build_skills_system_prompt(tmpdir)
        assert result is not None
        assert "scan the <available_skills>" in result
        assert "<name>test</name>" in result
        assert "read_file" in result


def test_build_skills_prompt_contains_marker():
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "test", "Test skill")
        result = build_skills_system_prompt(tmpdir)
        assert result is not None
        assert SKILLS_PROMPT_MARKER in result


# --- P1-10: Skills injection with existing system messages ---

def test_skills_injected_even_with_existing_system_message():
    """Skills prompt must be injected even when session already has a system message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "test", "Test skill")
        skills_prompt = build_skills_system_prompt(tmpdir)

        session = Session.new("/test")
        session.add_message("system", "You are a helpful assistant.")  # base prompt
        agent = AgentLoop(MockProvider(), session, skills_prompt=skills_prompt)

        agent._inject_skills_prompt()

        system_msgs = [m for m in session.messages if m.get("role") == "system"]
        assert len(system_msgs) == 2
        assert "helpful assistant" in system_msgs[0]["content"]
        assert SKILLS_PROMPT_MARKER in system_msgs[1]["content"]


def test_skills_not_doubly_injected():
    """Skills prompt must not be injected twice if already present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "test", "Test skill")
        skills_prompt = build_skills_system_prompt(tmpdir)

        session = Session.new("/test")
        session.add_message("system", skills_prompt)  # already injected
        agent = AgentLoop(MockProvider(), session, skills_prompt=skills_prompt)

        agent._inject_skills_prompt()
        agent._inject_skills_prompt()  # call again

        system_msgs = [m for m in session.messages if m.get("role") == "system"]
        assert len(system_msgs) == 1


def test_skills_injected_on_restored_session():
    """Skills prompt must be injected when restoring an old session with its own system message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_skill(tmpdir, "test", "Test skill")
        skills_prompt = build_skills_system_prompt(tmpdir)

        # Simulate a restored session with a base system prompt
        session = Session.new("/test")
        session.add_message("system", "You are a coding assistant.")
        session.add_message("user", "hello")
        session.add_message("assistant", "hi there")

        agent = AgentLoop(MockProvider(), session, skills_prompt=skills_prompt)
        agent._inject_skills_prompt()

        system_msgs = [m for m in session.messages if m.get("role") == "system"]
        assert len(system_msgs) == 2
        assert SKILLS_PROMPT_MARKER in system_msgs[1]["content"]


def test_no_injection_without_skills_prompt():
    """No system message added when skills_prompt is None."""
    session = Session.new("/test")
    agent = AgentLoop(MockProvider(), session, skills_prompt=None)
    agent._inject_skills_prompt()
    assert len(session.messages) == 0
