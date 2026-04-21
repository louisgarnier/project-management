"""Tests for GET /api/topics/{topic_id}/evidence (Story 10.3).

Uses the same MagicMock chaining pattern as test_topic_lineage.py: db.table.side_effect
dispatches per table name; each table returns a MagicMock whose .select()/.eq()/.in_()
calls build up a query that .execute() finally resolves against fixture data.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


# --------------------------------------------------------------------------- #
# Fixture builder
# --------------------------------------------------------------------------- #


def _make_evidence_db(
    topics_by_id: dict,
    sources_by_parent: dict | None = None,
    updates_by_topic_id: dict | None = None,
    calls_by_id: dict | None = None,
    match_groups_by_call: dict | None = None,
):
    """MagicMock DB that answers everything the evidence handler needs.

    Serves:
      - topics: .select(...).eq("id", val) / .eq("merged_into_topic_id", val)
      - topic_updates: .select(...).in_("topic_id", ids).order("created_at")
      - calls: .select(...).eq("id", val)
      - topic_match_groups: .select(...).eq("call_id", val)
    """
    sources_by_parent = sources_by_parent or {}
    updates_by_topic_id = updates_by_topic_id or {}
    calls_by_id = calls_by_id or {}
    match_groups_by_call = match_groups_by_call or {}

    db = MagicMock()

    def table_side(name):
        t = MagicMock()

        if name == "topics":
            select = MagicMock()
            t.select.return_value = select

            def eq_side(col, val):
                result = MagicMock()
                if col == "id":
                    result.execute.return_value.data = (
                        [topics_by_id[val]] if val in topics_by_id else []
                    )
                elif col == "merged_into_topic_id":
                    result.execute.return_value.data = sources_by_parent.get(val, [])
                else:
                    result.execute.return_value.data = []
                return result

            select.eq.side_effect = eq_side
            return t

        if name == "topic_updates":
            select = MagicMock()
            t.select.return_value = select

            def in_side(col, values):
                assert col == "topic_id"
                result = MagicMock()
                order = MagicMock()
                result.order.return_value = order
                rows = []
                for tid in values:
                    rows.extend(updates_by_topic_id.get(tid, []))
                rows = sorted(rows, key=lambda r: r["created_at"])
                order.execute.return_value.data = rows
                return result

            select.in_.side_effect = in_side
            return t

        if name == "calls":
            select = MagicMock()
            t.select.return_value = select

            def eq_side(col, val):
                assert col == "id"
                result = MagicMock()
                result.execute.return_value.data = (
                    [calls_by_id[val]] if val in calls_by_id else []
                )
                return result

            select.eq.side_effect = eq_side
            return t

        if name == "topic_match_groups":
            select = MagicMock()
            t.select.return_value = select

            def eq_side(col, val):
                assert col == "call_id"
                result = MagicMock()
                result.execute.return_value.data = match_groups_by_call.get(val, [])
                return result

            select.eq.side_effect = eq_side
            return t

        return t

    db.table.side_effect = table_side
    return db


# --------------------------------------------------------------------------- #
# Test 1 — 404 on missing topic
# --------------------------------------------------------------------------- #


@patch("backend.routers.topics.get_client")
def test_evidence_404_on_missing_topic(mock_gc):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_gc.return_value = mock_db

    r = TestClient(app).get("/api/topics/nonexistent/evidence")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Test 2 — No-lineage topic returns single-node lineage
# --------------------------------------------------------------------------- #


@patch("backend.routers.topics.get_client")
def test_evidence_no_lineage_single_node(mock_gc):
    mock_gc.return_value = _make_evidence_db(
        topics_by_id={
            "t1": {
                "id": "t1", "name": "API design", "archived": False,
                "merged_into_topic_id": None,
            },
        },
        sources_by_parent={},
        updates_by_topic_id={
            "t1": [{
                "topic_id": "t1", "call_id": "call-1",
                "summary": "initial design discussed",
                "transcript_excerpt": "we want REST",
                "follow_up_items": [], "decisions": [],
                "status": "open", "owner": "Us", "sentiment": "neutral",
                "created_at": "2026-04-10T09:00:00Z",
            }],
        },
        calls_by_id={
            "call-1": {
                "id": "call-1", "title": "Kickoff",
                "created_at": "2026-04-10T08:00:00Z",
                "pending_topics": None,
                "verification_cache": None,
            },
        },
    )

    r = TestClient(app).get("/api/topics/t1/evidence")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["topic_id"] == "t1"
    assert body["topic_name"] == "API design"
    assert len(body["lineage"]) == 1
    assert body["lineage"][0]["topic_id"] == "t1"
    assert body["lineage"][0]["archived"] is False
    assert body["lineage"][0]["merged_into_topic_id"] is None

    assert len(body["calls"]) == 1
    c = body["calls"][0]
    assert c["source_topic_id"] == "t1"
    assert c["source_topic_name"] == "API design"
    assert c["call_title"] == "Kickoff"
    assert c["call_id"] == "call-1"
    assert c["raw_extract"] is None
    assert c["match_group"] is None
    assert c["not_discussed_verification"] is None
    assert c["is_not_discussed"] is False


# --------------------------------------------------------------------------- #
# Test 3 — M:N-merged topic: lineage + interleaved calls
# --------------------------------------------------------------------------- #


@patch("backend.routers.topics.get_client")
def test_evidence_mn_merge_lineage_and_interleaved_calls(mock_gc):
    """Merged topic C with archived sources A and B.
    A has a row on call-1, B has a row on call-1, C has a row on call-2.
    Endpoint for C returns lineage = [C, A, B] and 3 chronological calls.
    """
    mock_gc.return_value = _make_evidence_db(
        topics_by_id={
            "c": {"id": "c", "name": "API strategy", "archived": False,
                  "merged_into_topic_id": None},
            "a": {"id": "a", "name": "REST API",     "archived": True,
                  "merged_into_topic_id": "c"},
            "b": {"id": "b", "name": "GraphQL API",  "archived": True,
                  "merged_into_topic_id": "c"},
        },
        sources_by_parent={
            "c": [
                {"id": "a", "name": "REST API",    "archived": True, "merged_into_topic_id": "c"},
                {"id": "b", "name": "GraphQL API", "archived": True, "merged_into_topic_id": "c"},
            ],
        },
        updates_by_topic_id={
            "a": [{"topic_id": "a", "call_id": "call-1", "summary": "REST raised",
                   "transcript_excerpt": "REST here",
                   "follow_up_items": [], "decisions": [],
                   "status": "open", "owner": "Us", "sentiment": "neutral",
                   "created_at": "2026-04-01T10:00:00Z"}],
            "b": [{"topic_id": "b", "call_id": "call-1", "summary": "GraphQL raised",
                   "transcript_excerpt": "GraphQL here",
                   "follow_up_items": [], "decisions": [],
                   "status": "open", "owner": "Us", "sentiment": "neutral",
                   "created_at": "2026-04-01T10:30:00Z"}],
            "c": [{"topic_id": "c", "call_id": "call-2", "summary": "Merged",
                   "transcript_excerpt": "consolidation",
                   "follow_up_items": [], "decisions": ["go REST"],
                   "status": "resolved", "owner": "Us", "sentiment": "positive",
                   "created_at": "2026-04-08T10:00:00Z"}],
        },
        calls_by_id={
            "call-1": {"id": "call-1", "title": "Kickoff",
                       "created_at": "2026-04-01T09:00:00Z",
                       "pending_topics": None, "verification_cache": None},
            "call-2": {"id": "call-2", "title": "Consolidation",
                       "created_at": "2026-04-08T09:00:00Z",
                       "pending_topics": None, "verification_cache": None},
        },
    )

    r = TestClient(app).get("/api/topics/c/evidence")
    assert r.status_code == 200, r.text
    body = r.json()

    # Lineage: self + 2 sources
    lineage_ids = [n["topic_id"] for n in body["lineage"]]
    assert lineage_ids[0] == "c"
    assert set(lineage_ids) == {"c", "a", "b"}
    assert len(body["lineage"]) == 3

    # Calls: 3 entries, chronological (created_at order → a-row, b-row, c-row)
    assert len(body["calls"]) == 3
    assert body["calls"][0]["source_topic_id"] in {"a", "b"}
    assert body["calls"][1]["source_topic_id"] in {"a", "b"}
    assert body["calls"][0]["source_topic_id"] != body["calls"][1]["source_topic_id"]
    assert body["calls"][2]["source_topic_id"] == "c"

    # Call-date formatting (ISO, present)
    for c in body["calls"]:
        assert c["call_date"] is not None


# --------------------------------------------------------------------------- #
# Test 4 — raw_extract populated from pending_topics by name
# --------------------------------------------------------------------------- #


@patch("backend.routers.topics.get_client")
def test_evidence_raw_extract_from_pending_topics(mock_gc):
    mock_gc.return_value = _make_evidence_db(
        topics_by_id={
            "t1": {"id": "t1", "name": "REST API", "archived": False,
                   "merged_into_topic_id": None},
        },
        sources_by_parent={},
        updates_by_topic_id={
            "t1": [{"topic_id": "t1", "call_id": "call-1", "summary": "merged",
                    "transcript_excerpt": "we picked REST",
                    "follow_up_items": ["benchmark"],
                    "decisions": ["go REST"],
                    "status": "open", "owner": "Us", "sentiment": "neutral",
                    "created_at": "2026-04-10T09:00:00Z"}],
        },
        calls_by_id={
            "call-1": {
                "id": "call-1", "title": "Kickoff",
                "created_at": "2026-04-10T08:00:00Z",
                "pending_topics": [
                    {
                        "name": "  rest api  ",  # case + whitespace diff — must still match
                        "summary": "raw extracted summary",
                        "follow_up_items": ["raw-fu-1", "raw-fu-2"],
                        "decisions": ["raw-decision"],
                    },
                    {
                        "name": "Unrelated",
                        "summary": "nope",
                        "follow_up_items": [],
                        "decisions": [],
                    },
                ],
                "verification_cache": None,
            },
        },
    )

    r = TestClient(app).get("/api/topics/t1/evidence")
    assert r.status_code == 200, r.text
    body = r.json()

    assert len(body["calls"]) == 1
    raw = body["calls"][0]["raw_extract"]
    assert raw is not None
    assert raw["summary"] == "raw extracted summary"
    assert raw["follow_up_items"] == ["raw-fu-1", "raw-fu-2"]
    assert raw["decisions"] == ["raw-decision"]


# --------------------------------------------------------------------------- #
# Test 5 — match_group populated
# --------------------------------------------------------------------------- #


@patch("backend.routers.topics.get_client")
def test_evidence_match_group_populated(mock_gc):
    mock_gc.return_value = _make_evidence_db(
        topics_by_id={
            "t1": {"id": "t1", "name": "REST API", "archived": False,
                   "merged_into_topic_id": None},
        },
        sources_by_parent={},
        updates_by_topic_id={
            "t1": [{"topic_id": "t1", "call_id": "call-1", "summary": "discussed",
                    "transcript_excerpt": "...",
                    "follow_up_items": [], "decisions": [],
                    "status": "open", "owner": "Us", "sentiment": "neutral",
                    "created_at": "2026-04-10T09:00:00Z"}],
        },
        calls_by_id={
            "call-1": {"id": "call-1", "title": "Kickoff",
                       "created_at": "2026-04-10T08:00:00Z",
                       "pending_topics": None, "verification_cache": None},
        },
        match_groups_by_call={
            "call-1": [
                {"project_topic_ids": ["t1"],
                 "call_topic_names": ["REST discussion", "API follow-up"]},
                {"project_topic_ids": ["other-id"],
                 "call_topic_names": ["other"]},
            ],
        },
    )

    r = TestClient(app).get("/api/topics/t1/evidence")
    assert r.status_code == 200, r.text
    body = r.json()

    mg = body["calls"][0]["match_group"]
    assert mg is not None
    assert mg["project_topic_ids"] == ["t1"]
    assert mg["call_topic_names"] == ["REST discussion", "API follow-up"]


# --------------------------------------------------------------------------- #
# Test 6 — not_discussed_verification populated
# --------------------------------------------------------------------------- #


@patch("backend.routers.topics.get_client")
def test_evidence_not_discussed_verification_populated(mock_gc):
    mock_gc.return_value = _make_evidence_db(
        topics_by_id={
            "t1": {"id": "t1", "name": "Pricing", "archived": False,
                   "merged_into_topic_id": None},
        },
        sources_by_parent={},
        updates_by_topic_id={
            "t1": [{"topic_id": "t1", "call_id": "call-1", "summary": "brought up",
                    "transcript_excerpt": "...",
                    "follow_up_items": [], "decisions": [],
                    "status": "open", "owner": "Us", "sentiment": "neutral",
                    "created_at": "2026-04-10T09:00:00Z"}],
        },
        calls_by_id={
            "call-1": {
                "id": "call-1", "title": "Kickoff",
                "created_at": "2026-04-10T08:00:00Z",
                "pending_topics": None,
                "verification_cache": {
                    "t1": {
                        "discussed": False,
                        "transcript_excerpt": None,
                        "reasoning": "Pricing was not mentioned in this call.",
                    },
                },
            },
        },
    )

    r = TestClient(app).get("/api/topics/t1/evidence")
    assert r.status_code == 200, r.text
    body = r.json()

    v = body["calls"][0]["not_discussed_verification"]
    assert v is not None
    assert v["discussed"] is False
    assert v["transcript_excerpt"] is None
    assert v["reasoning"] == "Pricing was not mentioned in this call."
