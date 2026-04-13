import pytest
from pydantic import ValidationError
from backend.services.topics_service import TopicIn, TopicUpdate, TopicOut, BriefItem, BriefOut


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


def test_topic_in_rejects_bad_status():
    with pytest.raises(ValidationError):
        TopicIn(
            name="X", summary="y", follow_up_items=[], decisions=[],
            status="invalid", owner="Us", sentiment="neutral",
        )


def test_topic_in_rejects_bad_sentiment():
    with pytest.raises(ValidationError):
        TopicIn(
            name="X", summary="y", follow_up_items=[], decisions=[],
            status="open", owner="Us", sentiment="bad",
        )


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


def test_topic_in_rejects_bad_owner():
    with pytest.raises(ValidationError):
        TopicIn(
            name="X", summary="y", follow_up_items=[], decisions=[],
            status="open", owner="BadValue", sentiment="neutral",
        )


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
