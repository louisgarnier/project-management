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


async def _call_claude(prompt: str) -> list[dict]:
    client = anthropic.AsyncAnthropic()
    logger.info("🤖 [Claude] Extracting topics")
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    logger.info(
        f"✅ [Claude] Topics extracted — "
        f"input={msg.usage.input_tokens} output={msg.usage.output_tokens}"
    )
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


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

    if call_number == 1:
        prompt = (
            f"Extract all key business topics from this call.\n\n"
            f"Return a JSON array where each element matches: {_TOPIC_SCHEMA}\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"Supporting documents:\n{artifact_text or 'None'}"
        )
        topics = await _call_claude(prompt)
        return {"call_number": 1, "followed_up": [], "not_discussed": [], "new_topics": topics}

    previous = _get_previous_topics(project_id, db)
    prev_names = {t["name"] for t in previous}

    prompt = (
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
