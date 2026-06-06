"""Tests for the 3 built-in specialists (merged per Q14)."""
from __future__ import annotations

import json

import pytest

from agents.specialists.doc_reader import DocReaderSpecialist
from agents.specialists.planner import PlannerSpecialist
from agents.specialists.triage import TriageSpecialist


# --- Identity / contract ---

@pytest.mark.parametrize("cls,expected_name", [
    (DocReaderSpecialist, "doc_reader"),
    (TriageSpecialist, "triage"),
    (PlannerSpecialist, "planner"),
])
def test_name_matches_class(cls, expected_name):
    assert cls().name == expected_name


def test_all_have_unique_names():
    names = {DocReaderSpecialist().name, TriageSpecialist().name, PlannerSpecialist().name}
    assert len(names) == 3


# --- Defaults ---

def test_doc_reader_defaults():
    sp = DocReaderSpecialist()
    assert sp.default_max_iterations == 5
    assert sp.default_timeout_seconds == 60
    assert "read_file" in sp.default_allowed_tools


def test_triage_defaults():
    sp = TriageSpecialist()
    assert sp.default_max_iterations == 2
    assert sp.default_timeout_seconds == 30
    assert "read_file" in sp.default_allowed_tools
    assert sp.default_provider == "deepseek"
    assert "deepseek" in sp.default_model


def test_planner_defaults():
    sp = PlannerSpecialist()
    assert sp.default_max_iterations == 8
    assert sp.default_timeout_seconds == 120
    assert "learning_path" in sp.default_allowed_tools


# --- System prompt renders (Decision 14: no brittle keyword tests) ---

def test_doc_reader_system_prompt_renders():
    sp = DocReaderSpecialist()
    rendered = sp.system_prompt_template.format(
        specialist_name=sp.name, task="summarize x", allowed_tools="read_file"
    )
    assert "doc_reader" in rendered
    assert "summarize x" in rendered
    # No memory / no delegation contract hint
    assert "memory" in rendered.lower() or "no memory" in rendered.lower()
    assert "delegate" in rendered.lower()


def test_triage_system_prompt_renders():
    sp = TriageSpecialist()
    rendered = sp.system_prompt_template.format(
        specialist_name=sp.name, task="classify this", allowed_tools="read_file"
    )
    assert "triage" in rendered
    assert "JSON" in rendered or "json" in rendered
    # Output contract: the 5 fields
    for field in ("task_type", "recommended_specialist", "confidence", "reason", "should_delegate"):
        assert field in rendered


def test_triage_prompt_uses_parenthesized_none_consistently():
    sp = TriageSpecialist()
    rendered = sp.system_prompt_template.format(
        specialist_name=sp.name, task="classify this", allowed_tools="read_file"
    )
    assert "recommended_specialist=(none)" in rendered
    assert "recommended_specialist=none" not in rendered


def test_planner_system_prompt_renders():
    sp = PlannerSpecialist()
    rendered = sp.system_prompt_template.format(
        specialist_name=sp.name, task="make a plan", allowed_tools="learning_path"
    )
    assert "planner" in rendered
    assert "make a plan" in rendered


# --- data_to_content per specialist ---

def test_doc_reader_data_to_content_with_key_points():
    sp = DocReaderSpecialist()
    out = sp.data_to_content(
        {"key_points": ["p1", "p2", "p3"], "source_files": ["a.md"], "char_count": 1200},
        content_cap=2000,
    )
    assert "p1" in out and "p2" in out and "p3" in out
    assert "a.md" in out
    assert "1200" in out


def test_doc_reader_data_to_content_with_empty_dict():
    sp = DocReaderSpecialist()
    out = sp.data_to_content({}, content_cap=2000)
    # Empty input: still returns a string (no exception)
    assert isinstance(out, str)


def test_doc_reader_data_to_content_with_string():
    sp = DocReaderSpecialist()
    out = sp.data_to_content("freeform prose summary", content_cap=2000)
    assert "freeform prose summary" in out


def test_triage_data_to_content_with_full_dict():
    sp = TriageSpecialist()
    out = sp.data_to_content(
        {
            "task_type": "document_summary",
            "recommended_specialist": "doc_reader",
            "confidence": 0.85,
            "reason": "long pasted doc",
            "should_delegate": True,
        },
        content_cap=2000,
    )
    assert "document_summary" in out
    assert "doc_reader" in out
    assert "0.85" in out
    assert "True" in out
    assert "Triage decision" in out


def test_triage_data_to_content_with_json_string():
    """Triage LLM may return JSON as a string; helper parses it."""
    sp = TriageSpecialist()
    raw = json.dumps({
        "task_type": "qa",
        "recommended_specialist": "(none)",
        "confidence": 0.3,
        "reason": "ambiguous",
        "should_delegate": False,
    })
    out = sp.data_to_content(raw, content_cap=2000)
    assert "qa" in out
    assert "ambiguous" in out


def test_triage_data_to_content_accepts_string_confidence():
    sp = TriageSpecialist()
    out = sp.data_to_content(
        {
            "task_type": "qa",
            "recommended_specialist": "(none)",
            "confidence": "0.30",
            "reason": "ambiguous",
            "should_delegate": False,
        },
        content_cap=2000,
    )
    assert "0.30" in out


def test_planner_data_to_content_with_steps():
    sp = PlannerSpecialist()
    out = sp.data_to_content(
        {
            "title": "Learn Transformers in 7 days",
            "steps": [
                {"day": 1, "topic": "Attention mechanism"},
                {"day": 2, "topic": "Self-attention"},
            ],
            "deadline": "2026-06-15",
        },
        content_cap=2000,
    )
    assert "Learn Transformers" in out
    assert "Attention" in out
    assert "Day 1" in out or "1. " in out
    assert "2026-06-15" in out


def test_planner_data_to_content_with_string_steps():
    sp = PlannerSpecialist()
    out = sp.data_to_content(
        {"title": "Plan", "steps": ["step one", "step two"]},
        content_cap=2000,
    )
    assert "Plan" in out
    assert "step one" in out


# --- Content cap is centralized in runner (Q14) ---

def test_data_to_content_does_not_apply_cap():
    """Each specialist's data_to_content returns full formatted text.
    The 2000-char cap is applied by the runner, not the specialist."""
    sp = DocReaderSpecialist()
    huge = {"key_points": ["x" * 3000]}
    out = sp.data_to_content(huge, content_cap=100)
    # Specialist returns the full string; cap is runner's responsibility
    assert len(out) > 100
    assert "x" * 100 in out
