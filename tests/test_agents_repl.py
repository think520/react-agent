"""Tests for the /specialists REPL command group."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.registry import SpecialistRegistry, InvocationRecord
from agents.specialists.triage import TriageSpecialist
from agents.specialists.doc_reader import DocReaderSpecialist
from agents.specialists.planner import PlannerSpecialist


@pytest.fixture
def repl():
    """Build a minimal REPL with a populated registry."""
    from cli.repl import REPL
    r = REPL.__new__(REPL)
    reg = SpecialistRegistry()
    reg.register(TriageSpecialist())
    reg.register(DocReaderSpecialist())
    reg.register(PlannerSpecialist())
    r.agent_registry = reg
    return r


def test_specialists_in_all_commands():
    from cli.repl import ALL_COMMANDS
    assert "specialists" in ALL_COMMANDS


def test_specialists_in_command_hints():
    from cli.repl import COMMAND_HINTS
    hints = [c for c, _ in COMMAND_HINTS]
    assert "/specialists" in hints
    assert "/specialists status" in hints
    assert "/specialists tools " in hints


def test_list_shows_all_three(repl, capsys):
    repl.handle_specialists_command("")
    out = capsys.readouterr().out
    assert "doc_reader" in out
    assert "triage" in out
    assert "planner" in out
    assert "3/3 enabled" in out


def test_list_shows_disabled_state(repl, capsys):
    # Disable one
    from agents.config import SpecialistConfig
    repl.agent_registry._configs["triage"].enabled = False
    repl.handle_specialists_command("")
    out = capsys.readouterr().out
    assert "2/3 enabled" in out
    assert "disabled" in out


def test_status_no_invocations(repl, capsys):
    repl.handle_specialists_command("status")
    out = capsys.readouterr().out
    assert "No specialist invocations" in out or "yet" in out


def test_status_shows_recent_invocations(repl, capsys):
    repl.agent_registry.record_invocation(
        "triage", ok=True, error_type=None, duration_ms=1500,
        content="decided", model="deepseek-v4-flash",
    )
    repl.agent_registry.record_invocation(
        "doc_reader", ok=False, error_type="timeout", duration_ms=30000,
        content="", model="MiniMax-M2.7",
    )
    repl.handle_specialists_command("status")
    out = capsys.readouterr().out
    assert "triage" in out
    assert "doc_reader" in out
    assert "timeout" in out


def test_tools_shows_effective_set(repl, capsys):
    repl.handle_specialists_command("tools triage")
    out = capsys.readouterr().out
    # triage defaults: read_file + knowledge_status
    assert "read_file" in out
    # The tool list is rendered as `  <name>  <desc>` lines.
    # Extract just the tool names by parsing those lines.
    import re
    tool_names = set()
    for line in out.splitlines():
        # The format string is `  \033[1;38;5;147m  {name}\033[0m  {desc}`
        m = re.search(r"147m  (\w+)", line)
        if m:
            tool_names.add(m.group(1))
    assert "read_file" in tool_names
    assert "knowledge_status" in tool_names
    # delegate_* and memory_* must be excluded from the actual tool list
    assert not any(n.startswith("delegate_") for n in tool_names)
    assert not any(n.startswith("memory_") for n in tool_names)


def test_tools_unknown_specialist(repl, capsys):
    repl.handle_specialists_command("tools bogus")
    out = capsys.readouterr().out
    assert "No specialist named" in out or "bogus" in out


def test_tools_no_arg_shows_usage(repl, capsys):
    repl.handle_specialists_command("tools")
    out = capsys.readouterr().out
    assert "Usage" in out


def test_unknown_subcommand_shows_help(repl, capsys):
    repl.handle_specialists_command("foo")
    out = capsys.readouterr().out
    assert "Unknown" in out
    assert "Specialists" in out or "specialists" in out


def test_no_registry_handles_gracefully(capsys):
    from cli.repl import REPL
    r = REPL.__new__(REPL)
    r.agent_registry = None
    r.handle_specialists_command("")
    out = capsys.readouterr().out
    assert "not initialized" in out.lower()
