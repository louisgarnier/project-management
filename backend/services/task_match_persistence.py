"""EPIC-19 — Task-level match group persistence.

Replaces the topic-level save_match_groups for EPIC-19 task-level matching.
Old topic-level path retained in topics_service.save_match_groups for
back-compat reads of historical projects.
"""
from __future__ import annotations

import logging
from typing import Literal, TypedDict

from backend.database.supabase_client import get_client

logger = logging.getLogger("calltracker.task_match_persistence")


class TaskRef(TypedDict, total=False):
    call_topic_name: str       # for call_task_refs
    project_topic_id: str      # for project_task_refs
    task_id: str               # the task UUID (v5-stamped for call refs, persistent for project refs)


class TaskMatchGroup(TypedDict, total=False):
    id: str  # EPIC-19 Phase B: DB row UUID, useful as a cache key
    kind: Literal["binding", "topic_merge"]
    call_task_refs: list[TaskRef]
    project_task_refs: list[TaskRef]
    target_topic_name: str | None  # EPIC-19: optional new topic name
    # EPIC-20: one finalized topic per group + explicit kind for pass routing
    finalized_topic_id: str
    group_kind: Literal["new_only", "old_only", "mixed"]


def _infer_group_kind(g: TaskMatchGroup) -> Literal["new_only", "old_only", "mixed"]:
    """EPIC-20: derive group_kind from refs. Empty groups treated as new_only placeholders."""
    has_call = bool(g.get("call_task_refs"))
    has_proj = bool(g.get("project_task_refs"))
    if has_call and has_proj:
        return "mixed"
    if has_proj:
        return "old_only"
    return "new_only"


def save_task_match_groups(
    call_id: str, groups: list[TaskMatchGroup], *, db=None,
) -> dict:
    """Persist task-level match groups. Idempotent (delete-then-insert)."""
    client = db if db is not None else get_client()
    client.table("topic_match_groups").delete().eq("call_id", call_id).execute()
    for g in groups:
        client.table("topic_match_groups").insert({
            "call_id": call_id,
            "kind": g.get("kind", "binding"),
            "call_task_refs": g.get("call_task_refs", []),
            "project_task_refs": g.get("project_task_refs", []),
            "target_topic_name": g.get("target_topic_name"),  # EPIC-19
            # EPIC-20: one-topic + explicit pass-routing kind
            "finalized_topic_id": g.get("finalized_topic_id"),
            "group_kind": g.get("group_kind") or _infer_group_kind(g),
            # Legacy cols populated for back-compat reads
            "call_topic_names": sorted({r.get("call_topic_name", "").lower().strip()
                                        for r in g.get("call_task_refs", [])
                                        if r.get("call_topic_name")}),
            "project_topic_ids": sorted({r.get("project_topic_id")
                                         for r in g.get("project_task_refs", [])
                                         if r.get("project_topic_id")}),
        }).execute()
    logger.info(f"🗄️ [TaskMatch] saved {len(groups)} group(s) for call {call_id}")
    return {"saved": len(groups)}


def load_task_match_groups(call_id: str, *, db=None) -> list[TaskMatchGroup]:
    """Return all task-level match groups for a call."""
    client = db if db is not None else get_client()
    rows = (
        client.table("topic_match_groups")
        .select("id, kind, call_task_refs, project_task_refs, target_topic_name, finalized_topic_id, group_kind")
        .eq("call_id", call_id)
        .execute()
        .data
    ) or []
    return [
        TaskMatchGroup(
            id=r.get("id"),
            kind=r.get("kind") or "binding",
            call_task_refs=r.get("call_task_refs") or [],
            project_task_refs=r.get("project_task_refs") or [],
            target_topic_name=r.get("target_topic_name"),  # EPIC-19
            finalized_topic_id=r.get("finalized_topic_id"),  # EPIC-20
            group_kind=r.get("group_kind") or "new_only",   # EPIC-20
        )
        for r in rows
    ]
