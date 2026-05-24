"""Tests for Stage 5 — topic clustering (mocked LLM).

EPIC-18 V5-CORE — Tests for structured registry rendering in cluster prompt.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.prompts.call_topics_v5_cluster import build_cluster_user_message
from backend.services.call_topics_v5 import stage_5_cluster as S5
from backend.services.call_topics_v5.stage_5_cluster import cluster_topics


def _units(n: int) -> list[dict]:
    return [{"unit_id": f"u_{i:04d}", "type": "task", "text": f"t{i}", "owner": "A", "evidence_lines": [i, i]} for i in range(1, n + 1)]


def test_validates_no_orphans():
    units = _units(3)
    raw = [
        {"topic_name": "A", "unit_ids": ["u_0001", "u_0002"], "new_topic": False, "importance": "high"},
        {"topic_name": "B", "unit_ids": ["u_0003"], "new_topic": True, "importance": "low"},
    ]
    kept, reasons = S5._validate_clusters(raw, {u["unit_id"] for u in units}, {"A"})
    assert len(kept) == 2
    assert reasons == []


def test_detects_orphans():
    units = _units(3)
    raw = [{"topic_name": "A", "unit_ids": ["u_0001"], "new_topic": False, "importance": "low"}]
    kept, reasons = S5._validate_clusters(raw, {u["unit_id"] for u in units}, set())
    assert any("ORPHANS" in r for r in reasons)


def test_detects_duplicate_unit_assignment():
    units = _units(3)
    raw = [
        {"topic_name": "A", "unit_ids": ["u_0001", "u_0002"], "new_topic": False, "importance": "high"},
        {"topic_name": "B", "unit_ids": ["u_0002", "u_0003"], "new_topic": True, "importance": "low"},
    ]
    kept, reasons = S5._validate_clusters(raw, {u["unit_id"] for u in units}, set())
    # Second cluster rejected because u_0002 already taken
    assert len(kept) == 1
    assert any("already assigned" in r for r in reasons)


def test_snaps_to_canonical_name_when_match():
    """LLM returns 'arm' but registry has 'ARM' — snap to canonical."""
    units = _units(1)
    raw = [{"topic_name": "arm", "unit_ids": ["u_0001"], "new_topic": True, "importance": "high"}]
    kept, _ = S5._validate_clusters(raw, {u["unit_id"] for u in units}, {"ARM"})
    assert kept[0]["topic_name"] == "ARM"
    assert kept[0]["new_topic"] is False


def test_cluster_topics_end_to_end(monkeypatch):
    units = _units(3)
    registry = [{"id": "r1", "name": "ARM", "description": ""}]
    llm_resp = json.dumps([
        {"topic_name": "ARM", "unit_ids": ["u_0001", "u_0002"], "new_topic": False, "importance": "high"},
        {"topic_name": "Stress Testing", "unit_ids": ["u_0003"], "new_topic": True, "importance": "medium"},
    ])
    monkeypatch.setattr(S5, "call_llm_raw", AsyncMock(return_value=llm_resp))
    out = asyncio.run(S5.cluster_topics(units, registry))
    assert len(out["clusters"]) == 2
    assert out["orphans"] == []


def test_registry_block_includes_tasks_and_key_terms():
    units = [{"unit_id": "u1", "text": "x"}]
    registry = [
        {"name": "ARM", "description": "Risk modeling",
         "key_terms": ["LMAC", "Monte Carlo"],
         "tasks": [{"task": "Test LMAC vs Monte Carlo Mac", "owner": "Mark"}]},
    ]
    msg = build_cluster_user_message(units, registry)
    assert "ARM" in msg
    assert "Key terms: LMAC, Monte Carlo" in msg
    assert "Existing tasks:" in msg
    assert "Test LMAC vs Monte Carlo Mac (Mark)" in msg


def test_empty_registry_block_unchanged_message():
    msg = build_cluster_user_message([], [])
    assert "(empty — first call of the project" in msg


def test_registry_caps_at_10_tasks():
    registry = [{
        "name": "A", "key_terms": [],
        "tasks": [{"task": f"task {i}"} for i in range(15)],
    }]
    msg = build_cluster_user_message([], registry)
    assert "… 5 more" in msg


def test_registry_handles_unassigned_owner():
    registry = [{
        "name": "B", "key_terms": [],
        "tasks": [{"task": "do X", "owner": "unassigned"}],
    }]
    msg = build_cluster_user_message([], registry)
    # 'unassigned' owner suffix should be suppressed
    assert "- do X\n" in msg or msg.endswith("- do X")
    assert "(unassigned)" not in msg


def test_registry_topic_with_no_tasks_or_key_terms():
    registry = [{"name": "Legacy Topic", "description": "An old topic"}]
    msg = build_cluster_user_message([], registry)
    assert "Legacy Topic" in msg
    assert "An old topic" in msg
    # No "Existing tasks:" header since there are none
    assert "Existing tasks:" not in msg


def _fake_llm_response(clusters):
    return json.dumps(clusters)


@pytest.mark.asyncio
@patch("backend.services.call_topics_v5.stage_5_cluster.call_llm_raw", new_callable=AsyncMock)
async def test_cluster_topics_passes_structured_registry_to_llm(mock_llm):
    """EPIC-18: Stage 5 forwards full registry structure (key_terms + tasks) to LLM."""
    mock_llm.return_value = _fake_llm_response([
        {"topic_name": "ARM", "unit_ids": ["u_0001"], "new_topic": False, "importance": "high"}
    ])
    units = [{"unit_id": "u_0001", "type": "task", "text": "Test LMAC vs Monte Carlo"}]
    registry = [{
        "name": "ARM", "key_terms": ["LMAC", "Monte Carlo"],
        "tasks": [{"task": "Investigate Monte Carlo job memory failure", "owner": "Mark"}]
    }]
    await cluster_topics(units, registry, llm="openrouter", model="deepseek/deepseek-v3.2")
    # Capture the user message passed to the LLM (args.args is positional args tuple)
    # call_llm_raw signature: (system_prompt, user_message, llm, *, max_tokens, model, temperature)
    user_msg = mock_llm.call_args.args[1]
    assert "Key terms: LMAC, Monte Carlo" in user_msg
    assert "Investigate Monte Carlo job memory failure (Mark)" in user_msg
