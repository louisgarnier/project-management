"""Tests for Stage 2 — atomic unit extraction (with mocked LLM)."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend.services.call_topics_v5 import stage_2_atomic as S2
from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript


def _mk_ingested(n: int = 5) -> dict:
    raw = "\n".join(f"[{i:04d}] line {i}" for i in range(1, n + 1))
    return ingest_transcript(raw)


def test_validates_clean_output():
    ingested = _mk_ingested(10)
    raw = [
        {"unit_id": "u_0001", "type": "task", "text": "Do X", "owner": "Mark", "evidence_lines": [1, 3]},
        {"unit_id": "u_0002", "type": "decision", "text": "Y agreed", "owner": "Nick", "evidence_lines": [5, 7]},
    ]
    units, rejected = S2._validate_units(raw, ingested["line_count"])
    assert len(units) == 2
    assert rejected == []
    assert units[0]["unit_id"] == "u_0001"


def test_rejects_invalid_type():
    raw = [{"unit_id": "u_0001", "type": "blob", "text": "x", "owner": "A", "evidence_lines": [1, 2]}]
    units, rejected = S2._validate_units(raw, 10)
    assert units == []
    assert "invalid type" in rejected[0]


def test_rejects_bad_unit_id():
    raw = [{"unit_id": "1", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 2]}]
    units, rejected = S2._validate_units(raw, 10)
    assert units == []


def test_rejects_duplicate_unit_id():
    raw = [
        {"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 2]},
        {"unit_id": "u_0001", "type": "task", "text": "y", "owner": "B", "evidence_lines": [3, 4]},
    ]
    units, rejected = S2._validate_units(raw, 10)
    assert len(units) == 1
    assert "duplicate" in rejected[0]


def test_rejects_out_of_bounds_evidence_lines():
    raw = [{"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 999]}]
    units, rejected = S2._validate_units(raw, 10)
    assert units == []
    assert "out of bounds" in rejected[0]


def test_rejects_inverted_evidence_lines():
    raw = [{"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [5, 2]}]
    units, rejected = S2._validate_units(raw, 10)
    assert units == []


def test_owner_defaults_to_unassigned():
    raw = [{"unit_id": "u_0001", "type": "task", "text": "x", "evidence_lines": [1, 2]}]
    units, rejected = S2._validate_units(raw, 10)
    assert len(units) == 1
    assert units[0]["owner"] == "unassigned"


def test_strip_code_fences():
    assert S2._strip_code_fences("```json\n[]\n```") == "[]"
    assert S2._strip_code_fences("[]") == "[]"
    assert S2._strip_code_fences("```\n[1,2]\n```") == "[1,2]"


def test_format_numbered_transcript():
    ingested = ingest_transcript("[0001] hello\n[0002] world")
    out = S2._format_numbered_transcript(ingested["lines"])
    assert out == "[0001] hello\n[0002] world"


def test_extract_atomic_units_happy_path(monkeypatch):
    """End-to-end with mocked LLM returning a clean JSON array."""
    ingested = _mk_ingested(10)
    llm_response = json.dumps([
        {"unit_id": "u_0001", "type": "task", "text": "Do X", "owner": "Mark", "evidence_lines": [1, 3]},
        {"unit_id": "u_0002", "type": "question", "text": "Y?", "owner": "Nick", "evidence_lines": [5, 7]},
    ])
    monkeypatch.setattr(S2, "call_llm_raw", AsyncMock(return_value=llm_response))
    out = asyncio.run(S2.extract_atomic_units(ingested, llm="openrouter", model="deepseek/deepseek-v3.2"))
    assert len(out["units"]) == 2
    assert out["rejected"] == []
    assert out["temperature"] == 0


def test_extract_atomic_units_handles_wrapped_dict(monkeypatch):
    """LLM wraps in {units: [...]} despite instructions — unwrap silently."""
    ingested = _mk_ingested(5)
    llm_response = json.dumps({"units": [
        {"unit_id": "u_0001", "type": "task", "text": "X", "owner": "A", "evidence_lines": [1, 2]},
    ]})
    monkeypatch.setattr(S2, "call_llm_raw", AsyncMock(return_value=llm_response))
    out = asyncio.run(S2.extract_atomic_units(ingested, llm="openrouter", model="deepseek/deepseek-v3.2"))
    assert len(out["units"]) == 1


def test_extract_atomic_units_malformed_json(monkeypatch):
    ingested = _mk_ingested(5)
    monkeypatch.setattr(S2, "call_llm_raw", AsyncMock(return_value="not json at all"))
    out = asyncio.run(S2.extract_atomic_units(ingested, llm="openrouter", model="deepseek/deepseek-v3.2"))
    assert out["units"] == []
    assert "not parseable" in out["rejected"][0]
