from unittest.mock import MagicMock, patch

from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

PROJECT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
TYPE_ID = "bbbbbbbb-0000-0000-0000-000000000002"
OTHER_ID = "cccccccc-0000-0000-0000-000000000003"


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
    m.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        make_type()
    ]
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
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        make_type()
    ]
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        updated
    ]
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
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        make_type(is_default=False)
    ]
    m.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [
        make_type()
    ]
    mock_gc.return_value = m
    r = client.delete(f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}")
    assert r.status_code == 204


@patch("backend.routers.artifact_types.get_client")
def test_delete_default_type_forbidden(mock_gc):
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        make_type(is_default=True)
    ]
    mock_gc.return_value = m
    r = client.delete(f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}")
    assert r.status_code == 403


@patch("backend.routers.artifact_types.get_client")
def test_delete_not_found(mock_gc):
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
        []
    )
    mock_gc.return_value = m
    r = client.delete(f"/api/projects/{PROJECT_ID}/artifact-types/{TYPE_ID}")
    assert r.status_code == 404


@patch("backend.routers.artifact_types.get_client")
def test_import_artifact_types(mock_gc):
    m = MagicMock()
    source = [{"name": "Imported Type", "prompt": "Imported prompt"}]
    m.table.return_value.select.return_value.in_.return_value.execute.return_value.data = (
        source
    )
    m.table.return_value.insert.return_value.execute.return_value.data = [make_type()]
    mock_gc.return_value = m
    r = client.post(
        f"/api/projects/{PROJECT_ID}/artifact-types/import",
        json={"type_ids": [OTHER_ID]},
    )
    assert r.status_code == 201
    assert len(r.json()) == 1


@patch("backend.routers.artifact_types.get_client")
def test_create_artifact_type_with_llm(mock_gc):
    """POST artifact type accepts optional llm field."""
    from uuid import uuid4

    m = MagicMock()
    created = {
        "id": str(uuid4()),
        "project_id": str(uuid4()),
        "name": "My Type",
        "prompt": "do x",
        "is_default": False,
        "llm": "groq",
        "created_at": "2026-01-01T00:00:00",
    }
    m.table.return_value.insert.return_value.execute.return_value.data = [created]
    mock_gc.return_value = m
    r = client.post(
        f"/api/projects/{created['project_id']}/artifact-types",
        json={"name": "My Type", "prompt": "do x", "llm": "groq"},
    )
    assert r.status_code == 201
    inserted = m.table.return_value.insert.call_args[0][0]
    assert inserted["llm"] == "groq"


@patch("backend.routers.artifact_types.get_client")
def test_update_artifact_type_reset_llm_to_null(mock_gc):
    """PATCH artifact type can set llm to null (reset to project default)."""
    from uuid import uuid4

    type_id = str(uuid4())
    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": type_id}
    ]
    updated = {
        "id": type_id,
        "project_id": project_id,
        "name": "My Type",
        "prompt": "do x",
        "is_default": False,
        "llm": None,
        "created_at": "2026-01-01T00:00:00",
    }
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        updated
    ]
    mock_gc.return_value = m
    r = client.patch(
        f"/api/projects/{project_id}/artifact-types/{type_id}", json={"llm": None}
    )
    assert r.status_code == 200
    update_payload = m.table.return_value.update.call_args[0][0]
    assert "llm" in update_payload
    assert update_payload["llm"] is None


@patch("backend.routers.artifact_types.get_client")
def test_seed_defaults_inserts_topics_prompt(mock_gc):
    """seed_defaults must insert exactly one category='topics' row."""
    from backend.routers.artifact_types import seed_defaults

    m = MagicMock()
    mock_gc.return_value = m
    seed_defaults("proj-1")
    # collect all rows from all insert calls
    all_rows = []
    for call in m.table.return_value.insert.call_args_list:
        rows = call.args[0] if call.args else []
        if isinstance(rows, list):
            all_rows.extend(rows)
        elif isinstance(rows, dict):
            all_rows.append(rows)
    topics_rows = [r for r in all_rows if r.get("category") == "topics"]
    assert (
        len(topics_rows) == 1
    ), f"Expected 1 topics row, got {len(topics_rows)}: {all_rows}"
    assert "prompt" in topics_rows[0]


@patch("backend.routers.artifact_types.get_client")
def test_create_artifact_type_sets_category_artifacts(mock_gc):
    """User-created types must always have category='artifacts'."""
    m = MagicMock()
    m.table.return_value.insert.return_value.execute.return_value.data = [
        {
            "id": "x",
            "project_id": "proj-1",
            "name": "T",
            "prompt": "P",
            "is_default": False,
            "category": "artifacts",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    mock_gc.return_value = m
    r = client.post(
        "/api/projects/proj-1/artifact-types",
        json={"name": "T", "prompt": "P"},
    )
    assert r.status_code == 201
    inserted = m.table.return_value.insert.call_args.args[0]
    assert inserted["category"] == "artifacts"


def test_get_defaults_for_call_topics_returns_new_default():
    """GET /api/artifact-types/defaults/call_topics returns the canonical default."""
    from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT

    resp = client.get("/api/artifact-types/defaults/call_topics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prompt"] == CALL_TOPICS_DEFAULT_PROMPT
    assert body["name"] == "Call Topics Extraction"
    assert body["category"] == "call_topics"
    assert body["llm"] == "openrouter"
    assert body["model"] == "anthropic/claude-sonnet-4.6"


def test_get_defaults_for_unknown_category_returns_404():
    resp = client.get("/api/artifact-types/defaults/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 8: model field propagation tests
# ---------------------------------------------------------------------------


def test_artifact_type_create_schema_accepts_model():
    """ArtifactTypeCreate Pydantic model accepts model and llm=openrouter."""
    from backend.routers.artifact_types import ArtifactTypeCreate

    a = ArtifactTypeCreate(
        name="X", prompt="Y", llm="openrouter", model="openai/gpt-4o"
    )
    assert a.model == "openai/gpt-4o"
    assert a.llm == "openrouter"


def test_artifact_type_update_schema_accepts_model():
    """ArtifactTypeUpdate Pydantic model accepts model."""
    from backend.routers.artifact_types import ArtifactTypeUpdate

    u = ArtifactTypeUpdate(llm="openrouter", model="google/gemini-2.5-pro")
    assert u.model == "google/gemini-2.5-pro"
    assert u.llm == "openrouter"


@patch("backend.routers.artifact_types.get_client")
def test_create_artifact_type_accepts_model(mock_gc):
    """POST a new type with llm='openrouter' + model='openai/gpt-4o'; both round-trip."""
    from uuid import uuid4

    m = MagicMock()
    created = {
        "id": str(uuid4()),
        "project_id": PROJECT_ID,
        "name": "OpenRouter Type",
        "prompt": "do something",
        "is_default": False,
        "llm": "openrouter",
        "model": "openai/gpt-4o",
        "created_at": "2026-01-01T00:00:00Z",
    }
    m.table.return_value.insert.return_value.execute.return_value.data = [created]
    mock_gc.return_value = m
    r = client.post(
        f"/api/projects/{PROJECT_ID}/artifact-types",
        json={
            "name": "OpenRouter Type",
            "prompt": "do something",
            "llm": "openrouter",
            "model": "openai/gpt-4o",
        },
    )
    assert r.status_code == 201
    assert r.json()["llm"] == "openrouter"
    assert r.json()["model"] == "openai/gpt-4o"
    # Verify model was included in the insert payload
    inserted = m.table.return_value.insert.call_args[0][0]
    assert inserted["model"] == "openai/gpt-4o"
    assert inserted["llm"] == "openrouter"


@patch("backend.routers.artifact_types.get_client")
def test_update_artifact_type_accepts_model(mock_gc):
    """PATCH a type with model='google/gemini-2.5-pro'; model round-trips."""
    from uuid import uuid4

    type_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": type_id}
    ]
    updated = {
        "id": type_id,
        "project_id": PROJECT_ID,
        "name": "My Type",
        "prompt": "do x",
        "is_default": False,
        "llm": "openrouter",
        "model": "google/gemini-2.5-pro",
        "created_at": "2026-01-01T00:00:00Z",
    }
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        updated
    ]
    mock_gc.return_value = m
    r = client.patch(
        f"/api/projects/{PROJECT_ID}/artifact-types/{type_id}",
        json={"llm": "openrouter", "model": "google/gemini-2.5-pro"},
    )
    assert r.status_code == 200
    assert r.json()["model"] == "google/gemini-2.5-pro"


def test_seed_defaults_inserts_workflow_and_library_seeded():
    """seed_defaults inserts 4 Tier-1 workflow prompts + library entries with seeded_by_default=true."""
    from unittest.mock import MagicMock, patch

    from backend.routers.artifact_types import seed_defaults

    inserted_rows: list[dict] = []
    mock = MagicMock()

    def table_side_effect(name):
        m = MagicMock()
        if name == "artifact_library":
            # Simulate 3 seeded-by-default library entries
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": "lib-1",
                    "name": "Executive Summary",
                    "kind": "llm",
                    "prompt": "...",
                    "template_id": None,
                    "llm": "openrouter",
                    "model": "anthropic/claude-sonnet-4.6",
                    "context_scope": "call",
                    "description": "",
                },
                {
                    "id": "lib-2",
                    "name": "Next Steps & Action Items",
                    "kind": "template",
                    "prompt": None,
                    "template_id": "next_steps",
                    "llm": None,
                    "model": None,
                    "context_scope": "call",
                    "description": "",
                },
                {
                    "id": "lib-3",
                    "name": "Questions for Stakeholders",
                    "kind": "template",
                    "prompt": None,
                    "template_id": "questions_list",
                    "llm": None,
                    "model": None,
                    "context_scope": "call",
                    "description": "",
                },
            ]
        elif name == "artifact_types":

            def capture(rows):
                if isinstance(rows, list):
                    inserted_rows.extend(rows)
                else:
                    inserted_rows.append(rows)
                return m

            m.insert.side_effect = capture
            m.insert.return_value.execute.return_value.data = []
        return m

    mock.table.side_effect = table_side_effect

    with patch("backend.routers.artifact_types.get_client", return_value=mock):
        seed_defaults("test-proj-id")

    categories = [r.get("category") for r in inserted_rows]
    # 4 Tier-1 workflow prompts
    assert categories.count("call_topics") == 1
    assert categories.count("project_topics") == 1
    assert categories.count("merge_verification") == 1
    assert categories.count("not_discussed_check") == 1
    # 3 Tier-2 library-backed artifacts
    assert categories.count("artifacts") == 3
    artifacts_inserted = [r for r in inserted_rows if r.get("category") == "artifacts"]
    assert all(r.get("library_ref_id") for r in artifacts_inserted)
    # Kinds preserved from library
    kinds = {r["name"]: r["kind"] for r in artifacts_inserted}
    assert kinds["Executive Summary"] == "llm"
    assert kinds["Next Steps & Action Items"] == "template"
    assert kinds["Questions for Stakeholders"] == "template"
