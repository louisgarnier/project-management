"""Tests for Stage 5 — topic clustering (mocked LLM)."""

import asyncio
import json
from unittest.mock import AsyncMock

from backend.services.call_topics_v5 import stage_5_cluster as S5


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
