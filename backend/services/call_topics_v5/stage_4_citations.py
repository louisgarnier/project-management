"""Stage 4 — citation resolution.

Pure code, no LLM. For each atomic unit, resolves `evidence_lines` to actual
transcript text. Attaches the verbatim string as `citation` field. The LLM
NEVER generates citation strings → 100% byte-identity by construction.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from backend.services.call_topics_v5.stage_0_ingest import IngestResult, resolve_lines

logger = logging.getLogger("calltracker.call_topics_v5.stage_4")


class UnitWithCitation(TypedDict, total=False):
    unit_id: str
    type: str
    text: str
    owner: str
    evidence_lines: list[int]
    citation: str
    citation_valid: bool
    validation_error: str | None


def resolve_citations(
    units: list[dict],
    ingested: IngestResult,
) -> list[UnitWithCitation]:
    """For each unit, resolve evidence_lines to verbatim transcript text.

    Validation failures (out-of-bounds, resolve error) are FLAGGED — not dropped.
    Stage 10 decides whether to escalate.
    """
    out: list[UnitWithCitation] = []
    for u in units:
        ev = u.get("evidence_lines") or []
        if not isinstance(ev, list) or len(ev) != 2:
            out.append({
                **u,
                "citation": "",
                "citation_valid": False,
                "validation_error": f"evidence_lines must be [start, end]; got {ev!r}",
            })
            continue
        try:
            start_idx = f"{int(ev[0]):04d}"
            end_idx = f"{int(ev[1]):04d}"
            text = resolve_lines(ingested, start_idx, end_idx)
        except (ValueError, KeyError, TypeError) as e:
            out.append({
                **u,
                "citation": "",
                "citation_valid": False,
                "validation_error": str(e),
            })
            continue
        if not text:
            out.append({
                **u,
                "citation": "",
                "citation_valid": False,
                "validation_error": "resolved citation is empty",
            })
            continue
        out.append({**u, "citation": text, "citation_valid": True, "validation_error": None})

    invalid_count = sum(1 for u in out if not u.get("citation_valid"))
    logger.info(
        "[Stage 4] resolved %d citations (%d invalid, flagged for Stage 10)",
        len(out), invalid_count,
    )
    return out
