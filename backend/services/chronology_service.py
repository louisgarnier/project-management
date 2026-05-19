"""Chronology cell generation (Story 15.7).

For each (project_topic, call) touched at project_updates commit, run two
LLM calls:
1. CHRONOLOGY_NARRATIVE — produce a 2-3 sentence frozen log entry.
2. RAG_VERIFICATION — audit the narrative against the topic_updates row's
   evidence excerpt.

Persist both to topic_updates.chronology_narrative + rag_verification_note.
Never raise — LLM failures are caught and marked so the pipeline can proceed.
"""

import logging
import time
from typing import Optional

from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("chronology_service")

NARRATIVE_HARD_CAP_CHARS = 600


async def generate_chronology_cell(
    project_topic_id: str, call_id: str, db
) -> tuple[Optional[str], Optional[str]]:
    """Generate and persist the chronology cell for one (topic, call) pair.

    Returns (narrative, rag_note). Returns (None, None) when the topic_updates
    row doesn't exist (nothing to do).

    On any LLM failure: persists ('', '(generation failed: <reason>)') and
    returns those values. Never raises.
    """
    start = time.time()
    rows = (
        db.table("topic_updates")
        .select("id, evidence, topic_id, call_id")
        .eq("topic_id", project_topic_id)
        .eq("call_id", call_id)
        .execute()
        .data
    )
    if not rows:
        return None, None
    row = rows[0]
    evidence = row.get("evidence") or []
    excerpt = _join_evidence(evidence)

    narrative_entry, rag_entry = _resolve_chronology_library_entries(db)
    if not narrative_entry or not rag_entry:
        msg = "library entries missing (Chronology Narrative or RAG Verification)"
        logger.warning(f"⚠️  [Chronology] {msg}")
        _persist(db, project_topic_id, call_id, "", f"(generation failed: {msg})")
        return "", f"(generation failed: {msg})"

    narrative_prompt = narrative_entry["prompt"]
    rag_prompt = rag_entry["prompt"]
    llm = narrative_entry.get("llm", "openrouter")
    model = narrative_entry.get("model", "deepseek/deepseek-v3.2")

    try:
        narrative_raw = await call_llm_raw(
            narrative_prompt,
            _format_narrative_input(row, excerpt),
            llm,
            max_tokens=1024,
            model=model,
        )
        narrative = (narrative_raw or "").strip()[:NARRATIVE_HARD_CAP_CHARS]

        rag_raw = await call_llm_raw(
            rag_prompt,
            _format_rag_input(narrative, excerpt, call_id),
            llm,
            max_tokens=512,
            model=model,
        )
        rag_note = (rag_raw or "").strip()

        _persist(db, project_topic_id, call_id, narrative, rag_note)
        latency_ms = int((time.time() - start) * 1000)
        rag_status = "verified" if rag_note.lower().strip() == "verified" else "drift"
        logger.info(
            f"🧬 [Chronology] topic={project_topic_id} call={call_id} "
            f"narrative_chars={len(narrative)} rag_status={rag_status} "
            f"latency_ms={latency_ms}"
        )
        return narrative, rag_note
    except Exception as e:  # noqa: BLE001
        msg = f"(generation failed: {type(e).__name__}: {e})"
        logger.exception(f"❌ [Chronology] topic={project_topic_id} call={call_id} failed")
        _persist(db, project_topic_id, call_id, "", msg)
        return "", msg


def _resolve_chronology_library_entries(db):
    rows = (
        db.table("artifact_library")
        .select("id, name, prompt, llm, model, category, seeded_by_default")
        .eq("category", "chronology")
        .execute()
        .data
    )
    narrative = next((r for r in rows if r["name"] == "Chronology Narrative"), None)
    rag = next((r for r in rows if r["name"] == "RAG Verification"), None)
    return narrative, rag


def _join_evidence(evidence: list[dict]) -> str:
    parts = []
    for e in evidence:
        speaker = e.get("speaker", "?")
        quote = e.get("quote", "")
        parts.append(f"{speaker}: {quote}")
    return "\n".join(parts)


def _format_narrative_input(row: dict, excerpt: str) -> str:
    tasks = row.get("tasks") or []
    oqs = row.get("open_questions") or []
    decs = row.get("decisions") or []
    return (
        f"TRANSCRIPT EXCERPT:\n{excerpt}\n\n"
        f"TASKS THIS CALL: {[t.get('task','') for t in tasks]}\n"
        f"OPEN QUESTIONS THIS CALL: {[q.get('text','') for q in oqs]}\n"
        f"DECISIONS THIS CALL: {[d.get('text','') for d in decs]}"
    )


def _format_rag_input(narrative: str, excerpt: str, call_id: str) -> str:
    return (
        f"NARRATIVE TO AUDIT:\n{narrative}\n\n"
        f"TRANSCRIPT EXCERPT:\n{excerpt}\n\n"
        f"CALL_DATE_OR_ID: {call_id}"
    )


def _persist(db, project_topic_id: str, call_id: str, narrative: str, rag_note: str) -> None:
    (
        db.table("topic_updates")
        .update({
            "chronology_narrative": narrative,
            "rag_verification_note": rag_note,
        })
        .eq("topic_id", project_topic_id)
        .eq("call_id", call_id)
        .execute()
    )
