"""Unit tests for the context-assembly seam (Story 15.6)."""

import pytest

from backend.services import artifact_generation


class _FakeTable:
    def __init__(self, name, store):
        self.name = name
        self._store = store
        self._filters = {}

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def order(self, *_args, **_kw):
        return self

    def execute(self):
        rows = self._store.get(self.name, [])
        for k, v in self._filters.items():
            rows = [r for r in rows if r.get(k) == v]
        return type("R", (), {"data": rows})()


class _FakeDB:
    def __init__(self, store: dict[str, list[dict]]):
        self._store = store

    def table(self, name: str):
        return _FakeTable(name, self._store)


def test_assemble_context_this_call_transcript():
    db = _FakeDB({
        "calls": [{"id": "c1", "transcript": "Hello world.", "project_id": "p1"}],
    })
    result = artifact_generation._assemble_context("this_call_transcript", "c1", "p1", db)
    assert "Hello world." in result


def test_assemble_context_all_call_transcripts_includes_current_and_prior_chronological():
    db = _FakeDB({
        "calls": [
            {"id": "c1", "transcript": "T1", "project_id": "p1", "created_at": "2026-05-01"},
            {"id": "c2", "transcript": "T2", "project_id": "p1", "created_at": "2026-05-02"},
            {"id": "c3", "transcript": "T3", "project_id": "p1", "created_at": "2026-05-03"},
        ],
    })
    result = artifact_generation._assemble_context("all_call_transcripts", "c3", "p1", db)
    assert "T1" in result and "T2" in result and "T3" in result
    assert result.index("T1") < result.index("T2") < result.index("T3")


def test_assemble_context_this_call_topics(monkeypatch):
    """Reads via list_call_topics (mocked); renders as structured text."""
    fake_topics = [
        {
            "name": "Topic A",
            "key_terms": ["x", "y"],
            "tasks": [{"task": "T", "next_step": "N", "owner": "O", "status": "open"}],
            "open_questions": [{"text": "Q?"}],
            "decisions": [{"text": "D"}],
        },
    ]
    monkeypatch.setattr(
        artifact_generation, "list_call_topics",
        lambda _call_id, _db=None: fake_topics
    )
    result = artifact_generation._assemble_context("this_call_topics", "c1", "p1", db=None)
    assert "Topic A" in result
    assert "Q?" in result
    assert "D" in result


def test_assemble_context_all_project_topics(monkeypatch):
    """Reads via list_project_topics (mocked); renders chronology cells if present."""
    fake_project_topics = [
        {
            "name": "Topic B",
            "calls": [
                {"call_date": "2026-05-01", "chronology_narrative": "X happened.", "tasks": []},
            ],
        }
    ]
    monkeypatch.setattr(
        artifact_generation, "list_project_topics",
        lambda _project_id, _db=None: fake_project_topics
    )
    result = artifact_generation._assemble_context("all_project_topics", "c1", "p1", db=None)
    assert "Topic B" in result
    assert "X happened." in result


def test_assemble_context_unknown_scope_raises():
    with pytest.raises(ValueError, match="unknown.*scope"):
        artifact_generation._assemble_context("invalid_scope", "c1", "p1", db=None)
