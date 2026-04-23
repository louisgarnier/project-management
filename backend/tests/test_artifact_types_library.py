from unittest.mock import MagicMock, patch

from backend.main import app
from fastapi.testclient import TestClient


def test_from_library_copies_entry_to_artifact_types():
    mock = MagicMock()

    # Two different select chains:
    # 1) artifact_library.select().eq(id).execute().data — returns the library entry
    # 2) artifact_types.insert(row).execute().data — returns the new row
    lib_entry = {
        "id": "lib-1",
        "name": "Risk Register",
        "description": "",
        "kind": "template",
        "prompt": None,
        "template_id": "risk_register",
        "llm": None,
        "model": None,
        "context_scope": "project",
    }
    inserted = {
        "id": "new-artifact-type-id",
        "project_id": "proj-1",
        "name": "Risk Register",
        "kind": "template",
        "template_id": "risk_register",
        "library_ref_id": "lib-1",
        "prompt": None,
        "is_default": False,
        "category": "artifacts",
        "llm": None,
        "model": None,
        "context_scope": "project",
    }

    def table_side_effect(name):
        m = MagicMock()
        if name == "artifact_library":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                lib_entry
            ]
        elif name == "artifact_types":
            m.insert.return_value.execute.return_value.data = [inserted]
        return m

    mock.table.side_effect = table_side_effect

    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.post(
            "/api/projects/proj-1/artifact-types/from-library",
            json={"library_id": "lib-1"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "template"
    assert body["library_ref_id"] == "lib-1"


def test_library_source_returns_linked_entry():
    mock = MagicMock()

    def table_side_effect(name):
        m = MagicMock()
        if name == "artifact_types":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "at-1", "library_ref_id": "lib-1", "name": "X"}
            ]
        elif name == "artifact_library":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": "lib-1",
                    "name": "Risk Register",
                    "kind": "template",
                    "template_id": "risk_register",
                }
            ]
        return m

    mock.table.side_effect = table_side_effect

    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.get("/api/artifact-types/at-1/library-source")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Risk Register"


def test_library_source_404_when_no_ref_and_no_name_match():
    mock = MagicMock()

    def table_side_effect(name):
        m = MagicMock()
        if name == "artifact_types":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "at-2", "library_ref_id": None, "name": "Custom Unique"}
            ]
        elif name == "artifact_library":
            # name-fallback lookup — returns empty (no system match)
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                []
            )
        return m

    mock.table.side_effect = table_side_effect

    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.get("/api/artifact-types/at-2/library-source")
    assert resp.status_code == 404


def test_library_source_name_fallback_for_existing_projects():
    """When library_ref_id is NULL, fall back to matching by name against is_system=true entries."""
    mock = MagicMock()

    def table_side_effect(name):
        m = MagicMock()
        if name == "artifact_types":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "at-3", "library_ref_id": None, "name": "Executive Summary"}
            ]
        elif name == "artifact_library":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": "lib-99",
                    "name": "Executive Summary",
                    "kind": "llm",
                    "is_system": True,
                }
            ]
        return m

    mock.table.side_effect = table_side_effect

    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.get("/api/artifact-types/at-3/library-source")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Executive Summary"


def test_publish_to_library_creates_entry_and_links():
    mock = MagicMock()
    source_type = {
        "id": "at-99",
        "name": "Board Meeting Summary",
        "kind": "llm",
        "prompt": "Write a board-style summary.",
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "context_scope": "call",
        "library_ref_id": None,
    }
    new_lib = {"id": "new-lib-id", "name": "Board Meeting Summary", "is_system": False}

    def table_side_effect(name):
        m = MagicMock()
        if name == "artifact_types":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                source_type
            ]
            m.update.return_value.eq.return_value.execute.return_value.data = [
                {"id": "at-99"}
            ]
        elif name == "artifact_library":
            m.insert.return_value.execute.return_value.data = [new_lib]
        return m

    mock.table.side_effect = table_side_effect

    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.post(
            "/api/artifact-types/at-99/publish-to-library",
            json={
                "name": "Board Meeting Summary",
                "description": "My custom board summary",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Board Meeting Summary"


def test_publish_to_library_rejects_template_kind():
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "at-tmpl", "kind": "template"}
    ]
    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.post(
            "/api/artifact-types/at-tmpl/publish-to-library",
            json={
                "name": "whatever",
                "description": "",
            },
        )
    assert resp.status_code == 400


def test_preview_llm_kind_returns_400():
    """Cannot preview an LLM artifact — nothing to render deterministically."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "at-llm", "kind": "llm"}
    ]
    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        client = TestClient(app)
        resp = client.post(
            "/api/artifact-types/at-llm/preview", json={"call_id": "call-1"}
        )
    assert resp.status_code == 400
