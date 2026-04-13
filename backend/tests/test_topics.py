import pytest
from pydantic import ValidationError
import unittest
import asyncio
from unittest.mock import patch, MagicMock
from backend.services.topics_service import TopicIn, TopicUpdate, TopicOut, BriefItem, BriefOut, extract_call_topics


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


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.extract_topics")
def test_extract_call1_returns_flat_list(mock_extract, mock_gc):
    """POST /extract on Call 1 returns a flat list with no buckets."""
    mock_gc.return_value = MagicMock()
    async def _fake():
        return {
            "call_number": 1,
            "followed_up": [],
            "not_discussed": [],
            "new_topics": [SAMPLE_TOPIC],
        }
    mock_extract.return_value = _fake()

    r = http.post(f"/api/calls/{CALL_ID}/topics/extract")
    assert r.status_code == 200
    body = r.json()
    assert body["call_number"] == 1
    assert len(body["new_topics"]) == 1
    assert body["new_topics"][0]["name"] == "Pricing"


@patch("backend.routers.topics.get_client")
@patch("backend.routers.topics.extract_topics")
def test_extract_call2_returns_three_buckets(mock_extract, mock_gc):
    """POST /extract on Call 2+ returns followed_up, not_discussed, new_topics."""
    mock_gc.return_value = MagicMock()
    async def _fake():
        return {
            "call_number": 2,
            "followed_up": [SAMPLE_TOPIC],
            "not_discussed": [{**SAMPLE_TOPIC, "name": "Legal Review"}],
            "new_topics": [{**SAMPLE_TOPIC, "name": "Support SLA"}],
        }
    mock_extract.return_value = _fake()

    r = http.post(f"/api/calls/{CALL_ID}/topics/extract")
    assert r.status_code == 200
    body = r.json()
    assert body["call_number"] == 2
    assert len(body["followed_up"]) == 1
    assert len(body["not_discussed"]) == 1
    assert body["not_discussed"][0]["name"] == "Legal Review"
    assert len(body["new_topics"]) == 1
    assert body["new_topics"][0]["name"] == "Support SLA"


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
