"""Stage 2 — atomic unit extraction.

Calls the LLM with the v5 atomic prompt, validates the JSON schema, returns
a flat list of atomic units. Temperature is forced to 0.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypedDict

from backend.prompts.call_topics_v5_atomic import (
    CALL_TOPICS_V5_ATOMIC_SYSTEM,
    build_atomic_user_message,
)
from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("calltracker.call_topics_v5.stage_2")

UNIT_TYPES = {"task", "decision", "question", "blocker", "statement"}


class AtomicUnit(TypedDict, total=False):
    unit_id: str
    type: str
    text: str
    owner: str
    evidence_lines: list[int]  # [start, end]


def _format_numbered_transcript(lines: list[dict]) -> str:
    """Lines from Stage 0 → "[NNNN] text" format suitable for the LLM."""
    return "\n".join(f"[{ln['idx']}] {ln['text']}" for ln in lines)


def _strip_code_fences(s: str) -> str:
    """Best-effort: strip ```json fences if the model emitted them despite instructions."""
    s = s.strip()
    if s.startswith("```"):
        # Drop the opening fence (e.g. ```json)
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        # Drop trailing fence
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3].rstrip()
    return s


def _validate_units(raw: list, line_count: int) -> tuple[list[AtomicUnit], list[str]]:
    """Validate the LLM output. Returns (kept_units, rejection_reasons)."""
    kept: list[AtomicUnit] = []
    reasons: list[str] = []
    seen_ids: set[str] = set()
    seq_re = re.compile(r"^u_\d{4}$")

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            reasons.append(f"item {i}: not a dict")
            continue
        uid = item.get("unit_id")
        if not isinstance(uid, str) or not seq_re.match(uid):
            reasons.append(f"item {i}: invalid unit_id {uid!r} (expect u_NNNN)")
            continue
        if uid in seen_ids:
            reasons.append(f"item {i}: duplicate unit_id {uid!r}")
            continue
        seen_ids.add(uid)
        t = item.get("type")
        if t not in UNIT_TYPES:
            reasons.append(f"{uid}: invalid type {t!r}")
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            reasons.append(f"{uid}: empty text")
            continue
        owner = item.get("owner")
        if owner is None or not isinstance(owner, str):
            owner = "unassigned"
        ev = item.get("evidence_lines")
        if (
            not isinstance(ev, list)
            or len(ev) != 2
            or not all(isinstance(x, int) for x in ev)
        ):
            reasons.append(f"{uid}: evidence_lines must be [int, int]")
            continue
        if ev[0] < 1 or ev[1] < 1 or ev[0] > ev[1] or ev[1] > line_count:
            reasons.append(
                f"{uid}: evidence_lines {ev!r} out of bounds (transcript has {line_count} lines)"
            )
            continue
        kept.append({
            "unit_id": uid,
            "type": t,
            "text": text.strip(),
            "owner": owner.strip() or "unassigned",
            "evidence_lines": ev,
        })
    return kept, reasons


async def extract_atomic_units(
    ingested: dict,
    project_context: str = "",
    *,
    llm: str = "openrouter",
    model: str | None = "deepseek/deepseek-v3.2",
) -> dict:
    """Run Stage 2 — atomic unit extraction.

    Returns:
        {"units": [AtomicUnit, ...], "rejected": [reason_strings], "model": ..., "temperature": 0}
    """
    numbered = _format_numbered_transcript(ingested["lines"])
    user_msg = build_atomic_user_message(numbered, project_context=project_context)

    logger.info(
        "[Stage 2] calling %s/%s on %d-line transcript (temp=0)",
        llm, model, ingested["line_count"],
    )
    raw_response = await call_llm_raw(
        CALL_TOPICS_V5_ATOMIC_SYSTEM,
        user_msg,
        llm,
        max_tokens=16384,
        model=model,
        temperature=0,
    )

    body = _strip_code_fences(raw_response)
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error("[Stage 2] LLM did not return valid JSON: %s", e)
        return {
            "units": [],
            "rejected": [f"LLM response not parseable as JSON: {e}"],
            "model": f"{llm}/{model}",
            "temperature": 0,
            "raw": raw_response[:500],
        }
    if not isinstance(parsed, list):
        # Some models wrap in {"units": [...]} despite instructions — try to unwrap
        if isinstance(parsed, dict):
            for k in ("units", "atomic_units", "items", "data"):
                if isinstance(parsed.get(k), list):
                    parsed = parsed[k]
                    break
        if not isinstance(parsed, list):
            return {
                "units": [],
                "rejected": [f"LLM returned {type(parsed).__name__}, expected array"],
                "model": f"{llm}/{model}",
                "temperature": 0,
            }

    units, rejected = _validate_units(parsed, ingested["line_count"])
    logger.info(
        "[Stage 2] extracted %d units (rejected %d)",
        len(units), len(rejected),
    )
    return {
        "units": units,
        "rejected": rejected,
        "model": f"{llm}/{model}",
        "temperature": 0,
    }
