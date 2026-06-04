"""Tests for runner.run_specialist — preflight, success, timeout, crash,
contract validation. Covers Invariants 5, 6, 7."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.config import SpecialistConfig
from agents.registry import SpecialistRegistry
from agents.runner import (
    CONTENT_CAP_ERROR,
    CONTENT_CAP_SPECIALIST,
    run_specialist,
)
from agents.specialists.doc_reader import DocReaderSpecialist
from agents.specialists.triage import TriageSpecialist
from agents.specialists.planner import PlannerSpecialist


# --- Fixtures ---

def _build_registry_with(specialist, yaml=None) -> SpecialistRegistry:
    reg = SpecialistRegistry()
    reg.register(specialist, yaml_overrides=yaml)
    return reg


def _mock_session() -> MagicMock:
    s = MagicMock()
    s.cwd = "/tmp"
    s.workspace_root = "/tmp"
    s.max_messages = None
    return s


def _app_config() -> dict:
    return {
        "llm": {
            "providers": {
                "minimax": {
                    "type": "minimax",
                    "base_url": "https://api.minimaxi.com/v1",
                    "api_key_env": "MINIMAX_API_KEY",
                    "model": "MiniMax-M2.7",
                },
                "deepseek": {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "model": "deepseek-v4-flash",
                },
            }
        },
        "agent": {"temperature": 0.7, "timeout": 60, "max_retries": 3},
    }


# --- Preflight errors ---

def test_unknown_specialist_returns_preflight_error():
    reg = _build_registry_with(TriageSpecialist())
    result = run_specialist(reg, "nonexistent", "do thing",
                            _mock_session(), _app_config())
    assert result.ok is False
    assert result.data["error_type"] == "not_found"
    assert "nonexistent" in result.content


def test_disabled_specialist_returns_preflight_error():
    reg = _build_registry_with(TriageSpecialist(), yaml={"enabled": False})
    result = run_specialist(reg, "triage", "classify",
                            _mock_session(), _app_config())
    assert result.ok is False
    assert result.data["error_type"] == "disabled"


# --- Success path ---

def test_success_records_invocation_and_returns_tool_result():
    reg = _build_registry_with(TriageSpecialist())
    # Patch ProviderFactory.create to return a fake provider
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.return_value = '{"task_type": "qa", "recommended_specialist": "(none)", "confidence": 0.3, "reason": "ok", "should_delegate": false}'
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "triage", "is this about a doc?",
                                _mock_session(), _app_config())

    assert result.ok is True
    assert "Triage decision" in result.content
    rec = reg.get_invocation(1)
    assert len(rec) == 1
    assert rec[0].ok is True
    assert rec[0].error_type is None


def test_long_content_truncated_to_2000():
    reg = _build_registry_with(DocReaderSpecialist())
    long_text = "x" * 5000
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        # doc_reader's data_to_content reads 'key_points' from the dict;
        # we pass a dict that has key_points with one huge bullet
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.return_value = '{"key_points": ["' + long_text + '"]}'
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "doc_reader", "summarize x",
                                _mock_session(), _app_config())

    assert result.ok is True
    assert len(result.content) <= CONTENT_CAP_SPECIALIST
    assert result.content.endswith("[...truncated; full result in data.result]")


# --- Timeout (Invariant 5) ---

def test_timeout_returns_error_type_timeout():
    reg = _build_registry_with(TriageSpecialist(), yaml={"timeout_seconds": 1})
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()

        def slow_run():
            import time
            time.sleep(5)
            return "too late"

        mock_loop_instance.run.side_effect = slow_run
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "triage", "anything",
                                _mock_session(), _app_config())

    assert result.ok is False
    assert result.data["error_type"] == "timeout"
    assert "timed out" in result.content.lower()
    # Invariant 9: error content <= 500 chars
    assert len(result.content) <= CONTENT_CAP_ERROR


# --- Crash (Invariant 6) ---

def test_crash_returns_error_type_crash():
    reg = _build_registry_with(TriageSpecialist())
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.side_effect = KeyError("'description'")
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "triage", "anything",
                                _mock_session(), _app_config())

    assert result.ok is False
    assert result.data["error_type"] == "crash"
    assert "KeyError" in result.content
    rec = reg.get_invocation(1)
    assert rec[0].ok is False
    assert rec[0].error_type == "crash"


# --- Triage contract validation (Invariant 7) ---

def test_triage_invalid_recommendation_returns_contract_violation():
    reg = _build_registry_with(TriageSpecialist())
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.return_value = (
            '{"task_type": "qa", "recommended_specialist": "unknown_specialist", '
            '"confidence": 0.9, "reason": "test", "should_delegate": true}'
        )
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "triage", "classify",
                                _mock_session(), _app_config())

    assert result.ok is False
    assert result.data["error_type"] == "contract_violation"
    assert "unknown_specialist" in result.content
    # Invariant: result not used for routing (parent LLM sees the error)
    rec = reg.get_invocation(1)
    assert rec[0].ok is False
    assert rec[0].error_type == "contract_violation"


def test_triage_valid_recommendation_passes():
    reg = _build_registry_with(TriageSpecialist())
    reg.register(DocReaderSpecialist())  # make "doc_reader" a valid recommendation
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.return_value = (
            '{"task_type": "summary", "recommended_specialist": "doc_reader", '
            '"confidence": 0.9, "reason": "long doc", "should_delegate": true}'
        )
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "triage", "classify",
                                _mock_session(), _app_config())

    assert result.ok is True
    assert "doc_reader" in result.content


def test_triage_non_json_output_passes_through():
    """If triage returns prose (no JSON), runner doesn't fail contract validation."""
    reg = _build_registry_with(TriageSpecialist())
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.return_value = "I'm not sure what you mean"
        MockLoop.return_value = mock_loop_instance

        result = run_specialist(reg, "triage", "classify",
                                _mock_session(), _app_config())

    # Non-JSON falls through to data_to_content's str branch; ok=True
    assert result.ok is True


# --- Parent session immutability (Invariant 10) ---

def test_parent_session_messages_never_mutated():
    """Runner must not modify parent_session.messages."""
    reg = _build_registry_with(TriageSpecialist())
    parent = _mock_session()
    parent.messages = [{"role": "user", "content": "hi"}]
    with patch("providers.factory.ProviderFactory.create") as pf_create, \
         patch("agents.runner.AgentLoop") as MockLoop:
        pf_create.return_value = MagicMock(timeout=30)
        mock_loop_instance = MagicMock()
        mock_loop_instance.run.return_value = '{"task_type": "qa", "recommended_specialist": "(none)", "confidence": 0.1, "reason": "x", "should_delegate": false}'
        MockLoop.return_value = mock_loop_instance

        run_specialist(reg, "triage", "anything", parent, _app_config())

    assert parent.messages == [{"role": "user", "content": "hi"}]
