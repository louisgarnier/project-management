"""Stage 1 — project context + topic registry loader.

Pure code, no LLM. Loads project metadata + the project's topic_registry
(controlled vocabulary of canonical topic names accumulated from prior calls).

The output `context_bundle` is consumed by Stage 2 (atomic extraction) and
Stage 5 (topic clustering — uses the registry as preferred vocabulary).

Empty registry → returns empty list, NOT error (covers new projects + the
arm_kickoff gold set transcript which has registry_state=empty_at_start).
"""

from __future__ import annotations

import logging
from typing import TypedDict

from backend.database.supabase_client import get_client
from backend.services.project_topic_state import get_project_topic_state

logger = logging.getLogger("calltracker.call_topics_v5.stage_1")


class ProjectMetadata(TypedDict, total=False):
    project_id: str
    name: str
    description: str
    context: str  # the project's `context` column — free-form notes from user
    default_llm: str
    default_model: str | None


class RegistryEntry(TypedDict, total=False):
    id: str
    name: str
    description: str
    key_terms: list[str]  # NEW EPIC-18
    tasks: list[dict]     # NEW EPIC-18
    approved_at: str
    approved_by_call_id: str | None


class ContextBundle(TypedDict):
    project_metadata: ProjectMetadata
    topic_registry: list[RegistryEntry]


def load_context(project_id: str, *, db=None) -> ContextBundle:
    """Load project metadata + topic_registry for a project.

    Args:
        project_id: UUID of the project.
        db: optional Supabase client (mostly for tests). Defaults to module-level singleton.

    Returns:
        ContextBundle with project_metadata + topic_registry list (possibly empty).

    Raises:
        ValueError if the project does not exist.
    """
    client = db if db is not None else get_client()

    # ── Project metadata ──
    proj_rows = (
        client.table("projects")
        .select("id, name, description, context, default_llm, default_model")
        .eq("id", project_id)
        .limit(1)
        .execute()
        .data
    )
    if not proj_rows:
        raise ValueError(f"project {project_id!r} not found")
    proj = proj_rows[0]
    metadata: ProjectMetadata = {
        "project_id": proj["id"],
        "name": proj.get("name") or "",
        "description": proj.get("description") or "",
        "context": proj.get("context") or "",
        "default_llm": proj.get("default_llm") or "openrouter",
        "default_model": proj.get("default_model"),
    }

    # ── Topic state (EPIC-18 unified read) ──
    topic_state = get_project_topic_state(project_id, db=client)
    # NOTE: field name `topic_registry` retained in ContextBundle for backward compat
    # with Stage 5 and orchestrator; semantically this is now the full topic state.
    registry: list[RegistryEntry] = [
        {
            "id": t["topic_id"],
            "name": t["name"],
            "description": t.get("summary") or "",
            # NEW (EPIC-18) — structural payload for Stage 5 V5-CORE
            "key_terms": t.get("key_terms") or [],
            "tasks": t.get("tasks") or [],
            "approved_at": t.get("latest_update_at") or "",
            "approved_by_call_id": t.get("first_raised_call_id"),
        }
        for t in topic_state
    ]

    logger.info(
        "[Stage 1] project_id=%s loaded — %d registry entries",
        project_id, len(registry),
    )
    return {"project_metadata": metadata, "topic_registry": registry}
