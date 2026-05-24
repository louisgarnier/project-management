"""EPIC-18 S2.3 — Unified similarity scoring."""
from backend.services.topic_similarity import (
    weighted_jaccard, weighted_jaccard_tokens, compute_idf, effective_token_set,
)


def test_effective_token_set_includes_name_and_key_terms():
    t = {"name": "Stress Testing", "key_terms": ["LMAC", "Monte Carlo"]}
    tokens = effective_token_set(t)
    assert "stress" in tokens
    assert "testing" in tokens
    assert "lmac" in tokens
    assert "monte" in tokens
    assert "carlo" in tokens


def test_effective_token_set_aggregates_per_task_key_terms():
    t = {"name": "X", "tasks": [{"key_terms": ["foo", "bar"]}, {"key_terms": ["baz"]}]}
    tokens = effective_token_set(t)
    assert {"foo", "bar", "baz"}.issubset(tokens)


def test_weighted_jaccard_full_overlap_returns_one():
    project_topics = [
        {"name": "Apple Banana", "key_terms": []},
        {"name": "Cherry Date", "key_terms": []},
    ]
    idf = compute_idf(project_topics)
    score = weighted_jaccard(["apple", "banana"], ["apple", "banana"], idf)
    assert score == 1.0


def test_weighted_jaccard_no_overlap_returns_zero():
    project_topics = [{"name": "Apple Banana"}]
    idf = compute_idf(project_topics)
    assert weighted_jaccard(["apple"], ["zebra"], idf) == 0.0


def test_compute_idf_assigns_lower_score_to_common_tokens():
    """Tokens appearing in many topics get lower IDF; rare tokens get higher."""
    project_topics = [
        {"name": "common rare1"},
        {"name": "common rare2"},
        {"name": "common rare3"},
    ]
    idf = compute_idf(project_topics)
    assert idf["common"] < idf["rare1"]
    assert idf["common"] < idf["rare2"]
    assert idf["common"] < idf["rare3"]
