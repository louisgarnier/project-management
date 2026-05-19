"""Unit tests for chronology_service.generate_chronology_cell (Story 15.7)."""

import pytest
from unittest.mock import AsyncMock

from backend.services import chronology_service


def _topic_update_row():
    return {
        "id": "row-1",
        "topic_id": "topic-uuid",
        "call_id": "call-uuid",
        "evidence": [{"speaker": "X", "quote": "We confirmed Y.", "citation": "transcript 2026-05-19 · lines 10-15"}],
        "tasks": [], "open_questions": [], "decisions": [],
    }


def _library_rows():
    return [
        {"id": "ln1", "name": "Chronology Narrative", "prompt": "NARRATIVE_PROMPT", "llm": "openrouter", "model": "deepseek/deepseek-v3.2", "category": "chronology", "seeded_by_default": True},
        {"id": "ln2", "name": "RAG Verification", "prompt": "RAG_PROMPT", "llm": "openrouter", "model": "deepseek/deepseek-v3.2", "category": "chronology", "seeded_by_default": True},
    ]


class _FakeTable:
    def __init__(self, store, name):
        self._store, self.name = store, name
        self._eq = {}

    def select(self, _cols):
        return self

    def eq(self, k, v):
        self._eq[k] = v
        return self

    def update(self, payload):
        # Find matching row and mutate in-place
        for r in self._store.get(self.name, []):
            if all(r.get(k) == v for k, v in self._eq.items()):
                r.update(payload)
        return self

    def execute(self):
        rows = self._store.get(self.name, [])
        for k, v in self._eq.items():
            rows = [r for r in rows if r.get(k) == v]
        return type("R", (), {"data": rows})()


class _FakeDB:
    def __init__(self, store):
        self._store = store

    def table(self, name):
        return _FakeTable(self._store, name)


@pytest.mark.asyncio
async def test_chronology_narrative_truncated_at_600_chars(monkeypatch):
    """Misbehaving model returns 900 chars; service truncates to 600."""
    store = {
        "topic_updates": [_topic_update_row()],
        "artifact_library": _library_rows(),
    }
    db = _FakeDB(store)
    long_text = "x" * 900
    monkeypatch.setattr(
        chronology_service, "call_llm_raw",
        AsyncMock(side_effect=[long_text, "verified"]),
    )
    n, r = await chronology_service.generate_chronology_cell("topic-uuid", "call-uuid", db)
    assert len(n) == 600
    assert n == "x" * 600
    assert r == "verified"


@pytest.mark.asyncio
async def test_chronology_llm_failure_persists_marker(monkeypatch):
    """LLM raises → service catches, persists '' + '(generation failed: ...)'."""
    store = {
        "topic_updates": [_topic_update_row()],
        "artifact_library": _library_rows(),
    }
    db = _FakeDB(store)
    monkeypatch.setattr(
        chronology_service, "call_llm_raw",
        AsyncMock(side_effect=RuntimeError("API down")),
    )
    n, r = await chronology_service.generate_chronology_cell("topic-uuid", "call-uuid", db)
    assert n == ""
    assert "generation failed" in r
    # Verify it was persisted in store
    assert store["topic_updates"][0]["chronology_narrative"] == ""
    assert "generation failed" in store["topic_updates"][0]["rag_verification_note"]


@pytest.mark.asyncio
async def test_chronology_rag_drift_persisted_verbatim(monkeypatch):
    store = {
        "topic_updates": [_topic_update_row()],
        "artifact_library": _library_rows(),
    }
    db = _FakeDB(store)
    drift = "2026-05-01 narrative claims memory ceiling fixed but transcript does not contain that"
    monkeypatch.setattr(
        chronology_service, "call_llm_raw",
        AsyncMock(side_effect=["A short narrative.", drift]),
    )
    n, r = await chronology_service.generate_chronology_cell("topic-uuid", "call-uuid", db)
    assert n == "A short narrative."
    assert r == drift
    assert store["topic_updates"][0]["rag_verification_note"] == drift


@pytest.mark.asyncio
async def test_chronology_skips_when_row_absent():
    """topic_updates row doesn't exist → returns (None, None) without LLM calls."""
    store = {"topic_updates": [], "artifact_library": _library_rows()}
    db = _FakeDB(store)
    n, r = await chronology_service.generate_chronology_cell("topic-uuid", "call-uuid", db)
    assert n is None
    assert r is None
