from unittest.mock import MagicMock, patch

from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_list_library_returns_all_entries():
    m = MagicMock()
    m.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
        {
            "id": "1",
            "name": "System A",
            "kind": "llm",
            "is_system": True,
            "seeded_by_default": True,
            "description": "",
            "prompt": "...",
            "template_id": None,
            "llm": "openrouter",
            "model": "anthropic/claude-sonnet-4.6",
            "context_scope": "call",
            "created_at": "2026-04-23T00:00:00+00:00",
        },
        {
            "id": "2",
            "name": "User B",
            "kind": "llm",
            "is_system": False,
            "seeded_by_default": False,
            "description": "",
            "prompt": "...",
            "template_id": None,
            "llm": "openrouter",
            "model": "deepseek/deepseek-chat",
            "context_scope": "call",
            "created_at": "2026-04-23T00:00:00+00:00",
        },
    ]
    with patch("backend.routers.library.get_client", return_value=m):
        resp = client.get("/api/library")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "System A"


def test_create_library_entry():
    m = MagicMock()
    created = {
        "id": "new-id",
        "name": "My Custom",
        "kind": "llm",
        "is_system": False,
        "description": "",
        "prompt": "...",
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-chat",
        "context_scope": "call",
        "seeded_by_default": False,
        "created_at": "2026-04-23T00:00:00+00:00",
    }
    m.table.return_value.insert.return_value.execute.return_value.data = [created]
    with patch("backend.routers.library.get_client", return_value=m):
        resp = client.post(
            "/api/library",
            json={
                "name": "My Custom",
                "description": "Custom summary",
                "kind": "llm",
                "prompt": "...",
                "llm": "openrouter",
                "model": "deepseek/deepseek-chat",
                "context_scope": "call",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "My Custom"


def test_patch_library_entry():
    m = MagicMock()
    updated = {"id": "lib1", "name": "Edited", "is_system": False}
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        updated
    ]
    with patch("backend.routers.library.get_client", return_value=m):
        resp = client.patch("/api/library/lib1", json={"name": "Edited"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Edited"


def test_delete_system_entry_returns_403():
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "sys1", "is_system": True},
    ]
    with patch("backend.routers.library.get_client", return_value=m):
        resp = client.delete("/api/library/sys1")
    assert resp.status_code == 403


def test_delete_user_entry_returns_204():
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "user1", "is_system": False},
    ]
    with patch("backend.routers.library.get_client", return_value=m):
        resp = client.delete("/api/library/user1")
    assert resp.status_code == 204


def test_reset_system_restores_originals():
    """POST /api/library/reset-system re-applies SYSTEM_LIBRARY values, overwriting edits."""
    from backend.library.seed import SYSTEM_LIBRARY as _SYS
    m = MagicMock()
    # Simulate all existing rows — one per SYSTEM_LIBRARY entry
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "x"}
    ]
    with patch("backend.routers.library.get_client", return_value=m):
        resp = client.post("/api/library/reset-system")
    assert resp.status_code == 200
    # One update call per SYSTEM_LIBRARY entry (count derived dynamically)
    update_count = m.table.return_value.update.call_count
    assert update_count == len(_SYS)
