"""EPIC-18 — Tests for unified project_topic_state read API."""
from unittest.mock import MagicMock
from backend.services.project_topic_state import get_project_topic_state, ProjectTopic


def _fake_db_with_view_rows(rows):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = rows
    return db


def test_returns_empty_list_for_no_topics():
    db = _fake_db_with_view_rows([])
    state = get_project_topic_state("proj-1", db=db)
    assert state == []


def test_maps_view_row_to_project_topic_shape():
    row = {
        "topic_id": "t-1", "project_id": "proj-1", "name": "ARM",
        "calls_open": 2, "first_raised_call_id": "c-1", "archived": False,
        "summary": "Account risk modeling", "status": "open",
        "sentiment": "neutral", "importance": "high", "evidence": [],
        "key_terms": ["LMAC", "Monte Carlo"], "tasks": [
            {"task": "Test LMAC vs Monte Carlo Mac", "key_terms": ["LMAC", "Monte Carlo"], "owner": "Mark"}
        ],
        "open_questions": [], "decisions": [],
        "chronology_narrative": None, "rag_verification_note": None,
        "latest_update_at": "2026-05-20T10:00:00Z",
    }
    db = _fake_db_with_view_rows([row])
    state = get_project_topic_state("proj-1", db=db)
    assert len(state) == 1
    t = state[0]
    assert t["topic_id"] == "t-1"
    assert t["name"] == "ARM"
    assert t["tasks"][0]["task"] == "Test LMAC vs Monte Carlo Mac"
    assert t["key_terms"] == ["LMAC", "Monte Carlo"]


def test_filters_by_project_id():
    db = _fake_db_with_view_rows([])
    get_project_topic_state("proj-1", db=db)
    db.table.assert_called_with("project_topic_state")
    db.table.return_value.select.return_value.eq.assert_called_with("project_id", "proj-1")
