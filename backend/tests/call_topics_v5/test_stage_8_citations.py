"""Tests for Stage 8 — task-level citation attachment (pure code)."""

from backend.services.call_topics_v5.stage_8_citations import attach_citations


def test_attaches_byte_identical_citations():
    pool = [
        {"unit_id": "u_0001", "owner": "Mark", "evidence_lines": [1, 2], "citation": "Hello world", "citation_valid": True},
        {"unit_id": "u_0002", "owner": "Nick", "evidence_lines": [5, 5], "citation": "Yes", "citation_valid": True},
    ]
    topics = [{
        "topic_name": "T",
        "tasks": [{
            "task": "X",
            "evidence_unit_ids": ["u_0001", "u_0002"],
        }],
    }]
    out = attach_citations(topics, pool)
    assert len(out[0]["tasks"][0]["citations"]) == 2
    assert out[0]["tasks"][0]["citations"][0]["quote"] == "Hello world"
    assert out[0]["tasks"][0]["citations"][0]["speaker"] == "Mark"
    assert out[0]["tasks"][0]["citations"][0]["lines"] == "0001-0002"
    assert out[0]["tasks"][0]["citations_below_min"] is False


def test_flags_below_min_when_one_citation():
    pool = [
        {"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True},
    ]
    topics = [{
        "topic_name": "T",
        "tasks": [{"task": "X", "evidence_unit_ids": ["u_0001"]}],
    }]
    out = attach_citations(topics, pool)
    assert out[0]["tasks"][0]["citations_below_min"] is True


def test_skips_invalid_citations():
    pool = [
        {"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True},
        {"unit_id": "u_0002", "owner": "B", "evidence_lines": [99, 99], "citation": "", "citation_valid": False, "validation_error": "out of bounds"},
    ]
    topics = [{
        "topic_name": "T",
        "tasks": [{"task": "X", "evidence_unit_ids": ["u_0001", "u_0002"]}],
    }]
    out = attach_citations(topics, pool)
    # u_0002 had invalid citation → skipped, leaving only 1 → flagged below_min
    assert len(out[0]["tasks"][0]["citations"]) == 1
    assert out[0]["tasks"][0]["citations_below_min"] is True


def test_missing_unit_ids_recorded():
    pool = [
        {"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True},
    ]
    topics = [{
        "topic_name": "T",
        "tasks": [{"task": "X", "evidence_unit_ids": ["u_0001", "u_9999"]}],
    }]
    out = attach_citations(topics, pool)
    assert "u_9999" in out[0]["tasks"][0]["missing_evidence_unit_ids"]
