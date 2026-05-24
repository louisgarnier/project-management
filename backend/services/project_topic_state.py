"""EPIC-18 — Unified read API for project topic state.

Single source of truth consumed by v5 Stage 1 (clustering context) and
Pass 1 (verify_new). Reads from the project_topic_state DB view
(see migration 034).

Replaces ad-hoc queries against topic_registry / topic_updates that
diverged historically. New consumers MUST use this; legacy paths to be
migrated in Tasks 4 + 5.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from backend.database.supabase_client import get_client

logger = logging.getLogger("calltracker.project_topic_state")


class ProjectTopic(TypedDict, total=False):
    topic_id: str
    name: str
    summary: str
    status: str
    sentiment: str
    importance: str
    calls_open: int
    first_raised_call_id: str | None
    key_terms: list[str]
    tasks: list[dict]
    open_questions: list[dict]
    decisions: list[dict]
    evidence: list[dict]
    chronology_narrative: str | None
    rag_verification_note: str | None
    latest_update_at: str | None


def get_project_topic_state(project_id: str, *, db=None) -> list[ProjectTopic]:
    """Return all non-archived topics for a project with their latest update.

    Single source of truth for both Stage 5 clustering and Pass 1 verification.
    """
    client = db if db is not None else get_client()
    rows = (
        client.table("project_topic_state")
        .select("*")
        .eq("project_id", project_id)
        .order("latest_update_at", desc=True)
        .execute()
        .data
    ) or []
    out: list[ProjectTopic] = []
    for r in rows:
        out.append({
            "topic_id": r["topic_id"],
            "name": r["name"],
            "summary": r.get("summary") or "",
            "status": r.get("status") or "open",
            "sentiment": r.get("sentiment") or "neutral",
            "importance": r.get("importance") or "medium",
            "calls_open": r.get("calls_open") or 0,
            "first_raised_call_id": r.get("first_raised_call_id"),
            "key_terms": r.get("key_terms") or [],
            "tasks": r.get("tasks") or [],
            "open_questions": r.get("open_questions") or [],
            "decisions": r.get("decisions") or [],
            "evidence": r.get("evidence") or [],
            "chronology_narrative": r.get("chronology_narrative"),
            "rag_verification_note": r.get("rag_verification_note"),
            "latest_update_at": r.get("latest_update_at"),
        })
    logger.info(f"🗄️ [ProjectTopicState] loaded {len(out)} topics for project {project_id}")
    return out
