from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

PROJECT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
TYPE_ID    = "bbbbbbbb-0000-0000-0000-000000000002"
OTHER_ID   = "cccccccc-0000-0000-0000-000000000003"


def make_type(is_default=False):
    return {
        "id": TYPE_ID,
        "project_id": PROJECT_ID,
        "name": "Test Type",
        "prompt": "Test prompt",
        "is_default": is_default,
        "created_at": "2026-04-12T00:00:00Z",
    }


@patch("backend.routers.artifact_types.get_client")
def test_list_returns_project_types(mock_gc):
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [make_type()]
    mock_gc.return_value = m
    r = client.get(f"/api/projects/{PROJECT_ID}/artifact-types")
    assert r.status_code == 200
    assert len(r.json()) == 1


@patch("backend.routers.artifact_types.get_client")
def test_create_artifact_type(mock_gc):
    m = MagicMock()
    m.table.return_value.insert.return_value.execute.return_value.data = [make_type()]
    mock_gc.return_value = m
    r = client.post(
        f"/api/projects/{PROJECT_ID}/artifact-types",
        json={"name": "Test Type", "prompt": "Test prompt"},
    )
    assert r.status_code == 201


@patch("backend.routers.artifact_types.get_client")
def test_update_artifact_type(mock_gc):
    m = MagicMock()
    updated = {**make_type(), "prompt": "New prompt"}
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [make_type()]
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
    mock_gc.return_value = m
    r = client.patch(
        f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}",
        json={"prompt": "New prompt"},
    )
    assert r.status_code == 200
    assert r.json()["prompt"] == "New prompt"


@patch("backend.routers.artifact_types.get_client")
def test_delete_custom_type(mock_gc):
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [make_type(is_default=False)]
    m.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [make_type()]
    mock_gc.return_value = m
    r = client.delete(f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}")
    assert r.status_code == 204


@patch("backend.routers.artifact_types.get_client")
def test_delete_default_type_forbidden(mock_gc):
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [make_type(is_default=True)]
    mock_gc.return_value = m
    r = client.delete(f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}")
    assert r.status_code == 403


@patch("backend.routers.artifact_types.get_client")
def test_delete_not_found(mock_gc):
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_gc.return_value = m
    r = client.delete(f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}")
    assert r.status_code == 404


@patch("backend.routers.artifact_types.get_client")
def test_import_artifact_types(mock_gc):
    m = MagicMock()
    source = [{"name": "Imported Type", "prompt": "Imported prompt"}]
    m.table.return_value.select.return_value.in_.return_value.execute.return_value.data = source
    m.table.return_value.insert.return_value.execute.return_value.data = [make_type()]
    mock_gc.return_value = m
    r = client.post(
        f"/api/projects/{PROJECT_ID}/artifact-types/import",
        json={"type_ids": [OTHER_ID]},
    )
    assert r.status_code == 201
    assert len(r.json()) == 1
