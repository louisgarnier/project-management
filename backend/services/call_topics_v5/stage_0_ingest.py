"""Stage 0 — transcript ingestion.

Pure code, no LLM. Parses the [NNNN] text format used in gold set transcripts.
Falls back to sequential 4-digit zero-padded numbering for raw transcripts that
don't have explicit line indices.

The output is a list of line objects: [{idx: "0001", text: "..."}].
Lookup by idx is O(1) via the secondary `by_idx` dict.
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict

logger = logging.getLogger("calltracker.call_topics_v5.stage_0")

# Matches "[NNNN] text" at the start of a line. The four digits are zero-padded.
_NUMBERED_LINE_RE = re.compile(r"^\[(\d{4})\]\s*(.*)$")


class Line(TypedDict):
    idx: str   # "0001"..."NNNN" zero-padded
    text: str  # the line content, prefix stripped if it had one


class IngestResult(TypedDict):
    lines: list[Line]
    by_idx: dict[str, Line]
    line_count: int
    format_detected: str  # "numbered" | "raw" | "mixed"


def ingest_transcript(raw: str) -> IngestResult:
    """Parse a raw transcript string into a list of indexed lines.

    Behavior:
    - If a line matches `[NNNN] text` → uses the captured idx.
    - If a line is non-empty and doesn't match → assigns the next sequential
      zero-padded idx (continuing from the highest idx seen so far, +1).
    - Empty / whitespace-only lines are skipped (no idx burned).

    Stable: same input → same output. Line text is preserved verbatim
    (including original casing/punctuation) so that Stage 4 citation
    resolution is byte-identical to the source.
    """
    if not isinstance(raw, str):
        raise ValueError(f"raw must be str, got {type(raw).__name__}")

    lines: list[Line] = []
    used_idx: set[str] = set()
    max_idx_seen = 0
    numbered_count = 0
    raw_count = 0

    def _next_fallback_idx() -> str:
        nonlocal max_idx_seen
        while True:
            max_idx_seen += 1
            candidate = f"{max_idx_seen:04d}"
            if candidate not in used_idx:
                return candidate

    for raw_line in raw.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        m = _NUMBERED_LINE_RE.match(stripped)
        if m:
            idx, text = m.group(1), m.group(2)
            if idx in used_idx:
                # Duplicate explicit idx — log and reassign to a fresh sequential one
                logger.warning(
                    "[Stage 0] duplicate explicit idx %r — reassigning sequentially", idx
                )
                idx = _next_fallback_idx()
            used_idx.add(idx)
            max_idx_seen = max(max_idx_seen, int(idx))
            lines.append({"idx": idx, "text": text})
            numbered_count += 1
        else:
            idx = _next_fallback_idx()
            used_idx.add(idx)
            lines.append({"idx": idx, "text": stripped})
            raw_count += 1

    if numbered_count > 0 and raw_count == 0:
        fmt = "numbered"
    elif numbered_count == 0 and raw_count > 0:
        fmt = "raw"
    elif numbered_count == 0 and raw_count == 0:
        fmt = "raw"  # empty input — call it "raw" with 0 lines
    else:
        fmt = "mixed"

    by_idx = {ln["idx"]: ln for ln in lines}
    return {
        "lines": lines,
        "by_idx": by_idx,
        "line_count": len(lines),
        "format_detected": fmt,
    }


def resolve_lines(result: IngestResult, start_idx: str, end_idx: str) -> str:
    """Return the verbatim concatenated text of lines [start_idx..end_idx] inclusive.
    Used by Stage 4 (citation resolution) — line indices are CONSTRUCTED by the
    LLM, the citation TEXT is read from this function. No LLM hallucination possible.

    Raises ValueError if start/end out of bounds.
    """
    if start_idx not in result["by_idx"]:
        raise ValueError(f"start_idx {start_idx!r} not in transcript")
    if end_idx not in result["by_idx"]:
        raise ValueError(f"end_idx {end_idx!r} not in transcript")
    start_int = int(start_idx)
    end_int = int(end_idx)
    if start_int > end_int:
        raise ValueError(f"start_idx {start_idx!r} > end_idx {end_idx!r}")

    collected: list[str] = []
    for i in range(start_int, end_int + 1):
        key = f"{i:04d}"
        if key in result["by_idx"]:
            collected.append(result["by_idx"][key]["text"])
    return "\n".join(collected)
