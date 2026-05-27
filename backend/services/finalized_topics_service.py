"""EPIC-20 Stage 1: per-call finalized topic list — CRUD.

The finalized topic list is the user's lifecycle decision for which topics are
alive for this call. Output of the topic_confirmation kanban stage; input to
the task_grouping stage.

A 'topic' entry is one of:
  - source='existing' + topic_id set: a project topic carried forward (possibly renamed)
  - source='new'      + topic_id null: a new topic introduced this call (materialised
                                        in topic_registry later, during Pass 3)
"""
from __future__ import annotations

import logging
from typing import Literal, TypedDict

from backend.database.supabase_client import get_client

logger = logging.getLogger("calltracker.finalized_topics")


class FinalizedTopic(TypedDict, total=False):
    id: str                 # uuid, server-generated on insert
    name: str
    source: Literal["existing", "new"]
    topic_id: str | None
    v5_cluster_id: str | None
    position: int


def load_finalized_topics(call_id: str, *, db=None) -> list[FinalizedTopic]:
    """Return the finalized topic list for a call, ordered by position."""
    client = db if db is not None else get_client()
    rows = (
        client.table("call_finalized_topics")
        .select("id, name, source, topic_id, v5_cluster_id, position")
        .eq("call_id", call_id)
        .order("position")
        .execute()
        .data
    ) or []
    return [
        FinalizedTopic(
            id=r.get("id"),
            name=r.get("name"),
            source=r.get("source"),
            topic_id=r.get("topic_id"),
            v5_cluster_id=r.get("v5_cluster_id"),
            position=r.get("position", 0),
        )
        for r in rows
    ]


def save_finalized_topics(
    call_id: str, topics: list[FinalizedTopic], *, db=None,
) -> dict:
    """Replace the full finalized topic list for a call (delete-then-insert).

    No transactional guarantee — Supabase Python lib doesn't expose them.
    UI reloads after save, so any partial state is visible.
    """
    client = db if db is not None else get_client()
    client.table("call_finalized_topics").delete().eq("call_id", call_id).execute()
    if not topics:
        logger.info("🗄️ [FinalizedTopics] cleared list for call %s", call_id)
        return {"saved": 0}
    rows = []
    for i, t in enumerate(topics):
        rows.append({
            "call_id": call_id,
            "name": t["name"],
            "source": t.get("source", "existing"),
            "topic_id": t.get("topic_id"),
            "v5_cluster_id": t.get("v5_cluster_id"),
            "position": i,
        })
    client.table("call_finalized_topics").insert(rows).execute()
    logger.info("🗄️ [FinalizedTopics] saved %d topic(s) for call %s", len(rows), call_id)
    return {"saved": len(rows)}
