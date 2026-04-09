from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_db_connected_when_supabase_responds(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    with patch("backend.database.supabase_client.get_client", return_value=mock_client):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["db"] == "connected"


def test_health_db_error_when_supabase_raises(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-key")

    with patch("backend.database.supabase_client.get_client", side_effect=Exception("connection refused")):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["db"] == "error"


def test_supabase_client_raises_without_env(monkeypatch):
    from backend.database.supabase_client import get_client

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    # Clear lru_cache so it re-evaluates env vars
    get_client.cache_clear()

    try:
        import pytest
        with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_KEY must be set"):
            get_client()
    finally:
        get_client.cache_clear()
