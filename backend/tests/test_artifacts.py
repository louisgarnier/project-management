import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

CALL_ID    = "aaaaaaaa-0000-0000-0000-000000000001"
TYPE_ID_1  = "bbbbbbbb-0000-0000-0000-000000000002"
TYPE_ID_2  = "cccccccc-0000-0000-0000-000000000003"
TYPE_ID_3  = "dddddddd-0000-0000-0000-000000000004"
TYPE_ID_4  = "eeeeeeee-0000-0000-0000-000000000005"
TYPE_ID_5  = "ffffffff-0000-0000-0000-000000000006"
ART_ID_1   = "11111111-0000-0000-0000-000000000001"
ART_ID_2   = "22222222-0000-0000-0000-000000000002"
ART_ID_3   = "33333333-0000-0000-0000-000000000003"


def make_artifact_type(type_id, prompt="Test prompt"):
    return {"id": type_id, "name": "Test Type", "prompt": prompt, "is_default": False}


def make_artifact(art_id, type_id, mode="claude", status="pending"):
    return {
        "id": art_id,
        "call_id": CALL_ID,
        "artifact_type_id": type_id,
        "mode": mode,
        "status": status,
        "content": "" if mode == "manual" else None,
        "prompt_used": "Test prompt",
        "error_message": None,
        "created_at": "2026-04-12T00:00:00Z",
    }


@patch("backend.routers.artifacts.get_client")
def test_post_creates_artifact_rows(mock_gc):
    """POST with 3 claude + 2 manual → 5 rows; manual rows have status='done'."""
    m = MagicMock()
    m.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        make_artifact_type(TYPE_ID_1),
        make_artifact_type(TYPE_ID_2),
        make_artifact_type(TYPE_ID_3),
        make_artifact_type(TYPE_ID_4),
        make_artifact_type(TYPE_ID_5),
    ]
    inserted = [
        make_artifact(ART_ID_1, TYPE_ID_1, mode="claude"),
        make_artifact(ART_ID_2, TYPE_ID_2, mode="claude"),
        make_artifact(ART_ID_3, TYPE_ID_3, mode="claude"),
        make_artifact("44444444-0000-0000-0000-000000000004", TYPE_ID_4, mode="manual", status="done"),
        make_artifact("55555555-0000-0000-0000-000000000005", TYPE_ID_5, mode="manual", status="done"),
    ]
    m.table.return_value.insert.return_value.execute.return_value.data = inserted
    mock_gc.return_value = m

    r = client.post(
        f"/api/calls/{CALL_ID}/artifacts",
        json={
            "selections": [
                {"artifact_type_id": TYPE_ID_1, "mode": "claude"},
                {"artifact_type_id": TYPE_ID_2, "mode": "claude"},
                {"artifact_type_id": TYPE_ID_3, "mode": "claude"},
                {"artifact_type_id": TYPE_ID_4, "mode": "manual"},
                {"artifact_type_id": TYPE_ID_5, "mode": "manual"},
            ]
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert len(data) == 5
    manual_rows = [a for a in data if a["mode"] == "manual"]
    assert all(a["status"] == "done" for a in manual_rows)


@patch("backend.routers.artifacts.get_client")
def test_post_snapshots_prompt_used(mock_gc):
    """prompt_used on the artifact row matches the artifact type's prompt at creation time."""
    m = MagicMock()
    m.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        make_artifact_type(TYPE_ID_1, prompt="Specific prompt text"),
    ]
    m.table.return_value.insert.return_value.execute.return_value.data = [
        {**make_artifact(ART_ID_1, TYPE_ID_1), "prompt_used": "Specific prompt text"},
    ]
    mock_gc.return_value = m

    r = client.post(
        f"/api/calls/{CALL_ID}/artifacts",
        json={"selections": [{"artifact_type_id": TYPE_ID_1, "mode": "claude"}]},
    )
    assert r.status_code == 201
    insert_call = m.table.return_value.insert.call_args[0][0]
    assert insert_call[0]["prompt_used"] == "Specific prompt text"


@patch("backend.routers.artifacts.get_client")
@patch("backend.routers.artifacts.generate_artifact")
def test_stream_emits_generating_then_done(mock_gen, mock_gc):
    """GET /stream (mocked Claude) → all claude artifacts emit generating then done."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": CALL_ID, "transcript": "Test transcript"},
    ]
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        make_artifact(ART_ID_1, TYPE_ID_1, mode="claude"),
        make_artifact(ART_ID_2, TYPE_ID_2, mode="claude"),
    ]
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_gc.return_value = m
    mock_gen.side_effect = AsyncMock(return_value="Generated content")

    with client.stream("GET", f"/api/calls/{CALL_ID}/artifacts/stream") as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    types = [e["type"] for e in events]
    assert "status" in types
    assert "done" in types
    assert events[-1]["type"] == "complete"


@patch("backend.routers.artifacts.get_client")
@patch("backend.routers.artifacts.generate_artifact")
def test_stream_one_error_does_not_block_others(mock_gen, mock_gc):
    """One Claude error → error event emitted; stream still completes with done for others."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": CALL_ID, "transcript": "Test transcript"},
    ]
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        make_artifact(ART_ID_1, TYPE_ID_1, mode="claude"),
        make_artifact(ART_ID_2, TYPE_ID_2, mode="claude"),
    ]
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    mock_gc.return_value = m

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Claude error")
        return "Generated content"

    mock_gen.side_effect = side_effect

    with client.stream("GET", f"/api/calls/{CALL_ID}/artifacts/stream") as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    error_events = [e for e in events if e["type"] == "error"]
    done_events = [e for e in events if e["type"] == "done"]
    assert len(error_events) == 1
    assert len(done_events) == 1
    assert events[-1]["type"] == "complete"


@patch("backend.routers.artifacts.get_client")
def test_stream_no_pending_artifacts_emits_complete(mock_gc):
    """If no pending claude artifacts exist, stream immediately emits complete."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": CALL_ID, "transcript": "Test transcript"},
    ]
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_gc.return_value = m

    with client.stream("GET", f"/api/calls/{CALL_ID}/artifacts/stream") as resp:
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    assert events == [{"type": "complete"}]


@patch("backend.routers.artifacts.get_client")
def test_list_artifacts_for_call(mock_gc):
    """GET /api/calls/{call_id}/artifacts returns all artifacts for the call."""
    m = MagicMock()
    # call-existence check: .select().eq().execute().data must be truthy
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": CALL_ID}
    ]
    # artifact fetch: .select().eq().neq().order().execute().data
    # neq("status", "stale") was added to filter out stale artifacts
    m.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.execute.return_value.data = [
        make_artifact(ART_ID_1, TYPE_ID_1, mode="claude", status="done"),
        make_artifact(ART_ID_2, TYPE_ID_2, mode="manual", status="done"),
    ]
    mock_gc.return_value = m
    r = client.get(f"/api/calls/{CALL_ID}/artifacts")
    assert r.status_code == 200
    assert len(r.json()) == 2


@patch("backend.routers.artifacts.get_client")
def test_patch_artifact_content(mock_gc):
    """PATCH /api/artifacts/{id} updates content and/or status."""
    m = MagicMock()
    updated = {**make_artifact(ART_ID_1, TYPE_ID_1), "content": "New content", "status": "done"}
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
    mock_gc.return_value = m
    r = client.patch(
        f"/api/artifacts/{ART_ID_1}",
        json={"content": "New content", "status": "done"},
    )
    assert r.status_code == 200
    assert r.json()["content"] == "New content"


@patch("backend.routers.artifacts.get_client")
def test_list_artifacts_call_not_found(mock_gc):
    """GET /api/calls/{call_id}/artifacts returns 404 when call does not exist."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_gc.return_value = m
    r = client.get(f"/api/calls/{CALL_ID}/artifacts")
    assert r.status_code == 404


@patch("backend.routers.artifacts.get_client")
def test_patch_artifact_empty_payload(mock_gc):
    """PATCH /api/artifacts/{id} with no fields returns 422."""
    mock_gc.return_value = MagicMock()
    r = client.patch(f"/api/artifacts/{ART_ID_1}", json={})
    assert r.status_code == 422


@patch("backend.routers.artifacts.get_client")
def test_patch_artifact_not_found(mock_gc):
    """PATCH /api/artifacts/{id} returns 404 when artifact does not exist."""
    m = MagicMock()
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []
    mock_gc.return_value = m
    r = client.patch(f"/api/artifacts/{ART_ID_1}", json={"content": "x"})
    assert r.status_code == 404


@patch("backend.routers.artifacts.get_client")
@patch("backend.routers.artifacts.generate_artifact")
def test_stream_uses_artifact_mode_as_llm(mock_gen, mock_gc):
    """SSE stream passes artifact.mode to generate_artifact as the llm param."""
    import asyncio

    async def _run():
        mock_gen.reset_mock()
        mock_gen.return_value = "groq output"

        m = MagicMock()
        m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "call-1", "transcript": "transcript text"}
        ]
        m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": ART_ID_1, "prompt_used": "do x", "mode": "groq"},
        ]
        m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
        mock_gc.return_value = m

        r = client.get("/api/calls/call-1/artifacts/stream",
                       headers={"Accept": "text/event-stream"})
        assert r.status_code == 200
        # generate_artifact must have been called with llm="groq"
        mock_gen.assert_called_once()
        _, _, llm_arg = mock_gen.call_args[0]
        assert llm_arg == "groq"

    asyncio.get_event_loop().run_until_complete(_run())


@patch("backend.routers.artifacts.get_client")
def test_create_selections_accepts_groq_mode(mock_gc):
    """POST /artifacts accepts mode='groq' and stores it."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"id": CALL_ID}]
    m.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": TYPE_ID_1, "prompt": "prompt text"}
    ]
    artifact_row = make_artifact(ART_ID_1, TYPE_ID_1, mode="groq", status="pending")
    m.table.return_value.insert.return_value.execute.return_value.data = [artifact_row]
    mock_gc.return_value = m
    r = client.post(f"/api/calls/{CALL_ID}/artifacts",
                    json={"selections": [{"artifact_type_id": TYPE_ID_1, "mode": "groq"}]})
    assert r.status_code == 201
    inserted = m.table.return_value.insert.call_args[0][0]
    assert inserted[0]["mode"] == "groq"
    assert inserted[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_generate_artifact_includes_topics_in_prompt():
    """generate_artifact must include topics JSON in the user message when topics are provided."""
    from backend.services.llm_service import generate_artifact
    from unittest.mock import AsyncMock, patch, MagicMock

    topics = [
        {
            "name": "Pricing",
            "status": "open",
            "owner": "Client",
            "sentiment": "concern",
            "summary": "Client pushed back on annual plan.",
            "follow_up_items": ["Send monthly breakdown"],
            "decisions": [],
        }
    ]

    captured_messages = {}

    async def fake_create(**kwargs):
        captured_messages["messages"] = kwargs.get("messages", [])
        m = MagicMock()
        m.content = [MagicMock(text="result")]
        m.usage = MagicMock(input_tokens=10, output_tokens=5)
        return m

    fake_client = MagicMock()
    fake_client.messages.create = fake_create

    with patch("backend.services.llm_service.anthropic.AsyncAnthropic", return_value=fake_client):
        await generate_artifact("Write a summary.", "The call transcript.", "claude", topics=topics)

    user_content = captured_messages["messages"][0]["content"]
    assert "Pricing" in user_content
    assert "Topics from this call" in user_content
    assert "Write a summary." in user_content


@pytest.mark.asyncio
async def test_generate_artifact_without_topics_has_no_topics_block():
    """generate_artifact must NOT include a topics block when topics=None."""
    from backend.services.llm_service import generate_artifact
    from unittest.mock import MagicMock, patch

    captured_messages = {}

    async def fake_create(**kwargs):
        captured_messages["messages"] = kwargs.get("messages", [])
        m = MagicMock()
        m.content = [MagicMock(text="result")]
        m.usage = MagicMock(input_tokens=10, output_tokens=5)
        return m

    fake_client = MagicMock()
    fake_client.messages.create = fake_create

    with patch("backend.services.llm_service.anthropic.AsyncAnthropic", return_value=fake_client):
        await generate_artifact("Write a summary.", "The call transcript.", "claude", topics=None)

    user_content = captured_messages["messages"][0]["content"]
    assert "Topics from this call" not in user_content
    assert "The call transcript." in user_content
    assert "Write a summary." in user_content


@patch("backend.routers.artifacts.get_client")
@patch("backend.routers.artifacts.generate_artifact")
@patch("backend.routers.artifacts._assemble_context")
def test_artifact_stream_injects_project_context(mock_assemble, mock_gen, mock_gc):
    """SSE stream delegates context assembly to _assemble_context during generation
    (Story 15.6: inline scope-branches replaced with single _assemble_context call).
    """
    db = MagicMock()
    mock_gc.return_value = db

    # call row: needs project_id and transcript
    call_chain = MagicMock()
    call_chain.execute.return_value = MagicMock(data=[
        {"id": "call-1", "transcript": "transcript text", "project_id": "proj-1"}
    ])
    call_chain.eq.return_value = call_chain
    call_chain.select.return_value = call_chain

    # topic_updates for call (used for call_topics context)
    updates_chain = MagicMock()
    updates_chain.execute.return_value = MagicMock(data=[])
    updates_chain.eq.return_value = updates_chain
    updates_chain.select.return_value = updates_chain

    # pending artifacts — include artifact_type_id so scope lookup fires
    pending_chain = MagicMock()
    pending_chain.execute.return_value = MagicMock(data=[
        {"id": "art-1", "prompt_used": "Summarise", "mode": "claude",
         "artifact_type_id": TYPE_ID_1}
    ])
    pending_chain.eq.return_value = pending_chain
    pending_chain.select.return_value = pending_chain

    # artifact_types row for scope lookup
    types_chain = MagicMock()
    types_chain.execute.return_value = MagicMock(data=[
        {"id": TYPE_ID_1, "context_scope": "all_project_topics",
         "model": None, "kind": "llm", "template_id": None, "llm": None}
    ])
    types_chain.in_.return_value = types_chain
    types_chain.select.return_value = types_chain

    def table_side(name):
        if name == "calls":
            return call_chain
        if name == "topic_updates":
            return updates_chain
        if name == "artifacts":
            return pending_chain
        if name == "artifact_types":
            return types_chain
        return MagicMock()

    db.table.side_effect = table_side

    assembled_ctx = "=== Project-level context assembled by _assemble_context ==="
    mock_assemble.return_value = assembled_ctx

    captured = {}

    async def fake_gen(prompt, context, mode, topics=None, model=None):
        captured["context"] = context
        return "generated content"
    mock_gen.side_effect = fake_gen

    # Fire the SSE stream request
    with client.stream("GET", f"/api/calls/call-1/artifacts/stream") as response:
        # Consume all events
        list(response.iter_lines())

    # Verify _assemble_context was called with the right scope, call_id and project_id
    mock_assemble.assert_called_once_with("all_project_topics", "call-1", "proj-1", db)
    # Verify generate_artifact received the assembled context string
    assert captured.get("context") == assembled_ctx
