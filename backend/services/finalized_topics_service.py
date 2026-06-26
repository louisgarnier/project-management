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
    _original_name: str     # client hint for rename detection in diff-save


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
    """Diff-based save: keep unchanged rows, update changed, delete removed, insert new.

    Why not delete-then-insert? `topic_match_groups.finalized_topic_id` has
    ON DELETE CASCADE, so bulk-delete-then-reinsert wipes ALL task_grouping
    work for this call on every save — even when no topic was removed.
    By only deleting rows whose names are absent from the new payload, the
    cascade fires only for the topics the user actually removed.

    Rename handling: a payload entry's `_original_name` (when present) is the
    join key against the existing rows, so a rename does an UPDATE (preserving
    the row id and thus its task_match_groups).

    Returns {saved, inserted, updated, deleted_with_cascade}.
    """
    client = db if db is not None else get_client()

    existing_rows = (
        client.table("call_finalized_topics")
        .select("id, name, source, topic_id, v5_cluster_id, position")
        .eq("call_id", call_id)
        .execute()
        .data
    ) or []
    existing_by_name = {(r["name"] or "").strip().lower(): r for r in existing_rows}

    if not topics:
        # Full clear — accept the cascade cost (user removed everything).
        client.table("call_finalized_topics").delete().eq("call_id", call_id).execute()
        logger.info(
            "🗄️ [FinalizedTopics] cleared list for call %s (cascade wiped %d match groups)",
            call_id, len(existing_rows),
        )
        return {"saved": 0, "inserted": 0, "updated": 0, "deleted_with_cascade": len(existing_rows)}

    inserted = 0
    updated = 0
    matched_existing_ids: set[str] = set()

    for i, t in enumerate(topics):
        new_name = (t["name"] or "").strip()
        orig_name = (t.get("_original_name") or "").strip()
        # Prefer _original_name as the join key — it's the row we want to keep
        # when the user is renaming. Fall back to the new name when no rename.
        join_key = (orig_name or new_name).lower()
        match = existing_by_name.get(join_key)
        # Edge case: orig_name wasn't on payload but the new_name matches an
        # existing row (e.g. user toggled a topic off then on). Treat as match.
        if not match and new_name and orig_name == "":
            match = existing_by_name.get(new_name.lower())
        if match:
            matched_existing_ids.add(match["id"])
            update_payload = {
                "name": new_name,
                "source": t.get("source", "existing"),
                "topic_id": t.get("topic_id"),
                "v5_cluster_id": t.get("v5_cluster_id"),
                "position": i,
            }
            client.table("call_finalized_topics").update(update_payload).eq(
                "id", match["id"]
            ).execute()
            updated += 1
        else:
            client.table("call_finalized_topics").insert({
                "call_id": call_id,
                "name": new_name,
                "source": t.get("source", "existing"),
                "topic_id": t.get("topic_id"),
                "v5_cluster_id": t.get("v5_cluster_id"),
                "position": i,
            }).execute()
            inserted += 1

    deleted_ids = [r["id"] for r in existing_rows if r["id"] not in matched_existing_ids]
    for did in deleted_ids:
        client.table("call_finalized_topics").delete().eq("id", did).execute()

    logger.info(
        "🗄️ [FinalizedTopics] saved call %s: inserted=%d updated=%d deleted=%d (cascade wiped match groups for removed topics)",
        call_id, inserted, updated, len(deleted_ids),
    )
    return {
        "saved": inserted + updated,
        "inserted": inserted,
        "updated": updated,
        "deleted_with_cascade": len(deleted_ids),
    }
