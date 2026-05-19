"""Tests for topics_service — new EPIC-15 schema + validator."""

import uuid

import pytest

from backend.services import topics_service


# ── _TOPIC_SCHEMA shape ─────────────────────────────────────────────────────

def test_topic_schema_describes_new_fields():
    """_TOPIC_SCHEMA must enumerate the v2/v3 fields and OMIT the pre-v2 legacy ones.

    NOTE: decisions + open_questions are now first-class v3 fields (Story 15.5),
    so they must be PRESENT — only the pre-v2 legacy keys remain excluded.
    """
    schema = topics_service._TOPIC_SCHEMA
    for required in ("name", "importance", "key_terms", "evidence", "tasks",
                     "open_questions", "decisions"):
        assert required in schema, f"v3 field missing from schema string: {required}"
    for legacy in ("follow_up_items", "rationale", "is_parked"):
        assert legacy not in schema, f"pre-v2 legacy field still in schema string: {legacy}"


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
    """v3: tasks=[] alone is fine; all three arrays empty is what triggers rejection.
    This test exercises the all-three-empty case (the rejection path)."""
    t = _valid_topic()
    t["tasks"] = []
    t["open_questions"] = []
    t["decisions"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert any(k in reason for k in ("tasks", "open_questions", "decisions"))


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


# ── EPIC-15 Phase 2 (Story 15.5) — _TOPIC_SCHEMA + validator with new arrays ──


def _valid_v3_topic() -> dict:
    base = _valid_topic()
    base["open_questions"] = [
        {"text": "Does the boost flag fix the ceiling?", "owner": "Nick", "status": "open"}
    ]
    base["decisions"] = [{"text": "Defer Mac retirement decision to Q3 review."}]
    return base


def test_validate_topic_accepts_empty_open_questions_and_decisions():
    """Both new arrays accept []; topic still valid if it has tasks."""
    t = _valid_topic()
    t["open_questions"] = []
    t["decisions"] = []
    ok, reason = topics_service._validate_topic(t)
    assert ok, reason


def test_validate_topic_accepts_populated_open_questions_and_decisions():
    ok, reason = topics_service._validate_topic(_valid_v3_topic())
    assert ok, reason


def test_validate_topic_accepts_empty_tasks_when_decisions_present():
    """Decision-only topic is valid — no actionable task needed when something was decided."""
    t = _valid_v3_topic()
    t["tasks"] = []
    ok, reason = topics_service._validate_topic(t)
    assert ok, reason


def test_validate_topic_rejects_all_three_arrays_empty():
    """A topic with evidence but NO task, NO open question, NO decision is dropped."""
    t = _valid_topic()
    t["tasks"] = []
    t["open_questions"] = []
    t["decisions"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert any(k in reason for k in ("tasks", "open_questions", "decisions"))


def test_validate_topic_rejects_open_question_missing_text():
    t = _valid_v3_topic()
    t["open_questions"][0]["text"] = ""
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "text" in reason or "open_question" in reason


def test_validate_topic_rejects_decision_missing_text():
    t = _valid_v3_topic()
    t["decisions"][0]["text"] = ""
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "text" in reason or "decision" in reason


def test_validate_topic_rejects_open_question_bad_status():
    """v3: open_questions[i].status is required and must be in the canonical set."""
    t = _valid_v3_topic()
    t["open_questions"][0]["status"] = "urgent"  # invalid
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "status" in reason or "open_question" in reason


def test_validate_topic_rejects_open_question_missing_status():
    """v3: missing status on an open_question rejects (parallel to tasks behaviour)."""
    t = _valid_v3_topic()
    del t["open_questions"][0]["status"]
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "status" in reason or "open_question" in reason


def test_validate_topic_accepts_missing_open_questions_key_as_empty():
    """Backwards-compat: a topic dict without the open_questions key validates as []
    (still requires non-empty tasks since the other arrays default to [])."""
    t = _valid_topic()
    # No open_questions / decisions keys at all — tasks must carry the load
    ok, reason = topics_service._validate_topic(t)
    assert ok, reason


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
             "prompt": "v1 body", "llm": "openrouter", "model": "deepseek/deepseek-v3.2",
             "name": "v1"},
            {"id": "lib-v2", "category": "call_topics", "seeded_by_default": True,
             "prompt": "v2 body", "llm": "openrouter", "model": "deepseek/deepseek-v3.2",
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
             "prompt": "v2 body", "llm": "openrouter", "model": "deepseek/deepseek-v3.2",
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

    # Build a valid extracted topic and stamp item ids (mirrors extract_call_topics)
    topic = _valid_topic()
    topic = topics_service._stamp_item_ids(topic, "c1")

    topics_service._persist_topic_update(
        topic=topic,
        topic_id="pt-stub",
        call_id="c1",
    )

    assert captured, "no payload captured — check _persist_topic_update signature"
    payload = captured[0]

    # Required new-shape keys must all be present
    # Note: 'name' is intentionally NOT in topic_updates payload — name lives on
    # the parent `topics` table (written by save_topics on insert). _persist_topic_update
    # writes only the per-call update row.
    # 'summary' is included (NOT NULL legacy column) and defaults to "" when absent.
    # open_questions + decisions were re-added as proper JSONB columns in migration 027 (Story 15.5).
    for k in ("importance", "evidence", "key_terms", "tasks", "status", "summary",
              "open_questions", "decisions"):
        assert k in payload, f"required new-shape key missing: {k}"
    assert "name" not in payload, "topic_updates has no 'name' column — must not be in payload"

    # Status must be rolled up from tasks — one open task → 'open'
    assert payload["status"] == "open"

    # Forbidden legacy keys must not appear (decisions + open_questions are no longer
    # legacy — they were re-added as proper JSONB columns by migration 027 / Story 15.5)
    for legacy in (
        "follow_up_items",
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


# ── Aggregate endpoint payload — must include new fields ──────────────────


def _build_aggregate_test_client(monkeypatch, project_id: str, topic_rows: list[dict]):
    """
    Stand up a TestClient with a fake supabase that serves topic_updates and
    topics rows — used to verify that listing endpoints expose key_terms /
    evidence / tasks in their payload.
    """
    topic_ids = list({r["topic_id"] for r in topic_rows if r.get("topic_id")})

    class _Tbl:
        def __init__(self, name):
            self._name = name
            self._filters: list = []
            self._order_called = False
            self._limit_val = None
            self._lt_filter = None

        def select(self, *_a, **_kw):
            return self

        def eq(self, col, val):
            self._filters.append((col, val))
            return self

        def in_(self, col, vals):
            # Store for use in execute (topics table scoped to prior_call_ids)
            self._filters.append(("__in__", col, vals))
            return self

        def lt(self, col, val):
            self._lt_filter = (col, val)
            return self

        def order(self, *_a, **_kw):
            self._order_called = True
            return self

        def limit(self, n):
            self._limit_val = n
            return self

        def execute(self):
            class _R:
                pass

            r = _R()

            if self._name == "topic_updates":
                # Filter by topic_id eq when listing for a single topic
                tid = next((v for c, v in self._filters if c == "topic_id"), None)
                if tid:
                    filtered = [row for row in topic_rows if row.get("topic_id") == tid]
                else:
                    filtered = list(topic_rows)
                r.data = filtered[: self._limit_val] if self._limit_val else filtered

            elif self._name == "topics":
                r.data = [
                    {
                        "id": tid,
                        "project_id": project_id,
                        "name": f"topic-{tid}",
                        "calls_open": 1,
                        "first_raised_call_id": "c1",
                        "archived": False,
                        "merged_into_topic_id": None,
                    }
                    for tid in topic_ids
                ]

            elif self._name == "calls":
                # Provide enough info for list_topics_prior_to_call
                r.data = [
                    {
                        "id": "c1",
                        "project_id": project_id,
                        "created_at": "2026-01-02T00:00:00+00:00",
                    }
                ]

            elif self._name == "projects":
                r.data = [{"id": project_id, "name": "Project X"}]

            else:
                r.data = []

            return r

    class _DB:
        def table(self, name):
            return _Tbl(name)

    monkeypatch.setattr(topics_service, "get_client", lambda: _DB())

    import importlib

    topics_router = importlib.import_module("backend.routers.topics")
    monkeypatch.setattr(topics_router, "get_client", lambda: _DB())

    from backend.main import app

    return TestClient(app)


_SAMPLE_TOPIC_ROW = {
    "id": "tu1",
    "topic_id": "t1",
    "call_id": "c1",
    "name": "Topic A",
    "importance": "high",
    "status": "open",
    "evidence": [{"speaker": "S", "quote": "Q", "citation": "C"}],
    "key_terms": ["alpha", "beta"],
    "tasks": [
        {
            "task_id": "task-1",
            "task": "do something",
            "next_step": "next",
            "status": "open",
            "owner": "",
        }
    ],
}


def test_list_project_topics_includes_new_fields(monkeypatch):
    """GET /api/projects/{id}/topics must return key_terms, evidence, tasks per topic."""
    client = _build_aggregate_test_client(monkeypatch, "p1", [_SAMPLE_TOPIC_ROW])
    r = client.get("/api/projects/p1/topics")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and len(data) > 0, f"expected non-empty list, got: {data!r}"
    first = data[0]
    for field in ("key_terms", "evidence", "tasks"):
        assert field in first, (
            f"GET /api/projects/p1/topics response missing '{field}'. "
            f"Present keys: {list(first.keys())}"
        )


# ── Round-trip integration: PATCH then verify ──────────────────────────────


def test_round_trip_patch_persists_new_shape(monkeypatch):
    """PATCH a topic with the full new-shape body, then verify all fields persisted.

    Architecture §7 integration seam — ensures backend round-trips don't strip
    fields silently. Mocks supabase; doesn't require migration 026 applied.
    """
    existing = {
        "id": "tu-rt", "call_id": "c1", "topic_id": "t-rt",
        "name": "Original",
        "importance": "medium",
        "key_terms": ["old-term"],
        "evidence": [{"speaker": "Old", "quote": "Old quote", "citation": "Old"}],
        "tasks": [
            {"task_id": "t-old", "task": "old task", "next_step": "old next", "status": "open", "owner": "Old"},
        ],
        "status": "open",
    }
    client, state = _build_patch_test_client(monkeypatch, existing)

    new_body = {
        "name": "RoundTrip",
        "importance": "low",
        "key_terms": ["alpha", "beta", "gamma"],
        "evidence": [
            {"speaker": "S1", "quote": "Q1", "citation": "C1"},
            {"speaker": "S2", "quote": "Q2", "citation": "C2"},
        ],
        "tasks": [
            {"task": "t1", "next_step": "n1", "status": "open",     "owner": "Nick"},
            {"task": "t2", "next_step": "n2", "status": "resolved", "owner": ""},
        ],
    }
    r = client.patch("/api/topics/tu-rt", json=new_body)
    assert r.status_code in (200, 204), r.text

    # Re-fetch the same row through the fake DB (state replicates the persisted row)
    row = state["row"]
    assert row["name"] == "RoundTrip"
    assert row["importance"] == "low"
    assert row["key_terms"] == ["alpha", "beta", "gamma"]
    assert len(row["evidence"]) == 2
    assert row["evidence"][0] == {"speaker": "S1", "quote": "Q1", "citation": "C1"}
    assert len(row["tasks"]) == 2

    # Status rollup: one task open + one resolved → rolled up to "open"
    assert row["status"] == "open"

    # Every task carries a task_id (stamped because new tasks lacked one)
    import uuid
    for task in row["tasks"]:
        assert task.get("task_id")
        uuid.UUID(task["task_id"])

    # Verify no legacy fields leaked into the persisted row from somewhere
    for legacy in ("decisions", "follow_up_items", "open_questions", "rationale", "is_parked", "sentiment"):
        assert legacy not in row, f"legacy field appeared in persisted row: {legacy}"


# ── Story 15.5 — item-stamping (rename _stamp_task_ids → _stamp_item_ids) ──

CALL_ID_SAMPLE = "00000000-1111-2222-3333-444444444444"


def test_stamp_item_ids_adds_uuid_to_tasks_back_compat():
    """Old test renamed: tasks get a task_id (legacy key kept for frontend compat)."""
    t = _valid_topic()
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    for task in stamped["tasks"]:
        assert "task_id" in task
        uuid.UUID(task["task_id"])


def test_stamp_item_ids_preserves_existing_task_ids():
    t = _valid_topic()
    existing = str(uuid.uuid4())
    t["tasks"][0]["task_id"] = existing
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    assert stamped["tasks"][0]["task_id"] == existing


def test_stamp_item_ids_preserves_existing_oq_and_decision_ids():
    """Symmetry — open_questions and decisions also preserve their existing id on re-save."""
    t = _valid_v3_topic()
    existing_oq_id = str(uuid.uuid4())
    existing_d_id = str(uuid.uuid4())
    t["open_questions"][0]["id"] = existing_oq_id
    t["decisions"][0]["id"] = existing_d_id
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    assert stamped["open_questions"][0]["id"] == existing_oq_id
    assert stamped["decisions"][0]["id"] == existing_d_id


def test_stamp_item_ids_stamps_tasks_open_questions_and_decisions():
    """Every item across 3 arrays gets a stable id; tasks use 'task_id', others use 'id'."""
    t = _valid_v3_topic()
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    for task in stamped["tasks"]:
        assert "task_id" in task
        uuid.UUID(task["task_id"])
    for oq in stamped["open_questions"]:
        assert "id" in oq
        uuid.UUID(oq["id"])
    for d in stamped["decisions"]:
        assert "id" in d
        uuid.UUID(d["id"])


def test_stamp_item_ids_stamps_added_in_call_id_on_every_item():
    t = _valid_v3_topic()
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    for task in stamped["tasks"]:
        assert task["added_in_call_id"] == CALL_ID_SAMPLE
    for oq in stamped["open_questions"]:
        assert oq["added_in_call_id"] == CALL_ID_SAMPLE
    for d in stamped["decisions"]:
        assert d["added_in_call_id"] == CALL_ID_SAMPLE


def test_stamp_item_ids_preserves_existing_added_in_call_id():
    """Re-save round-trip: items keep their original first-call provenance."""
    t = _valid_v3_topic()
    original_call = "ffffffff-1111-2222-3333-444444444444"
    t["tasks"][0]["added_in_call_id"] = original_call
    t["open_questions"][0]["added_in_call_id"] = original_call
    t["decisions"][0]["added_in_call_id"] = original_call
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    assert stamped["tasks"][0]["added_in_call_id"] == original_call
    assert stamped["open_questions"][0]["added_in_call_id"] == original_call
    assert stamped["decisions"][0]["added_in_call_id"] == original_call


def test_stamp_item_ids_handles_missing_arrays():
    """Topic dict without open_questions / decisions keys returns those keys as []."""
    t = _valid_topic()
    stamped = topics_service._stamp_item_ids(t, CALL_ID_SAMPLE)
    assert stamped["open_questions"] == []
    assert stamped["decisions"] == []


# ── Story 15.5 — _persist_topic_update writes open_questions + decisions ──


def test_persist_payload_includes_open_questions_and_decisions(monkeypatch):
    """_persist_topic_update writes open_questions + decisions to the topic_updates payload."""
    captured = {}

    class _FakeExec:
        def __init__(self, payload):
            self._payload = payload
        def execute(self):
            class _R:
                data = [{"id": "row-1"}]
            return _R()

    class _FakeTable:
        def insert(self, payload):
            captured["payload"] = payload
            return _FakeExec(payload)

    class _FakeClient:
        def table(self, name):
            assert name == "topic_updates"
            return _FakeTable()

    monkeypatch.setattr(topics_service, "get_client", lambda: _FakeClient())

    topic = _valid_v3_topic()
    topics_service._persist_topic_update(topic, "topic-1", "call-1")

    assert "open_questions" in captured["payload"]
    assert "decisions" in captured["payload"]
    assert captured["payload"]["open_questions"] == topic["open_questions"]
    assert captured["payload"]["decisions"] == topic["decisions"]


def test_persist_payload_handles_missing_arrays_as_empty(monkeypatch):
    """When extraction returns a topic without the new keys, persist []."""
    captured = {}

    class _FakeExec:
        def execute(self):
            class _R:
                data = [{"id": "row-1"}]
            return _R()

    class _FakeTable:
        def insert(self, payload):
            captured["payload"] = payload
            return _FakeExec()

    class _FakeClient:
        def table(self, name):
            assert name == "topic_updates"
            return _FakeTable()

    monkeypatch.setattr(topics_service, "get_client", lambda: _FakeClient())

    topic = _valid_topic()  # no open_questions/decisions keys
    topics_service._persist_topic_update(topic, "topic-1", "call-1")

    assert captured["payload"]["open_questions"] == []
    assert captured["payload"]["decisions"] == []


def test_persist_payload_does_not_write_chronology_fields(monkeypatch):
    """Story 15.7 owns chronology_narrative + rag_verification_note. Story 15.5 must not write them."""
    captured = {}

    class _FakeExec:
        def execute(self):
            class _R:
                data = [{"id": "row-1"}]
            return _R()

    class _FakeTable:
        def insert(self, payload):
            captured["payload"] = payload
            return _FakeExec()

    class _FakeClient:
        def table(self, name):
            return _FakeTable()

    monkeypatch.setattr(topics_service, "get_client", lambda: _FakeClient())

    topics_service._persist_topic_update(_valid_v3_topic(), "topic-1", "call-1")

    assert "chronology_narrative" not in captured["payload"]
    assert "rag_verification_note" not in captured["payload"]


# ── Story 15.5 — PATCH /api/topics accepts open_questions + decisions partial fields ──


def test_patch_topic_accepts_open_questions_partial(monkeypatch):
    """PATCH /topics/{id} accepts open_questions; stamps id + added_in_call_id."""
    from backend.routers import topics as topics_router

    captured = {}

    class _Tbl:
        def __init__(self, name):
            self.name = name
            self._sel = None
        def select(self, cols):
            self._sel = cols
            return self
        def eq(self, k, v):
            self._eq = (k, v)
            return self
        def update(self, payload):
            captured["payload"] = payload
            return self
        def execute(self):
            if self.name == "topic_updates" and self._sel == "call_id":
                class R: data = [{"call_id": "call-99"}]
                return R()
            class R: data = [{"id": "topic-row-1", **captured.get("payload", {})}]
            return R()

    class _DB:
        def table(self, name): return _Tbl(name)

    monkeypatch.setattr(topics_router, "get_client", lambda: _DB())

    import asyncio
    body = topics_router.TopicPatch(
        open_questions=[{"text": "Does the boost flag fix it?", "status": "open", "owner": ""}]
    )
    asyncio.run(topics_router.patch_topic("topic-row-1", body))

    assert "open_questions" in captured["payload"]
    oq = captured["payload"]["open_questions"][0]
    assert "id" in oq
    uuid.UUID(oq["id"])
    assert oq["added_in_call_id"] == "call-99"


def test_patch_topic_accepts_decisions_partial(monkeypatch):
    """PATCH accepts decisions; stamps id + added_in_call_id."""
    from backend.routers import topics as topics_router

    captured = {}

    class _Tbl:
        def __init__(self, name):
            self.name = name
            self._sel = None
        def select(self, cols):
            self._sel = cols
            return self
        def eq(self, k, v):
            self._eq = (k, v)
            return self
        def update(self, payload):
            captured["payload"] = payload
            return self
        def execute(self):
            if self.name == "topic_updates" and self._sel == "call_id":
                class R: data = [{"call_id": "call-99"}]
                return R()
            class R: data = [{"id": "topic-row-1", **captured.get("payload", {})}]
            return R()

    class _DB:
        def table(self, name): return _Tbl(name)

    monkeypatch.setattr(topics_router, "get_client", lambda: _DB())

    import asyncio
    body = topics_router.TopicPatch(
        decisions=[{"text": "Defer Mac retirement decision to Q3 review."}]
    )
    asyncio.run(topics_router.patch_topic("topic-row-1", body))

    assert "decisions" in captured["payload"]
    d = captured["payload"]["decisions"][0]
    uuid.UUID(d["id"])
    assert d["added_in_call_id"] == "call-99"


def test_patch_topic_accepts_open_questions_and_decisions_together(monkeypatch):
    """Single PATCH call can update both new arrays in one round-trip."""
    from backend.routers import topics as topics_router

    captured = {}

    class _Tbl:
        def __init__(self, name):
            self.name = name
            self._sel = None
        def select(self, cols):
            self._sel = cols
            return self
        def eq(self, k, v):
            self._eq = (k, v)
            return self
        def update(self, payload):
            captured["payload"] = payload
            return self
        def execute(self):
            if self.name == "topic_updates" and self._sel == "call_id":
                class R: data = [{"call_id": "call-99"}]
                return R()
            class R: data = [{"id": "topic-row-1", **captured.get("payload", {})}]
            return R()

    class _DB:
        def table(self, name): return _Tbl(name)

    monkeypatch.setattr(topics_router, "get_client", lambda: _DB())

    import asyncio
    body = topics_router.TopicPatch(
        open_questions=[{"text": "Q?", "status": "open", "owner": ""}],
        decisions=[{"text": "D"}],
    )
    asyncio.run(topics_router.patch_topic("topic-row-1", body))

    assert "open_questions" in captured["payload"]
    assert "decisions" in captured["payload"]
    assert captured["payload"]["open_questions"][0]["added_in_call_id"] == "call-99"
    assert captured["payload"]["decisions"][0]["added_in_call_id"] == "call-99"
