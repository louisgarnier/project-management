"""EPIC-19 — Backfill historical topic-level match_groups to task-level shape.

Old shape: {call_topic_names: [...], project_topic_ids: [...]}
New shape: {call_task_refs: [...], project_task_refs: [...], kind: 'binding'}

For each historical row: fan out all tasks of each call_topic_name AND all
tasks of each project_topic_id. Conservative — produces an N:M binding row
linking every old-side task to every new-side task. Manual review may be
needed for accuracy on important historical projects.

Usage:
  python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid> --dry-run
  python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid>
  python3 -m backend.scripts.migrate_match_groups_to_task_level --all
"""
from __future__ import annotations

import argparse
import sys

from backend.database.supabase_client import get_client


def backfill_for_call(call_id: str, *, dry_run: bool) -> dict:
    db = get_client()
    rows = db.table("topic_match_groups").select("*").eq("call_id", call_id).execute().data or []
    converted = 0
    for r in rows:
        # Already migrated?
        if r.get("call_task_refs") or r.get("project_task_refs"):
            continue
        old_names = r.get("call_topic_names") or []
        old_pids = r.get("project_topic_ids") or []
        # Build refs from pending_topics + project_topic_state
        call_task_refs = []
        if old_names:
            call_row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
            pending = (call_row[0] or {}).get("pending_topics") or []
            for name in old_names:
                for t in pending:
                    if (t.get("name") or "").lower() == name.lower():
                        for task in t.get("tasks") or []:
                            if task.get("task_id"):
                                call_task_refs.append({
                                    "call_topic_name": name,
                                    "task_id": task["task_id"],
                                })
        project_task_refs = []
        for pid in old_pids:
            state_row = (
                db.table("project_topic_state")
                .select("tasks")
                .eq("topic_id", pid)
                .limit(1)
                .execute()
                .data
            )
            tasks = (state_row[0] or {}).get("tasks") if state_row else []
            for task in (tasks or []):
                if task.get("task_id"):
                    project_task_refs.append({
                        "project_topic_id": pid,
                        "task_id": task["task_id"],
                    })
        if dry_run:
            print(
                f"  would update group {r['id']}: "
                f"{len(call_task_refs)} call refs + {len(project_task_refs)} project refs"
            )
        else:
            db.table("topic_match_groups").update({
                "kind": "binding",
                "call_task_refs": call_task_refs,
                "project_task_refs": project_task_refs,
            }).eq("id", r["id"]).execute()
            converted += 1
    return {"call_id": call_id, "converted": converted, "total_rows": len(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="UUID of single project")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.project or args.all):
        print("error: --project <uuid> or --all required", file=sys.stderr)
        return 1

    db = get_client()
    q = db.table("calls").select("id, project_id")
    if args.project:
        q = q.eq("project_id", args.project)
    calls = q.execute().data or []
    print(f"📥 Found {len(calls)} call(s) to scan")
    total_converted = 0
    for c in calls:
        result = backfill_for_call(c["id"], dry_run=args.dry_run)
        total_converted += result["converted"]
        if result["total_rows"] > 0:
            print(
                f"  call {c['id']}: {result['converted']}/{result['total_rows']} "
                f"group(s) backfilled"
            )
    print(f"✅ Done. Total converted: {total_converted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
