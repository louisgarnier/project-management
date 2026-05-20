"""Tests for citation_verify — verbatim quote post-verifier."""

from backend.services.citation_verify import verify_citations, find_quote_lines


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
