"""Tests for Stage 1 — project context + topic_registry loader."""

import pytest

from backend.services.call_topics_v5.stage_1_context import load_context


class _FakeQuery:
    """Minimal chainable fake mimicking the Supabase client query builder."""

    def __init__(self, response_data):
        self._response = response_data

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        class _R:
            pass
        r = _R()
        r.data = self._response
        return r


class FakeDB:
    """Returns canned responses per table name."""

    def __init__(self, *, projects=None, topic_registry=None):
        self._projects = projects or []
        self._topic_registry = topic_registry or []

    def table(self, name: str):
        if name == "projects":
            return _FakeQuery(self._projects)
        if name == "topic_registry":
            return _FakeQuery(self._topic_registry)
        raise AssertionError(f"unexpected table {name!r}")


def test_loads_project_metadata_and_empty_registry(monkeypatch):
    monkeypatch.setattr(
        "backend.services.call_topics_v5.stage_1_context.get_project_topic_state",
        lambda project_id, db=None: [],
    )
    db = FakeDB(
        projects=[
            {
                "id": "proj-1",
                "name": "SWIB",
                "description": "RAM engagement",
                "context": "weekly cadence",
                "default_llm": "openrouter",
                "default_model": "deepseek/deepseek-v3.2",
            }
        ],
        topic_registry=[],
    )
    out = load_context("proj-1", db=db)
    assert out["project_metadata"]["project_id"] == "proj-1"
    assert out["project_metadata"]["name"] == "SWIB"
    assert out["project_metadata"]["default_llm"] == "openrouter"
    assert out["topic_registry"] == []


def test_loads_populated_registry(monkeypatch):
    fake_topics = [
        {
            "topic_id": "t1", "name": "Stress Testing", "summary": "PA stress test work stream",
            "key_terms": [], "tasks": [], "open_questions": [], "decisions": [], "evidence": [],
            "status": "open", "sentiment": "neutral", "importance": "medium",
            "calls_open": 0, "first_raised_call_id": "call-xyz",
            "chronology_narrative": None, "rag_verification_note": None,
            "latest_update_at": "2026-05-22T10:00:00+00:00",
        },
        {
            "topic_id": "t2", "name": "ARM", "summary": "",
            "key_terms": [], "tasks": [], "open_questions": [], "decisions": [], "evidence": [],
            "status": "open", "sentiment": "neutral", "importance": "medium",
            "calls_open": 0, "first_raised_call_id": None,
            "chronology_narrative": None, "rag_verification_note": None,
            "latest_update_at": "2026-05-22T11:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        "backend.services.call_topics_v5.stage_1_context.get_project_topic_state",
        lambda project_id, db=None: fake_topics,
    )
    db = FakeDB(
        projects=[{"id": "proj-1", "name": "x"}],
        topic_registry=[],
    )
    out = load_context("proj-1", db=db)
    assert len(out["topic_registry"]) == 2
    assert out["topic_registry"][0]["name"] == "Stress Testing"
    assert out["topic_registry"][1]["name"] == "ARM"
    assert out["topic_registry"][1]["approved_by_call_id"] is None


def test_missing_project_raises(monkeypatch):
    monkeypatch.setattr(
        "backend.services.call_topics_v5.stage_1_context.get_project_topic_state",
        lambda project_id, db=None: [],
    )
    db = FakeDB(projects=[], topic_registry=[])
    with pytest.raises(ValueError, match="not found"):
        load_context("nonexistent", db=db)


def test_missing_optional_fields_default_safely(monkeypatch):
    """Project row with None for nullable fields → safe defaults."""
    monkeypatch.setattr(
        "backend.services.call_topics_v5.stage_1_context.get_project_topic_state",
        lambda project_id, db=None: [],
    )
    db = FakeDB(
        projects=[
            {
                "id": "proj-1",
                "name": None,
                "description": None,
                "context": None,
                "default_llm": None,
                "default_model": None,
            }
        ],
        topic_registry=[],
    )
    out = load_context("proj-1", db=db)
    meta = out["project_metadata"]
    assert meta["name"] == ""
    assert meta["description"] == ""
    assert meta["context"] == ""
    # default_llm falls back to "openrouter" (sane default for the v5 pipeline)
    assert meta["default_llm"] == "openrouter"
    assert meta["default_model"] is None


def test_load_context_includes_full_topic_state(monkeypatch):
    """EPIC-18: Stage 1 now loads structured topic state (key_terms + tasks),
    not just registry names."""
    fake_topics = [
        {
            "topic_id": "t-1", "name": "ARM", "summary": "Risk modeling",
            "key_terms": ["LMAC", "Monte Carlo"],
            "tasks": [{"task": "Test LMAC", "owner": "Mark"}],
            "open_questions": [], "decisions": [], "evidence": [],
            "status": "open", "sentiment": "neutral", "importance": "high",
            "calls_open": 2, "first_raised_call_id": "c-1",
            "chronology_narrative": None, "rag_verification_note": None,
            "latest_update_at": "2026-05-20T10:00:00Z",
        },
    ]
    monkeypatch.setattr(
        "backend.services.call_topics_v5.stage_1_context.get_project_topic_state",
        lambda project_id, db=None: fake_topics,
    )
    db = FakeDB(projects=[{
        "id": "proj-1", "name": "P", "description": "", "context": "",
        "default_llm": "openrouter", "default_model": None,
    }])
    out = load_context("proj-1", db=db)
    assert len(out["topic_registry"]) == 1
    entry = out["topic_registry"][0]
    assert entry["name"] == "ARM"
    assert entry["tasks"][0]["task"] == "Test LMAC"
    assert "LMAC" in entry["key_terms"]
