from unittest.mock import MagicMock, patch

from backend.main import app
from starlette.testclient import TestClient

client = TestClient(app)

PROJECT_ID = "proj-abc"
CALL_ID = "call-123"

MOCK_CALL = {
    "id": CALL_ID,
    "project_id": PROJECT_ID,
    "title": "Q1 Review",
    "kanban_stage": "transcript",
    "transcript": None,
    "created_at": "2026-04-09T00:00:00Z",
}

MOCK_CALL_DONE = {**MOCK_CALL, "kanban_stage": "done"}


def _mock_client():
    return MagicMock()


# --- GET /api/projects/{project_id}/calls ---


def test_list_calls_returns_empty():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.get(f"/api/projects/{PROJECT_ID}/calls")
    assert r.status_code == 200
    assert r.json() == []


def test_list_calls_returns_calls():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[MOCK_CALL])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.get(f"/api/projects/{PROJECT_ID}/calls")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Q1 Review"


# --- POST /api/projects/{project_id}/calls ---


def test_post_call_creates_call():
    mc = _mock_client()
    mc.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[MOCK_CALL]
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(
            f"/api/projects/{PROJECT_ID}/calls", json={"title": "Q1 Review"}
        )
    assert r.status_code == 201
    assert r.json()["kanban_stage"] == "transcript"
    assert r.json()["title"] == "Q1 Review"


# --- GET /api/calls/{call_id} ---


def test_get_call_returns_call():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[MOCK_CALL])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.get(f"/api/calls/{CALL_ID}")
    assert r.status_code == 200
    assert r.json()["id"] == CALL_ID


def test_get_call_returns_404_when_missing():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.get("/api/calls/nonexistent")
    assert r.status_code == 404


# --- PATCH /api/calls/{call_id}/stage ---


def test_patch_stage_valid_transition():
    mc = _mock_client()
    # select current stage
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{"kanban_stage": "transcript"}])
    )
    # update returns updated call
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{**MOCK_CALL, "kanban_stage": "artifacts"}])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.patch(f"/api/calls/{CALL_ID}/stage", json={"new_stage": "artifacts"})
    assert r.status_code == 200
    assert r.json()["kanban_stage"] == "artifacts"


def test_patch_stage_rejects_skip():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{"kanban_stage": "transcript"}])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.patch(f"/api/calls/{CALL_ID}/stage", json={"new_stage": "done"})
    assert r.status_code == 422


def test_patch_stage_returns_404_when_call_missing():
    mc = _mock_client()
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.patch(
            "/api/calls/nonexistent/stage", json={"new_stage": "artifacts"}
        )
    assert r.status_code == 404
