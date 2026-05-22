"""Tests for Stage 0 — transcript ingestion."""

from pathlib import Path

import pytest

from backend.services.call_topics_v5.stage_0_ingest import (
    ingest_transcript,
    resolve_lines,
)

# Gold set transcripts live in docs/project/config/gold set/
# (with a space in the folder name — preserved as-is).
GOLD_SET_DIR = Path(__file__).resolve().parents[3] / "docs" / "project" / "config" / "gold set"


def test_parses_numbered_format():
    """[NNNN] text lines parsed correctly."""
    raw = "[0001] First line.\n[0002] Second line.\n[0003] Third."
    out = ingest_transcript(raw)
    assert out["line_count"] == 3
    assert out["format_detected"] == "numbered"
    assert out["lines"][0] == {"idx": "0001", "text": "First line."}
    assert out["lines"][1] == {"idx": "0002", "text": "Second line."}
    assert out["lines"][2] == {"idx": "0003", "text": "Third."}
    assert out["by_idx"]["0001"]["text"] == "First line."


def test_skips_blank_lines():
    """Empty lines are skipped — no idx burned."""
    raw = "[0001] First.\n\n   \n[0002] Second."
    out = ingest_transcript(raw)
    assert out["line_count"] == 2


def test_raw_format_fallback_numbers_sequentially():
    """Lines without [NNNN] prefix get sequential zero-padded indices."""
    raw = "First raw line.\nSecond.\nThird."
    out = ingest_transcript(raw)
    assert out["line_count"] == 3
    assert out["format_detected"] == "raw"
    assert out["lines"][0]["idx"] == "0001"
    assert out["lines"][1]["idx"] == "0002"
    assert out["lines"][2]["idx"] == "0003"


def test_mixed_format_preserves_explicit_indices():
    """Mixed numbered + raw — explicit indices kept, fallback fills around them."""
    raw = "Raw line first.\n[0005] Explicit fifth.\nRaw after."
    out = ingest_transcript(raw)
    assert out["line_count"] == 3
    assert out["format_detected"] == "mixed"
    # First raw line gets idx 0001 (sequential start)
    assert out["lines"][0]["idx"] == "0001"
    assert out["lines"][0]["text"] == "Raw line first."
    # Explicit 0005 preserved
    assert out["lines"][1]["idx"] == "0005"
    # Next raw line continues from max seen (0005) + 1 = 0006
    assert out["lines"][2]["idx"] == "0006"


def test_stable_across_reruns():
    """Same input twice → identical output."""
    raw = "[0001] Hello.\n[0002] World."
    a = ingest_transcript(raw)
    b = ingest_transcript(raw)
    assert a == b


def test_duplicate_explicit_idx_logs_and_reassigns():
    """Duplicate [0001] in input — second occurrence reassigned to next fallback."""
    raw = "[0001] First.\n[0001] Duplicate."
    out = ingest_transcript(raw)
    assert out["line_count"] == 2
    assert out["lines"][0]["idx"] == "0001"
    assert out["lines"][1]["idx"] == "0002"


def test_empty_input():
    raw = ""
    out = ingest_transcript(raw)
    assert out["line_count"] == 0
    assert out["lines"] == []
    assert out["by_idx"] == {}


def test_non_string_raises():
    with pytest.raises(ValueError):
        ingest_transcript(123)  # type: ignore[arg-type]


def test_resolve_lines_returns_verbatim_text():
    raw = "[0001] Line one.\n[0002] Line two.\n[0003] Line three."
    out = ingest_transcript(raw)
    text = resolve_lines(out, "0001", "0002")
    assert text == "Line one.\nLine two."


def test_resolve_lines_single_line():
    raw = "[0001] Only.\n[0002] Other."
    out = ingest_transcript(raw)
    assert resolve_lines(out, "0001", "0001") == "Only."


def test_resolve_lines_rejects_out_of_bounds():
    raw = "[0001] One."
    out = ingest_transcript(raw)
    with pytest.raises(ValueError):
        resolve_lines(out, "0001", "0099")


def test_resolve_lines_rejects_inverted_range():
    raw = "[0001] One.\n[0002] Two."
    out = ingest_transcript(raw)
    with pytest.raises(ValueError):
        resolve_lines(out, "0002", "0001")


# ── Gold set transcripts — end-to-end ──


@pytest.mark.parametrize(
    "filename,expected_line_count",
    [
        ("arm_kickoff_05112026_numbered.txt", 241),
        ("snowflake_kickoff_numbered.txt", 278),
        ("factset_05182026_numbered.txt", 297),
    ],
)
def test_gold_set_transcripts_parse_cleanly(filename, expected_line_count):
    """All 3 gold set transcripts ingest with the expected line count + numbered format."""
    path = GOLD_SET_DIR / filename
    if not path.exists():
        pytest.skip(f"Gold set transcript {filename} not present (CI without docs).")
    raw = path.read_text(encoding="utf-8")
    out = ingest_transcript(raw)
    assert out["line_count"] == expected_line_count, (
        f"{filename}: expected {expected_line_count} lines, got {out['line_count']}"
    )
    assert out["format_detected"] == "numbered", (
        f"{filename}: expected numbered format, got {out['format_detected']}"
    )
    # First line idx is always 0001
    assert out["lines"][0]["idx"] == "0001"
    # Last line idx matches expected
    assert out["lines"][-1]["idx"] == f"{expected_line_count:04d}"


def test_gold_set_resolve_lines_byte_identical():
    """Resolve a known line range from the ARM transcript and verify byte-identity."""
    path = GOLD_SET_DIR / "arm_kickoff_05112026_numbered.txt"
    if not path.exists():
        pytest.skip("Gold set transcript not present.")
    raw = path.read_text(encoding="utf-8")
    out = ingest_transcript(raw)
    # First line of ARM kickoff is hard-coded — we know what it should be
    text = resolve_lines(out, "0001", "0001")
    assert text == "with the memory boost to see how that affects performance of the actual PRD job."
