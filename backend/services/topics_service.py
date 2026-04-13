from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


class TopicIn(BaseModel):
    """One topic as submitted by the frontend (save endpoint)."""
    name: str
    summary: str
    follow_up_items: list[str]
    decisions: list[str]
    status: Literal["open", "in_progress", "resolved"]
    owner: Literal["Us", "Client", "Both"]
    sentiment: Literal["positive", "neutral", "concern"]


class TopicUpdate(TopicIn):
    """TopicIn extended with DB identity + disposition for not-discussed topics."""
    topic_id: Optional[str] = None          # None → brand new topic
    disposition: Optional[Literal["keep_as_is", "archive"]] = None


class TopicOut(BaseModel):
    """One topic row as returned from DB queries."""
    id: str
    project_id: str
    name: str
    first_raised_call_id: Optional[str]
    calls_open: int
    archived: bool
    created_at: str
    # Latest update fields (populated from most recent topic_update row)
    summary: Optional[str] = None
    follow_up_items: list[str] = []
    decisions: list[str] = []
    status: Optional[Literal["open", "in_progress", "resolved"]] = None
    owner: Optional[Literal["Us", "Client", "Both"]] = None
    sentiment: Optional[Literal["positive", "neutral", "concern"]] = None


class BriefItem(BaseModel):
    topic_id: str
    name: str
    calls_open: int
    sentiment: Literal["positive", "neutral", "concern"]
    last_summary: str
    last_follow_up_items: list[str]


class BriefOut(BaseModel):
    priority_topics: list[BriefItem]
    decisions_to_confirm: list[dict]
    watch_list: list[BriefItem]


import asyncio
import json
import os

import anthropic
from backend.database.supabase_client import get_client
from backend.utils.logger import get_logger

logger = get_logger("topics_service")

_EXTRACT_SYSTEM = (
    "You are an expert at extracting business topics from client call transcripts. "
    "Return ONLY a valid JSON array. No markdown, no explanation."
)

_TOPIC_SCHEMA = (
    '{"name":"string","summary":"string","follow_up_items":["string"],'
    '"decisions":["string"],"status":"open|in_progress|resolved",'
    '"owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}'
)


async def _call_claude(prompt: str) -> list[dict] | dict:
    client = anthropic.AsyncAnthropic()
    logger.info("🤖 [Claude] Extracting topics")
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    if not msg.content or msg.content[0].type != "text":
        raise ValueError("Claude returned no text content")
    raw = msg.content[0].text.strip()
    logger.info(
        f"✅ [Claude] Topics extracted — "
        f"input={msg.usage.input_tokens} output={msg.usage.output_tokens}"
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        logger.error(f"❌ [Claude] Invalid JSON in topics response: {e}\nRaw: {raw[:200]}")
        raise ValueError(f"Claude returned invalid JSON: {e}") from e


def _get_previous_topics(project_id: str, db) -> list[dict]:
    """Return all non-archived topics for a project with their most recent update."""
    topics = (
        db.table("topics")
        .select("id, name, calls_open, first_raised_call_id")
        .eq("project_id", project_id)
        .eq("archived", False)
        .execute()
        .data
    )
    result = []
    for t in topics:
        updates = (
            db.table("topic_updates")
            .select("summary, follow_up_items, decisions, status, owner, sentiment")
            .eq("topic_id", t["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        latest = updates[0] if updates else {}
        result.append({
            "topic_id": t["id"],
            "name": t["name"],
            "calls_open": t["calls_open"],
            "summary": latest.get("summary", ""),
            "follow_up_items": latest.get("follow_up_items", []),
            "decisions": latest.get("decisions", []),
            "status": latest.get("status", "open"),
            "owner": latest.get("owner", "Us"),
            "sentiment": latest.get("sentiment", "neutral"),
        })
    return result


def _get_topics_prompt(project_id: str, db) -> str | None:
    """Return the project's stored topics-extraction prompt, or None if not set."""
    rows = (
        db.table("artifact_types")
        .select("prompt")
        .eq("project_id", project_id)
        .eq("category", "topics")
        .order("created_at")
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["prompt"] if rows else None


def extract_topics(call_id: str):
    """
    Returns a coroutine that resolves to:
      {
        "call_number": int,
        "followed_up": [...],
        "not_discussed": [...],
        "new_topics": [...],
      }
    Exposed as a regular function so unittest.mock.patch creates a MagicMock
    (not AsyncMock), allowing tests to set return_value to a coroutine directly.
    """
    return _extract_topics_impl(call_id)


async def _extract_topics_impl(call_id: str) -> dict:
    db = get_client()

    call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    call = call_row[0]
    project_id = call["project_id"]
    transcript = call["transcript"] or ""

    artifacts_rows = (
        db.table("artifacts")
        .select("content")
        .eq("call_id", call_id)
        .eq("status", "done")
        .execute()
        .data
    )
    artifact_text = "\n\n".join(r["content"] for r in artifacts_rows if r.get("content"))

    done_calls = (
        db.table("calls")
        .select("id")
        .eq("project_id", project_id)
        .eq("kanban_stage", "done")
        .execute()
        .data
    )
    call_number = len(done_calls) + 1

    # Look up project's topics prompt; fall back to hardcoded schema hint
    stored_prompt = _get_topics_prompt(project_id, db)
    base_instructions = stored_prompt or (
        f"Extract all key business topics from this call.\n\n"
        f"Return a JSON array where each element matches: {_TOPIC_SCHEMA}"
    )

    if call_number == 1:
        prompt = (
            f"{base_instructions}\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"Supporting documents:\n{artifact_text or 'None'}"
        )
        topics = await _call_claude(prompt)
        return {"call_number": 1, "followed_up": [], "not_discussed": [], "new_topics": topics}

    previous = _get_previous_topics(project_id, db)
    prev_names = {t["name"] for t in previous}

    prompt = (
        f"{base_instructions}\n\n"
        f"Below are the open topics from previous calls.\n\n"
        f"Previous topics (JSON):\n{json.dumps(previous, indent=2)}\n\n"
        f"Now review the new call transcript below. For each previous topic:\n"
        f"- If it was discussed, update summary/follow_ups/decisions/status/sentiment accordingly.\n"
        f"- If it was NOT discussed, return it unchanged.\n"
        f"Also extract any brand new topics not in the previous list.\n\n"
        f"Return a JSON object with three keys: "
        f'"followed_up" (array), "not_discussed" (array), "new_topics" (array). '
        f"Each topic matches: {_TOPIC_SCHEMA}\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Supporting documents:\n{artifact_text or 'None'}"
    )
    raw = await _call_claude(prompt)

    if isinstance(raw, list):
        followed_up = [t for t in raw if t["name"] in prev_names]
        not_discussed = [t for t in previous if t["name"] not in {x["name"] for x in raw}]
        new_topics = [t for t in raw if t["name"] not in prev_names]
    else:
        followed_up = raw.get("followed_up", [])
        not_discussed = raw.get("not_discussed", [])
        new_topics = raw.get("new_topics", [])

    return {
        "call_number": call_number,
        "followed_up": followed_up,
        "not_discussed": not_discussed,
        "new_topics": new_topics,
    }


async def save_topics(call_id: str, topics: list[TopicUpdate]) -> dict:
    """
    For each topic:
    - topic_id is None → insert new row in `topics`, then insert topic_update
    - topic_id exists + disposition == "archive" → set archived=True, skip topic_update
    - topic_id exists otherwise → insert topic_update, update calls_open
    """
    db = get_client()

    call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]

    saved = 0
    for t in topics:
        if t.topic_id is None:
            inserted = (
                db.table("topics")
                .insert({
                    "project_id": project_id,
                    "name": t.name,
                    "first_raised_call_id": call_id,
                    "calls_open": 0 if t.status == "resolved" else 1,
                    "archived": False,
                })
                .execute()
                .data
            )
            topic_id = inserted[0]["id"]
            logger.info(f"🗄️ [DB] Inserted new topic: {topic_id}")
        else:
            topic_id = t.topic_id
            if t.disposition == "archive":
                db.table("topics").update({"archived": True}).eq("id", topic_id).execute()
                logger.info(f"🗄️ [DB] Archived topic: {topic_id}")
                saved += 1
                continue
            if t.status == "resolved":
                db.table("topics").update({"calls_open": 0}).eq("id", topic_id).execute()
            else:
                # Fetch-then-increment: not atomic, but safe for single-user app (no concurrent writes)
                current = (
                    db.table("topics").select("calls_open").eq("id", topic_id).execute().data
                )
                current_open = current[0]["calls_open"] if current else 0
                db.table("topics").update({"calls_open": current_open + 1}).eq("id", topic_id).execute()

        db.table("topic_updates").insert({
            "topic_id": topic_id,
            "call_id": call_id,
            "summary": t.summary,
            "follow_up_items": t.follow_up_items,
            "decisions": t.decisions,
            "status": t.status,
            "owner": t.owner,
            "sentiment": t.sentiment,
        }).execute()
        logger.info(f"🗄️ [DB] Inserted topic_update for topic: {topic_id}")
        saved += 1

    return {"saved": saved}


async def validate_call(call_id: str) -> dict:
    """
    1. Check at least one topic_update exists for this call → 422 "no_topics" if not
    2. Check all non-archived previously-open topics have a topic_update for this call
       → 422 "unacknowledged_topics:id1,id2" if any missing
    3. Advance kanban_stage to 'done'
    """
    db = get_client()

    # 1. At least one topic for this call
    this_call_updates = (
        db.table("topic_updates").select("topic_id").eq("call_id", call_id).execute().data
    )
    if not this_call_updates:
        raise ValueError("no_topics")

    acknowledged_ids = {r["topic_id"] for r in this_call_updates}

    # 2. Find previously-open topics not acknowledged in this call
    # Use _get_previous_topics() to get each topic's LATEST status (not any historical status)
    call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
    project_id = call_row[0]["project_id"]

    previous_topics = _get_previous_topics(project_id, db)
    # Only topics whose LATEST update is still open or in_progress
    open_topic_ids = {
        t["topic_id"] for t in previous_topics
        if t["status"] in ("open", "in_progress")
    }
    unacknowledged = open_topic_ids - acknowledged_ids

    if unacknowledged:
        raise ValueError(f"unacknowledged_topics:{','.join(unacknowledged)}")

    # 3. Advance stage
    result = (
        db.table("calls")
        .update({"kanban_stage": "done"})
        .eq("id", call_id)
        .execute()
        .data
    )
    logger.info(f"✅ [Topics] Call {call_id} validated → done")
    return result[0]


async def generate_brief(call_id: str) -> dict:
    """
    Returns:
      {
        "priority_topics": [...],       # open/in_progress, sorted concern-first then calls_open desc
        "decisions_to_confirm": [...],  # decisions from the most recent done call in this project
        "watch_list": [...],            # topics with sentiment=concern
      }
    """
    db = get_client()

    call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]

    previous = _get_previous_topics(project_id, db)

    if not previous:
        return {"priority_topics": [], "decisions_to_confirm": [], "watch_list": []}

    open_topics = [t for t in previous if t["status"] in ("open", "in_progress")]

    def sort_key(t: dict) -> tuple:
        sent_order = {"concern": 0, "neutral": 1, "positive": 2}
        return (sent_order.get(t["sentiment"], 1), -t["calls_open"])

    priority = sorted(open_topics, key=sort_key)

    priority_items = [
        {
            "topic_id": t["topic_id"],
            "name": t["name"],
            "calls_open": t["calls_open"],
            "sentiment": t["sentiment"],
            "last_summary": t["summary"],
            "last_follow_up_items": t["follow_up_items"],
        }
        for t in priority
    ]

    # Decisions from the most recent done call in this project
    done_calls = (
        db.table("calls")
        .select("id, created_at")
        .eq("project_id", project_id)
        .eq("kanban_stage", "done")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    decisions_to_confirm: list[dict] = []
    if done_calls:
        last_call_id = done_calls[0]["id"]
        updates_with_decisions = (
            db.table("topic_updates")
            .select("decisions, topic_id")
            .eq("call_id", last_call_id)
            .execute()
            .data
        )
        for u in updates_with_decisions:
            topic_rows = (
                db.table("topics").select("name").eq("id", u["topic_id"]).execute().data
            )
            topic_name = topic_rows[0]["name"] if topic_rows else "Unknown"
            for d in (u.get("decisions") or []):
                decisions_to_confirm.append({"text": d, "topic_name": topic_name})

    watch_list = [i for i in priority_items if i["sentiment"] == "concern"]

    return {
        "priority_topics": priority_items,
        "decisions_to_confirm": decisions_to_confirm,
        "watch_list": watch_list,
    }


async def list_project_topics(project_id: str, db=None) -> list[dict]:
    """Return all non-archived topics for a project, enriched with latest update fields."""
    if db is None:
        db = get_client()
    return _get_previous_topics(project_id, db)
