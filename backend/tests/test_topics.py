import pytest
from pydantic import ValidationError
import unittest
import asyncio
from unittest.mock import patch, MagicMock
from backend.services.topics_service import TopicIn, TopicUpdate, TopicOut, BriefItem, BriefOut, extract_call_topics, aggregate_topics


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
        name="X", summary="y", follow_up_items=[], decisions=[],
        status="invalid", owner="Us", sentiment="neutral",
    )
    assert t.status == "open"


def test_topic_in_normalizes_sentiment():
    """Known sentiment synonyms are mapped; truly unknown values fall back to 'neutral'."""
    t_bad = TopicIn(
        name="X", summary="y", follow_up_items=[], decisions=[],
        status="open", owner="Us", sentiment="bad",
    )
    assert t_bad.sentiment == "concern"  # "bad" → concern

    t_unknown = TopicIn(
        name="X", summary="y", follow_up_items=[], decisions=[],
        status="open", owner="Us", sentiment="unknown_xyz",
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
        name="X", summary="y", follow_up_items=[], decisions=[],
        status="open", owner="BadValue", sentiment="neutral",
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

CALL_ID    = "aaaaaaaa-0000-0000-0000-000000000001"
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



TOPIC_ID  = "cccccccc-0000-0000-0000-000000000001"
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

    payload = [{
        "topic_id": TOPIC_ID2,
        "name": "Pricing",
        "summary": "Not discussed.",
        "follow_up_items": [],
        "decisions": [],
        "status": "open",
        "owner": "Client",
        "sentiment": "concern",
        "disposition": "keep_as_is",
    }]
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
            {"topic_id": TOPIC_ID, "name": "Pricing", "calls_open": 3,
             "sentiment": "concern", "last_summary": "Monthly pref.", "last_follow_up_items": []},
            {"topic_id": TOPIC_ID2, "name": "SLA", "calls_open": 1,
             "sentiment": "neutral", "last_summary": "In progress.", "last_follow_up_items": []},
        ],
        "decisions_to_confirm": [{"text": "DPA signed", "topic_name": "Legal"}],
        "watch_list": [
            {"topic_id": TOPIC_ID, "name": "Pricing", "calls_open": 3,
             "sentiment": "concern", "last_summary": "Monthly pref.", "last_follow_up_items": []},
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
def test_get_project_topics_returns_non_archived(mock_gc):
    m = MagicMock()

    # Mock: topics query (non-archived topics)
    topics_mock = MagicMock()
    topics_mock.data = [
        {"id": TOPIC_ID, "name": "Pricing", "calls_open": 2,
         "first_raised_call_id": CALL_ID},
    ]
    # Mock: topic_updates query (latest update per topic)
    updates_mock = MagicMock()
    updates_mock.data = [
        {"summary": "Monthly pref.", "follow_up_items": ["Send breakdown"],
         "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"},
    ]

    # Chain the mocks: topics select → eq(project_id) → eq(archived) → execute
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = topics_mock
    # topic_updates: select → eq(topic_id) → order → limit → execute
    m.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = updates_mock
    mock_gc.return_value = m

    r = http.get(f"/api/projects/{PROJECT_ID}/topics")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "Pricing"
    assert body[0]["status"] == "open"
    assert body[0]["calls_open"] == 2


def test_get_topics_prompt_returns_stored_prompt():
    """_get_topics_prompt returns (prompt, llm) when a row exists."""
    from backend.services.topics_service import _get_topics_prompt
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .order.return_value.limit.return_value.execute.return_value.data = [
            {"prompt": "STORED PROMPT", "llm": "groq"}
        ]
    prompt, llm = _get_topics_prompt("proj-1", mock_db)
    assert prompt == "STORED PROMPT"
    assert llm == "groq"


def test_get_topics_prompt_falls_back_to_none():
    """_get_topics_prompt returns (None, None) when no row exists."""
    from backend.services.topics_service import _get_topics_prompt
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .order.return_value.limit.return_value.execute.return_value.data = []
    prompt, llm = _get_topics_prompt("proj-1", mock_db)
    assert prompt is None
    assert llm is None


@patch("backend.services.topics_service.get_client")
def test_validate_call_advances_to_artifacts(mock_gc):
    """validate_call must advance the call to 'artifacts', not 'done'."""
    import asyncio
    from backend.services.topics_service import validate_call

    mock_db = MagicMock()

    def table_side(name):
        m = MagicMock()
        if name == "topic_updates":
            m.select.return_value.eq.return_value.execute.return_value.data = [{"topic_id": "topic-1"}]
        elif name == "calls":
            m.select.return_value.eq.return_value.execute.return_value.data = [{"project_id": "proj-1"}]
            m.update.return_value.eq.return_value.execute.return_value.data = [{"kanban_stage": "artifacts"}]
        elif name == "topics":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
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
    def test_extract_call_topics_happy_path(self, mock_llm, mock_gc):
        """Returns flat list of topics from transcript only."""
        db = MagicMock()
        mock_gc.return_value = db
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"project_id": "proj-1", "transcript": "We discussed the budget and timeline."}
        ]
        db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"default_llm": "groq"}]

        async def fake_llm(prompt, llm):
            return [
                {"name": "Budget", "summary": "Discussed Q2 budget", "follow_up_items": [],
                 "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral"}
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
                m.select.return_value.eq.return_value.execute.return_value.data = [{"project_id": "proj-1"}]
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
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

        with patch("backend.services.topics_service.list_topics_prior_to_call", return_value=[]):
            with patch("backend.services.topics_service._get_topics_prompt", return_value=(None, "groq")):
                call_topics = [{"name": "Budget", "summary": "Q2 budget", "follow_up_items": [],
                                "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral"}]
                result = self._run(aggregate_topics("call-1", call_topics))

        self.assertTrue(result.get("auto_advanced"))
        self.assertEqual(result["call_number"], 1)

    @patch("backend.services.topics_service.get_client")
    def test_aggregate_call2_advances_to_project_matching(self, mock_gc):
        """Call 2: previous topics exist → saves pending_topics, advances to project_matching."""
        db = MagicMock()
        mock_gc.return_value = db

        prev_topic = {"topic_id": "t-1", "name": "Budget", "calls_open": 1,
                      "summary": "old summary", "follow_up_items": [], "decisions": [],
                      "status": "open", "owner": "Us", "sentiment": "neutral"}

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "calls":
                m.select.return_value.eq.return_value.execute.return_value.data = [{"project_id": "proj-1"}]
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "call-0"}]
                m.update.return_value.eq.return_value.execute.return_value.data = [{}]
            elif table_name == "topics":
                m.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = [{"id": "t-1"}]
            else:
                m.select.return_value.eq.return_value.execute.return_value.data = []
            return m
        db.table.side_effect = table_side_effect

        call_topics = [
            {"name": "Budget", "summary": "Budget discussed", "follow_up_items": [],
             "decisions": [], "status": "in_progress", "owner": "Us", "sentiment": "neutral"},
            {"name": "Timeline", "summary": "New topic", "follow_up_items": [],
             "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"},
        ]
        with patch("backend.services.topics_service.list_topics_prior_to_call", return_value=[prev_topic]):
            with patch("backend.services.topics_service._get_topics_prompt", return_value=(None, "groq")):
                result = self._run(aggregate_topics("call-1", call_topics))

        self.assertEqual(result["advanced_to"], "project_matching")
        self.assertEqual(result["call_number"], 2)


class TestTopicsTimeline(unittest.TestCase):

    @patch("backend.services.topics_service.get_client")
    def test_timeline_no_topics(self, mock_gc):
        """Empty project returns empty topics list and empty calls list."""
        from backend.services.topics_service import list_topics_timeline
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
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
            {"id": "c3", "title": "Follow-up", "call_number": 3, "kanban_stage": "done"},
        ]
        topics = [{"id": "t1", "name": "Risk Model", "first_raised_call_id": "c2"}]
        updates = [
            {
                "topic_id": "t1", "call_id": "c2",
                "summary": "First discussion", "follow_up_items": ["item1"],
                "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral",
            }
        ]
        latest = [{"id": "t1", "status": "open", "owner": "Us", "sentiment": "neutral"}]

        topics_call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = calls
            elif name == "topics":
                # First call: active topics (archived=False), Second call: archived (archived=True)
                topics_call_count["n"] += 1
                if topics_call_count["n"] == 1:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = topics
                elif topics_call_count["n"] == 2:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                else:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                m.select.return_value.in_.return_value.execute.return_value.data = latest
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = updates
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
                "topic_id": "t1", "call_id": "c1",
                "summary": "Raised", "follow_up_items": [], "decisions": [],
                "status": "open", "owner": "Us", "sentiment": "neutral",
            },
            {
                "topic_id": "t1", "call_id": "c2",
                "summary": "Resolved now", "follow_up_items": [], "decisions": [],
                "status": "resolved", "owner": "Us", "sentiment": "positive",
            },
        ]
        latest = [{"id": "t1", "status": "resolved", "owner": "Us", "sentiment": "positive"}]

        topics_call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = calls
            elif name == "topics":
                topics_call_count["n"] += 1
                if topics_call_count["n"] == 1:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = topics
                else:
                    m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                m.select.return_value.in_.return_value.execute.return_value.data = latest
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = updates
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
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = calls
                # Second query: fetch pending_topics/extraction_cache for calls without updates
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "c1", "pending_topics": None, "extraction_cache": None}
                ]
            elif name == "topics":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                m.select.return_value.in_.return_value.execute.return_value.data = []
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = []
                m.select.return_value.in_.return_value.order.return_value.execute.return_value.data = []
            return m
        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        self.assertEqual(len(result["calls"]), 1)
        self.assertEqual(result["topics"], [])

    @patch("backend.services.topics_service.get_client")
    def test_timeline_includes_pending_rows_for_calls_without_topic_updates(self, mock_gc):
        """Calls at call_topics stage with extraction_cache but no topic_updates
        appear in the timeline as pending rows with type='pending'."""
        from backend.services.topics_service import list_topics_timeline
        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "call_topics"},
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
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = calls
                # Second query: fetch pending_topics/extraction_cache for calls without updates
                m.select.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "c1", "pending_topics": None, "extraction_cache": extraction_cache}
                ]
            elif name == "topics":
                # No committed topics
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                m.select.return_value.in_.return_value.execute.return_value.data = []
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.in_.return_value.execute.return_value.data = []
                m.select.return_value.in_.return_value.order.return_value.execute.return_value.data = []
            return m
        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)

        # Should have 2 pending topic rows
        self.assertEqual(len(result["topics"]), 2)

        # All topic_ids should start with "pending:"
        for topic in result["topics"]:
            self.assertTrue(
                topic["topic_id"].startswith("pending:"),
                f"Expected topic_id to start with 'pending:', got {topic['topic_id']}"
            )

        # Each should have a call_updates entry for c1 with type="pending"
        for topic in result["topics"]:
            self.assertIn("c1", topic["call_updates"])
            self.assertEqual(topic["call_updates"]["c1"]["type"], "pending")

        # Summaries should be preserved from extraction_cache
        summaries = {t["name"]: t["call_updates"]["c1"]["summary"] for t in result["topics"]}
        self.assertEqual(summaries["Pricing"], "Client prefers monthly billing.")
        self.assertEqual(summaries["Timeline"], "Q3 deadline confirmed.")

        # call_updates must have exactly one key (no not_discussed for other calls)
        for topic in result["topics"]:
            self.assertEqual(len(topic["call_updates"]), 1, "pending row must have exactly one call_updates entry")

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
