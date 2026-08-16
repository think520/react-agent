"""Tests for concept edit + relationship creation (TASKS_LIBRARY_REWORK task 4)."""

import pytest

from graph.concept_store import ConceptStore


@pytest.fixture
def store(tmp_path):
    return ConceptStore(str(tmp_path / "concept_graph.db"))


def _seed_two(store):
    a = store.upsert_concept(name="A", level="core", definition="dA")
    b = store.upsert_concept(name="B", level="core", definition="dB")
    return a, b


# --- update_concept ---

def test_update_concept_rename(store):
    a, _ = _seed_two(store)
    updated = store.update_concept(a["concept_id"], name="A2")
    assert updated["concept_id"] == a["concept_id"]
    assert updated["name"] == "A2"
    assert store.get_concept_by_name("A") is None
    assert store.get_concept_by_name("A2")["concept_id"] == a["concept_id"]


def test_update_concept_rename_conflict(store):
    a, _ = _seed_two(store)
    with pytest.raises(ValueError, match="concept_name_conflict"):
        store.update_concept(a["concept_id"], name="B")


def test_update_concept_definition_aliases_note(store):
    a, _ = _seed_two(store)
    updated = store.update_concept(a["concept_id"], definition="new def", aliases=["a1"], note="note")
    assert updated["definition"] == "new def"
    assert updated["aliases"] == ["a1"]
    assert updated["note"] == "note"
    assert updated["concept_id"] == a["concept_id"]
    assert updated["level"] == "core"


def test_update_concept_missing(store):
    with pytest.raises(ValueError, match="concept_not_found"):
        store.update_concept("nope", name="x")


def test_update_concept_no_fields_returns_existing(store):
    a, _ = _seed_two(store)
    result = store.update_concept(a["concept_id"])
    assert result["concept_id"] == a["concept_id"]


# --- create_relationship ---

def test_create_relationship_success(store):
    a, b = _seed_two(store)
    rel = store.create_relationship(a["concept_id"], b["concept_id"], "前置知识", note="n")
    assert rel["from_id"] == a["concept_id"]
    assert rel["to_id"] == b["concept_id"]
    assert rel["rel_type"] == "前置知识"
    assert rel["evidence_level"] == "user"
    assert rel["note"] == "n"


def test_create_relationship_self_loop(store):
    a, _ = _seed_two(store)
    with pytest.raises(ValueError, match="self_relationship"):
        store.create_relationship(a["concept_id"], a["concept_id"], "属于")


def test_create_relationship_duplicate(store):
    a, b = _seed_two(store)
    store.create_relationship(a["concept_id"], b["concept_id"], "属于")
    with pytest.raises(ValueError, match="relationship_exists"):
        store.create_relationship(a["concept_id"], b["concept_id"], "属于")


def test_create_relationship_invalid_type(store):
    a, b = _seed_two(store)
    with pytest.raises(ValueError, match="invalid_rel_type"):
        store.create_relationship(a["concept_id"], b["concept_id"], "非法类型")


def test_create_relationship_missing_concept(store):
    a, _ = _seed_two(store)
    with pytest.raises(ValueError, match="concept_not_found"):
        store.create_relationship(a["concept_id"], "missing", "属于")


def test_create_relationship_custom_user_type(store):
    a, b = _seed_two(store)
    rel = store.create_relationship(a["concept_id"], b["concept_id"], "user:custom")
    assert rel["rel_type"] == "user:custom"


# --- delete_relationship cascades evidence ---

def test_delete_relationship_cascades_evidence(store):
    a, b = _seed_two(store)
    rel = store.create_relationship(a["concept_id"], b["concept_id"], "属于")
    store.add_evidence(rel_id=rel["rel_id"], document_id="doc-1", excerpt="ev")
    assert store.evidence_for_relationship(rel["rel_id"])
    assert store.delete_relationship(rel["rel_id"]) is True
    assert store.evidence_for_relationship(rel["rel_id"]) == []
