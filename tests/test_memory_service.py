"""Tests for MemoryService — service layer for permanent memory, daily memory, and promotion."""

import os
import pytest

from core.memory import MemoryManager
from service.memory_service import MemoryService


@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path)


@pytest.fixture
def svc(workspace):
    return MemoryService(workspace)


@pytest.fixture
def manager(workspace):
    return MemoryManager(workspace)


# --- save ---

def test_save(svc):
    result = svc.save("test", "Test entry", "hello world")
    assert result["ok"]
    assert result["name"] == "test"
    assert result["type"] == "user"


def test_save_empty_name(svc):
    result = svc.save("", "desc", "content")
    assert not result["ok"]
    assert "name" in result["error"]


def test_save_empty_content(svc):
    result = svc.save("test", "desc", "")
    assert not result["ok"]
    assert "content" in result["error"]


def test_save_invalid_type_defaults_to_user(svc):
    result = svc.save("test", "desc", "content", entry_type="invalid")
    assert result["ok"]
    assert result["type"] == "user"


# --- recall ---

def test_recall_no_memories(svc):
    result = svc.recall("test query")
    assert result["ok"]
    assert result["results"] == []
    assert result["fallback"] == []


def test_recall_with_fallback(manager, svc):
    manager.save("pref", "User preference", "likes dark mode", "user")
    result = svc.recall("nonexistent query")
    assert result["ok"]
    # Should fall back to listing all entries
    assert len(result["fallback"]) >= 1


# --- list_entries ---

def test_list_entries_empty(svc):
    result = svc.list_entries()
    assert result["ok"]
    assert result["entries"] == []


def test_list_entries_with_data(manager, svc):
    manager.save("a", "desc a", "content a", "user")
    manager.save("b", "desc b", "content b", "project")

    result = svc.list_entries()
    assert result["ok"]
    assert len(result["entries"]) == 2


# --- get_entry ---

def test_get_entry_found(manager, svc):
    manager.save("my-pref", "User preference", "likes dark mode", "user")
    result = svc.get_entry("my-pref")
    assert result["ok"]
    assert result["name"] == "my-pref"
    assert result["content"] == "likes dark mode"
    assert result["type"] == "user"


def test_get_entry_not_found(svc):
    result = svc.get_entry("nonexistent")
    assert not result["ok"]
    assert "not found" in result["error"].lower()


# --- forget ---

def test_forget(manager, svc):
    manager.save("temp", "temporary", "content", "user")
    result = svc.forget("temp")
    assert result["ok"]
    assert result["name"] == "temp"


def test_forget_not_found(svc):
    result = svc.forget("nonexistent")
    assert not result["ok"]
    assert "not found" in result["error"].lower()


# --- daily_save ---

def test_daily_save(svc):
    result = svc.daily_save("Learned about Python decorators", tags=["python"])
    assert result["ok"]
    assert result["path"] is not None
    assert result["date"] is not None


def test_daily_save_empty_content(svc):
    result = svc.daily_save("")
    assert not result["ok"]
    assert "content" in result["error"]


# --- daily_read ---

def test_daily_read_today_empty(svc):
    result = svc.daily_read()
    assert result["ok"]
    assert result["content"] == ""


def test_daily_read_after_save(svc):
    svc.daily_save("Test content")
    result = svc.daily_read()
    assert result["ok"]
    assert "Test content" in result["content"]


def test_daily_read_specific_date(svc):
    result = svc.daily_read(date="2020-01-01")
    assert result["ok"]
    assert result["content"] == ""


# --- get_stats ---

def test_get_stats(manager, svc):
    manager.save("a", "desc", "content", "user")
    result = svc.get_stats()
    assert result["ok"]
    assert result["total"] >= 1


# --- Data contract ---

def test_all_results_have_ok_field(svc, manager):
    manager.save("x", "desc", "content", "user")
    methods = [
        svc.save("y", "desc", "content"),
        svc.recall("test"),
        svc.list_entries(),
        svc.get_entry("x"),
        svc.forget("y"),
        svc.daily_save("text"),
        svc.daily_read(),
        svc.get_stats(),
    ]
    for r in methods:
        assert "ok" in r, f"Missing 'ok' in {r}"
