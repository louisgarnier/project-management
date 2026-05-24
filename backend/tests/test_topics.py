import pytest
from pydantic import ValidationError
import unittest
import asyncio
from unittest.mock import patch, MagicMock
from backend.services.topics_service import (
    TopicIn,
    TopicUpdate,
    TopicOut,
    BriefItem,
    BriefOut,
    extract_call_topics,
    aggregate_topics,
)


def test_topic_in_valid():
    t = TopicIn(
        name="Pricing",
        summary="Client pushed back on annual plan.",
        follow_up_items=["Send monthly breakdown"],
        decisions=["Monthly billing preferred"],
        status="open",
        owner="Client",
        sentiment="concern",
    )
    assert t.name == "Pricing"
    assert t.status == "open"


def test_topic_in_normalizes_status():
    """Unknown status values fall back to 'open' rather than raising."""
    t = TopicIn(
        name="X",
        summary="y",
        follow_up_items=[],
        decisions=[],
        status="invalid",
        owner="Us",
        sentiment="neutral",
    )
    assert t.status == "open"


def test_topic_in_normalizes_sentiment():
    """Known sentiment synonyms are mapped; truly unknown values fall back to 'neutral'."""
    t_bad = TopicIn(
        name="X",
        summary="y",
        follow_up_items=[],
        decisions=[],
        status="open",
        owner="Us",
        sentiment="bad",
    )
    assert t_bad.sentiment == "concern"  # "bad" → concern

    t_unknown = TopicIn(
        name="X",
        summary="y",
        follow_up_items=[],
        decisions=[],
        status="open",
        owner="Us",
        sentiment="unknown_xyz",
    )
    assert t_unknown.sentiment == "neutral"  # truly unknown → neutral


def test_topic_update_has_disposition():
    tu = TopicUpdate(
        topic_id="aaaaaaaa-0000-0000-0000-000000000001",
        name="Pricing",
        summary="Not discussed.",
        follow_up_items=[],
        decisions=[],
        status="open",
        owner="Client",
        sentiment="concern",
        disposition="keep_as_is",
    )
    assert tu.disposition == "keep_as_is"


def test_brief_out_shape():
    b = BriefOut(priority_topics=[], decisions_to_confirm=[], watch_list=[])
    assert b.priority_topics == []


def test_topic_in_normalizes_owner():
    """Unknown owner values fall back to 'Us' rather than raising."""
    t = TopicIn(
        name="X",
        summary="y",
        follow_up_items=[],
        decisions=[],
        status="open",
        owner="BadValue",
        sentiment="neutral",
    )
    assert t.owner == "Us"


def test_brief_item_valid():
    bi = BriefItem(
        topic_id="aaaaaaaa-0000-0000-0000-000000000001",
        name="Pricing",
        calls_open=2,
        sentiment="concern",
        last_summary="Client pushed back.",
        last_follow_up_items=["Send breakdown"],
    )
    assert bi.sentiment == "concern"
    assert bi.calls_open == 2


def test_topic_update_new_topic_no_id():
    """topic_id=None signals a brand-new topic (not yet in DB)."""
    tu = TopicUpdate(
        topic_id=None,
        name="New Topic",
        summary="Just came up.",
        follow_up_items=[],
        decisions=[],
        status="open",
        owner="Us",
        sentiment="neutral",
        disposition=None,
    )
    assert tu.topic_id is None
    assert tu.disposition is None


import json
from unittest.mock import AsyncMock, MagicMock, patch
from backend.main import app
from fastapi.testclient import TestClient

http = TestClient(app)

CALL_ID = "aaaaaaaa-0000-0000-0000-000000000001"
PROJECT_ID = "bbbbbbbb-0000-0000-0000-000000000001"

SAMPLE_TOPIC = {
    "name": "Pricing",
    "summary": "Client prefers monthly billing.",
    "follow_up_items": ["Send monthly breakdown"],
    "decisions": [],
    "status": "open",
    "owner": "Client",
    "sentiment": "concern",
}


TOPIC_ID = "cccccccc-0000-0000-0000-000000000001"
TOPIC_ID2 = "cccccccc-0000-0000-0000-000000000002"


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.save_topics")
def test_save_topics_returns_200(mock_save, mock_gc):
    mock_gc.return_value = MagicMock()
    mock_save.return_value = {"saved": 2}

    payload = [
        {
            "topic_id": None,
            "name": "Pricing",
            "summary": "Monthly preferred.",
            "follow_up_items": ["Send breakdown"],
            "decisions": [],
            "status": "open",
            "owner": "Client",
            "sentiment": "concern",
            "disposition": None,
        },
        {
            "topic_id": TOPIC_ID,
            "name": "Legal Review",
            "summary": "DPA signed.",
            "follow_up_items": [],
            "decisions": ["DPA signed off"],
            "status": "resolved",
            "owner": "Us",
            "sentiment": "positive",
            "disposition": None,
        },
    ]
    r = http.post(f"/api/calls/{CALL_ID}/topics", json=payload)
    assert r.status_code == 200
    assert r.json()["saved"] == 2


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.save_topics")
def test_save_topics_keep_as_is_disposition(mock_save, mock_gc):
    """keep_as_is disposition on a not-discussed topic still gets saved."""
    mock_gc.return_value = MagicMock()
    mock_save.return_value = {"saved": 1}

    payload = [
        {
            "topic_id": TOPIC_ID2,
            "name": "Pricing",
            "summary": "Not discussed.",
            "follow_up_items": [],
            "decisions": [],
            "status": "open",
            "owner": "Client",
            "sentiment": "concern",
            "disposition": "keep_as_is",
        }
    ]
    r = http.post(f"/api/calls/{CALL_ID}/topics", json=payload)
    assert r.status_code == 200
    mock_save.assert_called_once()


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.validate_call")
def test_validate_advances_to_done(mock_validate, mock_gc):
    mock_gc.return_value = MagicMock()
    mock_validate.return_value = {"kanban_stage": "artifacts"}

    r = http.post(f"/api/calls/{CALL_ID}/topics/validate")
    assert r.status_code == 200
    assert r.json()["kanban_stage"] == "artifacts"


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.validate_call")
def test_validate_returns_422_no_topics(mock_validate, mock_gc):
    mock_gc.return_value = MagicMock()
    mock_validate.side_effect = ValueError("no_topics")

    r = http.post(f"/api/calls/{CALL_ID}/topics/validate")
    assert r.status_code == 422


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.validate_call")
def test_validate_returns_422_unacknowledged(mock_validate, mock_gc):
    mock_gc.return_value = MagicMock()
    mock_validate.side_effect = ValueError(
        f"unacknowledged_topics:{TOPIC_ID},{TOPIC_ID2}"
    )

    r = http.post(f"/api/calls/{CALL_ID}/topics/validate")
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["error"] == "unacknowledged_topics"
    assert TOPIC_ID in body["detail"]["ids"]


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.generate_brief")
def test_brief_call1_returns_empty(mock_brief, mock_gc):
    """Call 1 has no prior topics — brief is empty."""
    mock_gc.return_value = MagicMock()
    mock_brief.return_value = {
        "priority_topics": [],
        "decisions_to_confirm": [],
        "watch_list": [],
    }

    r = http.get(f"/api/calls/{CALL_ID}/brief")
    assert r.status_code == 200
    body = r.json()
    assert body["priority_topics"] == []
    assert body["watch_list"] == []


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.generate_brief")
def test_brief_call2_returns_sorted_topics(mock_brief, mock_gc):
    """Call 2 brief: priority topics sorted by calls_open desc, concern first."""
    mock_gc.return_value = MagicMock()
    mock_brief.return_value = {
        "priority_topics": [
            {
                "topic_id": TOPIC_ID,
                "name": "Pricing",
                "calls_open": 3,
                "sentiment": "concern",
                "last_summary": "Monthly pref.",
                "last_follow_up_items": [],
            },
            {
                "topic_id": TOPIC_ID2,
                "name": "SLA",
                "calls_open": 1,
                "sentiment": "neutral",
                "last_summary": "In progress.",
                "last_follow_up_items": [],
            },
        ],
        "decisions_to_confirm": [{"text": "DPA signed", "topic_name": "Legal"}],
        "watch_list": [
            {
                "topic_id": TOPIC_ID,
                "name": "Pricing",
                "calls_open": 3,
                "sentiment": "concern",
                "last_summary": "Monthly pref.",
                "last_follow_up_items": [],
            },
        ],
    }

    r = http.get(f"/api/calls/{CALL_ID}/brief")
    assert r.status_code == 200
    body = r.json()
    assert len(body["priority_topics"]) == 2
    assert body["priority_topics"][0]["calls_open"] == 3
    assert len(body["watch_list"]) == 1
    assert len(body["decisions_to_confirm"]) == 1


@patch("backend.routers.topics.get_client")
def test_get_project_topics_returns_non_archived(mock_gc, monkeypatch):
    m = MagicMock()
    mock_gc.return_value = m

    # Mock get_project_topic_state to return unified view
    fake_state = [
        {
            "topic_id": TOPIC_ID,
            "name": "Pricing",
            "summary": "Monthly pref.",
            "status": "open",
            "sentiment": "concern",
            "importance": "medium",
            "calls_open": 2,
            "first_raised_call_id": CALL_ID,
            "key_terms": [],
            "tasks": [],
            "open_questions": [],
            "decisions": [],
            "evidence": [],
            "chronology_narrative": None,
            "rag_verification_note": None,
            "latest_update_at": None,
        },
    ]
    monkeypatch.setattr(
        "backend.services.topics_service.get_project_topic_state",
        lambda project_id, db=None: fake_state,
    )

    r = http.get(f"/api/projects/{PROJECT_ID}/topics")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "Pricing"
    assert body[0]["status"] == "open"
    assert body[0]["calls_open"] == 2


def test_get_topics_prompt_returns_stored_prompt():
    """_get_topics_prompt returns (prompt, llm, model) when a row exists."""
    from backend.services.topics_service import _get_topics_prompt
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"prompt": "STORED PROMPT", "llm": "groq", "model": None}
    ]
    prompt, llm, model = _get_topics_prompt("proj-1", mock_db)
    assert prompt == "STORED PROMPT"
    assert llm == "groq"
    assert model is None


def test_get_topics_prompt_falls_back_to_none():
    """_get_topics_prompt returns (None, None, None) when no row exists."""
    from backend.services.topics_service import _get_topics_prompt
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = (
        []
    )
    prompt, llm, model = _get_topics_prompt("proj-1", mock_db)
    assert prompt is None
    assert llm is None
    assert model is None


@patch("backend.services.topics_service.get_client")
def test_validate_call_advances_to_artifacts(mock_gc):
    """validate_call must advance the call to 'artifacts', not 'done'."""
    import asyncio
    from backend.services.topics_service import validate_call

    mock_db = MagicMock()

    def table_side(name):
        m = MagicMock()
        if name == "topic_updates":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"topic_id": "topic-1"}
            ]
        elif name == "calls":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"project_id": "proj-1"}
            ]
            m.update.return_value.eq.return_value.execute.return_value.data = [
                {"kanban_stage": "artifacts"}
            ]
        elif name == "topics":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                []
            )
        return m

    mock_db.table.side_effect = table_side
    mock_gc.return_value = mock_db

    result = asyncio.run(validate_call("call-1"))
    assert result["kanban_stage"] == "artifacts"


class TestExtractCallTopics(unittest.TestCase):

    def _run(self, coro):
        return asyncio.run(coro)

    @patch("backend.services.topics_service.get_client")
    @patch("backend.services.topics_service._call_llm")
    @patch("backend.services.topics_service._resolve_call_topics_prompt")
    def test_extract_call_topics_happy_path(self, mock_resolve, mock_llm, mock_gc):
        """Returns flat list of v2-schema topics from transcript."""
        db = MagicMock()
        mock_gc.return_value = db

        # _resolve_call_topics_prompt is patched out; returns (prompt_body, llm, model, name)
        mock_resolve.return_value = ("STUB_PROMPT", "openrouter", None, "test-lib-entry")

        # extract_call_topics queries: calls (project_id+transcript), projects (context)
        def table_side(name):
            t = MagicMock()
            if name == "calls":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"project_id": "proj-1", "transcript": "We discussed the budget."}
                ]
            elif name == "projects":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"context": ""}
                ]
            return t

        db.table.side_effect = table_side

        async def fake_llm(prompt, llm, *, model=None):
            # v2 schema — must satisfy _validate_topic
            return [
                {
                    "name": "Budget",
                    "importance": "high",
                    "key_terms": ["Q2", "budget"],
                    "evidence": [
                        {
                            "speaker": "Alice",
                            "quote": "We need to review the budget.",
                            "citation": "transcript 2026-01-01 · lines 1-2",
                        }
                    ],
                    "tasks": [
                        {
                            "task": "Review Q2 budget",
                            "next_step": "Alice to send draft by Friday.",
                            "status": "open",
                            "owner": "Alice",
                        }
                    ],
                }
            ]

        mock_llm.side_effect = fake_llm

        result = self._run(extract_call_topics("call-1"))

        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["name"], "Budget")

    @patch("backend.services.topics_service.get_client")
    def test_extract_call_topics_no_transcript(self, mock_gc):
        """Raises ValueError when transcript is empty."""
        db = MagicMock()
        mock_gc.return_value = db
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"project_id": "proj-1", "transcript": ""}
        ]
        with self.assertRaises(ValueError) as ctx:
            self._run(extract_call_topics("call-1"))
        self.assertEqual(str(ctx.exception), "no_transcript")


class TestAggregateTopics(unittest.TestCase):

    def _run(self, coro):
        return asyncio.run(coro)

    @patch("backend.services.topics_service.get_client")
    @patch("backend.services.topics_service.save_topics")
    def test_aggregate_call1_auto_advances(self, mock_save, mock_gc):
        """Call 1: no previous topics → saves all as new, returns auto_advanced=True."""
        db = MagicMock()
        mock_gc.return_value = db

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "calls":
                m.select.return_value.eq.return_value.execute.return_value.data = [
                    {"project_id": "proj-1"}
                ]
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                    []
                )
                m.update.return_value.eq.return_value.execute.return_value.data = [{}]
            elif table_name == "topic_updates":
                m.select.return_value.eq.return_value.execute.return_value.data = []
                m.delete.return_value.eq.return_value.execute.return_value.data = []
            else:
                m.select.return_value.eq.return_value.execute.return_value.data = []
            return m

        db.table.side_effect = table_side_effect

        async def fake_save(call_id, topics):
            return {"saved": len(topics)}

        mock_save.side_effect = fake_save

        with patch(
            "backend.services.topics_service.list_topics_prior_to_call", return_value=[]
        ):
            with patch(
                "backend.services.topics_service._get_topics_prompt",
                return_value=(None, "groq", None),
            ):
                call_topics = [
                    {
                        "name": "Budget",
                        "summary": "Q2 budget",
                        "follow_up_items": [],
                        "decisions": [],
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                    }
                ]
                result = self._run(aggregate_topics("call-1", call_topics))

        self.assertTrue(result.get("auto_advanced"))
        self.assertEqual(result["call_number"], 1)

    @patch("backend.services.topics_service.get_client")
    def test_aggregate_call2_advances_to_project_matching(self, mock_gc):
        """Call 2: previous topics exist → saves pending_topics, advances to project_matching."""
        db = MagicMock()
        mock_gc.return_value = db

        prev_topic = {
            "topic_id": "t-1",
            "name": "Budget",
            "calls_open": 1,
            "summary": "old summary",
            "follow_up_items": [],
            "decisions": [],
            "status": "open",
            "owner": "Us",
            "sentiment": "neutral",
        }

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "calls":
                m.select.return_value.eq.return_value.execute.return_value.data = [
                    {"project_id": "proj-1"}
                ]
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "call-0"}
                ]
                m.update.return_value.eq.return_value.execute.return_value.data = [{}]
            elif table_name == "topics":
                m.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = [
                    {"id": "t-1"}
                ]
            else:
                m.select.return_value.eq.return_value.execute.return_value.data = []
            return m

        db.table.side_effect = table_side_effect

        call_topics = [
            {
                "name": "Budget",
                "summary": "Budget discussed",
                "follow_up_items": [],
                "decisions": [],
                "status": "in_progress",
                "owner": "Us",
                "sentiment": "neutral",
            },
            {
                "name": "Timeline",
                "summary": "New topic",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Client",
                "sentiment": "concern",
            },
        ]
        with patch(
            "backend.services.topics_service.list_topics_prior_to_call",
            return_value=[prev_topic],
        ):
            with patch(
                "backend.services.topics_service._get_topics_prompt",
                return_value=(None, "groq", None),
            ):
                result = self._run(aggregate_topics("call-1", call_topics))

        self.assertEqual(result["advanced_to"], "project_matching")
        self.assertEqual(result["call_number"], 2)


class TestTopicsTimeline(unittest.TestCase):

    @patch("backend.services.topics_service.get_client")
    def test_timeline_no_topics(self, mock_gc):
        """Empty project returns empty topics list and empty calls list."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
            []
        )
        db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = (
            []
        )
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
            []
        )
        result = list_topics_timeline("proj-1", db)
        self.assertEqual(result["calls"], [])
        self.assertEqual(result["topics"], [])

    @patch("backend.services.topics_service.get_client")
    def test_timeline_new_and_not_discussed(self, mock_gc):
        """Topic raised in call 2 appears as new in call 2, not_discussed in call 3, absent in call 1."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
            {"id": "c2", "title": "Review", "call_number": 2, "kanban_stage": "done"},
            {
                "id": "c3",
                "title": "Follow-up",
                "call_number": 3,
                "kanban_stage": "done",
            },
        ]
        topics = [{"id": "t1", "name": "Risk Model", "first_raised_call_id": "c2"}]
        updates = [
            {
                "topic_id": "t1",
                "call_id": "c2",
                "summary": "First discussion",
                "follow_up_items": ["item1"],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            }
        ]
        latest = [{"id": "t1", "status": "open", "owner": "Us", "sentiment": "neutral"}]

        topics_call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    calls
                )
            elif name == "topics":
                # First call: active topics (archived=False), Second call: archived (archived=True)
                topics_call_count["n"] += 1
                if topics_call_count["n"] == 1:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        topics
                    )
                elif topics_call_count["n"] == 2:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        []
                    )
                else:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        []
                    )
                m.select.return_value.in_.return_value.execute.return_value.data = (
                    latest
                )
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = (
                    updates
                )
            return m

        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        self.assertEqual(len(result["calls"]), 3)
        self.assertEqual(len(result["topics"]), 1)

        t = result["topics"][0]
        self.assertNotIn("c1", t["call_updates"])
        self.assertEqual(t["call_updates"]["c2"]["type"], "new")
        self.assertEqual(t["call_updates"]["c2"]["summary"], "First discussion")
        self.assertEqual(t["call_updates"]["c3"]["type"], "not_discussed")

    @patch("backend.services.topics_service.get_client")
    def test_timeline_marks_merge_result_with_has_sources(self, mock_gc):
        """An active topic that is the target of M:N merges (archived topics
        pointing to it via merged_into_topic_id) gets has_sources=True and
        source_names populated. Powers the '+ new (merged)' cell label."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
            {"id": "c2", "title": "Review", "call_number": 2, "kanban_stage": "done"},
        ]
        # Active topic 'c' is the merge target; archived 'a' and 'b' point to it.
        active = [
            {
                "id": "c",
                "name": "API strategy",
                "first_raised_call_id": "c2",
                "archived": False,
                "merged_into_topic_id": None,
            }
        ]
        archived = [
            {
                "id": "a",
                "name": "REST API",
                "first_raised_call_id": "c1",
                "archived": True,
                "merged_into_topic_id": "c",
            },
            {
                "id": "b",
                "name": "GraphQL API",
                "first_raised_call_id": "c1",
                "archived": True,
                "merged_into_topic_id": "c",
            },
        ]
        updates = [
            {
                "topic_id": "c",
                "call_id": "c2",
                "summary": "merged",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
            {
                "topic_id": "a",
                "call_id": "c1",
                "summary": "REST raised",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
            {
                "topic_id": "b",
                "call_id": "c1",
                "summary": "GraphQL raised",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
        ]
        latest = [
            {"id": "c", "status": "open", "owner": "Us", "sentiment": "neutral"},
            {"id": "a", "status": "open", "owner": "Us", "sentiment": "neutral"},
            {"id": "b", "status": "open", "owner": "Us", "sentiment": "neutral"},
        ]

        topics_call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    calls
                )
            elif name == "topics":
                topics_call_count["n"] += 1
                if topics_call_count["n"] == 1:
                    # active
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        active
                    )
                elif topics_call_count["n"] == 2:
                    # archived
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        archived
                    )
                # .select("id, name").in_("id", [...]).execute().data → merged-name lookup
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "c", "name": "API strategy"},
                ]
            elif name == "topic_updates":
                # updates query: .select(...).in_().in_().execute()
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = (
                    updates
                )
                # latest_updates query: .select(...).in_().order().execute()
                m.select.return_value.in_.return_value.order.return_value.execute.return_value.data = [
                    {
                        "topic_id": "c",
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                        "created_at": "2026-04-08",
                    },
                    {
                        "topic_id": "a",
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                        "created_at": "2026-04-01",
                    },
                    {
                        "topic_id": "b",
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                        "created_at": "2026-04-01",
                    },
                ]
            return m

        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        merged_target = next(t for t in result["topics"] if t["topic_id"] == "c")
        self.assertTrue(merged_target["has_sources"])
        self.assertEqual(
            sorted(merged_target["source_names"]), ["GraphQL API", "REST API"]
        )
        # Archived sources have has_sources=False (they're leaves, not targets)
        for tid in ("a", "b"):
            src = next(t for t in result["topics"] if t["topic_id"] == tid)
            self.assertFalse(src["has_sources"])
            self.assertEqual(src["source_names"], [])

    @patch("backend.services.topics_service.get_client")
    def test_timeline_returns_ancestor_topic_ids_and_merge_call_id(self, mock_gc):
        """Merge-result topics expose ancestor_topic_ids (ordered by ancestor
        first_raised_call_id); archived rows expose merge_call_id (the call where
        they were folded in). Powers Story 10.9 chevron + indented rendering."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
            {"id": "c2", "title": "Review", "call_number": 2, "kanban_stage": "done"},
        ]
        active = [
            {
                "id": "merged",
                "name": "API Strategy",
                "first_raised_call_id": "c2",
                "archived": False,
                "merged_into_topic_id": None,
            }
        ]
        archived = [
            {
                "id": "a",
                "name": "REST API",
                "first_raised_call_id": "c1",
                "archived": True,
                "merged_into_topic_id": "merged",
            },
            {
                "id": "b",
                "name": "GraphQL API",
                "first_raised_call_id": "c1",
                "archived": True,
                "merged_into_topic_id": "merged",
            },
        ]
        updates = [
            {
                "topic_id": "merged",
                "call_id": "c2",
                "summary": "Unified API",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
            {
                "topic_id": "a",
                "call_id": "c1",
                "summary": "REST discussed",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
            {
                "topic_id": "b",
                "call_id": "c1",
                "summary": "GraphQL discussed",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
        ]

        topics_call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    calls
                )
            elif name == "topics":
                topics_call_count["n"] += 1
                if topics_call_count["n"] == 1:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        active
                    )
                elif topics_call_count["n"] == 2:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        archived
                    )
                # merged-name lookup
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "merged", "name": "API Strategy"}
                ]
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = (
                    updates
                )
                m.select.return_value.in_.return_value.order.return_value.execute.return_value.data = [
                    {
                        "topic_id": "merged",
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                        "created_at": "2026-04-08",
                    },
                    {
                        "topic_id": "a",
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                        "created_at": "2026-04-01",
                    },
                    {
                        "topic_id": "b",
                        "status": "open",
                        "owner": "Us",
                        "sentiment": "neutral",
                        "created_at": "2026-04-01",
                    },
                ]
            return m

        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        merged_target = next(t for t in result["topics"] if t["topic_id"] == "merged")
        self.assertEqual(merged_target.get("ancestor_topic_ids"), ["a", "b"])
        for tid in ("a", "b"):
            src = next(t for t in result["topics"] if t["topic_id"] == tid)
            self.assertEqual(src.get("merge_call_id"), "c2")

    @patch("backend.services.topics_service.get_client")
    def test_timeline_followed_up_and_absent(self, mock_gc):
        """Topic raised in call 1 and followed up in call 2."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
            {"id": "c2", "title": "Review", "call_number": 2, "kanban_stage": "done"},
        ]
        topics = [{"id": "t1", "name": "Dashboard", "first_raised_call_id": "c1"}]
        updates = [
            {
                "topic_id": "t1",
                "call_id": "c1",
                "summary": "Raised",
                "follow_up_items": [],
                "decisions": [],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
            {
                "topic_id": "t1",
                "call_id": "c2",
                "summary": "Resolved now",
                "follow_up_items": [],
                "decisions": [],
                "status": "resolved",
                "owner": "Us",
                "sentiment": "positive",
            },
        ]
        latest = [
            {"id": "t1", "status": "resolved", "owner": "Us", "sentiment": "positive"}
        ]

        topics_call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    calls
                )
            elif name == "topics":
                topics_call_count["n"] += 1
                if topics_call_count["n"] == 1:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        topics
                    )
                else:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                        []
                    )
                m.select.return_value.in_.return_value.execute.return_value.data = (
                    latest
                )
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = (
                    updates
                )
            return m

        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        t = result["topics"][0]
        self.assertEqual(t["call_updates"]["c1"]["type"], "new")
        self.assertEqual(t["call_updates"]["c2"]["type"], "followed_up")
        self.assertEqual(t["call_updates"]["c2"]["status"], "resolved")

    @patch("backend.services.topics_service.get_client")
    def test_timeline_calls_exist_no_topics(self, mock_gc):
        """When calls exist but project has no topics and no extraction_cache,
        returns calls list with empty topics."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
        ]

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                # First query: list calls for project
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    calls
                )
                # Second query: fetch pending_topics/extraction_cache for calls without updates
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "c1", "pending_topics": None, "extraction_cache": None}
                ]
            elif name == "topics":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                    []
                )
                m.select.return_value.in_.return_value.execute.return_value.data = []
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = (
                    []
                )
                m.select.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    []
                )
            return m

        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        self.assertEqual(len(result["calls"]), 1)
        self.assertEqual(result["topics"], [])

    @patch("backend.services.topics_service.get_client")
    def test_timeline_includes_pending_rows_for_calls_without_topic_updates(
        self, mock_gc
    ):
        """Calls at call_topics stage with extraction_cache but no topic_updates
        appear in the timeline as pending rows with type='pending'."""
        from backend.services.topics_service import list_topics_timeline

        db = MagicMock()

        calls = [
            {
                "id": "c1",
                "title": "Kickoff",
                "call_number": 1,
                "kanban_stage": "call_topics",
            },
        ]
        extraction_cache = [
            {
                "name": "Pricing",
                "summary": "Client prefers monthly billing.",
                "follow_up_items": ["Send breakdown"],
                "decisions": [],
                "status": "open",
                "owner": "Client",
                "sentiment": "concern",
            },
            {
                "name": "Timeline",
                "summary": "Q3 deadline confirmed.",
                "follow_up_items": [],
                "decisions": ["Q3 deadline"],
                "status": "open",
                "owner": "Us",
                "sentiment": "neutral",
            },
        ]

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                # First query: list calls for project (with .in_ for kanban stages + .order)
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    calls
                )
                # Second query: fetch pending_topics/extraction_cache for calls without updates
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {
                        "id": "c1",
                        "pending_topics": None,
                        "extraction_cache": extraction_cache,
                    }
                ]
            elif name == "topics":
                # No committed topics
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
                    []
                )
                m.select.return_value.in_.return_value.execute.return_value.data = []
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = (
                    []
                )
                m.select.return_value.in_.return_value.order.return_value.execute.return_value.data = (
                    []
                )
            return m

        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)

        # Should have 2 pending topic rows
        self.assertEqual(len(result["topics"]), 2)

        # All topic_ids should start with "pending:"
        for topic in result["topics"]:
            self.assertTrue(
                topic["topic_id"].startswith("pending:"),
                f"Expected topic_id to start with 'pending:', got {topic['topic_id']}",
            )

        # Each should have a call_updates entry for c1 with type="pending"
        for topic in result["topics"]:
            self.assertIn("c1", topic["call_updates"])
            self.assertEqual(topic["call_updates"]["c1"]["type"], "pending")

        # Summaries should be preserved from extraction_cache
        summaries = {
            t["name"]: t["call_updates"]["c1"]["summary"] for t in result["topics"]
        }
        self.assertEqual(summaries["Pricing"], "Client prefers monthly billing.")
        self.assertEqual(summaries["Timeline"], "Q3 deadline confirmed.")

        # call_updates must have exactly one key (no not_discussed for other calls)
        for topic in result["topics"]:
            self.assertEqual(
                len(topic["call_updates"]),
                1,
                "pending row must have exactly one call_updates entry",
            )

        # Verify field mapping for Pricing topic
        pricing = next(t for t in result["topics"] if t["name"] == "Pricing")
        self.assertEqual(pricing["first_raised_call_id"], "c1")
        self.assertEqual(pricing["status"], "open")
        self.assertEqual(pricing["owner"], "Client")
        self.assertEqual(pricing["sentiment"], "concern")
        pricing_cell = pricing["call_updates"]["c1"]
        self.assertEqual(pricing_cell["type"], "pending")
        self.assertEqual(pricing_cell["owner"], "Client")
        self.assertEqual(pricing_cell["sentiment"], "concern")
        self.assertEqual(pricing_cell["follow_up_items"], ["Send breakdown"])
        self.assertEqual(pricing_cell["decisions"], [])

        # Verify field mapping for Timeline topic
        timeline = next(t for t in result["topics"] if t["name"] == "Timeline")
        self.assertEqual(timeline["first_raised_call_id"], "c1")
        timeline_cell = timeline["call_updates"]["c1"]
        self.assertEqual(timeline_cell["type"], "pending")
        self.assertEqual(timeline_cell["decisions"], ["Q3 deadline"])
        self.assertEqual(timeline_cell["follow_up_items"], [])


@patch("backend.routers.topics.get_client")
def test_promote_not_discussed_inserts_ptid_only_match_group(mock_gc):
    """Promoting a not-discussed topic persists a ptid-only match group so
    subsequent merge re-runs treat it as an Updated Topic, not not-discussed.
    """
    mock_db = MagicMock()
    mock_gc.return_value = mock_db
    # No pre-existing group for this topic
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
        []
    )

    r = http.post(
        f"/api/calls/{CALL_ID}/topics/promote-not-discussed",
        json={"topic_id": TOPIC_ID},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["created"] is True

    # Verify insert was called on topic_match_groups with the correct payload
    insert_calls = [
        call
        for call in mock_db.table.return_value.insert.call_args_list
        if call.args and call.args[0].get("call_id") == CALL_ID
    ]
    assert len(insert_calls) == 1
    inserted = insert_calls[0].args[0]
    assert inserted["project_topic_ids"] == [TOPIC_ID]
    assert inserted["call_topic_names"] == []


@patch("backend.routers.topics.get_client")
def test_promote_not_discussed_is_idempotent(mock_gc):
    """Calling promote twice for the same topic does not duplicate the match group."""
    mock_db = MagicMock()
    mock_gc.return_value = mock_db
    # Pre-existing ptid-only group for this topic
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"project_topic_ids": [TOPIC_ID], "call_topic_names": []}
    ]

    r = http.post(
        f"/api/calls/{CALL_ID}/topics/promote-not-discussed",
        json={"topic_id": TOPIC_ID},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "created": False}
    # Insert should not have been called because the group already exists
    mock_db.table.return_value.insert.assert_not_called()


def test_list_topics_prior_to_call_includes_archived_later():
    """Topic X raised in Call 1, archived via M:N merge in Call 2, should still
    appear on Call 2's matching page with archived_later=True and the
    merged_into_name populated so the UI can render a visual cue.
    """
    from backend.services.topics_service import list_topics_prior_to_call

    call1_at = "2026-04-01T00:00:00Z"
    call2_at = "2026-04-08T00:00:00Z"

    mock_db = MagicMock()

    topics_call_count = {"n": 0}

    def table_side_effect(name):
        m = MagicMock()
        if name == "calls":
            # Chain 1: .select("created_at").eq("id", call2).execute().data → current call
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"created_at": call2_at}
            ]
            # Chain 2: .select("id").eq("project_id", …).lt("created_at", …) → prior calls
            m.select.return_value.eq.return_value.lt.return_value.execute.return_value.data = [
                {"id": "call-1"}
            ]

            # Chain 3: all_call_rows — .select("id, created_at").eq("project_id", …).execute()
            # Needs to overwrite the first chain's default .select.return_value.eq.return_value
            # — use a side_effect on .eq so we can branch on the selected columns.
            def eq_side(col, val):
                result = MagicMock()
                if col == "id" and val == "call-2":
                    result.execute.return_value.data = [{"created_at": call2_at}]
                elif col == "project_id":
                    # Chained as prior_calls OR all_call_rows.
                    # The prior_calls chain adds .lt(...), all_call_rows goes direct to .execute().
                    result.lt.return_value.execute.return_value.data = [
                        {"id": "call-1"}
                    ]
                    result.execute.return_value.data = [
                        {"id": "call-1", "created_at": call1_at},
                        {"id": "call-2", "created_at": call2_at},
                    ]
                return result

            m.select.return_value.eq.side_effect = eq_side
        elif name == "topics":
            topics_call_count["n"] += 1
            if topics_call_count["n"] == 1:
                # Main query: .select(...).eq("project_id").in_("first_raised_call_id") — returns all topics raised by prior calls
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
                    # Active Call-1 topic still alive
                    {
                        "id": "survivor",
                        "name": "Survivor",
                        "calls_open": 1,
                        "first_raised_call_id": "call-1",
                        "archived": False,
                        "merged_into_topic_id": None,
                    },
                    # Call-1 topic archived via M:N merge in Call 2
                    {
                        "id": "archived-via-call-2",
                        "name": "Old REST",
                        "calls_open": 1,
                        "first_raised_call_id": "call-1",
                        "archived": True,
                        "merged_into_topic_id": "merge-target-c2",
                    },
                ]
            else:
                # merge-target lookup: .select("id, name, first_raised_call_id").in_("id", [...])
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {
                        "id": "merge-target-c2",
                        "name": "API Strategy",
                        "first_raised_call_id": "call-2",
                    },
                ]
        elif name == "topic_updates":
            m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {
                    "summary": "s",
                    "follow_up_items": [],
                    "decisions": [],
                    "status": "open",
                    "owner": "Us",
                    "sentiment": "neutral",
                }
            ]
        return m

    mock_db.table.side_effect = table_side_effect

    result = list_topics_prior_to_call("call-2", "proj-1", mock_db)

    # Should include BOTH the survivor AND the archived-via-later-merge topic
    names = {t["name"] for t in result}
    assert names == {"Survivor", "Old REST"}

    survivor = next(t for t in result if t["name"] == "Survivor")
    assert survivor["archived_later"] is False
    assert survivor["merged_into_name"] is None

    archived_later = next(t for t in result if t["name"] == "Old REST")
    assert archived_later["archived_later"] is True
    assert archived_later["merged_into_name"] == "API Strategy"


def test_topic_in_accepts_new_fields():
    t = TopicIn(
        name="Risk model selection",
        summary="Benchmark gates Phase 2 kickoff.",
        follow_up_items=["Nick: run benchmark"],
        decisions=["Phase 2 gated on benchmark."],
        open_questions=["Does MC Mac's ceiling apply with caching?"],
        status="open",
        owner="Us",
        sentiment="concern",
        is_parked=False,
        importance="high",
        rationale="All 4 criteria met.",
    )
    assert t.open_questions == ["Does MC Mac's ceiling apply with caching?"]
    assert t.is_parked is False
    assert t.importance == "high"
    assert t.rationale == "All 4 criteria met."


def test_topic_in_defaults_for_new_fields():
    """New fields are optional with sensible defaults — backwards compat for old callers."""
    t = TopicIn(
        name="X",
        summary="y",
        follow_up_items=[],
        decisions=[],
        status="open",
        owner="Us",
        sentiment="neutral",
    )
    assert t.open_questions == []
    assert t.is_parked is False
    assert t.importance == "medium"
    assert t.rationale == ""


def test_topic_in_importance_validation():
    """Importance is restricted to high/medium/low."""
    with pytest.raises(ValidationError):
        TopicIn(
            name="X",
            summary="y",
            follow_up_items=[],
            decisions=[],
            status="open",
            owner="Us",
            sentiment="neutral",
            importance="critical",  # invalid — must raise
        )


@pytest.mark.skip(
    reason="EPIC-15: Python-constant fallback removed from extract_call_topics. "
    "Prompt is now resolved library-only via _resolve_call_topics_prompt; "
    "no CALL_TOPICS_DEFAULT_PROMPT Python fallback exists. "
    "Also imports removed CALL_TOPICS_DEFAULT_PROMPT alias."
)
def test_extract_call_topics_uses_new_default_prompt(monkeypatch):
    """When no stored prompt is set, extract_call_topics uses CALL_TOPICS_DEFAULT_PROMPT."""
    from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT  # noqa: F401

    captured = {}

    async def fake_call_llm(prompt, llm, *, model=None):
        captured["prompt"] = prompt
        return []

    mock_client = MagicMock()
    # Stub first query: calls table → returns one row with project_id + transcript
    calls_select = MagicMock()
    calls_select.execute.return_value.data = [
        {"project_id": "p1", "transcript": "Some call transcript text."}
    ]
    # Stub second query: projects table → returns default_llm + context
    projects_select = MagicMock()
    projects_select.execute.return_value.data = [{"default_llm": "groq", "context": ""}]
    # Stub third query: topics vocabulary — empty
    topics_select = MagicMock()
    topics_select.execute.return_value.data = []

    # table('calls').select('project_id, transcript').eq('id', call_id).execute()
    # table('projects').select('default_llm, context').eq('id', project_id).execute()
    # table('topics').select('name').eq('project_id', project_id).eq('archived', False).execute()
    def table_side_effect(name):
        tbl = MagicMock()
        if name == "calls":
            tbl.select.return_value.eq.return_value = calls_select
        elif name == "projects":
            tbl.select.return_value.eq.return_value = projects_select
        elif name == "topics":
            tbl.select.return_value.eq.return_value.eq.return_value = topics_select
        return tbl

    mock_client.table.side_effect = table_side_effect

    monkeypatch.setattr("backend.services.topics_service._call_llm", fake_call_llm)
    monkeypatch.setattr(
        "backend.services.topics_service._get_topics_prompt",
        lambda project_id, db, category="call_topics": (None, None, None),
    )
    monkeypatch.setattr(
        "backend.services.topics_service.get_client", lambda: mock_client
    )

    asyncio.run(extract_call_topics("call1"))

    assert "[ROLE]" in captured["prompt"]
    assert "[RUBRIC]" in captured["prompt"]
    assert CALL_TOPICS_DEFAULT_PROMPT in captured["prompt"]


def test_get_previous_topics_uses_unified_view(monkeypatch):
    """EPIC-18: _get_previous_topics now reads from project_topic_state view."""
    from backend.services.topics_service import _get_previous_topics
    from unittest.mock import MagicMock

    fake_state = [
        {"topic_id": "t-1", "name": "ARM", "summary": "Risk", "status": "open",
         "sentiment": "neutral", "importance": "high", "calls_open": 2,
         "first_raised_call_id": "c-1", "key_terms": ["LMAC"], "tasks": [{"task": "x"}],
         "open_questions": [], "decisions": [], "evidence": [],
         "chronology_narrative": None, "rag_verification_note": None,
         "latest_update_at": None},
    ]
    monkeypatch.setattr(
        "backend.services.topics_service.get_project_topic_state",
        lambda project_id, db=None: fake_state,
    )
    out = _get_previous_topics("proj-1", MagicMock())
    assert len(out) == 1
    assert out[0]["name"] == "ARM"
    assert out[0]["key_terms"] == ["LMAC"]
    assert out[0]["tasks"][0]["task"] == "x"
    # Legacy keys still populated for frontend back-compat
    assert out[0]["follow_up_items"] == []
    assert out[0]["owner"] == "Us"
    assert out[0]["is_parked"] is False
    assert out[0]["rationale"] == ""
