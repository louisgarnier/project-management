"""EPIC-20 backfill — populate call_finalized_topics + finalized_topic_id +
group_kind on existing topic_match_groups rows.

Per call:
  1. Collect distinct target topics from existing match groups
     (target_topic_name first, falling back to topic_registry.name via project_topic_ids[0])
  2. Insert call_finalized_topics rows (one per distinct topic, position by encounter order)
  3. Update each topic_match_group with corresponding finalized_topic_id
  4. Derive + persist group_kind from refs

Idempotent: skip rows already populated.

Usage:
  python3 -m backend.scripts.backfill_finalized_topics --dry-run
  python3 -m backend.scripts.backfill_finalized_topics --call <call-uuid>
  python3 -m backend.scripts.backfill_finalized_topics --all
"""
from __future__ import annotations

import argparse
import logging
import sys

from backend.database.supabase_client import get_client

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill20")


def _resolve_topic_name(db, group: dict) -> tuple[str, str | None]:
    """Return (name, topic_id-or-None) for a group's target topic.

    Priority:
      1. target_topic_name (EPIC-19 user-chosen new topic name)
      2. topic_registry.name for project_topic_ids[0]
      3. fallback '(unnamed)'
    """
    name = (group.get("target_topic_name") or "").strip()
    project_ids = group.get("project_topic_ids") or []
    primary_topic_id = project_ids[0] if project_ids else None
    if not name and primary_topic_id:
        try:
            t = db.table("topic_registry").select("name").eq("id", primary_topic_id).single().execute()
            name = ((t.data or {}).get("name") or "").strip()
        except Exception as e:
            logger.warning("⚠️  topic_registry lookup failed for %s: %s", primary_topic_id, e)
    if not name:
        name = "(unnamed)"
    return name, primary_topic_id


def _infer_kind(group: dict) -> str:
    has_call = bool(group.get("call_task_refs"))
    has_proj = bool(group.get("project_task_refs"))
    if has_call and has_proj:
        return "mixed"
    if has_proj:
        return "old_only"
    return "new_only"


def backfill_call(call_id: str, *, dry_run: bool) -> dict:
    db = get_client()
    groups = db.table("topic_match_groups").select(
        "id, call_task_refs, project_task_refs, project_topic_ids, target_topic_name, finalized_topic_id, group_kind"
    ).eq("call_id", call_id).execute().data or []
    if not groups:
        logger.info("call %s: no groups, skip", call_id)
        return {"topics": 0, "groups": 0, "skipped": 0}

    # 1. Collect distinct topics (first-encounter wins for source/topic_id)
    topics_in_order: list[dict] = []
    seen_names: set[str] = set()
    for g in groups:
        name, topic_id = _resolve_topic_name(db, g)
        if name in seen_names:
            continue
        seen_names.add(name)
        topics_in_order.append({
            "name": name,
            "source": "existing" if topic_id else "new",
            "topic_id": topic_id,
        })

    if dry_run:
        logger.info("call %s [DRY]: would insert %d topics, update %d groups",
                    call_id, len(topics_in_order), len(groups))
        return {"topics": len(topics_in_order), "groups": len(groups), "skipped": 0}

    # 2. Insert call_finalized_topics
    existing_ft = db.table("call_finalized_topics").select("id, name").eq("call_id", call_id).execute().data or []
    ft_by_name = {r["name"]: r["id"] for r in existing_ft}
    to_insert = []
    for i, t in enumerate(topics_in_order):
        if t["name"] in ft_by_name:
            continue
        to_insert.append({
            "call_id": call_id,
            "name": t["name"],
            "source": t["source"],
            "topic_id": t["topic_id"],
            "position": i,
        })
    if to_insert:
        inserted = db.table("call_finalized_topics").insert(to_insert).execute().data or []
        for r in inserted:
            ft_by_name[r["name"]] = r["id"]

    # 3+4. Update each group with finalized_topic_id + group_kind
    updated_groups = 0
    skipped = 0
    for g in groups:
        if g.get("finalized_topic_id") and g.get("group_kind"):
            skipped += 1
            continue
        name, _ = _resolve_topic_name(db, g)
        ftid = ft_by_name.get(name)
        if not ftid:
            logger.warning("⚠️  call %s group %s: no finalized topic for %r", call_id, g["id"], name)
            continue
        kind = _infer_kind(g)
        db.table("topic_match_groups").update({
            "finalized_topic_id": ftid,
            "group_kind": kind,
        }).eq("id", g["id"]).execute()
        updated_groups += 1

    logger.info("✅ call %s: %d topics inserted, %d groups updated, %d already populated",
                call_id, len(to_insert), updated_groups, skipped)
    return {"topics": len(to_insert), "groups": updated_groups, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--call", help="Backfill a single call by id")
    parser.add_argument("--all", action="store_true", help="Backfill all calls in the DB")
    parser.add_argument("--dry-run", action="store_true", help="Print actions, don't mutate")
    args = parser.parse_args()

    if not args.call and not args.all:
        parser.error("must pass --call <id> or --all")

    db = get_client()
    if args.call:
        call_ids = [args.call]
    else:
        rows = db.table("calls").select("id").execute().data or []
        call_ids = [r["id"] for r in rows]

    totals = {"topics": 0, "groups": 0, "skipped": 0}
    for cid in call_ids:
        try:
            r = backfill_call(cid, dry_run=args.dry_run)
            for k in totals:
                totals[k] += r[k]
        except Exception as e:
            logger.error("❌ call %s: %s", cid, e)
    logger.info("DONE — %d topics, %d groups updated, %d already populated",
                totals["topics"], totals["groups"], totals["skipped"])


if __name__ == "__main__":
    sys.exit(main() or 0)
