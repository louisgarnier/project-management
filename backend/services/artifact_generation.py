"""Context-assembly seam for LLM artifact generation (Story 15.6).

Given an artifact_type's `context_scope` value, builds the string-shaped context
that goes into the LLM prompt. Centralised here so all 4 enum values are handled
in one place; gen_one and any future caller just supplies (scope, call_id,
project_id) and gets back a ready-to-paste string.

The module-level names `list_call_topics` and `list_project_topics` are sync
DB query helpers that accept the db client. They are exposed as module attributes
so tests can monkeypatch them directly.
"""

from typing import Literal

import backend.services.topics_service as _topics_svc

ContextScope = Literal[
    "this_call_transcript",
    "all_call_transcripts",
    "this_call_topics",
    "all_project_topics",
]


def list_call_topics(call_id: str, db=None) -> list[dict]:
    """Sync DB query for topics belonging to a single call.

    Mirrors the logic of topics_service.list_call_topics without requiring an
    event loop, so it can be called from inside an async context without
    asyncio.run() conflicts.
    """
    if db is None:
        from backend.database.supabase_client import get_client
        db = get_client()

    updates = (
        db.table("topic_updates")
        .select(
            "id, topic_id, summary, status, sentiment, importance, "
            "evidence, key_terms, tasks, created_at, "
            "open_questions, decisions, chronology_narrative, rag_verification_note"
        )
        .eq("call_id", call_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )

    # Deduplicate: keep only the latest update per topic_id
    seen: set[str] = set()
    deduped = []
    for u in updates:
        tid = u["topic_id"]
        if tid not in seen:
            seen.add(tid)
            deduped.append(u)

    result = []
    for u in deduped:
        topic_rows = (
            db.table("topics")
            .select("id, name, calls_open")
            .eq("id", u["topic_id"])
            .execute()
            .data
        )
        if topic_rows:
            t = topic_rows[0]
            result.append(
                {
                    "id": u["id"],
                    "topic_id": t["id"],
                    "name": t["name"],
                    "calls_open": t.get("calls_open"),
                    "summary": u.get("summary") or "",
                    "status": u.get("status") or "open",
                    "sentiment": u.get("sentiment") or "neutral",
                    "importance": u.get("importance") or "medium",
                    "evidence": u.get("evidence") or [],
                    "key_terms": u.get("key_terms") or [],
                    "tasks": u.get("tasks") or [],
                    "open_questions": u.get("open_questions") or [],
                    "decisions": u.get("decisions") or [],
                    "chronology_narrative": u.get("chronology_narrative"),
                    "rag_verification_note": u.get("rag_verification_note"),
                }
            )

    return result


def list_project_topics(project_id: str, db=None) -> list[dict]:
    """Sync DB query for all non-archived project topics with per-call history.

    Delegates to topics_service._get_previous_topics which is already sync.
    """
    if db is None:
        from backend.database.supabase_client import get_client
        db = get_client()
    return _topics_svc._get_previous_topics(project_id, db)


def _assemble_context(scope: str, call_id: str, project_id: str, db) -> str:
    """Build the LLM context string for the given scope.

    - this_call_transcript → only the current call's transcript text.
    - all_call_transcripts → every transcript in this project, chronological,
       INCLUDING the current call, labelled by call date.
    - this_call_topics → only this call's topic_updates, rendered as structured
       text (name + 3 anchor sections + key_terms).
    - all_project_topics → all topic_updates across all calls in the project,
       chronological per topic, INCLUDING any chronology_narrative +
       rag_verification_note text on each (topic, call) cell when present.

    Raises ValueError on unknown scope.
    """
    if scope == "this_call_transcript":
        return _render_call_transcript(call_id, db)
    if scope == "all_call_transcripts":
        return _render_all_call_transcripts(project_id, db)
    if scope == "this_call_topics":
        topics = list_call_topics(call_id, db)
        return _render_call_topics_text(topics)
    if scope == "all_project_topics":
        topics = list_project_topics(project_id, db)
        return _render_project_topics_text(topics)
    raise ValueError(f"unknown context_scope: {scope!r}")


def _render_call_transcript(call_id: str, db) -> str:
    rows = db.table("calls").select("transcript").eq("id", call_id).execute().data
    if not rows:
        return ""
    return rows[0].get("transcript") or ""


def _render_all_call_transcripts(project_id: str, db) -> str:
    rows = (
        db.table("calls")
        .select("id, transcript, created_at")
        .eq("project_id", project_id)
        .order("created_at")
        .execute()
        .data
    )
    blocks = []
    for r in rows:
        if not r.get("transcript"):
            continue
        date = (r.get("created_at") or "")[:10]
        blocks.append(f"=== Call {date} ===\n{r['transcript']}")
    return "\n\n".join(blocks)


def _render_call_topics_text(topics: list[dict]) -> str:
    if not topics:
        return "(no topics extracted for this call)"
    blocks = []
    for t in topics:
        lines = [f"## {t.get('name', '(unnamed)')}"]
        kt = t.get("key_terms") or []
        if kt:
            lines.append(f"Key terms: {', '.join(kt)}")
        tasks = t.get("tasks") or []
        if tasks:
            lines.append("Tasks:")
            for task in tasks:
                step = task.get("next_step") or ""
                owner = task.get("owner") or ""
                lines.append(
                    f"  - {task.get('task', '')} (next: {step}; owner: {owner}; status: {task.get('status', 'open')})"
                )
        oqs = t.get("open_questions") or []
        if oqs:
            lines.append("Open questions:")
            for q in oqs:
                if isinstance(q, str):
                    lines.append(f"  - {q}")
                else:
                    lines.append(f"  - {q.get('text', '')}")
        decisions = t.get("decisions") or []
        if decisions:
            lines.append("Decisions:")
            for d in decisions:
                if isinstance(d, str):
                    lines.append(f"  - {d}")
                else:
                    lines.append(f"  - {d.get('text', '')}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_project_topics_text(project_topics: list[dict]) -> str:
    """Render project-scoped topics with chronology cells per (topic, call)."""
    if not project_topics:
        return "(no project topics)"
    blocks = []
    for t in project_topics:
        lines = [f"## {t.get('name', '(unnamed)')}"]
        calls = t.get("calls") or []
        for c in calls:
            date = (c.get("call_date") or "")[:10]
            narrative = c.get("chronology_narrative") or ""
            rag = c.get("rag_verification_note") or ""
            if narrative:
                lines.append(f"  [{date}] {narrative}")
                if rag:
                    lines.append(f"    rag: {rag}")
            tasks = c.get("tasks") or []
            for task in tasks:
                lines.append(f"  [{date}] task: {task.get('task', '')}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
