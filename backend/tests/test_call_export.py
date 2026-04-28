"""Tests for GET /api/calls/{id}/export — single-call markdown recap.

Built 2026-04-28 alongside the export feature. Locks down the response
shape (markdown body + attachment headers + 404 when call missing) so
the format stays stable for whatever consumes it (email, file save, etc.).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.main import app
from starlette.testclient import TestClient

client = TestClient(app)

CALL_ID = "call-export-1"
PROJECT_ID = "proj-export-1"


def _mk_db_returning(call_row, project_row, sibling_calls, artifacts, type_rows):
    """Build a Supabase MagicMock that responds to the chain of .table()/.select()
    /.eq()/.in_()/.order()/.execute() calls used by build_call_export."""
    db = MagicMock()

    def table_side(name):
        t = MagicMock()
        if name == "calls":
            # Two distinct chains:
            #   .select(...).eq("id", call_id).execute()  → call_row
            #   .select(...).eq("project_id", pid).order().execute()  → sibling_calls
            select = t.select.return_value
            select.eq.return_value.execute.return_value = MagicMock(data=call_row)
            select.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=sibling_calls
            )
            return t
        if name == "projects":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=project_row
            )
            return t
        if name == "artifacts":
            t.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value = MagicMock(
                data=artifacts
            )
            return t
        if name == "artifact_types":
            t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                data=type_rows
            )
            return t
        return t

    db.table.side_effect = table_side
    return db


def test_export_404_when_call_missing():
    db = _mk_db_returning(call_row=[], project_row=[], sibling_calls=[], artifacts=[], type_rows=[])
    with patch("backend.services.export_service.get_client", return_value=db), \
         patch("backend.services.export_service.list_call_topics",
               new=AsyncMock(return_value=[])):
        r = client.get(f"/api/calls/{CALL_ID}/export")
    assert r.status_code == 404
    assert r.json()["detail"] == "Call not found"


def test_export_returns_markdown_with_attachment_headers():
    call_row = [{
        "id": CALL_ID,
        "title": "Kickoff",
        "project_id": PROJECT_ID,
        "kanban_stage": "done",
        "created_at": "2026-04-08T00:00:00+00:00",
    }]
    project_row = [{"id": PROJECT_ID, "name": "RAM Project", "context": "Long-term context."}]
    sibling_calls = [{"id": CALL_ID, "created_at": "2026-04-08T00:00:00+00:00"}]
    artifacts: list[dict] = []
    type_rows: list[dict] = []

    db = _mk_db_returning(
        call_row=call_row,
        project_row=project_row,
        sibling_calls=sibling_calls,
        artifacts=artifacts,
        type_rows=type_rows,
    )

    topics = [{
        "name": "Risk Model Selection",
        "summary": "Team weighing LMAC vs Monte Carlo Mac.",
        "follow_up_items": ["Nick: run benchmark"],
        "decisions": ["Phase 2 gated on benchmark"],
        "open_questions": ["Does memory boost help?"],
        "status": "open",
        "owner": "Us",
        "sentiment": "concern",
        "is_parked": False,
        "importance": "high",
        "rationale": "All 4 criteria met",
    }]

    with patch("backend.services.export_service.get_client", return_value=db), \
         patch("backend.services.export_service.list_call_topics",
               new=AsyncMock(return_value=topics)):
        r = client.get(f"/api/calls/{CALL_ID}/export")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment;")
    # Filename uses slugified project name + call number + ISO date
    assert "ram-project-call-1-2026-04-08" in cd
    body = r.text
    # Header reflects project + call meta
    assert "# RAM Project — Call 1: Kickoff" in body
    assert "**Project:** RAM Project" in body
    assert "**Date:** 2026-04-08" in body
    # Project context surfaces
    assert "## Project context" in body
    assert "Long-term context." in body
    # Topic section + every anchor list rendered
    assert "## Topics discussed (1)" in body
    assert "### Risk Model Selection" in body
    assert "Phase 2 gated on benchmark" in body
    assert "Nick: run benchmark" in body
    assert "Does memory boost help?" in body
    # Empty artifacts section still rendered
    assert "## Artifacts (0)" in body
    assert "_No artifacts generated for this call._" in body


def test_export_renders_artifacts_with_type_names():
    call_row = [{
        "id": CALL_ID,
        "title": "Working Session",
        "project_id": PROJECT_ID,
        "kanban_stage": "done",
        "created_at": "2026-04-15T12:00:00+00:00",
    }]
    project_row = [{"id": PROJECT_ID, "name": "Alpha", "context": ""}]
    sibling_calls = [
        {"id": "older-call", "created_at": "2026-04-01T00:00:00+00:00"},
        {"id": CALL_ID,      "created_at": "2026-04-15T12:00:00+00:00"},
    ]
    artifacts = [
        {"id": "a1", "artifact_type_id": "t1", "status": "done", "mode": "openrouter",
         "content": "## Next Steps\n- Do thing"},
        {"id": "a2", "artifact_type_id": "t2", "status": "done", "mode": "manual",
         "content": "Risk: foo"},
    ]
    type_rows = [
        {"id": "t1", "name": "Email Summary"},
        {"id": "t2", "name": "Risk Register"},
    ]

    db = _mk_db_returning(call_row, project_row, sibling_calls, artifacts, type_rows)

    with patch("backend.services.export_service.get_client", return_value=db), \
         patch("backend.services.export_service.list_call_topics",
               new=AsyncMock(return_value=[])):
        r = client.get(f"/api/calls/{CALL_ID}/export")

    assert r.status_code == 200
    body = r.text
    # This is the second call in the project chronologically → call number 2
    assert "Call 2:" in body
    assert "## Artifacts (2)" in body
    assert "### Email Summary" in body
    assert "### Risk Register" in body
    assert "## Next Steps\n- Do thing" in body
    assert "Risk: foo" in body
    # No project context section when context is blank
    assert "## Project context" not in body
