"""Tests for Stage 6 — registry reconciliation (pure code)."""

from backend.services.call_topics_v5.stage_6_reconcile import reconcile_with_registry


def test_canonical_match_no_proposal():
    clusters = [
        {"topic_name": "ARM", "unit_ids": ["u_0001"], "new_topic": False, "importance": "high"},
    ]
    registry = [{"id": "r1", "name": "ARM", "description": ""}]
    out = reconcile_with_registry(clusters, registry)
    assert len(out["working_topics"]) == 1
    assert out["working_topics"][0]["registry_id"] == "r1"
    assert out["working_topics"][0]["provisional"] is False
    assert out["new_topic_proposals"] == []


def test_new_proposal_with_suggested_match():
    """New topic with strong lexical similarity to registry → suggested_match populated.
    'ARM kickoff working group' vs 'ARM working group' = 3/4 = 0.75 → above threshold."""
    clusters = [
        {"topic_name": "ARM kickoff working group", "unit_ids": ["u_0001"], "new_topic": True, "importance": "high"},
    ]
    registry = [{"id": "r1", "name": "ARM working group", "description": ""}]
    out = reconcile_with_registry(clusters, registry)
    assert len(out["new_topic_proposals"]) == 1
    prop = out["new_topic_proposals"][0]
    assert prop["suggested_match_id"] == "r1"
    assert prop["suggested_match_name"] == "ARM working group"
    assert prop["lexical_similarity_to_existing"] >= 0.6


def test_new_proposal_no_suggested_match():
    """Unrelated new topic → no suggested_match."""
    clusters = [
        {"topic_name": "Snowflake onboarding", "unit_ids": ["u_0001"], "new_topic": True, "importance": "medium"},
    ]
    registry = [{"id": "r1", "name": "ARM", "description": ""}]
    out = reconcile_with_registry(clusters, registry)
    prop = out["new_topic_proposals"][0]
    assert prop["suggested_match_id"] is None
    assert prop["lexical_similarity_to_existing"] < 0.6


def test_case_insensitive_canonical_match():
    """Cluster name 'arm' matches registry 'ARM'."""
    clusters = [
        {"topic_name": "arm", "unit_ids": ["u_0001"], "new_topic": False, "importance": "high"},
    ]
    registry = [{"id": "r1", "name": "ARM", "description": ""}]
    out = reconcile_with_registry(clusters, registry)
    assert out["working_topics"][0]["topic_name"] == "ARM"  # snapped to canonical
    assert out["working_topics"][0]["registry_id"] == "r1"
    assert out["working_topics"][0]["new_topic"] is False
    assert out["new_topic_proposals"] == []


def test_empty_registry_makes_everything_new():
    clusters = [
        {"topic_name": "Stress Testing", "unit_ids": ["u_0001"], "new_topic": True, "importance": "high"},
        {"topic_name": "ARM", "unit_ids": ["u_0002"], "new_topic": True, "importance": "medium"},
    ]
    registry = []
    out = reconcile_with_registry(clusters, registry)
    assert len(out["working_topics"]) == 2
    assert all(w["new_topic"] for w in out["working_topics"])
    assert len(out["new_topic_proposals"]) == 2
