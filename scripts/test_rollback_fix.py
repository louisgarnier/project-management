"""
Targeted test for the two rollback bugs (no LLM calls needed).
Uses stored extraction_cache from the ZZZZ project's current state.

Run from project root:
  python3 scripts/test_rollback_fix.py
"""
import asyncio, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://hxwbxmyufapinzxanvaa.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4d2J4bXl1ZmFwaW56eGFudmFhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTcxODk1MCwiZXhwIjoyMDkxMjk0OTUwfQ.GYp-olCvtesJKFBVZc39kZPNjlE1-C4HpqzmC1OnvXA")

from backend.database.supabase_client import get_client
from backend.services.topics_service import aggregate_topics, rollback_to_stage

RED="\033[91m"; GREEN="\033[92m"; YELLOW="\033[93m"; CYAN="\033[96m"; BOLD="\033[1m"; RESET="\033[0m"
BUGS = []

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def bug(label, detail):
    BUGS.append(f"{label}: {detail}")
    print(f"  {RED}BUG [{label}]{RESET} {detail}")
def section(t): print(f"\n{BOLD}{CYAN}{'═'*60}\n{t}\n{'═'*60}{RESET}")
def step(msg):  print(f"\n  {YELLOW}→{RESET} {msg}")

ZPID = "294c73a0-8a6d-4686-a955-8643ef300fee"
C1   = "b63e8845-f345-40b8-9acd-87a2aa7302a6"

def row(cid):
    db = get_client()
    r = db.table("calls").select(
        "kanban_stage,extraction_cache,pending_topics,merge_cache,merge_status"
    ).eq("id", cid).execute().data
    return r[0] if r else {}

def updates(cid):
    db = get_client()
    return db.table("topic_updates").select("topic_id").eq("call_id", cid).execute().data

FAKE_TOPICS = [
    {"name": "Risk Run Schedule", "summary": "S01-S06 timing discussed.", "follow_up_items": ["Confirm with Nick"], "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral"},
    {"name": "UAT Environment Access", "summary": "Snowflake UAT not provisioned.", "follow_up_items": ["Anand to provision"], "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"},
    {"name": "CTF Hierarchy Mapping", "summary": "Breakdown confirmed with Hassan.", "follow_up_items": [], "decisions": ["CTF: BL > Sub-BL > AC1/2/3"], "status": "resolved", "owner": "Client", "sentiment": "positive"},
]

async def main():
    db = get_client()

    # Clean state
    db.postgrest.session.patch(
        f"/calls?id=eq.{C1}",
        content=json.dumps({"kanban_stage": "call_topics", "extraction_status": "done",
                            "extraction_cache": FAKE_TOPICS, "pending_topics": None,
                            "merge_cache": None, "merge_status": "idle", "is_locked": False}),
        headers={"Content-Type": "application/json", "Prefer": "return=representation"},
    )
    db.table("topic_updates").delete().eq("call_id", C1).execute()
    db.table("topic_match_groups").delete().eq("call_id", C1).execute()
    db.table("topics").delete().eq("project_id", ZPID).execute()
    ok("C1 reset to call_topics with extraction_cache")

    # ── Auto-advance C1 → artifacts ───────────────────────────────────
    section("BUG 3 TEST — C1 rollback: artifacts → project_matching")
    step("Auto-advance C1 to artifacts")
    r = await aggregate_topics(C1, FAKE_TOPICS)
    assert r.get("auto_advanced"), f"Expected auto_advanced, got {r}"
    assert row(C1)["kanban_stage"] == "artifacts"
    ok(f"C1 at artifacts, {len(updates(C1))} topic_updates")

    step("Rollback C1: artifacts → project_matching")
    rollback_to_stage(C1, "project_matching")
    r1 = row(C1)
    assert r1["kanban_stage"] == "project_matching"
    ok("C1 stage=project_matching")
    if r1.get("pending_topics"):
        ok(f"pending_topics restored: {len(r1['pending_topics'])} topics ✓")
    else:
        bug("BUG3", "pending_topics still null after rollback→project_matching")
    if not r1.get("extraction_cache"):
        ok("extraction_cache cleared ✓")
    else:
        bug("BUG3", f"extraction_cache should be null, has {len(r1['extraction_cache'])} entries")
    if not updates(C1):
        ok("topic_updates deleted ✓")
    else:
        bug("BUG3", f"topic_updates should be empty, has {len(updates(C1))} rows")

    # ── Re-run C1 back to artifacts for Bug 4 test ────────────────────
    section("BUG 4 TEST — C1 rollback: artifacts → project_updates")
    step("Re-run C1: call_topics → artifacts")
    rollback_to_stage(C1, "call_topics")
    r = await aggregate_topics(C1, FAKE_TOPICS)
    assert r.get("auto_advanced")
    assert row(C1)["kanban_stage"] == "artifacts"
    ok(f"C1 back at artifacts, {len(updates(C1))} topic_updates")

    step("Rollback C1: artifacts → project_updates")
    rollback_to_stage(C1, "project_updates")
    r2 = row(C1)
    assert r2["kanban_stage"] == "project_updates"
    ok("C1 stage=project_updates")
    # merge_cache may still be null (merge never ran), but pending_topics should be set
    # so the user can re-run the merge preview
    if r2.get("pending_topics"):
        ok(f"pending_topics restored: {len(r2['pending_topics'])} topics ✓ (merge preview can re-run)")
    else:
        bug("BUG4", "pending_topics null — merge preview has no data to run on")
    if not updates(C1):
        ok("topic_updates deleted ✓")
    else:
        bug("BUG4", f"topic_updates should be empty, has {len(updates(C1))} rows")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{BOLD}{'─'*40}{RESET}")
    print(f"Bugs remaining: {RED if BUGS else GREEN}{len(BUGS)}{RESET}")
    for i, b in enumerate(BUGS, 1):
        print(f"  {RED}{i}.{RESET} {b}")
    if not BUGS:
        print(f"{GREEN}Both rollback bugs fixed ✓{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
