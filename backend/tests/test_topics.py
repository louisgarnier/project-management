import pytest
from pydantic import ValidationError
from backend.services.topics_service import TopicIn, TopicUpdate, TopicOut, BriefOut


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
