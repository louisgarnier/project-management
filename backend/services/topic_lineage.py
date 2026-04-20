"""Topic lineage helpers — walk merged_into_topic_id to collect full ancestor history.

Every merge prompt, verification prompt, and evidence-API consumer uses this module
as the single source of truth for per-topic history across M:N merges.
"""


def get_topic_lineage(topic_id: str, db) -> list[dict]:
    """BFS starting at topic_id, walking topics.merged_into_topic_id backwards.

    Returns [{id, name, archived, merged_into_topic_id}, ...] with self first.
    Cycle guard: visited set prevents infinite recursion.
    """
    visited: set[str] = set()
    result: list[dict] = []
    queue: list[str] = [topic_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        # Fetch the topic row itself
        rows = (
            db.table("topics")
            .select("id, name, archived, merged_into_topic_id")
            .eq("id", current_id)
            .execute()
            .data
        )
        if not rows:
            continue
        result.append(rows[0])

        # Find source topics whose merged_into_topic_id = current
        sources = (
            db.table("topics")
            .select("id, name, archived, merged_into_topic_id")
            .eq("merged_into_topic_id", current_id)
            .execute()
            .data
        )
        for s in sources:
            if s["id"] not in visited:
                queue.append(s["id"])

    return result


def get_lineage_topic_updates(topic_id: str, db) -> list[dict]:
    """Return topic_updates rows for the full lineage, chronologically ordered.

    Each row is enriched with:
      source_topic_id      — the topic_id the row originally belonged to
      source_topic_name    — the name of that source topic
      call_title           — looked up from calls table (may equal call_id if missing)

    Rows missing both transcript_excerpt and summary are filtered out.
    """
    lineage = get_topic_lineage(topic_id, db)
    if not lineage:
        return []

    lineage_ids = [n["id"] for n in lineage]
    name_by_id = {n["id"]: n["name"] for n in lineage}

    rows = (
        db.table("topic_updates")
        .select("topic_id, call_id, summary, transcript_excerpt, "
                "follow_up_items, decisions, status, owner, sentiment, created_at")
        .in_("topic_id", lineage_ids)
        .order("created_at")
        .execute()
        .data
    )

    # Cache call titles to avoid duplicate lookups
    title_cache: dict[str, str] = {}

    def _call_title(call_id: str) -> str:
        if call_id in title_cache:
            return title_cache[call_id]
        call_rows = db.table("calls").select("title").eq("id", call_id).execute().data
        title = call_rows[0]["title"] if call_rows else call_id
        title_cache[call_id] = title
        return title

    enriched: list[dict] = []
    for r in rows:
        if not r.get("transcript_excerpt") and not r.get("summary"):
            continue
        enriched.append({
            **r,
            "source_topic_id": r["topic_id"],
            "source_topic_name": name_by_id.get(r["topic_id"], r["topic_id"]),
            "call_title": _call_title(r["call_id"]),
        })
    return enriched
