"""Tests for Stage 4 — citation resolution (pure code, no LLM)."""

from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
from backend.services.call_topics_v5.stage_4_citations import resolve_citations


def test_resolves_byte_identical_citation():
    raw = "[0001] First line.\n[0002] Second line.\n[0003] Third."
    ingested = ingest_transcript(raw)
    units = [
        {"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 2]},
    ]
    out = resolve_citations(units, ingested)
    assert len(out) == 1
    assert out[0]["citation"] == "First line.\nSecond line."
    assert out[0]["citation_valid"] is True
    assert out[0]["validation_error"] is None


def test_out_of_bounds_flagged_not_dropped():
    raw = "[0001] One line."
    ingested = ingest_transcript(raw)
    units = [{"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [1, 99]}]
    out = resolve_citations(units, ingested)
    assert len(out) == 1  # flagged, not dropped
    assert out[0]["citation_valid"] is False
    assert "not in transcript" in out[0]["validation_error"]


def test_inverted_range_flagged():
    raw = "[0001] A.\n[0002] B."
    ingested = ingest_transcript(raw)
    units = [{"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A", "evidence_lines": [2, 1]}]
    out = resolve_citations(units, ingested)
    assert out[0]["citation_valid"] is False


def test_missing_evidence_lines_flagged():
    raw = "[0001] A."
    ingested = ingest_transcript(raw)
    units = [{"unit_id": "u_0001", "type": "task", "text": "x", "owner": "A"}]
    out = resolve_citations(units, ingested)
    assert out[0]["citation_valid"] is False


def test_preserves_all_unit_fields():
    raw = "[0001] hello.\n[0002] world."
    ingested = ingest_transcript(raw)
    units = [
        {"unit_id": "u_0001", "type": "decision", "text": "Y", "owner": "Nick", "evidence_lines": [1, 1]},
    ]
    out = resolve_citations(units, ingested)
    assert out[0]["unit_id"] == "u_0001"
    assert out[0]["type"] == "decision"
    assert out[0]["text"] == "Y"
    assert out[0]["owner"] == "Nick"
    assert out[0]["citation"] == "hello."
