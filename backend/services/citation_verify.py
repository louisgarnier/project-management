"""Citation verifier — EPIC-18 S2.1: line-number based, mirrors v5 Stage 4 pattern.

The LLM emits `evidence_lines: [start, end]`. Code resolves to verbatim text
via the v5 ingest line index. Verification is a bounds check; no string
matching that could fail on whitespace/punctuation drift.

LEGACY: verify_citations() retained for backward compat with Pass 2 + Pass 3,
which still use the free-form quote contract. Those are out of scope for
EPIC-18; they will be migrated in a future epic.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("calltracker.citation_verify")


# ── EPIC-18 NEW VERIFIER ──────────────────────────────────────────────────────
def verify_evidence_lines(
    citations: list[dict],
    transcripts: dict[str, dict],
) -> tuple[bool, list[str]]:
    """For each citation, check that evidence_lines is in-bounds for the cited
    call's ingested transcript.

    Args:
        citations: list of {"call_id": str, "evidence_lines": [start, end], ...}.
        transcripts: {call_id: ingested_dict_from_stage_0}. Each must have line_count.

    Returns:
        (all_ok, list_of_failure_messages).
    """
    failed: list[str] = []
    for i, c in enumerate(citations):
        call_id = c.get("call_id")
        ev = c.get("evidence_lines")
        if not call_id:
            failed.append(f"citation #{i}: missing call_id")
            continue
        ingested = transcripts.get(call_id)
        if ingested is None:
            failed.append(f"citation #{i}: call_id {call_id!r} not in supplied transcripts")
            continue
        if not isinstance(ev, list) or len(ev) != 2:
            failed.append(f"citation #{i}: evidence_lines must be [start, end] (got {ev!r})")
            continue
        try:
            start, end = int(ev[0]), int(ev[1])
        except (TypeError, ValueError):
            failed.append(f"citation #{i}: evidence_lines values must be integers (got {ev!r})")
            continue
        line_count = ingested.get("line_count", 0)
        if start < 1 or end > line_count:
            failed.append(f"citation #{i}: lines [{start},{end}] out of bounds (transcript has {line_count} lines)")
            continue
        if start > end:
            failed.append(f"citation #{i}: inverted range [{start},{end}] (start > end)")
            continue
    return (len(failed) == 0, failed)


def resolve_evidence_lines(
    call_id: str, evidence_lines: list[int], transcripts: dict[str, dict],
) -> str:
    """Resolve evidence_lines to verbatim transcript text via v5 ingest line index."""
    from backend.services.call_topics_v5.stage_0_ingest import resolve_lines
    ingested = transcripts.get(call_id)
    if ingested is None:
        return ""
    start = f"{int(evidence_lines[0]):04d}"
    end = f"{int(evidence_lines[1]):04d}"
    try:
        return resolve_lines(ingested, start, end)
    except ValueError:
        return ""


# ── LEGACY (Pass 2 + Pass 3, deprecate in future epic) ───────────────────────
def verify_citations(citations: list[dict], transcripts_by_call: dict[str, str]) -> tuple[bool, list[str]]:
    """LEGACY string-match verifier for Pass 2 and Pass 3. Not used by Pass 1 after EPIC-18.
    
    For each citation, check the quote appears verbatim in the cited call's transcript.

    Args:
        citations: list of {"call_id": str, "quote": str, ...} dicts.
        transcripts_by_call: {call_id: transcript_body} map.

    Returns:
        (all_ok, list_of_failure_messages). Empty failures => all_ok=True.
    """
    failed: list[str] = []
    for i, c in enumerate(citations):
        call_id = c.get("call_id")
        quote = c.get("quote", "")
        if not call_id:
            failed.append(f"citation #{i}: missing call_id")
            continue
        body = transcripts_by_call.get(call_id)
        if body is None:
            failed.append(f"citation #{i}: call_id {call_id!r} not in supplied transcripts")
            continue
        if not quote:
            failed.append(f"citation #{i}: empty quote")
            continue
        if quote not in body:
            preview = quote if len(quote) <= 240 else quote[:240] + "…"
            failed.append(
                f"citation #{i}: this quote was not found verbatim in the cited transcript — \"{preview}\""
            )
    return (len(failed) == 0, failed)


def find_quote_lines(quote: str, transcript_body: str) -> str | None:
    """LEGACY helper. Find a verbatim quote in transcript_body and return the line range as 'X-Y'.

    Lines are 1-indexed. Returns None if the quote is not found.
    """
    idx = transcript_body.find(quote)
    if idx == -1:
        return None
    before = transcript_body[:idx]
    start_line = before.count("\n") + 1
    end_line = start_line + quote.count("\n")
    return f"{start_line}-{end_line}"
