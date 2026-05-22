"""Tests for Stage 3 — adversarial recall pass (mocked LLM)."""

import asyncio
import json
from unittest.mock import AsyncMock

from backend.services.call_topics_v5 import stage_3_recall as S3
from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript


def _mk_ingested(n: int = 10) -> dict:
    raw = "\n".join(f"[{i:04d}] line {i}" for i in range(1, n + 1))
    return ingest_transcript(raw)


def test_recall_pass_returns_new_units(monkeypatch):
    ingested = _mk_ingested(10)
    existing = [
        {"unit_id": "u_0001", "type": "task", "text": "X", "owner": "A", "evidence_lines": [1, 2]},
    ]
    llm_resp = json.dumps([
        {"unit_id": "u_0002", "type": "decision", "text": "Y", "owner": "B", "evidence_lines": [5, 6]},
    ])
    monkeypatch.setattr(S3, "call_llm_raw", AsyncMock(return_value=llm_resp))
    out = asyncio.run(S3.recall_pass(ingested, existing))
    assert len(out["new_units"]) == 1
    assert out["new_units"][0]["unit_id"] == "u_0002"
    assert len(out["merged_pool"]) == 2


def test_recall_pass_empty_addition(monkeypatch):
    """LLM returns [] when nothing missed."""
    ingested = _mk_ingested(5)
    existing = [{"unit_id": "u_0001", "type": "task", "text": "X", "owner": "A", "evidence_lines": [1, 2]}]
    monkeypatch.setattr(S3, "call_llm_raw", AsyncMock(return_value="[]"))
    out = asyncio.run(S3.recall_pass(ingested, existing))
    assert out["new_units"] == []
    assert len(out["merged_pool"]) == 1


def test_recall_pass_dedupes_against_existing(monkeypatch):
    """LLM accidentally re-emits an existing unit_id — must be filtered."""
    ingested = _mk_ingested(10)
    existing = [{"unit_id": "u_0001", "type": "task", "text": "X", "owner": "A", "evidence_lines": [1, 2]}]
    llm_resp = json.dumps([
        {"unit_id": "u_0001", "type": "task", "text": "duplicate!", "owner": "X", "evidence_lines": [3, 4]},
        {"unit_id": "u_0002", "type": "task", "text": "really new", "owner": "Y", "evidence_lines": [5, 6]},
    ])
    monkeypatch.setattr(S3, "call_llm_raw", AsyncMock(return_value=llm_resp))
    out = asyncio.run(S3.recall_pass(ingested, existing))
    assert len(out["new_units"]) == 1
    assert out["new_units"][0]["unit_id"] == "u_0002"


def test_recall_pass_malformed_response(monkeypatch):
    ingested = _mk_ingested(5)
    existing = [{"unit_id": "u_0001", "type": "task", "text": "X", "owner": "A", "evidence_lines": [1, 2]}]
    monkeypatch.setattr(S3, "call_llm_raw", AsyncMock(return_value="not json"))
    out = asyncio.run(S3.recall_pass(ingested, existing))
    assert out["new_units"] == []
    assert out["merged_pool"] == existing  # source preserved on failure
