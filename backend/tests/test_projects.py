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
    with patch(
        "backend.routers.projects.get_client",
        return_value=_mock_client(data=[MOCK_PROJECT]),
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
