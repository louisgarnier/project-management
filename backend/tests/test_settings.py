from unittest.mock import MagicMock, patch


def test_get_system_settings_returns_singleton():
    from fastapi.testclient import TestClient
    from backend.main import app

    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": 1,
            "default_llm": "openrouter",
            "default_model": "deepseek/deepseek-v3.2",
        }
    ]
    with patch("backend.routers.settings.get_client", return_value=m):
        client = TestClient(app)
        resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["default_llm"] == "openrouter"


def test_patch_system_settings_updates():
    from fastapi.testclient import TestClient
    from backend.main import app

    m = MagicMock()
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": 1,
            "default_llm": "openrouter",
            "default_model": "anthropic/claude-sonnet-4.6",
        }
    ]
    with patch("backend.routers.settings.get_client", return_value=m):
        client = TestClient(app)
        resp = client.patch(
            "/api/settings", json={"default_model": "anthropic/claude-sonnet-4.6"}
        )
    assert resp.status_code == 200
    assert resp.json()["default_model"] == "anthropic/claude-sonnet-4.6"


def test_patch_system_settings_empty_returns_422():
    from fastapi.testclient import TestClient
    from backend.main import app

    m = MagicMock()
    with patch("backend.routers.settings.get_client", return_value=m):
        client = TestClient(app)
        resp = client.patch("/api/settings", json={})
    assert resp.status_code == 422
