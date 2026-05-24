"""EPIC-18 STREAM 5 — One-shot reprocess all calls' verify_new caches.

Why: STREAM 2 changed the verify_new output schema (line-number citations,
no extraction_grounded field, new verdict states). Existing cached results
are unreadable by the new frontend. Two options:
  (a) Versioned reader supporting both shapes — complex, ongoing maint cost
  (b) Reprocess past calls under new schema — this script (D6 = b)

This script resets verify_new_status + verify_new_cache to NULL for matching
calls. The user must re-open each call in the UI to trigger fresh Pass 1
under the new schema.

Usage:
  python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid>
  python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid> --dry-run
  python3 -m backend.scripts.repopulate_verify_new_cache --all
"""

from __future__ import annotations
import argparse
import asyncio
import sys

from backend.database.supabase_client import get_client


async def reprocess_call(call_id: str, *, dry_run: bool) -> dict:
    """Reset a single call's verify_new state to trigger fresh Pass 1."""
    db = get_client()
    if dry_run:
        return {"call_id": call_id, "action": "would_reprocess", "ok": True}
    # Reset state to trigger re-run via existing background task path
    db.table("calls").update({
        "verify_new_status": None,
        "verify_new_cache": None,
    }).eq("id", call_id).execute()
    return {"call_id": call_id, "action": "reset_pending_ui_trigger", "ok": True}


async def main():
    """Main entry point."""
    ap = argparse.ArgumentParser(
        description="Reset verify_new_cache to trigger re-processing under new schema"
    )
    ap.add_argument("--project", help="UUID of a single project to reset")
    ap.add_argument("--all", action="store_true", help="Reset across ALL projects")
    ap.add_argument("--dry-run", action="store_true", help="List what would be reset; no DB writes")
    args = ap.parse_args()

    if not (args.project or args.all):
        print("error: --project <uuid> or --all required", file=sys.stderr)
        return 1

    db = get_client()
    q = db.table("calls").select("id, project_id, verify_new_status")
    if args.project:
        q = q.eq("project_id", args.project)
    q = q.not_.is_("verify_new_status", "null")
    calls = q.execute().data or []
    print(f"📥 Found {len(calls)} call(s) with verify_new_cache to reprocess")
    if args.dry_run:
        print("DRY RUN — no DB changes")
    for c in calls:
        result = await reprocess_call(c["id"], dry_run=args.dry_run)
        print(f"  {result['action']}: {c['id']} (project {c['project_id']})")
    print(f"✅ Done. User must re-open each call in the UI to trigger fresh Pass 1.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
