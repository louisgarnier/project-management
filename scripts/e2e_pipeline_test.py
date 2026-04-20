"""
End-to-end pipeline test: 3 calls, all stages, all rollbacks.
Reports every invariant violation as a BUG.

Run from project root:
  python3 scripts/e2e_pipeline_test.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://hxwbxmyufapinzxanvaa.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4d2J4bXl1ZmFwaW56eGFudmFhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTcxODk1MCwiZXhwIjoyMDkxMjk0OTUwfQ.GYp-olCvtesJKFBVZc39kZPNjlE1-C4HpqzmC1OnvXA")

from backend.database.supabase_client import get_client
from backend.services.topics_service import (
    aggregate_topics, rollback_to_stage, save_match_groups,
    validate_project_updates, list_topics_timeline, get_pending_topics,
)

# ── Colours ──────────────────────────────────────────────────────────────────
RED   = "\033[91m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"
RESET = "\033[0m"

BUGS = []
PASSES = []

def ok(msg):
    PASSES.append(msg)
    print(f"  {GREEN}✓{RESET} {msg}")

def bug(label, detail):
    BUGS.append(f"{label}: {detail}")
    print(f"  {RED}BUG [{label}]{RESET} {detail}")

def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}{title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

def step(msg):
    print(f"\n  {YELLOW}→{RESET} {msg}")

# ── DB helpers ────────────────────────────────────────────────────────────────
def db_call(call_id):
    db = get_client()
    rows = db.table("calls").select(
        "id,kanban_stage,extraction_status,extraction_cache,pending_topics,merge_status,merge_cache"
    ).eq("id", call_id).execute().data
    return rows[0] if rows else None

def db_topic_updates(call_id):
    db = get_client()
    return db.table("topic_updates").select("topic_id,status").eq("call_id", call_id).execute().data

def db_topics(project_id):
    db = get_client()
    return db.table("topics").select("id,name,calls_open").eq("project_id", project_id).execute().data

def db_match_groups(call_id):
    db = get_client()
    return db.table("topic_match_groups").select("*").eq("call_id", call_id).execute().data

def assert_stage(call_id, expected, label):
    row = db_call(call_id)
    actual = row["kanban_stage"] if row else "NOT FOUND"
    if actual == expected:
        ok(f"{label}: stage={actual}")
    else:
        bug(label, f"expected stage={expected}, got {actual}")

def assert_has_extraction_cache(call_id, label):
    row = db_call(call_id)
    cache = row.get("extraction_cache") if row else None
    if cache:
        ok(f"{label}: extraction_cache populated ({len(cache)} topics)")
    else:
        bug(label, f"extraction_cache is null/empty")

def assert_no_extraction_cache(call_id, label):
    row = db_call(call_id)
    cache = row.get("extraction_cache") if row else None
    if not cache:
        ok(f"{label}: extraction_cache cleared")
    else:
        bug(label, f"extraction_cache should be null but has {len(cache)} entries")

def assert_has_pending_topics(call_id, label):
    row = db_call(call_id)
    pt = row.get("pending_topics") if row else None
    if pt:
        ok(f"{label}: pending_topics populated ({len(pt)} topics)")
    else:
        bug(label, f"pending_topics is null/empty")

def assert_no_pending_topics(call_id, label):
    row = db_call(call_id)
    pt = row.get("pending_topics") if row else None
    if not pt:
        ok(f"{label}: pending_topics cleared")
    else:
        bug(label, f"pending_topics should be null but has {len(pt)} entries")

def assert_topic_updates_count(call_id, expected_min, label):
    updates = db_topic_updates(call_id)
    if len(updates) >= expected_min:
        ok(f"{label}: topic_updates count={len(updates)} (>={expected_min})")
    else:
        bug(label, f"expected >={expected_min} topic_updates, got {len(updates)}")

def assert_no_topic_updates(call_id, label):
    updates = db_topic_updates(call_id)
    if not updates:
        ok(f"{label}: topic_updates empty")
    else:
        bug(label, f"expected 0 topic_updates, got {len(updates)}")

def assert_no_match_groups(call_id, label):
    groups = db_match_groups(call_id)
    if not groups:
        ok(f"{label}: match_groups empty")
    else:
        bug(label, f"expected 0 match_groups, got {len(groups)}")

def assert_has_match_groups(call_id, label):
    groups = db_match_groups(call_id)
    if groups:
        ok(f"{label}: match_groups present ({len(groups)})")
    else:
        bug(label, f"expected match_groups but found none")


# ── Project & data setup ──────────────────────────────────────────────────────
PROJECT_ID = "c665c1ae-c0eb-4e13-95ee-cac787e62754"

TRANSCRIPT_1 = """
John: Let's kick off. Today we want to cover the risk run schedule and data pipeline.
Sarah: The overnight runs S01 through S06 complete by 6am. S07A is still pending spec sign-off.
John: Right, S07A needs the factor grouping columns defined. Mark, can you own that?
Mark: Yes I'll send the column spec by Friday.
Sarah: Also the Snowflake UAT environment is not provisioned yet. We need that before testing.
John: Agreed. Anand, can you raise that with the DBA team this week?
Anand: Will do. Should have access by end of week.
Sarah: One more thing - the CTF composite hierarchy mapping needs to be confirmed with Hassan.
John: Hassan confirmed the breakdown: CTF splits by Business Line then Sub-BL then AC1/AC2/AC3.
Mark: Good. So we can proceed with the Snowflake normalised schema as planned.
John: Let's close here and reconvene Thursday.
"""

TRANSCRIPT_2 = """
John: Update from last week - Mark sent the S07A column spec, looks good.
Sarah: Yes, approved on our side. Now we need FactSet to implement in UAT.
Nick: We can have that in UAT by next Wednesday. Charlie is handling the implementation.
John: Great. Snowflake UAT access - Anand did that get resolved?
Anand: Yes, all team members have access now. I also started the normalised schema build.
Sarah: On the CTF hierarchy - I noticed AC2 grouping has an issue. Some accounts map to two sub-BLs.
Hassan: That's a known data quality issue. We'll resolve it on our side before go-live.
John: New topic - the S07L scope. Are we including performance attribution in Phase 1?
Hassan: No, S07L is out of Phase 1 scope. Confirmed. Phase 2 only.
Nick: Noted. We'll park S07L for now.
John: Action items: Nick to deploy S07A to UAT by Wednesday. Hassan to fix AC2 mapping.
"""

TRANSCRIPT_3 = """
John: S07A is in UAT - Nick confirmed deployment Tuesday.
Nick: Correct. Testing showed one issue: factor contribution columns are off by one row in the output.
Sarah: That's a regression from the column spec update. Need a fix before we can validate.
Nick: Charlie is on it, should be fixed by Friday.
John: Meanwhile - the ARM (Aggregated Risk Model) dashboard structure. John McLean-Hann, update?
JMH: I've wireframed the Fund Risk Analytics section. ARM shows MV, TE, Vol at composite level.
Hassan: Looks right. We also need Active VaR and Active ETL columns.
JMH: I'll add those. Should have a revised mockup by end of week.
Anand: The Snowflake schema is ready for the ARM data load. Waiting on the factor contributions fix.
John: So we're blocked on the S07A factor fix before we can load ARM data into Snowflake.
Sarah: Confirmed. Once Nick's fix is in we can proceed.
"""

def reset_project():
    """Delete all calls/topics/updates for the test project."""
    db = get_client()
    # Get all call IDs
    calls = db.table("calls").select("id").eq("project_id", PROJECT_ID).execute().data
    for c in calls:
        cid = c["id"]
        db.table("topic_updates").delete().eq("call_id", cid).execute()
        db.table("topic_match_groups").delete().eq("call_id", cid).execute()
        db.table("artifacts").delete().eq("call_id", cid).execute()
    db.table("calls").delete().eq("project_id", PROJECT_ID).execute()
    db.table("topics").delete().eq("project_id", PROJECT_ID).execute()
    print(f"  {YELLOW}↺{RESET} Project reset: deleted {len(calls)} calls")

def create_call(title):
    db = get_client()
    row = db.table("calls").insert({
        "project_id": PROJECT_ID,
        "title": title,
        "kanban_stage": "transcript",
    }).execute().data[0]
    print(f"  + Created call '{title}' id={row['id'][:8]}...")
    return row["id"]

def submit_transcript(call_id, transcript):
    db = get_client()
    db.table("calls").update({
        "transcript": transcript.strip(),
        "kanban_stage": "call_topics",
    }).eq("id", call_id).execute()

def fake_extraction(call_id, topics):
    """Simulate extraction_cache being populated (skip actual LLM call)."""
    db = get_client()
    db.table("calls").update({
        "extraction_cache": topics,
        "extraction_status": "done",
    }).eq("id", call_id).execute()

def advance_to_done(call_id):
    db = get_client()
    db.table("calls").update({"kanban_stage": "done"}).eq("id", call_id).execute()

FAKE_TOPICS_1 = [
    {"name": "S07A Factor Grouping Spec", "summary": "Column spec needed before UAT.", "follow_up_items": ["Mark to send spec by Friday"], "decisions": [], "status": "in_progress", "owner": "Both", "sentiment": "neutral"},
    {"name": "Snowflake UAT Provisioning", "summary": "UAT env not yet provisioned.", "follow_up_items": ["Anand to raise with DBA"], "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"},
    {"name": "CTF Composite Hierarchy Mapping", "summary": "Confirmed breakdown with Hassan.", "follow_up_items": [], "decisions": ["CTF splits by Business Line then Sub-BL then AC1/AC2/AC3"], "status": "resolved", "owner": "Client", "sentiment": "positive"},
]

FAKE_TOPICS_2 = [
    {"name": "S07A UAT Deployment", "summary": "Column spec approved, Nick deploying to UAT by Wednesday.", "follow_up_items": ["Nick to deploy S07A to UAT by Wednesday"], "decisions": ["S07A spec approved"], "status": "in_progress", "owner": "Us", "sentiment": "positive"},
    {"name": "AC2 Hierarchy Data Quality", "summary": "Some accounts map to two sub-BLs, Hassan to fix.", "follow_up_items": ["Hassan to fix AC2 mapping before go-live"], "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"},
    {"name": "S07L Phase 1 Scope Decision", "summary": "S07L performance attribution deferred to Phase 2.", "follow_up_items": [], "decisions": ["S07L out of Phase 1 — Phase 2 only"], "status": "resolved", "owner": "Both", "sentiment": "neutral"},
]

FAKE_TOPICS_3 = [
    {"name": "S07A Factor Contribution Row Bug", "summary": "Factor columns off by one row in UAT output, Charlie fixing.", "follow_up_items": ["Charlie to fix factor row issue by Friday"], "decisions": [], "status": "open", "owner": "Us", "sentiment": "concern"},
    {"name": "ARM Dashboard Wireframe", "summary": "JMH wireframed Fund Risk Analytics — MV, TE, Vol. Hassan requested Active VaR and Active ETL.", "follow_up_items": ["JMH to add Active VaR/ETL columns to mockup"], "decisions": [], "status": "in_progress", "owner": "Client", "sentiment": "positive"},
    {"name": "Snowflake ARM Data Load Blocker", "summary": "Schema ready but blocked on S07A factor fix before data load.", "follow_up_items": [], "decisions": [], "status": "open", "owner": "Both", "sentiment": "concern"},
]


async def main():
    section("SETUP — Reset project")
    reset_project()

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 1 — Normal forward flow (auto-advance path)")
    # ═══════════════════════════════════════════════════════════════════
    c1 = create_call("Call 1")

    step("Submit transcript → call_topics")
    submit_transcript(c1, TRANSCRIPT_1)
    assert_stage(c1, "call_topics", "C1 after transcript")

    step("Simulate extraction → extraction_cache populated")
    fake_extraction(c1, FAKE_TOPICS_1)
    assert_has_extraction_cache(c1, "C1 after extraction")

    step("aggregate_topics → Call 1 auto-advance to artifacts")
    result = await aggregate_topics(c1, FAKE_TOPICS_1)
    if result.get("auto_advanced"):
        ok("C1 aggregate: auto_advanced=True")
    else:
        bug("C1 aggregate", f"expected auto_advanced=True, got {result}")
    assert_stage(c1, "artifacts", "C1 after aggregate")
    assert_no_extraction_cache(c1, "C1 after aggregate")
    assert_no_pending_topics(c1, "C1 after aggregate")
    assert_topic_updates_count(c1, 3, "C1 after aggregate topic_updates")

    topics_after_c1 = db_topics(PROJECT_ID)
    if len(topics_after_c1) >= 3:
        ok(f"C1: {len(topics_after_c1)} topics in project")
    else:
        bug("C1 topics", f"expected >=3 project topics, got {len(topics_after_c1)}")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 1 — Rollback tests (all valid targets)")
    # ═══════════════════════════════════════════════════════════════════

    # -- Rollback: artifacts → call_topics --------------------------------
    step("Rollback C1: artifacts → call_topics")
    rollback_to_stage(c1, "call_topics")
    assert_stage(c1, "call_topics", "C1 rollback→call_topics stage")
    assert_has_extraction_cache(c1, "C1 rollback→call_topics: extraction_cache rebuilt")
    assert_no_pending_topics(c1, "C1 rollback→call_topics: pending_topics cleared")
    assert_no_topic_updates(c1, "C1 rollback→call_topics: topic_updates deleted")
    assert_no_match_groups(c1, "C1 rollback→call_topics: match_groups deleted")

    # Re-run forward to artifacts for next rollback tests
    result = await aggregate_topics(c1, FAKE_TOPICS_1)
    assert_stage(c1, "artifacts", "C1 re-aggregate to artifacts")
    assert_topic_updates_count(c1, 3, "C1 re-aggregate topic_updates")

    # -- Rollback: artifacts → project_matching ---------------------------
    step("Rollback C1: artifacts → project_matching (Call 1 never went through project_matching)")
    rollback_to_stage(c1, "project_matching")
    assert_stage(c1, "project_matching", "C1 rollback→project_matching stage")
    # For Call 1 (auto-advance), pending_topics was never set.
    # After rollback, the page needs SOME data. Check what's available.
    row = db_call(c1)
    has_data = bool(row.get("pending_topics")) or bool(row.get("extraction_cache"))
    if has_data:
        ok("C1 rollback→project_matching: page has data (pending_topics or extraction_cache)")
    else:
        bug("C1 rollback→project_matching",
            "pending_topics=null AND extraction_cache=null — project_matching page will be empty for Call 1")
    assert_no_topic_updates(c1, "C1 rollback→project_matching: topic_updates deleted")

    # Re-run forward to artifacts again
    # First restore to call_topics so we can re-aggregate
    rollback_to_stage(c1, "call_topics")
    result = await aggregate_topics(c1, FAKE_TOPICS_1)
    assert_stage(c1, "artifacts", "C1 re-run to artifacts (for project_updates test)")

    # -- Rollback: artifacts → project_updates ----------------------------
    step("Rollback C1: artifacts → project_updates (Call 1 never went through project_updates)")
    rollback_to_stage(c1, "project_updates")
    assert_stage(c1, "project_updates", "C1 rollback→project_updates stage")
    # For Call 1, merge_cache was never set. Check what's available.
    row = db_call(c1)
    has_merge = bool(row.get("merge_cache"))
    if has_merge:
        ok("C1 rollback→project_updates: merge_cache present")
    else:
        bug("C1 rollback→project_updates",
            "merge_cache=null — project_updates page will be empty for Call 1 (merge never ran)")
    assert_no_topic_updates(c1, "C1 rollback→project_updates: topic_updates deleted")

    # Re-run forward to artifacts (restore)
    rollback_to_stage(c1, "call_topics")
    result = await aggregate_topics(c1, FAKE_TOPICS_1)
    assert_stage(c1, "artifacts", "C1 restore to artifacts after project_updates rollback test")

    # -- Advance C1 to done for cascade tests later -----------------------
    step("Advance C1 to done")
    advance_to_done(c1)
    assert_stage(c1, "done", "C1 advanced to done")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 2 — Normal forward flow (project_matching path)")
    # ═══════════════════════════════════════════════════════════════════
    c2 = create_call("Call 2")

    step("Submit transcript → call_topics")
    submit_transcript(c2, TRANSCRIPT_2)
    assert_stage(c2, "call_topics", "C2 after transcript")

    step("Simulate extraction → extraction_cache populated")
    fake_extraction(c2, FAKE_TOPICS_2)
    assert_has_extraction_cache(c2, "C2 after extraction")

    step("aggregate_topics → Call 2 advances to project_matching")
    result = await aggregate_topics(c2, FAKE_TOPICS_2)
    if result.get("auto_advanced"):
        bug("C2 aggregate", "unexpected auto_advance — Call 2 should see prior topics")
    else:
        ok(f"C2 aggregate: advanced_to={result.get('advanced_to')}")
    assert_stage(c2, "project_matching", "C2 after aggregate")
    assert_has_pending_topics(c2, "C2 after aggregate: pending_topics set")
    assert_no_extraction_cache(c2, "C2 after aggregate: extraction_cache cleared")

    step("save_match_groups → project_updates")
    db = get_client()
    project_topics = db_topics(PROJECT_ID)
    # Build simple match groups: match each call topic to a project topic or mark as new
    pt_map = {t["name"]: t["id"] for t in project_topics}
    match_groups = []
    for ft in FAKE_TOPICS_2:
        # Try to find a match by keyword
        matched_id = None
        for pt_name, pt_id in pt_map.items():
            if any(word in pt_name for word in ft["name"].split()[:2]):
                matched_id = pt_id
                break
        match_groups.append({
            "project_topic_id": matched_id,
            "call_topic_names": [ft["name"]],
        })
    result = await save_match_groups(c2, match_groups)
    assert_stage(c2, "project_updates", "C2 after save_match_groups")
    assert_has_match_groups(c2, "C2 after save_match_groups")
    assert_has_pending_topics(c2, "C2 after save_match_groups: pending_topics preserved")

    step("validate_project_updates → artifacts")
    # Build topics payload from pending_topics + match groups
    pending = await get_pending_topics(c2)
    # Give each a topic_id if matched
    topics_payload = []
    groups = db_match_groups(c2)
    for g in groups:
        for name in g.get("call_topic_names", []):
            matching = next((p for p in pending if p["name"] == name), None)
            if matching:
                topics_payload.append({
                    **matching,
                    "topic_id": g.get("project_topic_id"),
                    "not_discussed": False,
                })
    if not topics_payload:
        # Fallback: save all as new
        topics_payload = [{**p, "topic_id": None, "not_discussed": False} for p in pending]

    result = await validate_project_updates(c2, topics_payload)
    assert_stage(c2, "artifacts", "C2 after validate_project_updates")
    assert_topic_updates_count(c2, 1, "C2 after validate: topic_updates created")

    topics_after_c2 = db_topics(PROJECT_ID)
    if len(topics_after_c2) >= 3:
        ok(f"C2: {len(topics_after_c2)} topics in project")
    else:
        bug("C2 topics", f"expected >=3 project topics after Call 2, got {len(topics_after_c2)}")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 2 — Rollback tests")
    # ═══════════════════════════════════════════════════════════════════

    # -- artifacts → project_updates --------------------------------------
    step("Rollback C2: artifacts → project_updates")
    rollback_to_stage(c2, "project_updates")
    assert_stage(c2, "project_updates", "C2 rollback→project_updates stage")
    assert_no_topic_updates(c2, "C2 rollback→project_updates: topic_updates deleted")
    assert_has_pending_topics(c2, "C2 rollback→project_updates: pending_topics preserved")
    assert_has_match_groups(c2, "C2 rollback→project_updates: match_groups preserved")
    row = db_call(c2)
    if row.get("merge_cache"):
        ok("C2 rollback→project_updates: merge_cache preserved")
    else:
        bug("C2 rollback→project_updates",
            "merge_cache=null — project_updates page will show nothing unless user re-runs merge (merge was never run in this test, but this verifies the clearing behaviour)")

    # Re-run forward
    result = await validate_project_updates(c2, topics_payload)
    assert_stage(c2, "artifacts", "C2 re-advance to artifacts")

    # -- artifacts → project_matching -------------------------------------
    step("Rollback C2: artifacts → project_matching")
    rollback_to_stage(c2, "project_matching")
    assert_stage(c2, "project_matching", "C2 rollback→project_matching stage")
    assert_no_topic_updates(c2, "C2 rollback→project_matching: topic_updates deleted")
    assert_has_pending_topics(c2, "C2 rollback→project_matching: pending_topics preserved")
    assert_has_match_groups(c2, "C2 rollback→project_matching: match_groups preserved (user work kept)")
    row = db_call(c2)
    if not row.get("merge_cache"):
        ok("C2 rollback→project_matching: merge_cache cleared")
    else:
        bug("C2 rollback→project_matching", "merge_cache should be cleared but still has data")

    # Re-run forward
    result = await save_match_groups(c2, match_groups)
    result = await validate_project_updates(c2, topics_payload)
    assert_stage(c2, "artifacts", "C2 re-advance to artifacts after project_matching rollback")

    # -- artifacts → call_topics ------------------------------------------
    step("Rollback C2: artifacts → call_topics")
    rollback_to_stage(c2, "call_topics")
    assert_stage(c2, "call_topics", "C2 rollback→call_topics stage")
    assert_has_extraction_cache(c2, "C2 rollback→call_topics: extraction_cache rebuilt")
    assert_no_pending_topics(c2, "C2 rollback→call_topics: pending_topics cleared")
    assert_no_topic_updates(c2, "C2 rollback→call_topics: topic_updates deleted")
    assert_no_match_groups(c2, "C2 rollback→call_topics: match_groups deleted")

    # project_matching → call_topics (no topic_updates at project_matching)
    step("Rollback C2: project_matching → call_topics")
    # Re-aggregate to project_matching first
    result = await aggregate_topics(c2, FAKE_TOPICS_2)
    assert_stage(c2, "project_matching", "C2 re-aggregated to project_matching")
    rollback_to_stage(c2, "call_topics")
    assert_stage(c2, "call_topics", "C2 rollback project_matching→call_topics stage")
    # extraction_cache should be rebuilt from pending_topics (set during aggregate)
    assert_has_extraction_cache(c2, "C2 rollback project_matching→call_topics: extraction_cache from pending_topics")
    assert_no_pending_topics(c2, "C2 rollback project_matching→call_topics: pending_topics cleared")

    # Re-run C2 fully to done for cascade tests
    step("Re-run C2 fully to done")
    result = await aggregate_topics(c2, FAKE_TOPICS_2)
    result = await save_match_groups(c2, match_groups)
    result = await validate_project_updates(c2, topics_payload)
    advance_to_done(c2)
    assert_stage(c2, "done", "C2 advanced to done")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 3 — Normal forward flow")
    # ═══════════════════════════════════════════════════════════════════
    c3 = create_call("Call 3")

    step("Submit transcript → call_topics")
    submit_transcript(c3, TRANSCRIPT_3)
    fake_extraction(c3, FAKE_TOPICS_3)
    assert_has_extraction_cache(c3, "C3 after extraction")

    step("aggregate_topics → project_matching")
    result = await aggregate_topics(c3, FAKE_TOPICS_3)
    assert_stage(c3, "project_matching", "C3 after aggregate")
    assert_has_pending_topics(c3, "C3 pending_topics")

    step("save_match_groups → project_updates")
    # Build match groups for C3
    project_topics_now = db_topics(PROJECT_ID)
    pt_map_now = {t["name"]: t["id"] for t in project_topics_now}
    match_groups_3 = []
    for ft in FAKE_TOPICS_3:
        matched_id = None
        for pt_name, pt_id in pt_map_now.items():
            if any(word in pt_name for word in ft["name"].split()[:2]):
                matched_id = pt_id
                break
        match_groups_3.append({"project_topic_id": matched_id, "call_topic_names": [ft["name"]]})
    await save_match_groups(c3, match_groups_3)
    assert_stage(c3, "project_updates", "C3 after save_match_groups")

    step("validate_project_updates → artifacts")
    pending_3 = await get_pending_topics(c3)
    topics_payload_3 = [{**p, "topic_id": None, "not_discussed": False} for p in pending_3]
    await validate_project_updates(c3, topics_payload_3)
    assert_stage(c3, "artifacts", "C3 after validate")
    assert_topic_updates_count(c3, 1, "C3 topic_updates created")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 3 — Rollback tests")
    # ═══════════════════════════════════════════════════════════════════

    step("Rollback C3: artifacts → call_topics")
    rollback_to_stage(c3, "call_topics")
    assert_stage(c3, "call_topics", "C3 rollback→call_topics stage")
    assert_has_extraction_cache(c3, "C3 rollback→call_topics: extraction_cache rebuilt")
    assert_no_pending_topics(c3, "C3 rollback→call_topics: pending_topics cleared")
    assert_no_match_groups(c3, "C3 rollback→call_topics: match_groups cleared")

    # Re-run C3 fully to done
    step("Re-run C3 fully to done")
    result = await aggregate_topics(c3, FAKE_TOPICS_3)
    await save_match_groups(c3, match_groups_3)
    await validate_project_updates(c3, topics_payload_3)
    advance_to_done(c3)
    assert_stage(c3, "done", "C3 advanced to done")

    # ═══════════════════════════════════════════════════════════════════
    section("CROSS-CALL CASCADE — Rollback C1, should cascade C2+C3 to call_topics")
    # ═══════════════════════════════════════════════════════════════════
    # State: C1=done, C2=done, C3=done

    step("Check all calls are done")
    for cid, name in [(c1, "C1"), (c2, "C2"), (c3, "C3")]:
        assert_stage(cid, "done", f"{name} at done before cascade test")

    step("Rollback C1: done → call_topics (should cascade C2, C3 → call_topics)")
    rollback_to_stage(c1, "call_topics")

    assert_stage(c1, "call_topics", "C1 after cascade rollback")
    assert_has_extraction_cache(c1, "C1 extraction_cache rebuilt from topic_updates")
    assert_no_topic_updates(c1, "C1 topic_updates deleted")

    # Cascade is triggered by the router, not by rollback_to_stage directly.
    # In this test we call rollback_to_stage directly, so no auto-cascade.
    # We manually cascade to simulate what the router does.
    step("Manually cascade C2 and C3 → call_topics (simulating router cascade)")
    rollback_to_stage(c2, "call_topics")
    rollback_to_stage(c3, "call_topics")

    assert_stage(c2, "call_topics", "C2 cascaded to call_topics")
    assert_stage(c3, "call_topics", "C3 cascaded to call_topics")
    assert_has_extraction_cache(c2, "C2 extraction_cache rebuilt after cascade")
    assert_has_extraction_cache(c3, "C3 extraction_cache rebuilt after cascade")
    assert_no_topic_updates(c2, "C2 topic_updates deleted after cascade")
    assert_no_topic_updates(c3, "C3 topic_updates deleted after cascade")
    assert_no_match_groups(c2, "C2 match_groups deleted after cascade")
    assert_no_match_groups(c3, "C3 match_groups deleted after cascade")

    # Check topics table — should be empty (all orphan-cleaned)
    remaining_topics = db_topics(PROJECT_ID)
    if not remaining_topics:
        ok("All topics orphan-cleaned after full cascade")
    else:
        bug("Cascade orphan cleanup", f"{len(remaining_topics)} topics remain in DB after all cascades: {[t['name'] for t in remaining_topics]}")

    # ═══════════════════════════════════════════════════════════════════
    section("TIMELINE — pending rows check after cascade")
    # ═══════════════════════════════════════════════════════════════════
    step("list_topics_timeline after cascade (all calls at call_topics with extraction_cache)")
    db = get_client()
    timeline = list_topics_timeline(PROJECT_ID, db)
    n_calls = len(timeline["calls"])
    n_topics = len(timeline["topics"])
    if n_calls == 3:
        ok(f"Timeline: {n_calls} calls present")
    else:
        bug("Timeline calls", f"expected 3 calls, got {n_calls}")

    if n_topics >= 9:  # 3 topics per call × 3 calls
        ok(f"Timeline: {n_topics} pending topic rows (>= 9 expected)")
    else:
        bug("Timeline pending rows", f"expected >=9 pending rows, got {n_topics}")

    pending_types = [
        t["call_updates"][list(t["call_updates"].keys())[0]]["type"]
        for t in timeline["topics"]
        if t["call_updates"]
    ]
    non_pending = [x for x in pending_types if x != "pending"]
    if not non_pending:
        ok("Timeline: all topic rows are type='pending'")
    else:
        bug("Timeline types", f"some rows are not type='pending': {set(non_pending)}")

    # ═══════════════════════════════════════════════════════════════════
    section("SUMMARY")
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}Passed: {GREEN}{len(PASSES)}{RESET}")
    print(f"{BOLD}Bugs:   {RED}{len(BUGS)}{RESET}\n")
    if BUGS:
        print(f"{RED}{BOLD}BUG LIST:{RESET}")
        for i, b in enumerate(BUGS, 1):
            print(f"  {RED}{i}.{RESET} {b}")
    else:
        print(f"{GREEN}No bugs found.{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
