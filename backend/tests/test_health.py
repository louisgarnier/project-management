from httpx import Client
from starlette.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "db" in body


def test_health_db_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["db"] == "not_configured"
