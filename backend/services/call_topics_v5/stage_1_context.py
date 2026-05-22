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

    # ── Topic registry (project-scoped, possibly empty) ──
    registry_rows = (
        client.table("topic_registry")
        .select("id, name, description, approved_at, approved_by_call_id")
        .eq("project_id", project_id)
        .order("approved_at", desc=False)  # stable order, oldest-first
        .execute()
        .data
    )
    registry: list[RegistryEntry] = [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r.get("description") or "",
            "approved_at": r["approved_at"],
            "approved_by_call_id": r.get("approved_by_call_id"),
        }
        for r in (registry_rows or [])
    ]

    logger.info(
        "[Stage 1] project_id=%s loaded — %d registry entries",
        project_id, len(registry),
    )
    return {"project_metadata": metadata, "topic_registry": registry}
