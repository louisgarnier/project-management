"""Tests for Stages 9 (confidence), 10 (validation), 12 (serialization)."""

from backend.services.call_topics_v5.stage_9_confidence import compute_task_confidence, attach_confidence
from backend.services.call_topics_v5.stage_10_validation import validate
from backend.services.call_topics_v5.stage_12_serialize import serialize_to_v4


# ── Stage 9 ───────────────────────────────────────────────────────────────


def test_confidence_high_when_strong_signals():
    pool = [
        {"unit_id": "u_0001", "owner": "Mark", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True},
        {"unit_id": "u_0002", "owner": "Nick", "evidence_lines": [3, 4], "citation": "y", "citation_valid": True},
        {"unit_id": "u_0003", "owner": "Anand", "evidence_lines": [5, 6], "citation": "z", "citation_valid": True},
    ]
    task = {
        "evidence_unit_ids": ["u_0001", "u_0002", "u_0003"],
        "owner": "Mark",
        "citations": [{"speaker": "Mark", "quote": "x", "lines": "0001-0002"}] * 3,
    }
    out = compute_task_confidence(task, {"new_topic": False}, pool)
    assert out["score"] >= 0.7


def test_confidence_low_when_weak_signals():
    pool = [{"unit_id": "u_0001", "owner": "", "evidence_lines": [1, 1], "citation": "x", "citation_valid": True}]
    task = {
        "evidence_unit_ids": ["u_0001"],
        "owner": "unassigned",
        "citations": [{"speaker": "", "quote": "x"}],
    }
    out = compute_task_confidence(task, {"new_topic": True}, pool)
    assert out["score"] < 0.5


def test_attach_confidence_to_topics():
    pool = [{"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 1], "citation": "x", "citation_valid": True}]
    topics = [{
        "topic_name": "T",
        "new_topic": False,
        "tasks": [{
            "task": "X",
            "evidence_unit_ids": ["u_0001"],
            "owner": "A",
            "citations": [{"speaker": "A", "quote": "x", "lines": "0001-0001"}],
        }],
    }]
    out = attach_confidence(topics, pool)
    assert "confidence" in out[0]["tasks"][0]
    assert 0.0 <= out[0]["tasks"][0]["confidence"]["score"] <= 1.0


# ── Stage 10 ───────────────────────────────────────────────────────────────


def test_validation_clean_path():
    pool = [{"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True}]
    topics = [{
        "topic_name": "ARM",
        "new_topic": False,
        "tasks": [{
            "task": "X",
            "evidence_unit_ids": ["u_0001"],
            "owner": "A",
            "citations": [
                {"speaker": "A", "quote": "x", "lines": "0001-0002"},
                {"speaker": "B", "quote": "y", "lines": "0050-0051"},
            ],
            "citations_below_min": False,
            "confidence": {"score": 0.85},
        }],
    }]
    report = validate(topics, pool, orphans=[])
    assert report["hard_failures"] == []
    assert report["soft_warnings"] == []
    assert report["clean"] is True


def test_validation_hard_failure_orphans():
    topics = []
    report = validate(topics, [], orphans=["u_0099"])
    assert any(hf["code"] == "H3_orphan_units" for hf in report["hard_failures"])


def test_validation_hard_failure_excluded_topic():
    pool = [{"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True}]
    topics = [{
        "topic_name": "Monte Carlo Mac memory failure",
        "new_topic": True,
        "tasks": [{
            "task": "X",
            "evidence_unit_ids": ["u_0001"],
            "owner": "A",
            "citations": [{"speaker": "A", "quote": "x", "lines": "0001-0002"}],
            "citations_below_min": True,
            "confidence": {"score": 0.6},
        }],
    }]
    excluded = [{"topic": "Monte Carlo Mac memory failure"}]
    report = validate(topics, pool, orphans=[], topics_explicitly_excluded=excluded)
    assert any(hf["code"] == "H5_extracted_excluded_topic" for hf in report["hard_failures"])


def test_validation_soft_warning_same_speaker_adjacent():
    pool = [{"unit_id": "u_0001", "owner": "A", "evidence_lines": [1, 2], "citation": "x", "citation_valid": True}]
    topics = [{
        "topic_name": "T",
        "new_topic": False,
        "tasks": [{
            "task": "X",
            "evidence_unit_ids": ["u_0001"],
            "owner": "A",
            "citations": [
                {"speaker": "Mark", "quote": "x", "lines": "0010-0011"},
                {"speaker": "Mark", "quote": "y", "lines": "0012-0013"},  # adjacent same speaker
            ],
            "citations_below_min": False,
            "confidence": {"score": 0.7},
        }],
    }]
    report = validate(topics, pool, orphans=[])
    assert any(s["code"] == "S1_same_speaker_adjacent_citations" for s in report["soft_warnings"])


# ── Stage 12 ───────────────────────────────────────────────────────────────


def test_serialize_to_v4_basic():
    synthesized = [{
        "topic_name": "ARM",
        "importance": "high",
        "tasks": [{
            "task": "X",
            "next_step": "y",
            "owner": "Mark",
            "status": "open",
            "key_terms": ["foo"],
            "open_questions": [],
            "decisions": [],
            "citations": [{"speaker": "Mark", "quote": "x", "lines": "0001-0002"}],
            "confidence": {"score": 0.8, "signals": {}},
        }],
    }]
    v4 = serialize_to_v4(synthesized)
    assert v4[0]["name"] == "ARM"
    assert v4[0]["importance"] == "high"
    assert len(v4[0]["tasks"]) == 1
    assert v4[0]["tasks"][0]["task"] == "X"
    assert v4[0]["tasks"][0]["confidence"]["score"] == 0.8


def test_serialize_preserves_per_task_data():
    synthesized = [{
        "topic_name": "T",
        "importance": "low",
        "tasks": [{
            "task": "X",
            "key_terms": ["k1", "k2"],
            "open_questions": [{"text": "Q?", "owner": "A", "status": "open"}],
            "decisions": [{"text": "D"}],
            "citations": [],
            "confidence": {"score": 0.5},
        }],
    }]
    v4 = serialize_to_v4(synthesized)
    assert v4[0]["tasks"][0]["key_terms"] == ["k1", "k2"]
    assert v4[0]["tasks"][0]["open_questions"][0]["text"] == "Q?"
    assert v4[0]["tasks"][0]["decisions"][0]["text"] == "D"
