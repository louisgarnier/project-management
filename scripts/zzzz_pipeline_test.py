"""
Full pipeline test on the ZZZZ project (real transcripts, real LLM).
Tests: full forward flow × 3 calls, then all rollback scenarios.

Run from project root:
  python3 scripts/zzzz_pipeline_test.py
"""
import asyncio, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://hxwbxmyufapinzxanvaa.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4d2J4bXl1ZmFwaW56eGFudmFhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTcxODk1MCwiZXhwIjoyMDkxMjk0OTUwfQ.GYp-olCvtesJKFBVZc39kZPNjlE1-C4HpqzmC1OnvXA")

from backend.database.supabase_client import get_client
from backend.services.topics_service import (
    extract_call_topics, aggregate_topics, rollback_to_stage,
    save_match_groups, validate_project_updates, get_pending_topics,
    list_topics_timeline,
)

RED="\033[91m"; GREEN="\033[92m"; YELLOW="\033[93m"; CYAN="\033[96m"; BOLD="\033[1m"; RESET="\033[0m"
BUGS = []

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")
def bug(label, detail):
    BUGS.append(f"{label}: {detail}")
    print(f"  {RED}BUG [{label}]{RESET} {detail}")
def section(t): print(f"\n{BOLD}{CYAN}{'═'*60}\n{t}\n{'═'*60}{RESET}")
def step(msg):  print(f"\n  {YELLOW}→{RESET} {msg}")

ZPID = "294c73a0-8a6d-4686-a955-8643ef300fee"
C1   = "b63e8845-f345-40b8-9acd-87a2aa7302a6"
C2   = "ed3335a3-3f29-4308-8120-0fc5aacb9fb4"
C3   = "e3648d11-b53f-49aa-9400-e025ffc99a75"
CALLS = [("C1", C1), ("C2", C2), ("C3", C3)]

# ── DB reads ──────────────────────────────────────────────────────────────────
def row(cid):
    db = get_client()
    r = db.table("calls").select(
        "id,title,kanban_stage,extraction_status,extraction_cache,pending_topics,merge_status,merge_cache,is_locked"
    ).eq("id", cid).execute().data
    return r[0] if r else {}

def updates(cid):
    db = get_client()
    return db.table("topic_updates").select("topic_id,status,summary").eq("call_id", cid).execute().data

def topics():
    db = get_client()
    return db.table("topics").select("id,name,calls_open,first_raised_call_id").eq("project_id", ZPID).execute().data

def match_groups(cid):
    db = get_client()
    return db.table("topic_match_groups").select("project_topic_id,call_topic_names").eq("call_id", cid).execute().data

# ── Assertions ────────────────────────────────────────────────────────────────
def chk_stage(name, cid, expected):
    actual = row(cid).get("kanban_stage", "?")
    if actual == expected: ok(f"{name} stage={actual}")
    else: bug(f"{name} stage", f"expected {expected}, got {actual}")

def chk_extraction_cache(name, cid, should_have):
    cache = row(cid).get("extraction_cache")
    if should_have:
        if cache: ok(f"{name} extraction_cache: {len(cache)} topics")
        else: bug(f"{name} extraction_cache", "null — should have topics")
    else:
        if not cache: ok(f"{name} extraction_cache: cleared ✓")
        else: bug(f"{name} extraction_cache", f"should be null but has {len(cache)} entries")

def chk_pending_topics(name, cid, should_have):
    pt = row(cid).get("pending_topics")
    if should_have:
        if pt: ok(f"{name} pending_topics: {len(pt)} topics")
        else: bug(f"{name} pending_topics", "null — should have topics")
    else:
        if not pt: ok(f"{name} pending_topics: cleared ✓")
        else: bug(f"{name} pending_topics", f"should be null but has {len(pt)} entries")

def chk_topic_updates(name, cid, should_have):
    u = updates(cid)
    if should_have:
        if u: ok(f"{name} topic_updates: {len(u)}")
        else: bug(f"{name} topic_updates", "empty — should have rows")
    else:
        if not u: ok(f"{name} topic_updates: empty ✓")
        else: bug(f"{name} topic_updates", f"should be empty but has {len(u)} rows")

def chk_match_groups(name, cid, should_have):
    mg = match_groups(cid)
    if should_have:
        if mg: ok(f"{name} match_groups: {len(mg)}")
        else: bug(f"{name} match_groups", "empty — should have groups")
    else:
        if not mg: ok(f"{name} match_groups: empty ✓")
        else: bug(f"{name} match_groups", f"should be empty but has {len(mg)}")

def snapshot(label):
    print(f"\n  {BOLD}── Snapshot: {label} ──{RESET}")
    for name, cid in CALLS:
        r = row(cid)
        u = updates(cid)
        ec_n = len(r.get("extraction_cache") or [])
        pt_n = len(r.get("pending_topics") or [])
        mg_n = len(match_groups(cid))
        print(f"    {name} | stage={r['kanban_stage']:<20} | topic_updates={len(u)} | "
              f"extraction_cache={ec_n} | pending_topics={pt_n} | match_groups={mg_n} | locked={r.get('is_locked')}")
    ts = topics()
    print(f"    topics table: {len(ts)} rows — {[t['name'][:30] for t in ts[:6]]}"
          + (f" ...+{len(ts)-6}" if len(ts)>6 else ""))

def cascade_rollback_later_calls(rolled_call_id, to_stage="call_topics"):
    """Simulate what the router cascade does."""
    db = get_client()
    rolled_row = db.table("calls").select("created_at").eq("id", rolled_call_id).execute().data
    if not rolled_row: return
    created_at = rolled_row[0]["created_at"]
    later = db.table("calls").select("id,title,kanban_stage").eq("project_id", ZPID)\
        .gt("created_at", created_at).order("created_at").execute().data
    for lc in later:
        step(f"  Cascade → {lc['title']} (currently {lc['kanban_stage']}) to {to_stage}")
        rollback_to_stage(lc["id"], to_stage)

# ─────────────────────────────────────────────────────────────────────────────
async def main():
    db = get_client()

    # ── Reset ZZZZ to clean call_topics state ─────────────────────────────
    section("RESET — Clean project state before test")
    for name, cid in CALLS:
        # Clear any stale state, leave transcript intact
        db.postgrest.session.patch(
            f"/calls?id=eq.{cid}",
            content=json.dumps({
                "kanban_stage": "call_topics",
                "extraction_status": "idle",
                "extraction_cache": None,
                "pending_topics": None,
                "merge_cache": None,
                "merge_status": "idle",
                "is_locked": False,
            }),
            headers={"Content-Type": "application/json", "Prefer": "return=representation"},
        )
        db.table("topic_updates").delete().eq("call_id", cid).execute()
        db.table("topic_match_groups").delete().eq("call_id", cid).execute()
        db.table("artifacts").delete().eq("call_id", cid).execute()
    db.table("topics").delete().eq("project_id", ZPID).execute()
    ok("ZZZZ reset: all calls at call_topics, all downstream tables cleared")
    snapshot("Initial state")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 1 — Extract topics (real LLM)")
    # ═══════════════════════════════════════════════════════════════════
    step("Running LLM extraction for C1...")
    c1_topics = await extract_call_topics(C1)
    if c1_topics:
        db.table("calls").update({"extraction_cache": c1_topics, "extraction_status": "done"}).eq("id", C1).execute()
        ok(f"C1 extraction: {len(c1_topics)} topics extracted")
        for t in c1_topics: print(f"    • {t['name']}")
    else:
        bug("C1 extraction", "returned empty topics")
        return
    chk_extraction_cache("C1", C1, True)

    step("aggregate_topics → C1 auto-advance")
    r1 = await aggregate_topics(C1, c1_topics)
    if r1.get("auto_advanced"):
        ok(f"C1 auto-advanced to artifacts (call_number={r1['call_number']})")
    else:
        bug("C1 aggregate", f"expected auto_advanced, got {r1}")
    chk_stage("C1", C1, "artifacts")
    chk_extraction_cache("C1", C1, False)
    chk_pending_topics("C1", C1, False)
    chk_topic_updates("C1", C1, True)

    c1_tu_count = len(updates(C1))
    c1_topics_in_db = topics()
    ok(f"C1: {len(c1_topics_in_db)} topics in project DB, {c1_tu_count} topic_updates")
    for t in c1_topics_in_db: print(f"    • {t['name']} (calls_open={t['calls_open']})")

    step("Advance C1 to done + lock")
    db.table("calls").update({"kanban_stage": "done", "is_locked": True}).eq("id", C1).execute()
    chk_stage("C1", C1, "done")
    ok("C1 locked")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 2 — Extract → project_matching → project_updates → done")
    # ═══════════════════════════════════════════════════════════════════
    step("Running LLM extraction for C2...")
    c2_topics = await extract_call_topics(C2)
    if c2_topics:
        db.table("calls").update({"extraction_cache": c2_topics, "extraction_status": "done"}).eq("id", C2).execute()
        ok(f"C2 extraction: {len(c2_topics)} topics extracted")
        for t in c2_topics: print(f"    • {t['name']}")
    else:
        bug("C2 extraction", "returned empty topics"); return
    chk_extraction_cache("C2", C2, True)

    step("aggregate_topics C2 → project_matching")
    r2 = await aggregate_topics(C2, c2_topics)
    if r2.get("auto_advanced"):
        bug("C2 aggregate", "unexpected auto_advance — C1 topics should be visible")
    else:
        ok(f"C2 advanced to project_matching (call_number={r2['call_number']})")
    chk_stage("C2", C2, "project_matching")
    chk_pending_topics("C2", C2, True)
    chk_extraction_cache("C2", C2, False)

    step("save_match_groups: auto-match C2 topics to existing project topics")
    c2_pending = await get_pending_topics(C2)
    project_topics_now = topics()
    pt_name_map = {t["name"].lower(): t["id"] for t in project_topics_now}

    def auto_match(call_topic_name, pt_map):
        """Fuzzy match: look for shared words."""
        words = [w.lower() for w in call_topic_name.split() if len(w) > 3]
        for pt_name, pt_id in pt_map.items():
            if any(w in pt_name for w in words):
                return pt_id
        return None

    mg2 = []
    for t in c2_pending:
        matched_id = auto_match(t["name"], pt_name_map)
        mg2.append({"project_topic_id": matched_id, "call_topic_names": [t["name"]]})
        status = f"→ EXISTING ({matched_id[:8]}...)" if matched_id else "→ NEW"
        print(f"    • {t['name']} {status}")
    await save_match_groups(C2, mg2)
    chk_stage("C2", C2, "project_updates")
    chk_match_groups("C2", C2, True)
    chk_pending_topics("C2", C2, True)

    step("validate_project_updates C2 → artifacts")
    c2_groups = match_groups(C2)
    topics_payload_2 = []
    for g in c2_groups:
        for name in g.get("call_topic_names", []):
            matching = next((p for p in c2_pending if p["name"] == name), None)
            if matching:
                topics_payload_2.append({**matching, "topic_id": g.get("project_topic_id"), "not_discussed": False})
    await validate_project_updates(C2, topics_payload_2)
    chk_stage("C2", C2, "artifacts")
    chk_topic_updates("C2", C2, True)

    c2_topics_in_db = topics()
    ok(f"After C2: {len(c2_topics_in_db)} topics in project DB")
    for t in c2_topics_in_db: print(f"    • {t['name']} (calls_open={t['calls_open']})")

    step("Advance C2 to done + lock")
    db.table("calls").update({"kanban_stage": "done", "is_locked": True}).eq("id", C2).execute()
    chk_stage("C2", C2, "done")

    # ═══════════════════════════════════════════════════════════════════
    section("CALL 3 — Extract → project_matching → project_updates → done")
    # ═══════════════════════════════════════════════════════════════════
    step("Running LLM extraction for C3...")
    c3_topics = await extract_call_topics(C3)
    if c3_topics:
        db.table("calls").update({"extraction_cache": c3_topics, "extraction_status": "done"}).eq("id", C3).execute()
        ok(f"C3 extraction: {len(c3_topics)} topics extracted")
        for t in c3_topics: print(f"    • {t['name']}")
    else:
        bug("C3 extraction", "returned empty topics"); return
    chk_extraction_cache("C3", C3, True)

    step("aggregate_topics C3 → project_matching")
    r3 = await aggregate_topics(C3, c3_topics)
    chk_stage("C3", C3, "project_matching")
    chk_pending_topics("C3", C3, True)

    step("save_match_groups C3")
    c3_pending = await get_pending_topics(C3)
    project_topics_now = topics()
    pt_name_map = {t["name"].lower(): t["id"] for t in project_topics_now}
    mg3 = []
    for t in c3_pending:
        matched_id = auto_match(t["name"], pt_name_map)
        mg3.append({"project_topic_id": matched_id, "call_topic_names": [t["name"]]})
        status = f"→ EXISTING ({matched_id[:8]}...)" if matched_id else "→ NEW"
        print(f"    • {t['name']} {status}")
    await save_match_groups(C3, mg3)
    chk_stage("C3", C3, "project_updates")

    step("validate_project_updates C3 → artifacts")
    c3_groups = match_groups(C3)
    topics_payload_3 = []
    for g in c3_groups:
        for name in g.get("call_topic_names", []):
            matching = next((p for p in c3_pending if p["name"] == name), None)
            if matching:
                topics_payload_3.append({**matching, "topic_id": g.get("project_topic_id"), "not_discussed": False})
    await validate_project_updates(C3, topics_payload_3)
    chk_stage("C3", C3, "artifacts")
    chk_topic_updates("C3", C3, True)

    step("Advance C3 to done + lock")
    db.table("calls").update({"kanban_stage": "done", "is_locked": True}).eq("id", C3).execute()
    chk_stage("C3", C3, "done")

    # ═══════════════════════════════════════════════════════════════════
    section("SNAPSHOT — All 3 calls at done")
    # ═══════════════════════════════════════════════════════════════════
    snapshot("All 3 calls done + locked")
    all_topics = topics()
    total_updates = sum(len(updates(cid)) for _, cid in CALLS)
    print(f"\n  Project topics: {len(all_topics)}")
    print(f"  Total topic_updates across all calls: {total_updates}")

    # ═══════════════════════════════════════════════════════════════════
    section("ROLLBACK TEST 1 — Roll back C2 to call_topics")
    # ═══════════════════════════════════════════════════════════════════
    topics_before = len(topics())
    c1_updates_before = len(updates(C1))

    step("Unlock C2 first (locked calls can't roll back)")
    db.table("calls").update({"is_locked": False}).eq("id", C2).execute()

    step("rollback_to_stage(C2, 'call_topics')")
    rollback_to_stage(C2, "call_topics")
    step("Cascade: roll back C3 → call_topics")
    cascade_rollback_later_calls(C2, "call_topics")

    snapshot("After rollback C2 → call_topics")

    section("  Assertions after C2 rollback:")
    chk_stage("C1", C1, "done")                       # C1 unchanged
    chk_stage("C2", C2, "call_topics")                # C2 rolled back
    chk_stage("C3", C3, "call_topics")                # C3 cascaded

    # C1 must be completely untouched
    c1_updates_after = len(updates(C1))
    if c1_updates_after == c1_updates_before:
        ok(f"C1 topic_updates unchanged: {c1_updates_after}")
    else:
        bug("C1 isolation", f"C1 topic_updates changed: {c1_updates_before} → {c1_updates_after}")

    chk_extraction_cache("C2", C2, True)              # rebuilt from topic_updates
    chk_pending_topics("C2", C2, False)               # cleared
    chk_topic_updates("C2", C2, False)                # deleted
    chk_match_groups("C2", C2, False)                 # deleted

    chk_extraction_cache("C3", C3, True)              # rebuilt from topic_updates
    chk_pending_topics("C3", C3, False)               # cleared
    chk_topic_updates("C3", C3, False)                # deleted
    chk_match_groups("C3", C3, False)                 # deleted

    # Topics table should only have C1's topics (C2+C3 orphan-cleaned)
    topics_now = topics()
    print(f"  Topics in DB after C2 rollback: {len(topics_now)}")
    for t in topics_now: print(f"    • {t['name']} (calls_open={t['calls_open']}, first_raised={t['first_raised_call_id'][:8]}...)")
    if all(t["first_raised_call_id"] == C1 for t in topics_now):
        ok(f"All remaining topics ({len(topics_now)}) belong to C1 only")
    elif topics_now:
        # Some may belong to C2/C3 if they were matched to C1 topics (not orphaned)
        non_c1 = [t for t in topics_now if t["first_raised_call_id"] != C1]
        if non_c1:
            bug("Orphan cleanup", f"{len(non_c1)} topics still exist that were first raised in C2/C3: {[t['name'] for t in non_c1]}")
    else:
        bug("Topic count", "all topics deleted, but C1's topics should remain")

    # Timeline check
    db_client = get_client()
    tl = list_topics_timeline(ZPID, db_client)
    n_pending = sum(1 for t in tl["topics"] if any(v.get("type") == "pending" for v in t["call_updates"].values()))
    n_committed = sum(1 for t in tl["topics"] if any(v.get("type") in ("new","followed_up") for v in t["call_updates"].values()))
    print(f"  Timeline: {len(tl['calls'])} calls, {len(tl['topics'])} topic rows ({n_committed} committed, {n_pending} pending)")
    if n_pending >= 1:
        ok(f"Timeline shows pending rows for C2/C3 ({n_pending} pending)")
    else:
        bug("Timeline pending", "no pending rows for C2/C3 after rollback")

    # ═══════════════════════════════════════════════════════════════════
    section("ROLLBACK TEST 2 — Roll back C1 to call_topics (C1 is done+locked)")
    # ═══════════════════════════════════════════════════════════════════
    step("Unlock C1")
    db.table("calls").update({"is_locked": False}).eq("id", C1).execute()

    step("rollback_to_stage(C1, 'call_topics')")
    rollback_to_stage(C1, "call_topics")
    step("Cascade: C2 and C3 already at call_topics — cascade still runs (idempotent)")
    cascade_rollback_later_calls(C1, "call_topics")

    snapshot("After rollback C1 → call_topics (all calls at call_topics)")

    section("  Assertions after C1 rollback:")
    chk_stage("C1", C1, "call_topics")
    chk_stage("C2", C2, "call_topics")
    chk_stage("C3", C3, "call_topics")

    chk_extraction_cache("C1", C1, True)
    chk_pending_topics("C1", C1, False)
    chk_topic_updates("C1", C1, False)
    chk_match_groups("C1", C1, False)

    # C2 and C3 already had extraction_cache from previous cascade — should still have it
    chk_extraction_cache("C2", C2, True)
    chk_extraction_cache("C3", C3, True)
    chk_topic_updates("C2", C2, False)
    chk_topic_updates("C3", C3, False)

    # Topics table should be fully empty (all orphan-cleaned)
    remaining = topics()
    if not remaining:
        ok("All topics orphan-cleaned — topics table empty ✓")
    else:
        bug("Orphan cleanup after C1 rollback", f"{len(remaining)} topics remain: {[t['name'] for t in remaining]}")

    # Timeline should show all 3 calls with pending rows
    tl2 = list_topics_timeline(ZPID, db_client)
    n_pending2 = sum(1 for t in tl2["topics"] if any(v.get("type") == "pending" for v in t["call_updates"].values()))
    print(f"  Timeline: {len(tl2['calls'])} calls, {len(tl2['topics'])} topic rows ({n_pending2} pending)")
    if len(tl2["calls"]) == 3:
        ok("Timeline: 3 calls present ✓")
    else:
        bug("Timeline calls", f"expected 3 calls, got {len(tl2['calls'])}")
    if n_pending2 >= 3:
        ok(f"Timeline shows pending rows for all calls ({n_pending2} pending rows)")
    else:
        bug("Timeline pending", f"expected >=3 pending rows, got {n_pending2}")

    # ═══════════════════════════════════════════════════════════════════
    section("ROLLBACK TEST 3 — project_matching → call_topics rollback (C2)")
    # ═══════════════════════════════════════════════════════════════════
    step("Re-run C1 to done (needed for C2/C3 to see prior topics)")
    result = await aggregate_topics(C1, c1_topics)
    db.table("calls").update({"kanban_stage": "done"}).eq("id", C1).execute()

    step("Re-run C2 to project_matching stage only")
    result = await aggregate_topics(C2, c2_topics)
    chk_stage("C2", C2, "project_matching")
    chk_pending_topics("C2", C2, True)

    step("Rollback C2 from project_matching → call_topics")
    rollback_to_stage(C2, "call_topics")
    cascade_rollback_later_calls(C2, "call_topics")
    chk_stage("C2", C2, "call_topics")
    chk_extraction_cache("C2", C2, True)  # rebuilt from pending_topics
    chk_pending_topics("C2", C2, False)
    chk_match_groups("C2", C2, False)
    chk_topic_updates("C2", C2, False)

    # ═══════════════════════════════════════════════════════════════════
    section("ROLLBACK TEST 4 — project_updates → call_topics rollback (C2)")
    # ═══════════════════════════════════════════════════════════════════
    step("Re-run C2 to project_updates stage")
    result = await aggregate_topics(C2, c2_topics)
    # Rebuild match groups with FRESH topic IDs (C1 was re-run → new topic IDs)
    fresh_pt_map = {t["name"].lower(): t["id"] for t in topics()}
    fresh_mg2 = []
    for t in c2_topics:
        matched_id = auto_match(t["name"], fresh_pt_map)
        fresh_mg2.append({"project_topic_id": matched_id, "call_topic_names": [t["name"]]})
    await save_match_groups(C2, fresh_mg2)
    chk_stage("C2", C2, "project_updates")

    step("Rollback C2 from project_updates → call_topics")
    rollback_to_stage(C2, "call_topics")
    cascade_rollback_later_calls(C2, "call_topics")
    chk_stage("C2", C2, "call_topics")
    chk_extraction_cache("C2", C2, True)
    chk_pending_topics("C2", C2, False)
    chk_match_groups("C2", C2, False)
    chk_topic_updates("C2", C2, False)

    # ═══════════════════════════════════════════════════════════════════
    section("ROLLBACK TEST 5 — artifacts → project_matching rollback (C1 auto-advance edge case)")
    # ═══════════════════════════════════════════════════════════════════
    step("Re-run C1 to artifacts (auto-advance)")
    result = await aggregate_topics(C1, c1_topics)
    chk_stage("C1", C1, "artifacts")
    chk_topic_updates("C1", C1, True)

    step("Rollback C1: artifacts → project_matching (C1 never went through project_matching)")
    rollback_to_stage(C1, "project_matching")
    chk_stage("C1", C1, "project_matching")
    chk_topic_updates("C1", C1, False)
    r = row(C1)
    has_data = bool(r.get("pending_topics")) or bool(r.get("extraction_cache"))
    if has_data:
        ok("C1 rollback→project_matching: page has data ✓")
    else:
        bug("C1 rollback→project_matching",
            "pending_topics=null AND extraction_cache=null — "
            "project_matching page will be empty (Call 1 never set pending_topics during auto-advance)")

    # ═══════════════════════════════════════════════════════════════════
    section("ROLLBACK TEST 6 — artifacts → project_updates rollback (C1 auto-advance edge case)")
    # ═══════════════════════════════════════════════════════════════════
    step("Re-run C1 to artifacts again")
    rollback_to_stage(C1, "call_topics")
    result = await aggregate_topics(C1, c1_topics)
    chk_stage("C1", C1, "artifacts")

    step("Rollback C1: artifacts → project_updates")
    rollback_to_stage(C1, "project_updates")
    chk_stage("C1", C1, "project_updates")
    chk_topic_updates("C1", C1, False)
    r = row(C1)
    has_merge = bool(r.get("merge_cache"))
    if has_merge:
        ok("C1 rollback→project_updates: merge_cache present")
    else:
        bug("C1 rollback→project_updates",
            "merge_cache=null — project_updates page empty (merge never ran for auto-advance call)")

    # ═══════════════════════════════════════════════════════════════════
    section("FINAL SUMMARY")
    # ═══════════════════════════════════════════════════════════════════
    snapshot("End state")
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}Total bugs found: {RED}{len(BUGS)}{RESET}\n")
    if BUGS:
        for i, b in enumerate(BUGS, 1):
            print(f"  {RED}{i}.{RESET} {b}")
    else:
        print(f"{GREEN}No bugs found.{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
