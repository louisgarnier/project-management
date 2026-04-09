from unittest.mock import MagicMock, patch

from backend.main import app
from starlette.testclient import TestClient

client = TestClient(app)

CALL_ID = "call-123"
PROJECT_ID = "proj-abc"

MOCK_CALL = {
    "id": CALL_ID,
    "project_id": PROJECT_ID,
    "title": "Q1 Review",
    "kanban_stage": "transcript",
    "transcript": None,
    "created_at": "2026-04-09T00:00:00Z",
}


def _mock_client():
    return MagicMock()


def test_submit_transcript_stores_and_advances_to_artifacts():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"kanban_stage": "transcript"}]
    )
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{**MOCK_CALL, "transcript": "Hello world", "kanban_stage": "artifacts"}]
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/transcript",
            json={"transcript": "Hello world"},
        )
    assert r.status_code == 200
    assert r.json()["kanban_stage"] == "artifacts"
    assert r.json()["transcript"] == "Hello world"


def test_submit_transcript_stores_exact_text():
    long_text = "Line one.\nLine two.\n" * 500
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"kanban_stage": "transcript"}]
    )
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{**MOCK_CALL, "transcript": long_text, "kanban_stage": "artifacts"}]
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/transcript",
            json={"transcript": long_text},
        )
    assert r.status_code == 200
    call_kwargs = mc.table.return_value.update.call_args[0][0]
    assert call_kwargs["transcript"] == long_text


def test_submit_transcript_returns_404_when_call_missing():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(
            "/api/calls/nonexistent/transcript",
            json={"transcript": "text"},
        )
    assert r.status_code == 404


def test_submit_transcript_returns_409_when_already_past_transcript_stage():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"kanban_stage": "artifacts"}]
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/transcript",
            json={"transcript": "duplicate submission"},
        )
    assert r.status_code == 409
