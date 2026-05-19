"""Per-call data adapter for the xlsx tracker exporter (Story 15.8).

Returns project topics in the shape expected by build_tracker_xlsx:
each topic has a `calls: list[dict]` with per-call chronology + items.
"""

from backend.database.supabase_client import get_client


def list_project_topics_with_call_history(project_id: str) -> list[dict]:
    """Return all topics for a project, each with a calls[] array of per-call
    topic_updates (chronology_narrative, rag_verification_note, tasks,
    open_questions, decisions).

    Returns sorted by topic name, calls within each topic sorted by call_date.
    """
    db = get_client()

    # 1. Get all (non-archived) topics for the project
    topic_rows = (
        db.table("topics")
        .select("id, name, project_id, archived")
        .eq("project_id", project_id)
        .eq("archived", False)
        .execute()
        .data
    )
    if not topic_rows:
        return []
    topic_ids = [t["id"] for t in topic_rows]

    # 2. Get all topic_updates rows for those topics
    updates = (
        db.table("topic_updates")
        .select("id, topic_id, call_id, evidence, key_terms, tasks, "
                "open_questions, decisions, chronology_narrative, "
                "rag_verification_note, status, created_at")
        .in_("topic_id", topic_ids)
        .execute()
        .data
    )

    # 3. Get call dates for all involved call_ids (sorted chronologically)
    call_ids = list({u["call_id"] for u in updates if u.get("call_id")})
    call_rows = []
    if call_ids:
        call_rows = (
            db.table("calls")
            .select("id, created_at, title")
            .in_("id", call_ids)
            .execute()
            .data
        )
    calls_by_id = {c["id"]: c for c in call_rows}

    # 4. Aggregate updates per topic
    updates_by_topic: dict[str, list[dict]] = {}
    for u in updates:
        updates_by_topic.setdefault(u["topic_id"], []).append(u)

    # 5. Build the per-topic result
    out = []
    for t in topic_rows:
        tid = t["id"]
        topic_updates = updates_by_topic.get(tid, [])
        # Union key_terms across all updates (preserve insertion order, deduplicate)
        all_key_terms: list[str] = []
        seen_kt: set[str] = set()
        for u in topic_updates:
            for kt in (u.get("key_terms") or []):
                if kt not in seen_kt:
                    seen_kt.add(kt)
                    all_key_terms.append(kt)

        # Build per-call list
        calls = []
        for u in topic_updates:
            call = calls_by_id.get(u["call_id"], {})
            call_date = (call.get("created_at") or "")[:10]
            calls.append({
                "call_id": u["call_id"],
                "call_date": call_date,
                "chronology_narrative": u.get("chronology_narrative"),
                "rag_verification_note": u.get("rag_verification_note"),
                "tasks": u.get("tasks") or [],
                "open_questions": u.get("open_questions") or [],
                "decisions": u.get("decisions") or [],
                "evidence": u.get("evidence") or [],
            })
        # Sort calls by date
        calls.sort(key=lambda c: c.get("call_date") or "")

        out.append({
            "id": tid,
            "name": t["name"],
            "key_terms": all_key_terms,
            "calls": calls,
        })

    # Sort topics by name
    out.sort(key=lambda t: t.get("name") or "")
    return out
