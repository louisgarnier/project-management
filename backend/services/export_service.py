"""Markdown export for a completed call — used by GET /api/calls/{id}/export.

Builds a single self-contained markdown document with:
  - Project + call metadata header
  - Per-topic sections (status, owner, sentiment, summary, decisions,
    follow-ups, open questions) for every topic discussed in this call
  - Generated artifacts (LLM, template, hybrid) with their stored content

Skipped on purpose:
  - Raw transcript (large; the topic summaries already capture intent)
  - Project-cumulative state (separate feature when needed)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from backend.database.supabase_client import get_client
from backend.services.topics_service import list_call_topics

logger = logging.getLogger("calltracker.export_service")


def _slugify(name: str) -> str:
    """Kebab-case a project name for filenames. 'RAM Project' → 'ram-project'."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "project").strip().lower())
    return s.strip("-") or "project"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "unknown date"
    try:
        # Supabase returns ISO with +00:00; tolerate either form
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]


def _bullets(items: list[str]) -> str:
    if not items:
        return "_None._"
    return "\n".join(f"- {x}" for x in items)


async def build_call_export(call_id: str) -> tuple[str, str]:
    """Return (filename, markdown_body) for a single call's export.

    Raises ValueError("call_not_found") if the call doesn't exist.
    """
    db = get_client()

    call_rows = (
        db.table("calls")
        .select("id, title, project_id, kanban_stage, created_at")
        .eq("id", call_id)
        .execute()
        .data
    )
    if not call_rows:
        raise ValueError("call_not_found")
    call = call_rows[0]

    project_rows = (
        db.table("projects")
        .select("id, name, context")
        .eq("id", call["project_id"])
        .execute()
        .data
    )
    project = project_rows[0] if project_rows else {"name": "Unknown Project", "context": ""}

    # Determine call number = chronological position within project
    sibling_calls = (
        db.table("calls")
        .select("id, created_at")
        .eq("project_id", call["project_id"])
        .order("created_at")
        .execute()
        .data
    )
    call_number = next((i + 1 for i, c in enumerate(sibling_calls) if c["id"] == call_id), 1)

    topics = await list_call_topics(call_id)

    artifact_rows = (
        db.table("artifacts")
        .select("id, artifact_type_id, status, content, mode")
        .eq("call_id", call_id)
        .neq("status", "stale")
        .order("created_at")
        .execute()
        .data
    )
    type_ids = list({a["artifact_type_id"] for a in artifact_rows if a.get("artifact_type_id")})
    type_name_by_id: dict[str, str] = {}
    if type_ids:
        type_rows = (
            db.table("artifact_types")
            .select("id, name")
            .in_("id", type_ids)
            .execute()
            .data
        )
        type_name_by_id = {t["id"]: t["name"] for t in type_rows}

    # ── Compose markdown ──
    call_date = _fmt_date(call.get("created_at"))
    title = (call.get("title") or "").strip() or f"Call {call_number}"

    parts: list[str] = []
    parts.append(f"# {project['name']} — Call {call_number}: {title}")
    parts.append("")
    parts.append(f"- **Project:** {project['name']}")
    parts.append(f"- **Call:** #{call_number} — {title}")
    parts.append(f"- **Date:** {call_date}")
    parts.append(f"- **Stage:** {call.get('kanban_stage', '?')}")
    parts.append("")

    if (project.get("context") or "").strip():
        parts.append("## Project context")
        parts.append("")
        parts.append(project["context"].strip())
        parts.append("")

    parts.append(f"## Topics discussed ({len(topics)})")
    parts.append("")
    if not topics:
        parts.append("_No topics extracted for this call._")
        parts.append("")
    else:
        for t in topics:
            tname = t.get("name") or "_(unnamed topic)_"
            parts.append(f"### {tname}")
            meta_bits = [
                f"**Status:** {t.get('status', '?')}",
                f"**Owner:** {t.get('owner', '?')}",
                f"**Sentiment:** {t.get('sentiment', '?')}",
                f"**Importance:** {t.get('importance', '?')}",
            ]
            if t.get("is_parked"):
                meta_bits.append("⏸ **Parked**")
            parts.append(" · ".join(meta_bits))
            parts.append("")
            summary = (t.get("summary") or "").strip()
            if summary:
                parts.append(summary)
                parts.append("")
            parts.append("**Decisions:**")
            parts.append(_bullets(t.get("decisions") or []))
            parts.append("")
            parts.append("**Follow-ups:**")
            parts.append(_bullets(t.get("follow_up_items") or []))
            parts.append("")
            parts.append("**Open questions:**")
            parts.append(_bullets(t.get("open_questions") or []))
            parts.append("")
            parts.append("---")
            parts.append("")

    parts.append(f"## Artifacts ({len(artifact_rows)})")
    parts.append("")
    if not artifact_rows:
        parts.append("_No artifacts generated for this call._")
        parts.append("")
    else:
        for a in artifact_rows:
            aname = type_name_by_id.get(a.get("artifact_type_id", ""), "Unnamed artifact")
            status = a.get("status", "?")
            mode = a.get("mode", "?")
            parts.append(f"### {aname}")
            parts.append(f"_Status: {status} · Mode: {mode}_")
            parts.append("")
            content = (a.get("content") or "").strip()
            if content:
                parts.append(content)
            else:
                parts.append("_No content._")
            parts.append("")
            parts.append("---")
            parts.append("")

    parts.append(f"_Exported {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from Project Management._")
    md = "\n".join(parts).rstrip() + "\n"

    filename = f"{_slugify(project['name'])}-call-{call_number}-{call_date}.md"
    logger.info(
        f"📤 [Export] Built call recap: call={call_id} "
        f"topics={len(topics)} artifacts={len(artifact_rows)} bytes={len(md)}"
    )
    return filename, md
