"""Tests for topics_service — new EPIC-15 schema + validator."""

import uuid

import pytest

from backend.services import topics_service


# ── _TOPIC_SCHEMA shape ─────────────────────────────────────────────────────

def test_topic_schema_describes_new_fields():
    """_TOPIC_SCHEMA must enumerate the v2 fields and OMIT the legacy ones."""
    schema = topics_service._TOPIC_SCHEMA
    for required in ("name", "importance", "key_terms", "evidence", "tasks"):
        assert required in schema, f"new field missing from schema string: {required}"
    for legacy in ("decisions", "follow_up_items", "open_questions", "rationale", "is_parked"):
        assert legacy not in schema, f"legacy field still in schema string: {legacy}"


# ── _validate_topic accepts a valid topic ──────────────────────────────────

def _valid_topic() -> dict:
    return {
        "name": "MC Mac memory issue",
        "importance": "high",
        "key_terms": ["MC Mac", "memory failure", "SO7 PA"],
        "evidence": [
            {
                "speaker": "Hassan",
                "quote": "the MC Mac is still failing on memory for the SO7 PA",
                "citation": "transcript 2026-04-13 · lines 145-148",
            }
        ],
        "tasks": [
            {
                "task": "investigate memory failure",
                "next_step": "Test boost flag + FVMAC on Mark's PA",
                "status": "open",
                "owner": "Nick",
            }
        ],
    }


def test_validate_topic_accepts_valid():
    ok, reason = topics_service._validate_topic(_valid_topic())
    assert ok, reason


# ── _validate_topic rejects empties ────────────────────────────────────────

def test_validate_topic_rejects_missing_evidence():
    t = _valid_topic()
    t["evidence"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "evidence" in reason


def test_validate_topic_rejects_missing_tasks():
    t = _valid_topic()
    t["tasks"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "tasks" in reason


def test_validate_topic_rejects_missing_key_terms():
    t = _valid_topic()
    t["key_terms"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "key_terms" in reason


def test_validate_topic_rejects_bad_importance():
    t = _valid_topic()
    t["importance"] = "urgent"
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "importance" in reason


def test_validate_topic_rejects_task_missing_next_step():
    t = _valid_topic()
    t["tasks"][0]["next_step"] = ""
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "next_step" in reason or "task" in reason


# ── _stamp_task_ids assigns a UUID to each task ───────────────────────────

def test_stamp_task_ids_adds_uuid():
    t = _valid_topic()
    stamped = topics_service._stamp_task_ids(t)
    for task in stamped["tasks"]:
        assert "task_id" in task
        uuid.UUID(task["task_id"])  # raises ValueError if not a UUID


def test_stamp_task_ids_preserves_existing_ids():
    t = _valid_topic()
    existing = str(uuid.uuid4())
    t["tasks"][0]["task_id"] = existing
    stamped = topics_service._stamp_task_ids(t)
    assert stamped["tasks"][0]["task_id"] == existing


# ── _status_rollup derives topic-level status from tasks ──────────────────

def test_status_rollup_all_resolved():
    tasks = [{"status": "resolved"}, {"status": "resolved"}]
    assert topics_service._status_rollup(tasks) == "resolved"


def test_status_rollup_any_open():
    tasks = [{"status": "open"}, {"status": "resolved"}]
    assert topics_service._status_rollup(tasks) == "open"


def test_status_rollup_any_in_progress_no_open():
    tasks = [{"status": "in_progress"}, {"status": "resolved"}]
    assert topics_service._status_rollup(tasks) == "in_progress"


def test_status_rollup_empty():
    assert topics_service._status_rollup([]) == "open"  # safety default


# ── Prompt resolution — library only, no Python fallback ──────────────────


class _FakeDB:
    """Minimal fake replicating supabase-py's chain API for these tests."""

    def __init__(self, tables: dict):
        self._tables = tables
        self._current = None
        self._filters = []

    def table(self, name):
        self._current = name
        self._filters = []
        return self

    def select(self, *_args, **_kw):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def execute(self):
        rows = list(self._tables.get(self._current, []))
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]

        class _R:
            def __init__(self, data):
                self.data = data

        return _R(rows)


def test_resolve_prompt_uses_call_selected_id():
    db = _FakeDB({
        "calls": [{"id": "c1", "call_topics_prompt_id": "lib-v2", "project_id": "p1"}],
        "artifact_library": [
            {"id": "lib-v1", "category": "call_topics", "seeded_by_default": False,
             "prompt": "v1 body", "model": "openrouter", "model_id": "deepseek/deepseek-v3.2",
             "name": "v1"},
            {"id": "lib-v2", "category": "call_topics", "seeded_by_default": True,
             "prompt": "v2 body", "model": "openrouter", "model_id": "deepseek/deepseek-v3.2",
             "name": "v2"},
        ],
    })
    prompt, llm, model, name = topics_service._resolve_call_topics_prompt("c1", db)
    assert prompt == "v2 body"
    assert llm == "openrouter"
    assert model == "deepseek/deepseek-v3.2"
    assert name == "v2"


def test_resolve_prompt_falls_back_to_seeded_default():
    db = _FakeDB({
        "calls": [{"id": "c1", "call_topics_prompt_id": None, "project_id": "p1"}],
        "artifact_library": [
            {"id": "lib-v2", "category": "call_topics", "seeded_by_default": True,
             "prompt": "v2 body", "model": "openrouter", "model_id": "deepseek/deepseek-v3.2",
             "name": "v2 default"},
        ],
    })
    prompt, _llm, _model, name = topics_service._resolve_call_topics_prompt("c1", db)
    assert prompt == "v2 body"
    assert name == "v2 default"


def test_resolve_prompt_hard_errors_when_library_empty():
    db = _FakeDB({
        "calls": [{"id": "c1", "call_topics_prompt_id": None, "project_id": "p1"}],
        "artifact_library": [],
    })
    with pytest.raises(ValueError, match="no_call_topics_prompt"):
        topics_service._resolve_call_topics_prompt("c1", db)


def test_resolve_prompt_invalid_call_raises():
    db = _FakeDB({"calls": [], "artifact_library": []})
    with pytest.raises(ValueError, match="not found"):
        topics_service._resolve_call_topics_prompt("missing", db)


# ── Persistence — only new-shape columns, no legacy keys ──────────────────


def test_persistence_payload_only_has_new_columns(monkeypatch):
    """Captures the dict sent to supabase insert/upsert. Asserts no legacy keys."""
    captured: list[dict] = []

    class _Tbl:
        def __init__(self):
            self._filters = []

        def insert(self, payload):
            if isinstance(payload, list):
                captured.extend(payload)
            else:
                captured.append(payload)
            return self

        def upsert(self, payload):
            return self.insert(payload)

        def update(self, _payload):
            return self

        def select(self, *_a, **_kw):
            return self

        def eq(self, *_a, **_kw):
            return self

        def order(self, *_a, **_kw):
            return self

        def execute(self):
            class _R:
                data = [{"id": "tu-stub"}]

            return _R()

    class _DB:
        def table(self, _n):
            return _Tbl()

    monkeypatch.setattr(topics_service, "get_client", lambda: _DB())

    # Build a valid extracted topic and stamp task_ids (mirrors extract_call_topics)
    topic = _valid_topic()
    topic = topics_service._stamp_task_ids(topic)

    topics_service._persist_topic_update(
        topic=topic,
        topic_id="pt-stub",
        call_id="c1",
    )

    assert captured, "no payload captured — check _persist_topic_update signature"
    payload = captured[0]

    # Required new-shape keys must all be present
    for k in ("name", "importance", "evidence", "key_terms", "tasks", "status"):
        assert k in payload, f"required new-shape key missing: {k}"

    # Status must be rolled up from tasks — one open task → 'open'
    assert payload["status"] == "open"

    # Forbidden legacy keys must not appear
    for legacy in (
        "decisions",
        "follow_up_items",
        "open_questions",
        "rationale",
        "is_parked",
        "owner",
        "sentiment",
    ):
        assert legacy not in payload, f"legacy field leaked into persistence: {legacy}"

    # Every task in the payload must carry a task_id UUID
    for task in payload["tasks"]:
        assert task.get("task_id"), f"task missing task_id: {task}"
        uuid.UUID(task["task_id"])  # raises ValueError if not a valid UUID


# ── PATCH /api/topics/{id} — partial body, status rollup, task_id stamping ──

import importlib

from fastapi.testclient import TestClient


def _build_patch_test_client(monkeypatch, existing_topic_row: dict):
    """Stand up a TestClient with a fake supabase that returns/updates a single topic_updates row."""
    state = {"row": dict(existing_topic_row)}

    class _Tbl:
        def __init__(self, name):
            self._name = name
            self._filters = []
            self._update_payload = None

        def select(self, *_a, **_kw):
            return self

        def eq(self, col, val):
            self._filters.append((col, val))
            return self

        def update(self, payload):
            self._update_payload = payload
            return self

        def delete(self):
            self._update_payload = "DELETE"
            return self

        def execute(self):
            class _R:
                pass

            r = _R()
            if self._name != "topic_updates":
                r.data = []
                return r
            # SELECT
            if self._update_payload is None:
                rid = next((v for c, v in self._filters if c == "id"), None)
                r.data = [state["row"]] if rid == state["row"]["id"] else []
                return r
            if self._update_payload == "DELETE":
                state["row"] = None
                r.data = []
                return r
            # UPDATE
            state["row"] = {**state["row"], **self._update_payload}
            r.data = [state["row"]]
            return r

    class _DB:
        def table(self, name):
            return _Tbl(name)

    monkeypatch.setattr(topics_service, "get_client", lambda: _DB())

    try:
        topics_router = importlib.import_module("backend.routers.topics")
        monkeypatch.setattr(topics_router, "get_client", lambda: _DB())
    except Exception:
        pass

    from backend.main import app

    return TestClient(app), state


def test_patch_topic_partial_updates_name_only(monkeypatch):
    existing = {
        "id": "tu1",
        "call_id": "c1",
        "topic_id": "t1",
        "name": "Old name",
        "importance": "medium",
        "key_terms": ["a"],
        "evidence": [{"speaker": "X", "quote": "Y", "citation": "Z"}],
        "tasks": [
            {
                "task_id": "task-1",
                "task": "old",
                "next_step": "x",
                "status": "open",
                "owner": "",
            }
        ],
        "status": "open",
    }
    client, state = _build_patch_test_client(monkeypatch, existing)
    r = client.patch("/api/topics/tu1", json={"name": "New name"})
    assert r.status_code in (200, 204), r.text
    assert state["row"]["name"] == "New name"
    # Untouched fields stay
    assert state["row"]["importance"] == "medium"


def test_patch_topic_tasks_triggers_status_rollup(monkeypatch):
    existing = {
        "id": "tu1",
        "call_id": "c1",
        "topic_id": "t1",
        "name": "T",
        "importance": "low",
        "key_terms": ["a"],
        "evidence": [{"speaker": "X", "quote": "Y", "citation": "Z"}],
        "tasks": [
            {
                "task_id": "task-1",
                "task": "a",
                "next_step": "b",
                "status": "open",
                "owner": "",
            }
        ],
        "status": "open",
    }
    client, state = _build_patch_test_client(monkeypatch, existing)
    new_tasks = [
        {
            "task_id": "task-1",
            "task": "a",
            "next_step": "b",
            "status": "resolved",
            "owner": "",
        },
        {
            "task_id": "task-2",
            "task": "c",
            "next_step": "d",
            "status": "resolved",
            "owner": "Nick",
        },
    ]
    r = client.patch("/api/topics/tu1", json={"tasks": new_tasks})
    assert r.status_code in (200, 204), r.text
    assert state["row"]["status"] == "resolved"  # rolled up
    assert len(state["row"]["tasks"]) == 2


def test_patch_topic_new_task_without_id_gets_stamped(monkeypatch):
    existing = {
        "id": "tu1",
        "call_id": "c1",
        "topic_id": "t1",
        "name": "T",
        "importance": "low",
        "key_terms": ["a"],
        "evidence": [{"speaker": "X", "quote": "Y", "citation": "Z"}],
        "tasks": [
            {
                "task_id": "task-1",
                "task": "a",
                "next_step": "b",
                "status": "open",
                "owner": "",
            }
        ],
        "status": "open",
    }
    client, state = _build_patch_test_client(monkeypatch, existing)
    new_tasks = [
        {
            "task_id": "task-1",
            "task": "a",
            "next_step": "b",
            "status": "open",
            "owner": "",
        },
        {
            "task": "fresh task",
            "next_step": "fresh next step",
            "status": "open",
            "owner": "",
        },  # no task_id
    ]
    r = client.patch("/api/topics/tu1", json={"tasks": new_tasks})
    assert r.status_code in (200, 204), r.text
    # Both tasks should have task_id
    assert len(state["row"]["tasks"]) == 2
    for task in state["row"]["tasks"]:
        assert task.get("task_id"), f"task missing task_id: {task}"
    # The new task (no task_id supplied) must have been stamped with a real UUID
    new_task = next(t for t in state["row"]["tasks"] if t.get("task") == "fresh task")
    uuid.UUID(new_task["task_id"])  # raises ValueError if not a valid UUID
    # The existing task preserves its original id (may not be UUID format)
    existing_task = next(t for t in state["row"]["tasks"] if t.get("task_id") == "task-1")
    assert existing_task["task_id"] == "task-1"
