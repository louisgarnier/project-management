from unittest.mock import MagicMock, patch

from backend.main import app
from starlette.testclient import TestClient

client = TestClient(app)

MOCK_PROJECT = {
    "id": "abc-123",
    "name": "Test Project",
    "description": "A test project",
    "created_at": "2026-04-09T00:00:00Z",
}


def _mock_client(data=None):
    mock = MagicMock()
    mock.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=data if data is not None else []
    )
    mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=data if data is not None else []
    )
    mock.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=data if data is not None else [])
    )
    return mock


def test_get_projects_returns_empty_list():
    with patch(
        "backend.routers.projects.get_client", return_value=_mock_client(data=[])
    ):
        response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_get_projects_returns_list():
    with patch(
        "backend.routers.projects.get_client",
        return_value=_mock_client(data=[MOCK_PROJECT]),
    ):
        response = client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Project"


def test_post_project_creates_and_returns_project():
    with (
        patch(
            "backend.routers.projects.get_client",
            return_value=_mock_client(data=[MOCK_PROJECT]),
        ),
        patch(
            "backend.routers.artifact_types.get_client",
            return_value=_mock_client(data=[]),
        ),
    ):
        response = client.post(
            "/api/projects",
            json={"name": "Test Project", "description": "A test project"},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "abc-123"
    assert body["name"] == "Test Project"


def test_delete_project_returns_204():
    with patch(
        "backend.routers.projects.get_client",
        return_value=_mock_client(data=[MOCK_PROJECT]),
    ):
        response = client.delete("/api/projects/abc-123")
    assert response.status_code == 204


def test_delete_nonexistent_project_returns_404():
    with patch(
        "backend.routers.projects.get_client", return_value=_mock_client(data=[])
    ):
        response = client.delete("/api/projects/nonexistent-id")
    assert response.status_code == 404


@patch("backend.routers.projects.get_client")
def test_get_project_by_id(mock_gc):
    """GET /api/projects/{id} returns the project."""
    from uuid import uuid4

    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": project_id,
            "name": "Test",
            "description": "",
            "default_llm": "groq",
            "created_at": "2026-01-01",
        }
    ]
    mock_gc.return_value = m
    r = client.get(f"/api/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["id"] == project_id


@patch("backend.routers.projects.get_client")
def test_get_project_not_found(mock_gc):
    """GET /api/projects/{id} returns 404 for unknown project."""
    from uuid import uuid4

    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
        []
    )
    mock_gc.return_value = m
    r = client.get(f"/api/projects/{uuid4()}")
    assert r.status_code == 404


@patch("backend.routers.projects.get_client")
def test_update_project_default_llm(mock_gc):
    """PATCH /api/projects/{id} updates default_llm."""
    from uuid import uuid4

    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": project_id,
            "name": "Test",
            "description": "",
            "default_llm": "claude",
            "created_at": "2026-01-01",
        }
    ]
    mock_gc.return_value = m
    r = client.patch(f"/api/projects/{project_id}", json={"default_llm": "claude"})
    assert r.status_code == 200
    assert r.json()["default_llm"] == "claude"


@patch("backend.routers.projects.get_client")
def test_update_project_invalid_llm(mock_gc):
    """PATCH /api/projects/{id} rejects unknown LLM values."""
    from uuid import uuid4

    mock_gc.return_value = MagicMock()
    r = client.patch(f"/api/projects/{uuid4()}", json={"default_llm": "unknown"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Task 8: default_model propagation tests
# ---------------------------------------------------------------------------


def test_project_update_schema_accepts_default_model():
    """ProjectUpdate Pydantic model accepts default_llm=openrouter and default_model."""
    from backend.routers.projects import ProjectUpdate

    p = ProjectUpdate(
        default_llm="openrouter", default_model="anthropic/claude-sonnet-4.6"
    )
    assert p.default_model == "anthropic/claude-sonnet-4.6"
    assert p.default_llm == "openrouter"


@patch("backend.routers.projects.get_client")
def test_patch_project_accepts_default_model(mock_gc):
    """PATCH /api/projects/{id} with default_model persists the field."""
    from uuid import uuid4

    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": project_id,
            "name": "Test",
            "description": "",
            "default_llm": "openrouter",
            "default_model": "anthropic/claude-sonnet-4.6",
            "created_at": "2026-01-01",
        }
    ]
    mock_gc.return_value = m
    r = client.patch(
        f"/api/projects/{project_id}",
        json={
            "default_llm": "openrouter",
            "default_model": "anthropic/claude-sonnet-4.6",
        },
    )
    assert r.status_code == 200
    assert r.json()["default_model"] == "anthropic/claude-sonnet-4.6"
    assert r.json()["default_llm"] == "openrouter"
    # Verify both fields were sent to the DB
    update_payload = m.table.return_value.update.call_args[0][0]
    assert update_payload["default_model"] == "anthropic/claude-sonnet-4.6"
    assert update_payload["default_llm"] == "openrouter"
