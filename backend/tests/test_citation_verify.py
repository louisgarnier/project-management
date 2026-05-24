"""Tests for citation_verify — line-number and verbatim quote verifiers.

EPIC-18 S2.1: New line-range verifier for Pass 1 (mirrors v5 Stage 4).
LEGACY: Old string-match verifier for Pass 2 + Pass 3 (backward compat).
"""

from backend.services.citation_verify import (
    verify_evidence_lines,
    resolve_evidence_lines,
    verify_citations,
    find_quote_lines,
)


# ──────────────────────────────────────────────────────────────────────────────
# EPIC-18 NEW LINE-RANGE VERIFIER TESTS
# ──────────────────────────────────────────────────────────────────────────────

def test_verify_evidence_lines_passes_for_valid_range():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": [10, 20]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert ok
    assert failures == []


def test_verify_evidence_lines_fails_for_unknown_call():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-X", "evidence_lines": [1, 5]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok
    assert "call-X" in failures[0]


def test_verify_evidence_lines_fails_for_out_of_bounds():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": [99, 200]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok
    assert "out of bounds" in failures[0]


def test_verify_evidence_lines_fails_for_inverted_range():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": [50, 10]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok


def test_verify_evidence_lines_fails_for_missing_call_id():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"evidence_lines": [10, 20]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok
    assert "missing call_id" in failures[0]


def test_verify_evidence_lines_fails_for_malformed_evidence_lines():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": "10-20"}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok


def test_resolve_evidence_lines_returns_verbatim_text():
    """Verify resolve_evidence_lines correctly concatenates lines from ingested transcript."""
    ingested = {
        "line_count": 3,
        "lines": [
            {"idx": "0001", "text": "Hello"},
            {"idx": "0002", "text": "World"},
            {"idx": "0003", "text": "!"},
        ],
        "by_idx": {
            "0001": {"idx": "0001", "text": "Hello"},
            "0002": {"idx": "0002", "text": "World"},
            "0003": {"idx": "0003", "text": "!"},
        },
        "format_detected": "raw",
    }
    transcripts = {"call-1": ingested}
    text = resolve_evidence_lines("call-1", [1, 2], transcripts)
    assert "Hello" in text and "World" in text


def test_resolve_evidence_lines_returns_empty_for_unknown_call():
    transcripts = {"call-1": {"line_count": 1}}
    text = resolve_evidence_lines("call-X", [1, 2], transcripts)
    assert text == ""


# ──────────────────────────────────────────────────────────────────────────────
# LEGACY STRING-MATCH VERIFIER TESTS (Pass 2 + Pass 3, backward compat)
# ──────────────────────────────────────────────────────────────────────────────

def test_verify_citations_all_pass():
    transcripts = {"call-1": "Hello world. This is a transcript.\nLine two here."}
    cits = [{"call_id": "call-1", "quote": "Hello world", "lines": ""}]
    ok, fails = verify_citations(cits, transcripts)
    assert ok is True
    assert fails == []


def test_verify_citations_missing_quote():
    transcripts = {"call-1": "Hello world."}
    cits = [{"call_id": "call-1", "quote": "Not present here", "lines": ""}]
    ok, fails = verify_citations(cits, transcripts)
    assert ok is False
    assert len(fails) == 1
    assert "not found" in fails[0].lower()


def test_verify_citations_missing_call_id():
    transcripts = {"call-1": "Hello"}
    cits = [{"call_id": "call-99", "quote": "Hello", "lines": ""}]
    ok, fails = verify_citations(cits, transcripts)
    assert ok is False
    assert "call-99" in fails[0]


def test_verify_citations_empty_list_passes():
    ok, fails = verify_citations([], {"call-1": "anything"})
    assert ok is True
    assert fails == []


def test_find_quote_lines_returns_range():
    body = "Line one\nLine two\nLine three\n"
    rng = find_quote_lines("Line two", body)
    assert rng == "2-2"


def test_find_quote_lines_returns_multi_line_range():
    body = "Line one\nQuote starts\ncontinues here\nLine four"
    rng = find_quote_lines("Quote starts\ncontinues here", body)
    assert rng == "2-3"


def test_find_quote_lines_returns_none_when_not_found():
    assert find_quote_lines("nope", "abc") is None


def test_legacy_verify_citations_still_works():
    """Pass 2 + Pass 3 use the old API; it must continue working."""
    transcripts = {"call-1": "Hello world, this is a transcript."}
    cits = [{"call_id": "call-1", "quote": "Hello world"}]
    ok, failures = verify_citations(cits, transcripts)
    assert ok
