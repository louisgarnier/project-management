"""Topic lineage helpers — walk merged_into_topic_id to collect full ancestor history.

Every merge prompt, verification prompt, and evidence-API consumer uses this module
as the single source of truth for per-topic history across M:N merges.
"""

from backend.utils.logger import db_logger as logger


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
                "tasks, decisions, open_questions, status, created_at, "
                "chronology_narrative, rag_verification_note")
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


def build_lineage_evidence_block(topic_name: str, topic_id: str, db) -> str:
    """Render per-call evidence as a text block for merge-prompt consumption.

    Format:
        == Topic: "{topic_name}" — Per-Call Evidence ==

        --- {call_title} ---
        (from archived topic: {source_topic_name})    # only when row came from ancestor
        Transcript: {transcript_excerpt}
        Summary: {summary}
        Action items from this call:
          - {task.task}
        Decisions from this call:
          - {decision.text}

    When there are no lineage rows, returns a single "(No historical excerpts
    available)" line so prompts don't break.
    """
    rows = get_lineage_topic_updates(topic_id, db)
    if not rows:
        return f'== Topic: "{topic_name}" ==\n(No historical excerpts available)\n'

    ancestor_sources = {
        r["source_topic_id"] for r in rows if r["source_topic_id"] != topic_id
    }
    if ancestor_sources:
        logger.info(
            f"🧬 [Lineage] Evidence for topic {topic_id} ({topic_name}) "
            f"includes {len(ancestor_sources)} ancestor(s): {sorted(ancestor_sources)}"
        )

    lines = [f'== Topic: "{topic_name}" — Per-Call Evidence ==']
    for r in rows:
        lines.append(f'\n--- {r["call_title"]} ---')
        if r["source_topic_id"] != topic_id:
            lines.append(f'(from archived topic: {r["source_topic_name"]})')
        if r.get("transcript_excerpt"):
            lines.append(f'Transcript: {r["transcript_excerpt"]}')
        if r.get("summary"):
            lines.append(f'Summary: {r["summary"]}')
        tasks = r.get("tasks") or []
        if tasks:
            lines.append("Action items from this call:")
            for task in tasks:
                task_text = task.get("task", "") if isinstance(task, dict) else str(task)
                lines.append(f"  - {task_text}")
        decisions = r.get("decisions") or []
        if decisions:
            lines.append("Decisions from this call:")
            for d in decisions:
                d_text = d.get("text", "") if isinstance(d, dict) else str(d)
                lines.append(f"  - {d_text}")
    return "\n".join(lines)


def get_lineage_match_groups(topic_id: str, db) -> list[dict]:
    """Return topic_match_groups whose project_topic_ids intersects the lineage.

    Enriched with call_title. Ordered by created_at ascending.
    """
    lineage = get_topic_lineage(topic_id, db)
    lineage_id_set = {n["id"] for n in lineage}

    all_groups = (
        db.table("topic_match_groups")
        .select("call_id, project_topic_ids, call_topic_names, created_at")
        .execute()
        .data
    )

    matched = [
        g for g in all_groups
        if any(pid in lineage_id_set for pid in (g.get("project_topic_ids") or []))
    ]
    matched.sort(key=lambda g: g.get("created_at", ""))

    title_cache: dict[str, str] = {}
    for g in matched:
        cid = g["call_id"]
        if cid not in title_cache:
            rows = db.table("calls").select("title").eq("id", cid).execute().data
            title_cache[cid] = rows[0]["title"] if rows else cid
        g["call_title"] = title_cache[cid]
    return matched
