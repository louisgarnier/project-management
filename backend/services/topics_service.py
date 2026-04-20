from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, field_validator

def _normalize_status(v: str) -> str:
    key = v.lower().replace("-", "_").replace(" ", "_")
    return {
        "open": "open",
        "in_progress": "in_progress", "in progress": "in_progress", "inprogress": "in_progress",
        "pending": "open", "active": "open", "ongoing": "open", "new": "open",
        "resolved": "resolved", "closed": "resolved", "done": "resolved", "complete": "resolved",
    }.get(key, "open")  # default: open


def _normalize_owner(v: str) -> str:
    key = v.lower().strip()
    return {
        "us": "Us", "we": "Us", "our": "Us", "ours": "Us", "our team": "Us",
        "internal": "Us", "our side": "Us", "team": "Us",
        "client": "Client", "them": "Client", "their": "Client", "they": "Client",
        "the client": "Client", "customer": "Client", "external": "Client",
        "both": "Both", "shared": "Both", "joint": "Both", "mutual": "Both",
        "both parties": "Both", "all": "Both",
    }.get(key, "Us")  # default: Us


def _normalize_sentiment(v: str) -> str:
    key = v.lower().strip()
    return {
        "positive": "positive", "good": "positive", "great": "positive", "optimistic": "positive",
        "neutral": "neutral", "mixed": "neutral", "unclear": "neutral", "n/a": "neutral",
        "concern": "concern", "negative": "concern", "bad": "concern", "risk": "concern",
        "at risk": "concern", "issue": "concern", "problem": "concern", "critical": "concern",
    }.get(key, "neutral")  # default: neutral


class TopicIn(BaseModel):
    """One topic as submitted by the frontend (save endpoint)."""
    name: str
    summary: str
    follow_up_items: list[str]
    decisions: list[str]
    status: Literal["open", "in_progress", "resolved"]
    owner: Literal["Us", "Client", "Both"]
    sentiment: Literal["positive", "neutral", "concern"]
    transcript_excerpt: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: object) -> object:
        return _normalize_status(v) if isinstance(v, str) else v

    @field_validator("owner", mode="before")
    @classmethod
    def normalize_owner(cls, v: object) -> object:
        return _normalize_owner(v) if isinstance(v, str) else v

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: object) -> object:
        return _normalize_sentiment(v) if isinstance(v, str) else v


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

from backend.database.supabase_client import get_client
from backend.services.llm_service import call_llm_raw
from backend.utils.logger import get_logger

logger = get_logger("topics_service")

_EXTRACT_SYSTEM = (
    "You are an expert at extracting business topics from client call transcripts. "
    "Return ONLY a valid JSON array. No markdown, no explanation."
)

_TOPIC_SCHEMA = (
    '{"name":"string","summary":"string","transcript_excerpt":"string — verbatim relevant section of the transcript",'
    '"follow_up_items":["string"],'
    '"decisions":["string"],"status":"open|in_progress|resolved",'
    '"owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}'
)


async def _call_llm(prompt: str, llm: str) -> list[dict] | dict:
    logger.info(f"🤖 [{llm}] Extracting topics")
    raw = await call_llm_raw(_EXTRACT_SYSTEM, prompt, llm)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        parsed = json.loads(raw.strip())
        logger.info(f"🔍 [{llm}] Topics raw keys sample: {_sample_keys(parsed)}")
        return _normalize_topic_keys(parsed)
    except json.JSONDecodeError as e:
        logger.error(f"❌ [{llm}] Invalid JSON in topics response: {e}\nRaw: {raw[:200]}")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e


def _sample_keys(parsed: list | dict) -> str:
    """Return field names from the first item for debugging."""
    try:
        first = parsed[0] if isinstance(parsed, list) else next(iter(parsed.values()))
        if isinstance(first, list) and first:
            first = first[0]
        return str(list(first.keys())) if isinstance(first, dict) else "?"
    except Exception:
        return "?"


_NAME_ALIASES = {"topic_name", "title", "topic", "subject", "heading"}
_SUMMARY_ALIASES = {"context", "description", "details", "detail", "overview", "content", "text", "body"}
_FOLLOW_UP_ALIASES = {"follow_ups", "action_items", "actions", "followups", "follow_up", "next_steps"}
_DECISIONS_ALIASES = {"decision", "key_decisions", "agreed", "agreements"}


def _normalize_topic(t: dict) -> dict:
    """Remap common LLM field-name variants to the canonical schema."""
    if not isinstance(t, dict):
        return t
    out = dict(t)
    for alias in _NAME_ALIASES:
        if "name" not in out and alias in out:
            out["name"] = out.pop(alias)
            break
    for alias in _SUMMARY_ALIASES:
        if "summary" not in out and alias in out:
            out["summary"] = out.pop(alias)
            break
    for alias in _FOLLOW_UP_ALIASES:
        if "follow_up_items" not in out and alias in out:
            out["follow_up_items"] = out.pop(alias)
            break
    for alias in _DECISIONS_ALIASES:
        if "decisions" not in out and alias in out:
            out["decisions"] = out.pop(alias)
            break
    # Ensure required string fields are never None/missing
    out.setdefault("name", "")
    out.setdefault("summary", "")
    out.setdefault("transcript_excerpt", None)
    out.setdefault("follow_up_items", [])
    out.setdefault("decisions", [])
    out.setdefault("status", "open")
    out.setdefault("owner", "Us")
    out.setdefault("sentiment", "neutral")
    return out


def _normalize_topic_keys(parsed: list | dict) -> list | dict:
    if isinstance(parsed, list):
        return [_normalize_topic(t) for t in parsed]
    # dict with buckets: followed_up / not_discussed / new_topics
    return {
        k: [_normalize_topic(t) for t in v] if isinstance(v, list) else v
        for k, v in parsed.items()
    }


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


def _get_topics_prompt(project_id: str, db, category: str = "call_topics") -> tuple[str | None, str | None]:
    """Return (prompt, llm) for the given workflow category, or (None, None) if not found."""
    rows = (
        db.table("artifact_types")
        .select("prompt, llm")
        .eq("project_id", project_id)
        .eq("category", category)
        .order("created_at")
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None, None
    return rows[0]["prompt"], rows[0].get("llm")





async def extract_call_topics(call_id: str) -> list[dict]:
    """
    Step 1 of two-step extraction: extract topics from this call's transcript ONLY.
    No previous project topics in context — eliminates extraction bias.
    Returns a flat list of topic dicts (not yet saved to DB).
    """
    db = get_client()

    call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    transcript = (call_row[0]["transcript"] or "").strip()
    if not transcript:
        raise ValueError("no_transcript")

    project_id = call_row[0]["project_id"]
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db, category="call_topics")
    proj_rows = db.table("projects").select("default_llm, context").eq("id", project_id).execute().data
    if stored_llm is None:
        stored_llm = proj_rows[0].get("default_llm") if proj_rows else "groq"
    llm = stored_llm or "groq"
    project_context = (proj_rows[0].get("context") or "").strip() if proj_rows else ""

    base_instruction = stored_prompt or (
        "You are an expert at analysing business call transcripts. Extract every distinct topic discussed — "
        "be exhaustive, do not merge separate topics into one.\n\n"
        "For each topic:\n"
        "- name: short label (3–6 words)\n"
        "- summary: 1–2 sentence recap of what was said\n"
        "- transcript_excerpt: the verbatim relevant section of the transcript where this topic was discussed. "
        "Include enough context to understand the discussion (typically 2–8 sentences). "
        "Copy the exact words from the transcript.\n"
        "- follow_up_items: concrete next steps or open questions (empty array if none)\n"
        "- decisions: anything explicitly agreed or decided (empty array if none)\n"
        "- status: open (unresolved), in_progress (being worked on), resolved (closed/agreed)\n"
        "- owner: Us (our team owns it), Client (client owns it), Both (shared)\n"
        "- sentiment: positive (good news/progress), neutral (informational), concern (risk/problem/blocker)\n\n"
        "Return ONLY a JSON array. No markdown, no explanation."
    )
    context_prefix = f"Project context:\n{project_context}\n\n" if project_context else ""
    prompt = (
        context_prefix
        + f"{base_instruction}\n\n"
        + f"Return a JSON array where each element matches this exact schema:\n{_TOPIC_SCHEMA}\n\n"
        + f"Transcript:\n{transcript}"
    )

    raw = await _call_llm(prompt, llm)
    # Flatten if LLM returned a dict (shouldn't happen with flat-list prompt, but safe)
    if isinstance(raw, dict):
        flat: list[dict] = []
        for v in raw.values():
            if isinstance(v, list):
                flat.extend(v)
        return flat
    return raw if isinstance(raw, list) else []


async def run_extraction_background(call_id: str) -> None:
    """
    Run extract_call_topics in the background, saving result to extraction_cache.
    Called via FastAPI BackgroundTasks so the HTTP response returns immediately.
    """
    db = get_client()
    try:
        topics = await extract_call_topics(call_id)
        db.table("calls").update({
            "extraction_cache": topics,
            "extraction_status": "done",
        }).eq("id", call_id).execute()
        logger.info(f"✅ [Topics] Background extraction complete: {len(topics)} topics saved for call {call_id}")
    except ValueError as e:
        db.table("calls").update({"extraction_status": "failed"}).eq("id", call_id).execute()
        logger.warning(f"⚠️ [Topics] Background extraction failed (ValueError): {e}")
    except Exception as e:
        db.table("calls").update({"extraction_status": "failed"}).eq("id", call_id).execute()
        logger.exception(f"❌ [Topics] Background extraction failed: {e}")


_AGGREGATE_SYSTEM = (
    "You are an expert at matching client call topics to an existing project topic list. "
    "Return ONLY valid JSON. No markdown, no explanation."
)


async def aggregate_topics(call_id: str, call_topics: list[dict]) -> dict:
    """
    Step 2 of two-step extraction: match call_topics against accumulated project topics.

    Call 1 (no previous topics): saves all as new, advances stage to 'artifacts',
      returns {"auto_advanced": True, "call_number": 1}.

    Call 2+: runs LLM to classify into 3 buckets, advances stage to 'project_topics',
      returns {call_number, followed_up, not_discussed, new_topics}.
    """
    db = get_client()

    call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]

    done_calls = (
        db.table("calls").select("id")
        .eq("project_id", project_id).eq("kanban_stage", "done")
        .execute().data
    )
    call_number = len(done_calls) + 1

    # Use timestamp-scoped prior topics so that:
    # - Call 1 always sees zero prior topics (earliest call → auto-advance)
    # - Earlier calls never see topics first raised by later calls, even after rollback
    previous = list_topics_prior_to_call(call_id, project_id, db)

    if not previous:
        # Idempotent: delete any topic_updates this call previously saved, then
        # orphan-clean topics that have no remaining updates. This ensures re-running
        # aggregate after a rollback doesn't stack duplicate topic rows.
        prior_updates = (
            db.table("topic_updates").select("topic_id").eq("call_id", call_id).execute().data
        )
        affected_ids = list({r["topic_id"] for r in prior_updates})
        if affected_ids:
            db.table("topic_updates").delete().eq("call_id", call_id).execute()
            for topic_id in affected_ids:
                remaining = (
                    db.table("topic_updates").select("id").eq("topic_id", topic_id).execute().data
                )
                if not remaining:
                    db.table("topics").delete().eq("id", topic_id).execute()
                    logger.info(f"🗄️ [Aggregate] Cleaned up orphan topic on re-run: {topic_id}")
            logger.info(f"🗄️ [Aggregate] Cleaned {len(affected_ids)} stale topics before re-save for call {call_id}")

        # Call 1: auto-advance — save all as new topics and jump to artifacts
        new_topics_to_save = [
            TopicUpdate(**{**t, "topic_id": None, "disposition": None})
            for t in call_topics
        ]
        await save_topics(call_id, new_topics_to_save)
        db.table("calls").update({"kanban_stage": "artifacts"}).eq("id", call_id).execute()
        db.table("calls").update({
            "extraction_cache": None,
            "extraction_status": "idle",
        }).eq("id", call_id).execute()
        logger.info(f"✅ [Topics] Call 1 auto-advanced: saved {len(new_topics_to_save)} topics → artifacts")
        return {"auto_advanced": True, "call_number": call_number}

    # Call 2+: save pending topics and advance to project_matching for manual matching
    db.table("calls").update({
        "pending_topics": call_topics,
        "kanban_stage": "project_matching",
    }).eq("id", call_id).execute()
    db.table("calls").update({
        "extraction_cache": None,
        "extraction_status": "idle",
    }).eq("id", call_id).execute()
    logger.info(
        f"✅ [Topics] Step-2 saved {len(call_topics)} pending topics → project_matching"
    )
    return {"advanced_to": "project_matching", "call_number": call_number}


async def get_pending_topics(call_id: str) -> list[dict]:
    """Return the validated call topics stored between call_topics and project_matching stages."""
    db = get_client()
    row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
    if not row:
        raise ValueError(f"Call {call_id} not found")
    return row[0].get("pending_topics") or []


async def save_match_groups(call_id: str, groups: list[dict]) -> dict:
    """
    Persist match groups and advance to project_updates.

    groups: [{"project_topic_ids": ["uuid", ...], "call_topic_names": ["name1", ...]}]
    """
    db = get_client()

    # Delete previous groups for this call (idempotent save)
    db.table("topic_match_groups").delete().eq("call_id", call_id).execute()

    for g in groups:
        db.table("topic_match_groups").insert({
            "call_id": call_id,
            "project_topic_ids": g.get("project_topic_ids", []),
            "call_topic_names": [n.lower().strip() for n in g.get("call_topic_names", [])],
        }).execute()

    db.table("calls").update({"kanban_stage": "project_updates"}).eq("id", call_id).execute()
    logger.info(f"✅ [Topics] Saved {len(groups)} match groups → project_updates")
    return {"saved": len(groups)}


async def run_merge_preview(call_id: str) -> list[dict]:
    """
    For each match group:
    - matched (project_topic_ids has entries): run LLM to merge existing topic + call topics → updated recap
    - new (project_topic_ids empty): return call topics as-is, topic_id=None

    Returns a list of topic dicts ready for ProjectUpdatesStage review.
    Each item has all TopicData fields plus topic_id (existing UUID or None).
    """
    db = get_client()

    call_row = db.table("calls").select("project_id, pending_topics").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]
    pending: list[dict] = call_row[0].get("pending_topics") or []

    groups = (
        db.table("topic_match_groups")
        .select("project_topic_ids, call_topic_names")
        .eq("call_id", call_id)
        .execute()
        .data
    )

    # Build lookup: call topic name → topic dict
    pending_by_name = {t["name"].lower().strip(): t for t in pending}

    # Load previous project topics for context
    previous = _get_previous_topics(project_id, db)
    prev_by_id = {t["topic_id"]: t for t in previous}

    def _load_transcript_excerpts(topic_id: str) -> list[dict]:
        """Load all per-call evidence for a topic, ordered by call date.
        Returns [{call, summary, transcript_excerpt, follow_up_items, decisions}, ...]"""
        rows = (
            db.table("topic_updates")
            .select("call_id, summary, transcript_excerpt, follow_up_items, decisions")
            .eq("topic_id", topic_id)
            .order("created_at")
            .execute()
            .data
        )
        result = []
        for r in rows:
            if not r.get("transcript_excerpt") and not r.get("summary"):
                continue
            # Resolve call title for context
            call_info = db.table("calls").select("title").eq("id", r["call_id"]).execute().data
            call_title = call_info[0]["title"] if call_info else r["call_id"]
            result.append({
                "call": call_title,
                "summary": r.get("summary", ""),
                "transcript_excerpt": r.get("transcript_excerpt"),
                "follow_up_items": r.get("follow_up_items") or [],
                "decisions": r.get("decisions") or [],
            })
        return result

    def _build_excerpt_context(topic_name: str, topic_id: str) -> str:
        """Build a per-call evidence block with transcript, follow-ups, and decisions."""
        excerpts = _load_transcript_excerpts(topic_id)
        if not excerpts:
            return f'== Topic: "{topic_name}" ==\n(No historical excerpts available)\n'
        lines = [f'== Topic: "{topic_name}" — Per-Call Evidence ==']
        for e in excerpts:
            lines.append(f'\n--- {e["call"]} ---')
            if e.get("transcript_excerpt"):
                lines.append(f'Transcript: {e["transcript_excerpt"]}')
            if e.get("summary"):
                lines.append(f'Summary: {e["summary"]}')
            if e.get("follow_up_items"):
                items = e["follow_up_items"]
                if isinstance(items, list) and items:
                    lines.append("Follow-ups from this call:")
                    for item in items:
                        lines.append(f"  - {item}")
            if e.get("decisions"):
                decs = e["decisions"]
                if isinstance(decs, list) and decs:
                    lines.append("Decisions from this call:")
                    for d in decs:
                        lines.append(f"  - {d}")
        return "\n".join(lines)

    # Get LLM config
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db, category="project_topics")
    proj_rows = db.table("projects").select("default_llm, context").eq("id", project_id).execute().data
    if stored_llm is None:
        stored_llm = proj_rows[0].get("default_llm") if proj_rows else "groq"
    llm = stored_llm or "groq"
    project_context = (proj_rows[0].get("context") or "").strip() if proj_rows else ""

    base_merge_instructions = stored_prompt or (
        "You are merging an existing project topic record with one or more new call topics that match it. "
        "Produce an updated topic that synthesises the history with the latest call information.\n\n"
        "CRITICAL RULES — follow these exactly:\n"
        "1. NEVER drop follow-up items. Include ALL follow-ups from ALL sources (existing + new). "
        "If both the existing topic and the call topic have follow-ups, UNION them — do not pick a subset.\n"
        "2. NEVER drop decisions. Include ALL decisions from ALL sources.\n"
        "3. The summary must cover ALL key points discussed — do not compress or omit details. "
        "If the discussion touched on specific numbers, dates, names, or commitments, include them.\n"
        "4. When in doubt, include more detail rather than less. Completeness beats brevity.\n"
        "5. Update status, sentiment, and owner to reflect the CURRENT state after this call.\n"
        "6. Preserve the exact wording of follow-up items and decisions unless they are truly duplicates."
    )
    merge_instructions = (
        f"Project context:\n{project_context}\n\n{base_merge_instructions}"
        if project_context else base_merge_instructions
    )

    async def merge_one(group: dict) -> list[dict]:
        """Return a list of topic dicts for one match group.

        Handles three group types:
        - Empty project_topic_ids (new topics): single call topic → as-is; multiple → LLM merge into one
        - Single project_topic_ids (1:1 match): LLM merge existing + call topics → updated existing
        - Multiple project_topic_ids (M:N merge): LLM merge all → one new topic, sources get archived
        """
        ptids = group.get("project_topic_ids") or []
        call_names = group.get("call_topic_names", [])
        call_matches = [pending_by_name[n.lower().strip()] for n in call_names if n.lower().strip() in pending_by_name]

        if not ptids:
            # New topic(s) from call
            if not call_matches:
                logger.warning("⚠️ [Topics] match group has empty project_topic_ids but no matching call topics — skipping")
                return []
            if len(call_matches) == 1:
                return [{**call_matches[0], "topic_id": None}]
            # Multiple call topics grouped as new → LLM merge into one with proposed name
            try:
                call_excerpts_parts = []
                for m in call_matches:
                    part = f'Topic: "{m.get("name", "")}"\n'
                    part += f'Transcript: {m.get("transcript_excerpt", "(none)")}\n'
                    part += f'Summary: {m.get("summary", "")}'
                    fups = m.get("follow_up_items") or []
                    if fups:
                        part += "\nFollow-ups:\n" + "\n".join(f"  - {f}" for f in fups)
                    decs = m.get("decisions") or []
                    if decs:
                        part += "\nDecisions:\n" + "\n".join(f"  - {d}" for d in decs)
                    call_excerpts_parts.append(part)
                call_excerpts = "\n\n".join(call_excerpts_parts)
                prompt = (
                    f"{merge_instructions}\n\n"
                    f"Multiple call topics need to be merged into ONE topic.\n"
                    f"They were extracted separately but cover the same subject.\n"
                    f"Propose a concise name that captures the combined scope.\n\n"
                    f"Call topics to merge:\n{call_excerpts}\n\n"
                    f"Remember: UNION all follow_up_items and decisions from every topic. "
                    f"The summary must cover ALL key points from ALL topics being merged.\n\n"
                    f"Return a single merged topic JSON:\n{_TOPIC_SCHEMA}"
                )
                merged = await _call_llm(prompt, llm)
                if isinstance(merged, list):
                    merged = merged[0] if merged else {}
                return [{**merged, "topic_id": None}]
            except Exception as e:
                logger.error(f"❌ [Topics] New-topic merge failed: {e} — returning first topic")
                return [{**call_matches[0], "topic_id": None}]

        if len(ptids) == 1:
            # Standard 1:1 match — update existing topic with RAG context
            ptid = ptids[0]
            existing = prev_by_id.get(ptid)
            if not existing:
                base = call_matches[0] if call_matches else {}
                return [{**base, "topic_id": ptid}]

            if not call_matches:
                return [{**existing, "topic_id": ptid}]

            # Build RAG context from historical transcript excerpts
            excerpt_context = _build_excerpt_context(existing.get("name", ""), ptid)
            call_excerpts_parts = []
            for m in call_matches:
                part = f'New from this call: "{m.get("name", "")}"\n'
                part += f'Transcript: {m.get("transcript_excerpt", "(none)")}\n'
                part += f'Summary: {m.get("summary", "")}'
                fups = m.get("follow_up_items") or []
                if fups:
                    part += "\nFollow-ups from this call:\n" + "\n".join(f"  - {f}" for f in fups)
                decs = m.get("decisions") or []
                if decs:
                    part += "\nDecisions from this call:\n" + "\n".join(f"  - {d}" for d in decs)
                call_excerpts_parts.append(part)
            call_excerpts = "\n\n".join(call_excerpts_parts)

            try:
                prompt = (
                    f"{merge_instructions}\n\n"
                    f"Historical discussion (grounded in actual transcripts):\n{excerpt_context}\n\n"
                    f"Current state:\n{json.dumps(existing, indent=2)}\n\n"
                    f"New call topic(s) matching this:\n{call_excerpts}\n\n"
                    f"Synthesize into an updated topic. Ground your summary in the transcript excerpts, "
                    f"not just prior summaries.\n"
                    f"UNION all follow_up_items from both existing and new — never drop any.\n"
                    f"UNION all decisions from both existing and new — never drop any.\n"
                    f"The summary must include ALL key points from both historical and new discussion.\n\n"
                    f"Return a single merged topic JSON:\n{_TOPIC_SCHEMA}"
                )
                merged = await _call_llm(prompt, llm)
                if isinstance(merged, list):
                    merged = merged[0] if merged else {}
                return [{**merged, "topic_id": ptid}]
            except Exception as e:
                logger.error(f"❌ [Topics] LLM merge failed for topic {ptid}: {e} — returning existing unchanged")
                return [{**existing, "topic_id": ptid}]

        # M:N merge — multiple existing topics + call topics → one new topic
        existing_topics = [prev_by_id[pid] for pid in ptids if pid in prev_by_id]
        all_inputs = existing_topics + call_matches
        if not all_inputs:
            logger.warning("⚠️ [Topics] M:N group has no resolvable topics — skipping")
            return []

        # Build RAG context for each source topic
        excerpt_sections = "\n\n".join(
            _build_excerpt_context(prev_by_id[pid].get("name", ""), pid)
            for pid in ptids if pid in prev_by_id
        )
        call_excerpts_parts = []
        for m in call_matches:
            part = f'New from this call: "{m.get("name", "")}"\n'
            part += f'Transcript: {m.get("transcript_excerpt", "(none)")}\n'
            part += f'Summary: {m.get("summary", "")}'
            fups = m.get("follow_up_items") or []
            if fups:
                part += "\nFollow-ups from this call:\n" + "\n".join(f"  - {f}" for f in fups)
            decs = m.get("decisions") or []
            if decs:
                part += "\nDecisions from this call:\n" + "\n".join(f"  - {d}" for d in decs)
            call_excerpts_parts.append(part)
        call_excerpts = "\n\n".join(call_excerpts_parts)

        try:
            prompt = (
                f"{merge_instructions}\n\n"
                f"You are merging multiple existing project topics into ONE new topic.\n"
                f"Propose a concise name that captures the combined scope.\n\n"
                f"Historical discussions (grounded in actual transcripts):\n{excerpt_sections}\n\n"
                f"Current state of existing topics:\n{json.dumps(existing_topics, indent=2)}\n\n"
                f"New call topic(s):\n{call_excerpts}\n\n"
                f"Synthesize everything into a single merged topic. Ground your summary in the "
                f"transcript excerpts, not just prior summaries.\n"
                f"UNION all follow_up_items from EVERY source topic — never drop any.\n"
                f"UNION all decisions from EVERY source topic — never drop any.\n"
                f"The summary must include ALL key points from ALL topics being merged.\n\n"
                f"Return a single merged topic JSON:\n{_TOPIC_SCHEMA}"
            )
            merged = await _call_llm(prompt, llm)
            if isinstance(merged, list):
                merged = merged[0] if merged else {}
            return [{**merged, "topic_id": None, "_source_topic_ids": ptids}]
        except Exception as e:
            logger.error(f"❌ [Topics] M:N merge failed: {e} — returning first existing unchanged")
            return [{**existing_topics[0], "topic_id": None, "_source_topic_ids": ptids}]

    per_group = await asyncio.gather(*[merge_one(g) for g in groups])
    # Flatten: each merge_one returns a list (1 item for matched/M:N groups, N for new groups)
    results = [item for sublist in per_group for item in sublist]

    # Collect all project_topic_ids that are in match groups
    matched_project_ids: set[str] = set()
    for g in groups:
        for pid in (g.get("project_topic_ids") or []):
            matched_project_ids.add(pid)

    # Build not-discussed entries for project topics NOT in any match group
    not_discussed = []
    for t in previous:
        if t["topic_id"] not in matched_project_ids:
            not_discussed.append({**t, "not_discussed": True})

    return [r for r in results if r] + not_discussed


async def _verify_merged_topics(call_id: str, merged_topics: list[dict]) -> list[dict]:
    """
    Post-merge verification pass: for each discussed topic, check the merged result
    against the full transcript to ensure no follow-ups, decisions, or key details were lost.
    Returns the verified/corrected topic list.
    """
    db = get_client()

    call_row = (
        db.table("calls")
        .select("project_id, transcript")
        .eq("id", call_id)
        .execute()
        .data
    )
    if not call_row:
        return merged_topics
    project_id = call_row[0]["project_id"]
    transcript = call_row[0].get("transcript") or ""
    if not transcript:
        logger.info(f"⚠️ [MergeVerify] No transcript for call {call_id} — skipping verification")
        return merged_topics

    # Get the merge_verification prompt
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db, category="merge_verification")
    proj_rows = db.table("projects").select("default_llm").eq("id", project_id).execute().data
    llm = stored_llm or (proj_rows[0]["default_llm"] if proj_rows else "groq")
    verify_instructions = stored_prompt or (
        "You are a quality reviewer for project topic data. "
        "Verify that the merged topic did NOT lose any important information. "
        "Check: are ALL follow-up items preserved? ALL decisions? Does the summary cover all key points? "
        "Return the corrected topic as JSON. Only ADD back what was lost, never remove anything."
    )

    # Collect all source follow-ups and decisions for each topic
    # so the verification prompt can compare against them
    groups = (
        db.table("topic_match_groups")
        .select("project_topic_ids, call_topic_names")
        .eq("call_id", call_id)
        .execute()
        .data
    )
    pending_row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
    pending: list[dict] = (pending_row[0].get("pending_topics") or []) if pending_row else []
    pending_by_name = {t["name"].lower().strip(): t for t in pending}

    previous = _get_previous_topics(project_id, db)
    prev_by_id = {t["topic_id"]: t for t in previous}

    # Build a map of source data per discussed topic for the verification prompt
    # Match merged topics to their groups by topic_id or name
    source_data_map: dict[int, dict] = {}
    for idx, topic in enumerate(merged_topics):
        if topic.get("not_discussed"):
            continue
        all_follow_ups: list[str] = []
        all_decisions: list[str] = []

        # Find the matching group
        tid = topic.get("topic_id")
        tname = (topic.get("name") or "").lower().strip()
        matched_group = None
        for g in groups:
            ptids = g.get("project_topic_ids") or []
            cnames = [n.lower().strip() for n in (g.get("call_topic_names") or [])]
            if tid and tid in ptids:
                matched_group = g
                break
            if any(n == tname for n in cnames):
                matched_group = g
                break

        if matched_group:
            # Collect from existing project topics
            for pid in (matched_group.get("project_topic_ids") or []):
                existing = prev_by_id.get(pid, {})
                all_follow_ups.extend(existing.get("follow_up_items") or [])
                all_decisions.extend(existing.get("decisions") or [])
            # Collect from call topics
            for cname in (matched_group.get("call_topic_names") or []):
                ct = pending_by_name.get(cname.lower().strip(), {})
                all_follow_ups.extend(ct.get("follow_up_items") or [])
                all_decisions.extend(ct.get("decisions") or [])

        source_data_map[idx] = {
            "all_follow_ups": all_follow_ups,
            "all_decisions": all_decisions,
        }

    verified = list(merged_topics)  # copy
    for idx, topic in enumerate(merged_topics):
        if topic.get("not_discussed"):
            continue
        source = source_data_map.get(idx)
        if not source:
            continue

        source_follow_ups = source["all_follow_ups"]
        source_decisions = source["all_decisions"]

        try:
            prompt = (
                f"{verify_instructions}\n\n"
                f"== Merged topic (to verify) ==\n{json.dumps(topic, indent=2)}\n\n"
                f"== Source follow-up items (must ALL be present) ==\n"
                f"{json.dumps(source_follow_ups, indent=2)}\n\n"
                f"== Source decisions (must ALL be present) ==\n"
                f"{json.dumps(source_decisions, indent=2)}\n\n"
                f"== Relevant section of call transcript ==\n"
                f"{transcript[:8000]}\n\n"
                f"Return the corrected topic JSON (same schema). "
                f"Add back any missing follow-ups, decisions, or key details. "
                f"Never remove or shorten anything that was already correct.\n"
                f"{_TOPIC_SCHEMA}"
            )
            corrected = await _call_llm(prompt, llm)
            if isinstance(corrected, list):
                corrected = corrected[0] if corrected else topic
            # Preserve internal fields
            corrected["topic_id"] = topic.get("topic_id")
            if "_source_topic_ids" in topic:
                corrected["_source_topic_ids"] = topic["_source_topic_ids"]
            verified[idx] = corrected
            logger.info(f"✅ [MergeVerify] Verified topic: {topic.get('name', '?')}")
        except Exception as e:
            logger.error(f"❌ [MergeVerify] Verification failed for '{topic.get('name', '?')}': {e} — keeping original")

    return verified


async def run_merge_background(call_id: str) -> None:
    """
    Run run_merge_preview in the background, then verify each merged topic
    against the transcript. Saves result to merge_cache.
    Called via FastAPI BackgroundTasks so the HTTP response returns immediately.
    """
    db = get_client()
    try:
        result = await run_merge_preview(call_id)
        # Post-merge verification pass: check each topic against transcript
        result = await _verify_merged_topics(call_id, result)
        db.table("calls").update({
            "merge_cache": result,
            "merge_status": "done",
        }).eq("id", call_id).execute()
        logger.info(f"✅ [Topics] Background merge+verify complete: {len(result)} topics saved for call {call_id}")
    except ValueError as e:
        db.table("calls").update({"merge_status": "failed"}).eq("id", call_id).execute()
        logger.warning(f"⚠️ [Topics] Background merge failed (ValueError): {e}")
    except Exception as e:
        db.table("calls").update({"merge_status": "failed"}).eq("id", call_id).execute()
        logger.exception(f"❌ [Topics] Background merge failed: {e}")


async def verify_not_discussed_topics(call_id: str) -> dict:
    """
    Check each not-discussed topic against the call transcript using the
    not_discussed_check workflow prompt. Returns a dict keyed by topic_id
    with {discussed: bool, transcript_excerpt: str|None, reasoning: str}.
    """
    db = get_client()

    call_row = (
        db.table("calls")
        .select("project_id, transcript")
        .eq("id", call_id)
        .execute()
        .data
    )
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]
    transcript = call_row[0].get("transcript") or ""
    if not transcript:
        logger.warning(f"⚠️ [Verification] No transcript for call {call_id}")
        return {}

    # Load match groups to identify which project topics are NOT discussed
    groups = (
        db.table("topic_match_groups")
        .select("project_topic_ids")
        .eq("call_id", call_id)
        .execute()
        .data
    )
    matched_ids: set[str] = set()
    for g in groups:
        for pid in (g.get("project_topic_ids") or []):
            matched_ids.add(pid)

    previous = _get_previous_topics(project_id, db)
    not_discussed = [t for t in previous if t["topic_id"] not in matched_ids]

    if not not_discussed:
        logger.info(f"✅ [Verification] No not-discussed topics for call {call_id}")
        return {}

    # Get the not_discussed_check prompt and LLM
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db, category="not_discussed_check")
    proj_rows = db.table("projects").select("default_llm").eq("id", project_id).execute().data
    llm = stored_llm or (proj_rows[0]["default_llm"] if proj_rows else "groq")
    check_instructions = stored_prompt or (
        "You are checking whether a project topic was actually discussed in a call transcript.\n"
        "Given the topic name, its latest summary, and the full call transcript, determine:\n"
        "1. Was this topic mentioned or discussed in the call? (yes/no)\n"
        "2. If yes, provide the relevant transcript excerpt.\n\n"
        'Return JSON: {"discussed": true/false, "transcript_excerpt": "..." or null, '
        '"reasoning": "one sentence explanation"}'
    )

    results: dict[str, dict] = {}

    for topic in not_discussed:
        topic_id = topic["topic_id"]
        try:
            prompt = (
                f"{check_instructions}\n\n"
                f"Topic name: {topic['name']}\n"
                f"Topic summary: {topic.get('summary', '(no summary)')}\n\n"
                f"Call transcript:\n{transcript}"
            )
            raw = await call_llm_raw(_EXTRACT_SYSTEM, prompt, llm)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())
            results[topic_id] = {
                "discussed": bool(parsed.get("discussed", False)),
                "transcript_excerpt": parsed.get("transcript_excerpt"),
                "reasoning": parsed.get("reasoning", ""),
            }
            logger.info(
                f"🔍 [Verification] {topic['name']}: discussed={results[topic_id]['discussed']}"
            )
        except Exception as e:
            logger.error(f"❌ [Verification] Failed for topic {topic['name']}: {e}")
            results[topic_id] = {
                "discussed": False,
                "transcript_excerpt": None,
                "reasoning": f"Verification failed: {e}",
            }

    return results


async def run_verification_background(call_id: str) -> None:
    """Run verify_not_discussed_topics in background, saving to verification_cache."""
    db = get_client()
    try:
        result = await verify_not_discussed_topics(call_id)
        db.table("calls").update({
            "verification_cache": result,
            "verification_status": "done",
        }).eq("id", call_id).execute()
        logger.info(f"✅ [Verification] Background verification complete for call {call_id}")
    except Exception as e:
        db.table("calls").update({"verification_status": "failed"}).eq("id", call_id).execute()
        logger.exception(f"❌ [Verification] Background verification failed: {e}")


async def validate_project_updates(call_id: str, topics: list[dict]) -> dict:
    """
    Save merged/reviewed topics and advance to artifacts.
    - topic_id set   → update existing topic (topic_update record)
    - topic_id None  → create new topic
    match groups and pending_topics are preserved as permanent records.
    """
    db = get_client()

    # Idempotent: delete any topic_updates this call previously saved before re-saving.
    # This prevents duplicate rows if validate_project_updates is called more than once
    # (e.g. after rolling back to project_updates and re-confirming).
    prior_updates = (
        db.table("topic_updates").select("topic_id").eq("call_id", call_id).execute().data
    )
    affected_ids = list({r["topic_id"] for r in prior_updates})
    if affected_ids:
        db.table("topic_updates").delete().eq("call_id", call_id).execute()
        for topic_id in affected_ids:
            remaining = (
                db.table("topic_updates").select("id").eq("topic_id", topic_id).execute().data
            )
            if not remaining:
                db.table("topics").delete().eq("id", topic_id).execute()
                logger.info(f"🗄️ [ValidateUpdates] Cleaned orphan topic on re-run: {topic_id}")
        logger.info(f"🗄️ [ValidateUpdates] Cleaned {len(affected_ids)} stale topic_updates before re-save for call {call_id}")

    # Skip not_discussed topics — they have no topic_update for this call
    topics_to_save = [t for t in topics if not t.get("not_discussed")]

    # Strip internal fields before building TopicUpdate models
    clean_fields = {"_source_topic_ids", "not_discussed", "pending_merge", "calls_open",
                    "verification_status", "topic_id", "disposition"}
    topic_updates = []
    for t in topics_to_save:
        model_data = {k: v for k, v in t.items() if k not in clean_fields}
        model_data["topic_id"] = t.get("topic_id")
        model_data["disposition"] = None
        topic_updates.append(TopicUpdate(**model_data))

    await save_topics(call_id, topic_updates)

    # Handle M:N merge archival: archive source topics and set merged_into_topic_id
    call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
    project_id = call_row[0]["project_id"] if call_row else None
    for t in topics_to_save:
        source_ids = t.get("_source_topic_ids")
        if source_ids and len(source_ids) > 1 and project_id:
            # Find the newly created topic (the one save_topics just inserted for this entry)
            # It's the topic with first_raised_call_id = call_id and matching name
            new_topic_rows = (
                db.table("topics")
                .select("id")
                .eq("project_id", project_id)
                .eq("first_raised_call_id", call_id)
                .eq("name", t.get("name", ""))
                .execute()
                .data
            )
            if new_topic_rows:
                new_topic_id = new_topic_rows[0]["id"]
                for source_id in source_ids:
                    db.table("topics").update({
                        "archived": True,
                        "merged_into_topic_id": new_topic_id,
                    }).eq("id", source_id).execute()
                    logger.info(f"🗄️ [Merge] Archived topic {source_id} → merged into {new_topic_id}")

    # Advance to artifacts — match groups and pending_topics are kept as permanent records
    db.table("calls").update({
        "kanban_stage": "artifacts",
    }).eq("id", call_id).execute()

    logger.info(f"✅ [Topics] project_updates validated → artifacts: {call_id}")
    return {"status": "ok"}


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

        update_row = {
            "topic_id": topic_id,
            "call_id": call_id,
            "summary": t.summary,
            "follow_up_items": t.follow_up_items,
            "decisions": t.decisions,
            "status": t.status,
            "owner": t.owner,
            "sentiment": t.sentiment,
        }
        if t.transcript_excerpt:
            update_row["transcript_excerpt"] = t.transcript_excerpt
        db.table("topic_updates").insert(update_row).execute()
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
        .update({"kanban_stage": "artifacts"})
        .eq("id", call_id)
        .execute()
        .data
    )
    logger.info(f"✅ [Topics] Call {call_id} validated → artifacts")
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


_ROLLBACK_STAGE_ORDER = [
    "transcript",
    "call_topics",
    "project_matching",
    "project_updates",
    "artifacts",
    "done",
]


def rollback_to_stage(call_id: str, target_stage: str) -> dict:
    """
    Roll back a call to the given target_stage, cascading cleanups as required.

    Cascade (each level includes all levels above it in the list):
      artifacts        → mark this call's artifacts stale; set kanban_stage="artifacts"
      project_updates  → delete topic_updates + orphan-cleanup; mark artifacts stale;
                         set kanban_stage="project_updates"  (keeps match_groups)
      project_matching → same as project_updates + delete topic_match_groups;
                         set kanban_stage="project_matching"  (keeps pending_topics)
      call_topics      → same as project_matching + clear pending_topics, extraction_cache,
                         extraction_status="idle"; set kanban_stage="call_topics"
      transcript       → same as call_topics + clear transcript, transcript_source;
                         set kanban_stage="transcript"
    """
    db = get_client()

    def _mark_artifacts_stale() -> None:
        artifacts = db.table("artifacts").select("id").eq("call_id", call_id).execute().data
        artifact_ids = [a["id"] for a in artifacts]
        if artifact_ids:
            db.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
            logger.info(f"⚠️ [Rollback] Marked {len(artifact_ids)} artifacts stale for call {call_id}")

    def _delete_topic_updates() -> None:
        # Collect affected topic_ids before deletion
        updates_before = (
            db.table("topic_updates").select("topic_id").eq("call_id", call_id).execute().data
        )
        affected_topic_ids = list({r["topic_id"] for r in updates_before})

        # Delete topic_updates for this call
        db.table("topic_updates").delete().eq("call_id", call_id).execute()
        logger.info(f"🗄️ [Rollback] Deleted topic_updates for call {call_id}")

        # Orphan-cleanup + calls_open recalc
        for topic_id in affected_topic_ids:
            remaining = (
                db.table("topic_updates").select("status").eq("topic_id", topic_id).execute().data
            )
            if not remaining:
                db.table("topics").delete().eq("id", topic_id).execute()
                logger.info(f"🗄️ [Rollback] Deleted orphan topic {topic_id}")
            else:
                calls_open = sum(1 for r in remaining if r["status"] in ("open", "in_progress"))
                db.table("topics").update({"calls_open": calls_open}).eq("id", topic_id).execute()
                logger.info(f"🗄️ [Rollback] Recalculated calls_open={calls_open} for topic {topic_id}")

    def _delete_match_groups() -> None:
        db.table("topic_match_groups").delete().eq("call_id", call_id).execute()
        logger.info(f"🗄️ [Rollback] Deleted topic_match_groups for call {call_id}")

    def _clear_extraction_fields() -> None:
        """Clear pending_topics, extraction_cache, extraction_status via raw HTTP (None-safe)."""
        payload = json.dumps({
            "pending_topics": None,
            "extraction_cache": None,
            "extraction_status": "idle",
        })
        response = db.postgrest.session.patch(
            f"/calls?id=eq.{call_id}",
            content=payload,
            headers={"Content-Type": "application/json", "Prefer": "return=representation"},
        )
        data = response.json()
        if not data:
            raise ValueError("Failed to clear fields via raw PATCH")
        logger.info(f"🗄️ [Rollback] Cleared extraction fields for call {call_id}")

    def _clear_merge_fields() -> None:
        """Reset merge_cache and merge_status to idle. Non-fatal if migration 016 not yet applied."""
        try:
            payload = json.dumps({"merge_cache": None, "merge_status": "idle"})
            response = db.postgrest.session.patch(
                f"/calls?id=eq.{call_id}",
                content=payload,
                headers={"Content-Type": "application/json", "Prefer": "return=representation"},
            )
            if response.json():
                logger.info(f"🗄️ [Rollback] Cleared merge fields for call {call_id}")
            else:
                logger.warning(f"⚠️ [Rollback] merge fields clear returned empty — migration 016 not applied?")
        except Exception as e:
            logger.warning(f"⚠️ [Rollback] Could not clear merge fields (non-fatal): {e}")

    def _clear_verification_fields() -> None:
        """Reset verification_cache and verification_status to idle."""
        try:
            payload = json.dumps({"verification_cache": None, "verification_status": "idle"})
            db.postgrest.session.patch(
                f"/calls?id=eq.{call_id}",
                content=payload,
                headers={"Content-Type": "application/json", "Prefer": "return=representation"},
            )
            logger.info(f"🗄️ [Rollback] Cleared verification fields for call {call_id}")
        except Exception as e:
            logger.warning(f"⚠️ [Rollback] Could not clear verification fields (non-fatal): {e}")

    def _un_merge_topics() -> None:
        """Reverse M:N merge: un-archive source topics, delete merged-into topics created at this call."""
        # Find topics that were created by the merge in this call (first_raised_call_id = call_id)
        merged_targets = (
            db.table("topics")
            .select("id")
            .eq("first_raised_call_id", call_id)
            .execute()
            .data
        )
        if not merged_targets:
            return

        target_ids = [t["id"] for t in merged_targets]

        # Find all archived topics that point to these targets
        for tid in target_ids:
            source_topics = (
                db.table("topics")
                .select("id")
                .eq("merged_into_topic_id", tid)
                .eq("archived", True)
                .execute()
                .data
            )
            for src in source_topics:
                payload = json.dumps({"archived": False, "merged_into_topic_id": None})
                db.postgrest.session.patch(
                    f"/topics?id=eq.{src['id']}",
                    content=payload,
                    headers={"Content-Type": "application/json", "Prefer": "return=representation"},
                )
                logger.info(f"🗄️ [Rollback] Un-archived source topic {src['id']} (was merged into {tid})")

        # Delete topic_updates for merged targets, then delete the target topics themselves
        for tid in target_ids:
            db.table("topic_updates").delete().eq("topic_id", tid).execute()
            db.table("topics").delete().eq("id", tid).execute()
            logger.info(f"🗄️ [Rollback] Deleted merged-into topic {tid} and its updates")

    def _clear_transcript_fields() -> None:
        """Clear transcript and transcript_source via raw HTTP (None-safe)."""
        payload = json.dumps({
            "transcript": None,
            "transcript_source": None,
        })
        response = db.postgrest.session.patch(
            f"/calls?id=eq.{call_id}",
            content=payload,
            headers={"Content-Type": "application/json", "Prefer": "return=representation"},
        )
        data = response.json()
        if not data:
            raise ValueError("Failed to clear fields via raw PATCH")
        logger.info(f"🗄️ [Rollback] Cleared transcript fields for call {call_id}")

    def _rebuild_pending_topics() -> None:
        """Rebuild pending_topics from topic_updates if it is not already set.

        Call 1 auto-advance path never sets pending_topics (it jumps straight to artifacts).
        Rolling back to project_matching or project_updates must restore it from topic_updates
        BEFORE those updates are deleted, so the page has data to show.
        """
        call_data = db.table("calls").select("pending_topics, extraction_cache").eq("id", call_id).execute().data
        if not call_data:
            return
        row = call_data[0]
        if row.get("pending_topics"):
            return  # already set — nothing to do (Call 2+ normal path)

        # Try extraction_cache first, then rebuild from topic_updates
        restore_data = row.get("extraction_cache")
        if not restore_data:
            updates = (
                db.table("topic_updates")
                .select("topic_id, summary, follow_up_items, decisions, status, owner, sentiment")
                .eq("call_id", call_id)
                .execute()
                .data
            )
            if updates:
                topic_ids = [u["topic_id"] for u in updates]
                names_rows = db.table("topics").select("id, name").in_("id", topic_ids).execute().data
                name_map = {r["id"]: r["name"] for r in names_rows}
                restore_data = [{**u, "name": name_map.get(u["topic_id"], "Unknown")} for u in updates]
                logger.info(f"🗄️ [Rollback] Rebuilt pending_topics from topic_updates for call {call_id} ({len(restore_data)} topics)")

        if restore_data:
            db.table("calls").update({"pending_topics": restore_data}).eq("id", call_id).execute()
            logger.info(f"🗄️ [Rollback] Restored pending_topics for call {call_id}")

    # --- Execute cascade based on target_stage ---

    if target_stage == "artifacts":
        _mark_artifacts_stale()

    elif target_stage == "project_updates":
        # Keep merge_cache/merge_status — that IS the project_updates content.
        # Clear only what comes after: topic_updates (re-created on next save), artifacts.
        # Restore pending_topics first (needed if merge_cache is null, so merge preview can re-run).
        # Un-merge BEFORE deleting topic_updates (needs to find merged-into topics).
        _un_merge_topics()
        _rebuild_pending_topics()
        _delete_topic_updates()
        _mark_artifacts_stale()
        _clear_verification_fields()

    elif target_stage == "project_matching":
        # Keep match_groups — that IS the project_matching content.
        # Restore pending_topics first (Call 1 auto-advance never sets it).
        # Clear everything after: topic_updates, merge, verification, artifacts.
        _un_merge_topics()
        _rebuild_pending_topics()
        _delete_topic_updates()
        _mark_artifacts_stale()
        _clear_merge_fields()
        _clear_verification_fields()

    elif target_stage == "call_topics":
        # Restore extraction_cache FIRST — topic_updates may be the only source (Call 1 auto-advance
        # path), so we must read them before deleting them below.
        # Priority: existing extraction_cache → pending_topics → rebuild from topic_updates
        call_data = db.table("calls").select("extraction_cache, pending_topics").eq("id", call_id).execute().data
        if call_data:
            row = call_data[0]
            if not row.get("extraction_cache"):
                restore_data = row.get("pending_topics")
                if not restore_data:
                    # Fallback: rebuild from topic_updates (Call 1 auto-advance case)
                    updates = (
                        db.table("topic_updates")
                        .select("topic_id, summary, follow_up_items, decisions, status, owner, sentiment")
                        .eq("call_id", call_id)
                        .execute()
                        .data
                    )
                    if updates:
                        topic_ids = [u["topic_id"] for u in updates]
                        names_rows = (
                            db.table("topics")
                            .select("id, name")
                            .in_("id", topic_ids)
                            .execute()
                            .data
                        )
                        name_map = {r["id"]: r["name"] for r in names_rows}
                        restore_data = [
                            {**u, "name": name_map.get(u["topic_id"], "Unknown")}
                            for u in updates
                        ]
                        logger.info(f"🗄️ [Rollback] Rebuilt extraction_cache from topic_updates for call {call_id} ({len(restore_data)} topics)")
                if restore_data:
                    db.table("calls").update({
                        "extraction_cache": restore_data,
                        "extraction_status": "done",
                    }).eq("id", call_id).execute()
                    logger.info(f"🗄️ [Rollback] Restored extraction_cache for call {call_id}")

        # Clear pending_topics — belongs to project_matching, not call_topics.
        db.postgrest.session.patch(
            f"/calls?id=eq.{call_id}",
            content=json.dumps({"pending_topics": None}),
            headers={"Content-Type": "application/json", "Prefer": "return=representation"},
        )

        # Delete everything downstream: topic_updates (created at project_updates), match_groups, merge, verification.
        _un_merge_topics()
        _delete_topic_updates()
        _delete_match_groups()
        _clear_merge_fields()
        _clear_verification_fields()
        _mark_artifacts_stale()

    elif target_stage == "transcript":
        # Keep transcript — that IS the transcript content.
        # Clear everything after: extraction, match_groups, topic_updates, merge, verification, artifacts.
        _un_merge_topics()
        _delete_topic_updates()
        _mark_artifacts_stale()
        _delete_match_groups()
        _clear_extraction_fields()
        _clear_merge_fields()
        _clear_verification_fields()

    else:
        raise ValueError(f"Unknown target_stage: {target_stage}")

    # Set the kanban_stage last
    db.table("calls").update({"kanban_stage": target_stage}).eq("id", call_id).execute()
    logger.info(f"✅ [Rollback] Call {call_id} rolled back to stage: {target_stage}")

    return {"rolled_back_to": target_stage}


async def list_call_topics(call_id: str) -> list[dict]:
    """Return topics discussed in this specific call — one entry per topic (latest update)."""
    db = get_client()

    updates = (
        db.table("topic_updates")
        .select("topic_id, summary, follow_up_items, decisions, status, owner, sentiment, created_at")
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
            result.append({
                "topic_id": t["id"],
                "name": t["name"],
                "calls_open": t["calls_open"],
                "summary": u.get("summary") or "",
                "follow_up_items": u.get("follow_up_items") or [],
                "decisions": u.get("decisions") or [],
                "status": u.get("status") or "open",
                "owner": u.get("owner") or "Us",
                "sentiment": u.get("sentiment") or "neutral",
            })

    return result


async def list_project_topics(project_id: str, db=None) -> list[dict]:
    """Return all non-archived topics for a project, enriched with latest update fields."""
    if db is None:
        db = get_client()
    return _get_previous_topics(project_id, db)


def list_topics_prior_to_call(call_id: str, project_id: str, db=None) -> list[dict]:
    """
    Return project topics that existed BEFORE the given call, based on call creation timestamps.
    A topic 'existed before call X' if its first_raised_call_id points to a call created before X.
    For the very first call, this always returns [].
    """
    if db is None:
        db = get_client()

    call_row = db.table("calls").select("created_at").eq("id", call_id).execute().data
    if not call_row:
        return []
    call_created_at = call_row[0]["created_at"]

    prior_calls = (
        db.table("calls")
        .select("id")
        .eq("project_id", project_id)
        .lt("created_at", call_created_at)
        .execute()
        .data
    )
    if not prior_calls:
        return []

    prior_call_ids = [c["id"] for c in prior_calls]

    topics = (
        db.table("topics")
        .select("id, name, calls_open, first_raised_call_id")
        .eq("project_id", project_id)
        .eq("archived", False)
        .in_("first_raised_call_id", prior_call_ids)
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


def list_topics_timeline(project_id: str, db=None) -> dict:
    """
    Build the full topic x call matrix for the timeline grid.

    Returns:
      {
        "calls": [{"id", "title", "call_number", "kanban_stage"}, ...],
        "topics": [{
          "topic_id", "name", "status", "owner", "sentiment",
          "first_raised_call_id",
          "call_updates": {
            "<call_id>": {
              "type": "new" | "followed_up" | "not_discussed" | "pending",
              "summary": str,
              "follow_up_items": [...],
              "decisions": [...],
              "status": str,
              "owner": str,
              "sentiment": str,
            }
          }
        }, ...]
      }

    Cell classification:
      - call before first_raised_call → absent (key not present)
      - call has a topic_update row  → "new" (first call) or "followed_up"
      - call >= first_raised and no row → "not_discussed"
      - call has no topic_updates and has extraction_cache/pending_topics → "pending" (synthetic row)
    """
    if db is None:
        db = get_client()

    COMPLETED_STAGES = ("call_topics", "project_matching", "project_updates", "artifacts", "done")
    raw_calls = (
        db.table("calls")
        .select("id, title, kanban_stage, created_at")
        .eq("project_id", project_id)
        .in_("kanban_stage", list(COMPLETED_STAGES))
        .order("created_at")
        .execute()
        .data
    )
    if not raw_calls:
        return {"calls": [], "topics": []}

    # call_number is not a DB column — assign it from chronological position
    all_calls = [
        {**c, "call_number": i + 1}
        for i, c in enumerate(raw_calls)
    ]

    call_ids = [c["id"] for c in all_calls]
    call_order = {c["id"]: i for i, c in enumerate(all_calls)}

    # Load both active and archived topics (archived shown with merged cell)
    active_topics = (
        db.table("topics")
        .select("id, name, first_raised_call_id, archived, merged_into_topic_id")
        .eq("project_id", project_id)
        .eq("archived", False)
        .execute()
        .data
    )
    archived_topics = (
        db.table("topics")
        .select("id, name, first_raised_call_id, archived, merged_into_topic_id")
        .eq("project_id", project_id)
        .eq("archived", True)
        .execute()
        .data
    )
    topics = active_topics + archived_topics
    if not topics:
        topic_ids = []
    else:
        topic_ids = [t["id"] for t in topics]

    # Build merged-into name lookup for archived topics
    merged_target_ids = list({t["merged_into_topic_id"] for t in archived_topics if t.get("merged_into_topic_id")})
    merged_name_map: dict[str, str] = {}
    if merged_target_ids:
        target_rows = db.table("topics").select("id, name").in_("id", merged_target_ids).execute().data
        merged_name_map = {r["id"]: r["name"] for r in target_rows}

    updates = (
        db.table("topic_updates")
        .select("topic_id, call_id, summary, follow_up_items, decisions, status, owner, sentiment")
        .in_("topic_id", topic_ids)
        .in_("call_id", call_ids)
        .execute()
        .data
    ) if topic_ids else []
    updates_index: dict[str, dict[str, dict]] = {}
    for u in updates:
        tid = u["topic_id"]
        cid = u["call_id"]
        if tid not in updates_index:
            updates_index[tid] = {}
        updates_index[tid][cid] = u

    # status/owner/sentiment live on topic_updates (not topics — dropped in migration 002)
    latest_updates = (
        db.table("topic_updates")
        .select("topic_id, status, owner, sentiment, created_at")
        .in_("topic_id", topic_ids)
        .order("created_at", desc=True)
        .execute()
        .data
    ) if topic_ids else []
    latest_state: dict = {}
    for u in latest_updates:
        tid = u["topic_id"]
        if tid not in latest_state:  # first = most recent
            latest_state[tid] = u

    result_topics = []
    for t in topics:
        tid = t["id"]
        first_call_id = t.get("first_raised_call_id")
        # If first_raised_call_id is None or not in the timeline's call set,
        # treat the topic as visible from the first call (all calls get not_discussed or update cells).
        first_idx = call_order.get(first_call_id, 0) if first_call_id else 0
        topic_updates_by_call = updates_index.get(tid, {})

        call_updates: dict[str, dict] = {}
        for c in all_calls:
            cid = c["id"]
            cidx = call_order[cid]

            if cidx < first_idx:
                continue  # absent

            if cid in topic_updates_by_call:
                u = topic_updates_by_call[cid]
                cell_type = "new" if cid == first_call_id else "followed_up"
                call_updates[cid] = {
                    "type": cell_type,
                    "summary": u.get("summary", ""),
                    "follow_up_items": u.get("follow_up_items") or [],
                    "decisions": u.get("decisions") or [],
                    "status": u.get("status", "open"),
                    "owner": u.get("owner", "Us"),
                    "sentiment": u.get("sentiment", "neutral"),
                }
            else:
                call_updates[cid] = {"type": "not_discussed"}

        # For archived topics, add a "merged" cell at the latest call with a topic_update
        is_archived = t.get("archived", False)
        merged_into_id = t.get("merged_into_topic_id")
        if is_archived and merged_into_id and topic_updates_by_call:
            # Find the last call that has an update for this topic
            latest_call_for_topic = max(
                topic_updates_by_call.keys(),
                key=lambda cid: call_order.get(cid, 0),
                default=None,
            )
            if latest_call_for_topic:
                merged_name = merged_name_map.get(merged_into_id, "")
                call_updates[latest_call_for_topic] = {
                    "type": "merged",
                    "merged_into_name": merged_name,
                    "merged_into_topic_id": merged_into_id,
                }

        ls = latest_state.get(tid, {})
        result_topics.append({
            "topic_id": tid,
            "name": t["name"],
            "status": ls.get("status", "open"),
            "owner": ls.get("owner", "Us"),
            "sentiment": ls.get("sentiment", "neutral"),
            "first_raised_call_id": first_call_id,
            "call_updates": call_updates,
            "archived": is_archived,
            "merged_into_topic_id": merged_into_id,
            "merged_into_name": merged_name_map.get(merged_into_id, "") if merged_into_id else None,
        })

    # ── Pending rows for calls with no committed topic_updates ──────────────
    calls_with_updates: set[str] = {u["call_id"] for u in updates}
    calls_without_updates = [c for c in all_calls if c["id"] not in calls_with_updates]

    if calls_without_updates:
        raw_ids = [c["id"] for c in calls_without_updates]
        raw_rows = (
            db.table("calls")
            .select("id, pending_topics, extraction_cache")
            .in_("id", raw_ids)
            .execute()
            .data
        )
        for row in raw_rows:
            cid = row["id"]
            raw_topics = row.get("pending_topics") or row.get("extraction_cache") or []
            for i, rt in enumerate(raw_topics):
                result_topics.append({
                    "topic_id": f"pending:{cid}:{i}",
                    "name": rt.get("name", ""),
                    "status": rt.get("status", "open"),
                    "owner": rt.get("owner", "Us"),
                    "sentiment": rt.get("sentiment", "neutral"),
                    "first_raised_call_id": cid,
                    "call_updates": {
                        cid: {
                            "type": "pending",
                            "summary": rt.get("summary", ""),
                            "follow_up_items": rt.get("follow_up_items") or [],
                            "decisions": rt.get("decisions") or [],
                            "status": rt.get("status", "open"),
                            "owner": rt.get("owner", "Us"),
                            "sentiment": rt.get("sentiment", "neutral"),
                        }
                    },
                })

    return {"calls": all_calls, "topics": result_topics}


def get_project_topics_context(project_id: str, db=None) -> str:
    """
    Build a compact summary of open/in_progress project topics for artifact context.
    Returns empty string if no open topics.
    """
    if db is None:
        db = get_client()
    previous = _get_previous_topics(project_id, db)
    open_topics = [t for t in previous if t.get("status") in ("open", "in_progress")]
    if not open_topics:
        return ""

    lines = ["=== Current Project Topics ==="]
    for t in open_topics:
        lines.append(
            f"\n• {t['name']} [{t['status']} / {t['owner']} / {t['sentiment']}]"
        )
        if t.get("summary"):
            lines.append(f"  Latest: {t['summary']}")
        for item in (t.get("follow_up_items") or [])[:3]:
            lines.append(f"  → {item}")
    return "\n".join(lines)
