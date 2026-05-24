"""Tests for Stage 7 — per-topic synthesis (mocked LLM)."""

import asyncio
import json
from unittest.mock import AsyncMock

from backend.services.call_topics_v5 import stage_7_synthesis as S7


def test_validates_clean_task():
    raw = [{
        "task": "Send hierarchy",
        "next_step": "Mark to email Friday",
        "owner": "Mark",
        "status": "open",
        "key_terms": ["hierarchy", "FactSet"],
        "open_questions": [],
        "decisions": [],
        "evidence_unit_ids": ["u_0001", "u_0002"],
    }]
    kept, rejected = S7._validate_synthesized(raw, {"u_0001", "u_0002"}, topic_unit_count=2)
    assert len(kept) == 1
    assert kept[0]["task"] == "Send hierarchy"
    assert rejected == []


def test_rejects_unknown_unit_id():
    raw = [{
        "task": "X",
        "next_step": "y",
        "owner": "A",
        "status": "open",
        "key_terms": [],
        "open_questions": [],
        "decisions": [],
        "evidence_unit_ids": ["u_0001", "u_9999"],  # 9999 not in valid set
    }]
    kept, rejected = S7._validate_synthesized(raw, {"u_0001"}, topic_unit_count=1)
    assert kept == []
    assert "unknown unit_ids" in rejected[0]


def test_rejects_too_few_evidence():
    """Topic has 2 units → min_evidence is 2, task with only 1 should be rejected."""
    raw = [{
        "task": "X", "next_step": "", "owner": "A", "status": "open",
        "key_terms": [], "open_questions": [], "decisions": [],
        "evidence_unit_ids": ["u_0001"],
    }]
    kept, rejected = S7._validate_synthesized(raw, {"u_0001", "u_0002"}, topic_unit_count=2)
    assert kept == []
    assert "need ≥2" in rejected[0]


def test_accepts_single_evidence_when_single_unit_topic():
    """Topic has only 1 unit → min_evidence is 1, task with 1 unit_id is fine."""
    raw = [{
        "task": "X", "next_step": "", "owner": "A", "status": "open",
        "key_terms": [], "open_questions": [], "decisions": [],
        "evidence_unit_ids": ["u_0001"],
    }]
    kept, rejected = S7._validate_synthesized(raw, {"u_0001"}, topic_unit_count=1)
    assert len(kept) == 1
    assert rejected == []


def test_synthesize_topic_e2e(monkeypatch):
    units = [
        {"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 2], "citation": "x"},
        {"unit_id": "u_0002", "type": "task", "text": "y", "owner": "B", "evidence_lines": [3, 4], "citation": "y"},
    ]
    llm_resp = json.dumps([{
        "task": "Combined task",
        "next_step": "do it",
        "owner": "A",
        "status": "open",
        "key_terms": ["alpha"],
        "open_questions": [],
        "decisions": [],
        "evidence_unit_ids": ["u_0001", "u_0002"],
    }])
    monkeypatch.setattr(S7, "call_llm_raw", AsyncMock(return_value=llm_resp))
    out = asyncio.run(S7.synthesize_topic("ARM", "high", units, llm="openrouter", model="deepseek/deepseek-v3.2"))
    assert out["topic_name"] == "ARM"
    assert len(out["tasks"]) == 1
    assert out["tasks"][0]["task"] == "Combined task"


def test_synthesize_all_topics_sequential(monkeypatch):
    pool = [
        {"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 2], "citation": "x"},
        {"unit_id": "u_0002", "type": "task", "text": "y", "owner": "B", "evidence_lines": [3, 4], "citation": "y"},
    ]
    working = [
        {"topic_name": "T1", "unit_ids": ["u_0001"], "importance": "high", "registry_id": "r1", "new_topic": False, "provisional": False},
        {"topic_name": "T2", "unit_ids": ["u_0002"], "importance": "low", "registry_id": None, "new_topic": True, "provisional": True},
    ]
    response = json.dumps([{
        "task": "X task",
        "next_step": "",
        "owner": "A",
        "status": "open",
        "key_terms": [],
        "open_questions": [],
        "decisions": [],
        "evidence_unit_ids": ["u_0001"],
    }])
    # Same response for both topics — they each have 1 unit so 1 evidence_unit_id is OK
    response2 = json.dumps([{
        "task": "Y task",
        "next_step": "",
        "owner": "B",
        "status": "open",
        "key_terms": [],
        "open_questions": [],
        "decisions": [],
        "evidence_unit_ids": ["u_0002"],
    }])
    mock = AsyncMock(side_effect=[response, response2])
    monkeypatch.setattr(S7, "call_llm_raw", mock)
    out = asyncio.run(S7.synthesize_all_topics(working, pool, llm="openrouter", model="deepseek/deepseek-v3.2"))
    assert len(out) == 2
    assert out[0]["registry_id"] == "r1"
    assert out[1]["provisional"] is True
