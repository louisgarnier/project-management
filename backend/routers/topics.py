from typing import Optional

from backend.database.supabase_client import get_client
from backend.services.topic_lineage import (
    get_topic_lineage,
    get_lineage_topic_updates,
)
from backend.services.topics_service import (
    save_topics, validate_call, generate_brief,
    list_project_topics, list_call_topics, extract_call_topics, aggregate_topics,
    get_pending_topics, save_match_groups, validate_project_updates,
    run_extraction_background,
    list_topics_timeline,
    list_topics_prior_to_call, rollback_to_stage,
    TopicUpdate,
    _stamp_item_ids, _status_rollup,
)
from backend.utils.logger import get_logger
from fastapi import APIRouter, BackgroundTasks, HTTPException
from openai import APIStatusError as OpenAIStatusError
from pydantic import BaseModel as PydanticBaseModel

router = APIRouter(prefix="/api", tags=["topics"])
logger = get_logger("topics_router")



@router.post("/calls/{call_id}/topics/extract_call")
async def extract_call(call_id: str, background_tasks: BackgroundTasks):
    """Step 1: fire-and-forget extraction. Result saved to calls.extraction_cache."""
    logger.info(f"📥 [Topics] Background extraction requested: call={call_id}")
    db = get_client()

    # Check if already processing
    call_row = db.table("calls").select("extraction_status").eq("id", call_id).execute().data
    if not call_row:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    status = call_row[0].get("extraction_status", "idle")
    if status == "processing":
        logger.info(f"⚠️ [Topics] Extraction already in progress: call={call_id}")
        return {"status": "processing"}

    # Mark as processing and fire background task
    db.table("calls").update({"extraction_status": "processing", "extraction_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(run_extraction_background, call_id)

    logger.info(f"✅ [Topics] Background extraction started: call={call_id}")
    return {"status": "processing"}


class AggregatePayload(PydanticBaseModel):
    topics: list[dict]


@router.post("/calls/{call_id}/topics/aggregate")
async def aggregate(call_id: str, payload: AggregatePayload):
    """Step 2: save pending call topics → advance to project_matching (or auto-advance Call 1)."""
    logger.info(
        f"📥 [Topics] Step-2 aggregate requested: call={call_id}, "
        f"input_topics={len(payload.topics)}"
    )
    try:
        result = await aggregate_topics(call_id, payload.topics)
        if result.get("auto_advanced"):
            logger.info(f"✅ [Topics] Auto-advanced Call 1: {call_id}")
        else:
            logger.info(f"✅ [Topics] Saved pending topics → project_matching: {call_id}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OpenAIStatusError as e:
        if e.status_code in (413, 429) or "rate_limit" in str(e).lower():
            logger.warning(f"⚠️ [Topics] LLM rate limit on Step-2: {e}")
            raise HTTPException(
                status_code=429,
                detail="Transcript too large for current LLM tier — wait a moment and try again",
            )
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")


@router.post("/calls/{call_id}/topics")
async def save(call_id: str, topics: list[TopicUpdate]):
    logger.info(f"📥 [Topics] Save requested: call={call_id}, count={len(topics)}")
    try:
        result = await save_topics(call_id, topics)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save failed: {e}")
        raise HTTPException(status_code=500, detail="Topic save failed")

    # After saving topics:
    # 1. Mark this call's artifacts stale
    # 2. Roll back any later calls that are past call_topics (their data is now stale)
    try:
        db = get_client()
        call_row = db.table("calls").select("kanban_stage, project_id, created_at").eq("id", call_id).execute().data
        if call_row:
            # Mark this call's artifacts stale
            artifacts = db.table("artifacts").select("id").eq("call_id", call_id).execute().data
            artifact_ids = [a["id"] for a in artifacts]
            if artifact_ids:
                db.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
                logger.info(f"⚠️ [Topics] Marked {len(artifact_ids)} artifacts stale: {call_id}")

            # Roll back later calls that are past call_topics
            project_id = call_row[0]["project_id"]
            created_at = call_row[0]["created_at"]
            _STAGE_ORDER = ["transcript", "call_topics", "project_matching", "project_updates", "artifacts", "done"]
            later_calls = (
                db.table("calls")
                .select("id, kanban_stage")
                .eq("project_id", project_id)
                .gt("created_at", created_at)
                .order("created_at")
                .execute()
                .data
            )
            for lc in later_calls:
                rollback_to_stage(lc["id"], "call_topics")
                logger.info(f"⚠️ [Topics] Rolled back later call {lc['id']} to call_topics after topic edit on {call_id}")
    except Exception as stale_err:
        logger.warning(f"⚠️ [Topics] Post-save cascade failed (non-fatal): {stale_err}")

    return result


@router.post("/calls/{call_id}/topics/validate")
async def validate(call_id: str):
    logger.info(f"📥 [Topics] Validate requested: call={call_id}")
    try:
        result = await validate_call(call_id)
        logger.info(f"✅ [Topics] Call validated: {call_id}")
        return result
    except ValueError as e:
        msg = str(e)
        if msg == "no_topics":
            raise HTTPException(status_code=422, detail="No topics saved for this call")
        if msg.startswith("unacknowledged_topics:"):
            ids = msg.split(":")[1].split(",")
            raise HTTPException(
                status_code=422,
                detail={"error": "unacknowledged_topics", "ids": ids},
            )
        raise HTTPException(status_code=422, detail=msg)


@router.get("/calls/{call_id}/topics/by-call")
async def list_topics_by_call(call_id: str):
    """Return topics that have a topic_update for this specific call (call-scoped view)."""
    logger.info(f"📥 [Topics] Call-scoped topics requested: call={call_id}")
    result = await list_call_topics(call_id)
    logger.info(f"✅ [Topics] Returned {len(result)} call-scoped topics")
    return result


@router.get("/calls/{call_id}/topics/pending")
async def get_pending(call_id: str):
    """Return validated call topics stored between call_topics and project_matching stages."""
    logger.info(f"📥 [Topics] Pending topics requested: call={call_id}")
    try:
        result = await get_pending_topics(call_id)
        logger.info(f"✅ [Topics] Returned {len(result)} pending topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class MatchGroupPayload(PydanticBaseModel):
    project_topic_ids: list[str] = []
    call_topic_names: list[str]


@router.post("/calls/{call_id}/topics/save-matches", status_code=200)
async def save_matches(call_id: str, groups: list[MatchGroupPayload]):
    """Save manual match groups and advance to project_updates."""
    logger.info(f"📥 [Topics] Save matches: call={call_id}, groups={len(groups)}")
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups])
        logger.info(f"✅ [Topics] Saved match groups; project_updates stage advanced")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save matches failed: {e}")
        raise HTTPException(status_code=500, detail="Save matches failed")


class PromotePayload(PydanticBaseModel):
    topic_id: str


@router.post("/calls/{call_id}/topics/promote-not-discussed", status_code=200)
async def promote_not_discussed(call_id: str, payload: PromotePayload):
    """Persist a not-discussed topic promotion as a ptid-only match group so
    subsequent merge re-runs (or page refreshes) keep the topic as an Updated
    Topic instead of rebuilding it as not-discussed.
    """
    logger.info(f"📥 [Topics] Promote not-discussed: call={call_id}, topic={payload.topic_id}")
    db = get_client()
    # Idempotent: if a group for this ptid already exists, skip
    existing = (
        db.table("topic_match_groups")
        .select("project_topic_ids, call_topic_names")
        .eq("call_id", call_id)
        .execute()
        .data
    )
    for g in existing:
        ptids = g.get("project_topic_ids") or []
        cnames = g.get("call_topic_names") or []
        if payload.topic_id in ptids and not cnames:
            logger.info(f"✅ [Topics] Promote no-op — ptid-only group already exists for {payload.topic_id}")
            return {"ok": True, "created": False}
    db.table("topic_match_groups").insert({
        "call_id": call_id,
        "project_topic_ids": [payload.topic_id],
        "call_topic_names": [],
    }).execute()
    logger.info(f"✅ [Topics] Promoted topic {payload.topic_id} as ptid-only match group")
    return {"ok": True, "created": True}


@router.get("/calls/{call_id}/topics/match-groups")
async def get_match_groups(call_id: str):
    """Return saved match groups for a call with project topic names resolved."""
    logger.info(f"📥 [Topics] Match groups requested: call={call_id}")
    db = get_client()

    groups = (
        db.table("topic_match_groups")
        .select("project_topic_ids, call_topic_names")
        .eq("call_id", call_id)
        .execute()
        .data
    )

    result = []
    for g in groups:
        ptids = g.get("project_topic_ids") or []
        names = []
        for ptid in ptids:
            row = db.table("topics").select("name").eq("id", ptid).execute().data
            if row:
                names.append(row[0]["name"])
        result.append({
            "project_topic_ids": ptids,
            "project_topic_names": names,
            "call_topic_names": g.get("call_topic_names", []),
        })

    logger.info(f"✅ [Topics] Returned {len(result)} match groups")
    return result




@router.post("/calls/{call_id}/topics/validate-updates")
async def validate_updates(call_id: str, topics: list[dict]):
    """Save reviewed merged topics and advance to artifacts."""
    logger.info(f"📥 [Topics] Validate updates: call={call_id}, count={len(topics)}")
    try:
        result = await validate_project_updates(call_id, topics)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Validate updates failed: {e}")
        raise HTTPException(status_code=500, detail="Validate updates failed")


@router.get("/projects/{project_id}/topics")
async def list_topics(project_id: str):
    logger.info(f"📥 [Topics] Dashboard requested: project={project_id}")
    db = get_client()
    result = await list_project_topics(project_id, db)
    logger.info(f"✅ [Topics] Returned {len(result)} topics")
    return result


@router.get("/projects/{project_id}/topics/prior-to-call/{call_id}")
async def get_topics_prior_to_call(project_id: str, call_id: str):
    """Return project topics that existed before the given call (timestamp-scoped)."""
    logger.info(f"📥 [Topics] Prior-to-call requested: project={project_id}, call={call_id}")
    db = get_client()
    try:
        result = list_topics_prior_to_call(call_id, project_id, db)
        logger.info(f"✅ [Topics] Prior-to-call: {len(result)} topics")
        return result
    except Exception as e:
        logger.error(f"❌ [Topics] Prior-to-call failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load prior topics")


@router.get("/projects/{project_id}/topics/timeline")
async def get_topics_timeline(project_id: str):
    """Return the full topic x call matrix for the timeline grid."""
    logger.info(f"📥 [Topics] Timeline requested: project={project_id}")
    db = get_client()
    try:
        result = list_topics_timeline(project_id, db)
        logger.info(
            f"✅ [Topics] Timeline: {len(result['calls'])} calls, {len(result['topics'])} topics"
        )
        return result
    except Exception as e:
        logger.error(f"❌ [Topics] Timeline failed: project={project_id} — {e}")
        raise HTTPException(status_code=500, detail="Failed to load topics timeline")


@router.delete("/calls/{call_id}/topics/{topic_id}", status_code=204)
async def delete_topic_from_call(call_id: str, topic_id: str):
    """
    Remove a topic from one specific call.
    - Deletes the topic_update row for (topic_id, call_id).
    - Recalculates topics.calls_open.
    - Deletes the topics row entirely if no updates remain (orphan).
    - Updates first_raised_call_id if it pointed at this call.
    Does NOT touch topic_updates from other calls.
    """
    logger.info(f"📥 [Topics] Delete topic {topic_id} from call {call_id}")
    db = get_client()

    # 1. Delete this call's update for the topic
    db.table("topic_updates").delete().eq("topic_id", topic_id).eq("call_id", call_id).execute()

    # 2. Check remaining updates across all calls
    remaining = (
        db.table("topic_updates")
        .select("call_id, status, created_at")
        .eq("topic_id", topic_id)
        .order("created_at")
        .execute()
        .data
    )

    if not remaining:
        # No updates left anywhere — delete the topic row entirely
        db.table("topics").delete().eq("id", topic_id).execute()
        logger.info(f"🗄️ [DB] Deleted orphan topic {topic_id} (no remaining updates)")
        return

    # 3. Recalculate calls_open
    calls_open = sum(1 for r in remaining if r["status"] in ("open", "in_progress"))
    db.table("topics").update({"calls_open": calls_open}).eq("id", topic_id).execute()

    # 4. Fix first_raised_call_id if it pointed at the deleted call
    topic_row = db.table("topics").select("first_raised_call_id").eq("id", topic_id).execute().data
    if topic_row and topic_row[0]["first_raised_call_id"] == call_id:
        # Assign to the earliest remaining call that has an update
        new_first = remaining[0]["call_id"]  # already ordered by created_at asc
        db.table("topics").update({"first_raised_call_id": new_first}).eq("id", topic_id).execute()
        logger.info(f"🗄️ [DB] Updated first_raised_call_id for topic {topic_id} → {new_first}")

    logger.info(f"✅ [Topics] Removed topic {topic_id} from call {call_id}, calls_open={calls_open}")


# --------------------------------------------------------------------------- #
# Story 10.3 — Topic Evidence API
# --------------------------------------------------------------------------- #


class LineageNode(PydanticBaseModel):
    topic_id: str
    name: str
    archived: bool
    merged_into_topic_id: str | None


class EvidenceRawExtract(PydanticBaseModel):
    summary: str
    follow_up_items: list[str]
    decisions: list[str]


class EvidenceMatchGroup(PydanticBaseModel):
    project_topic_ids: list[str]
    call_topic_names: list[str]


class EvidenceVerification(PydanticBaseModel):
    discussed: bool | None
    transcript_excerpt: str | None
    reasoning: str
    error: str | None = None


class EvidenceCall(PydanticBaseModel):
    call_id: str
    call_title: str
    call_date: str | None
    source_topic_id: str
    source_topic_name: str
    transcript_excerpt: str | None
    merged_summary: str
    follow_up_items: list[str]
    decisions: list[str]
    status: str
    raw_extract: EvidenceRawExtract | None
    match_group: EvidenceMatchGroup | None
    not_discussed_verification: EvidenceVerification | None
    is_not_discussed: bool


class TopicEvidenceResponse(PydanticBaseModel):
    topic_id: str
    topic_name: str
    lineage: list[LineageNode]
    calls: list[EvidenceCall]


@router.get("/topics/{topic_id}/evidence", response_model=TopicEvidenceResponse)
async def get_topic_evidence(topic_id: str):
    """Return the ancestor-aware per-call evidence trail for a topic.

    Used by the frontend evidence panel (Story 10.4). Walks the lineage chain via
    topics.merged_into_topic_id, collects topic_updates rows across all ancestors,
    and enriches each row with call metadata, the original raw pending_topics
    extract, the saved match group, and any not-discussed verification result.
    """
    logger.info(f"📥 [Topics] Evidence requested: topic={topic_id}")
    db = get_client()

    # 1. Fetch the target topic — 404 if missing
    topic_rows = (
        db.table("topics")
        .select("id, name, archived, merged_into_topic_id")
        .eq("id", topic_id)
        .execute()
        .data
    )
    if not topic_rows:
        logger.info(f"⚠️ [Topics] Evidence 404: topic {topic_id} not found")
        raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
    topic_row = topic_rows[0]

    # 2. Lineage
    lineage_raw = get_topic_lineage(topic_id, db)
    lineage = [
        LineageNode(
            topic_id=n["id"],
            name=n["name"],
            archived=bool(n.get("archived", False)),
            merged_into_topic_id=n.get("merged_into_topic_id"),
        )
        for n in lineage_raw
    ]

    # 3. Ancestor-inclusive topic_updates rows (chronological)
    update_rows = get_lineage_topic_updates(topic_id, db)

    # Caches to avoid N+1 lookups
    call_cache: dict[str, dict | None] = {}
    match_group_cache: dict[str, list[dict]] = {}

    def _load_call(call_id: str) -> dict | None:
        if call_id in call_cache:
            return call_cache[call_id]
        rows = (
            db.table("calls")
            .select("id, title, created_at, pending_topics, verification_cache")
            .eq("id", call_id)
            .execute()
            .data
        )
        call_cache[call_id] = rows[0] if rows else None
        return call_cache[call_id]

    def _load_match_groups(call_id: str) -> list[dict]:
        if call_id in match_group_cache:
            return match_group_cache[call_id]
        rows = (
            db.table("topic_match_groups")
            .select("project_topic_ids, call_topic_names")
            .eq("call_id", call_id)
            .execute()
            .data
        )
        match_group_cache[call_id] = rows or []
        return match_group_cache[call_id]

    def _find_raw_extract(pending_topics, source_name: str) -> EvidenceRawExtract | None:
        if not pending_topics or not isinstance(pending_topics, list):
            return None
        needle = (source_name or "").strip().lower()
        if not needle:
            return None
        for pt in pending_topics:
            if not isinstance(pt, dict):
                continue
            name = (pt.get("name") or "").strip().lower()
            if name == needle:
                return EvidenceRawExtract(
                    summary=pt.get("summary", "") or "",
                    follow_up_items=pt.get("follow_up_items", []) or [],
                    decisions=pt.get("decisions", []) or [],
                )
        return None

    def _find_match_group(call_id: str, source_tid: str) -> EvidenceMatchGroup | None:
        for g in _load_match_groups(call_id):
            ptids = g.get("project_topic_ids") or []
            if source_tid in ptids:
                return EvidenceMatchGroup(
                    project_topic_ids=ptids,
                    call_topic_names=g.get("call_topic_names") or [],
                )
        return None

    def _find_verification(verification_cache, source_tid: str) -> EvidenceVerification | None:
        if not isinstance(verification_cache, dict):
            return None
        entry = verification_cache.get(source_tid)
        if not isinstance(entry, dict):
            return None
        discussed_raw = entry.get("discussed")
        return EvidenceVerification(
            discussed=discussed_raw if isinstance(discussed_raw, bool) else None,
            transcript_excerpt=entry.get("transcript_excerpt"),
            reasoning=entry.get("reasoning", "") or "",
            error=entry.get("error"),
        )

    calls: list[EvidenceCall] = []
    for row in update_rows:
        call_id = row["call_id"]
        source_tid = row["source_topic_id"]
        source_name = row["source_topic_name"]
        call = _load_call(call_id) or {}

        calls.append(EvidenceCall(
            call_id=call_id,
            call_title=row.get("call_title") or call_id,
            call_date=call.get("created_at"),
            source_topic_id=source_tid,
            source_topic_name=source_name,
            transcript_excerpt=row.get("transcript_excerpt"),
            merged_summary=row.get("summary") or "",
            follow_up_items=row.get("follow_up_items") or [],
            decisions=row.get("decisions") or [],
            status=row.get("status") or "open",
            raw_extract=_find_raw_extract(call.get("pending_topics"), source_name),
            match_group=_find_match_group(call_id, source_tid),
            not_discussed_verification=_find_verification(call.get("verification_cache"), source_tid),
            is_not_discussed=False,
        ))

    logger.info(
        f"✅ [Topics] Evidence assembled: topic={topic_id}, "
        f"lineage={len(lineage)}, calls={len(calls)}"
    )
    return TopicEvidenceResponse(
        topic_id=topic_row["id"],
        topic_name=topic_row["name"],
        lineage=lineage,
        calls=calls,
    )


# --------------------------------------------------------------------------- #
# Story 15.1 — PATCH /api/topics/{topic_id}  (partial new-shape body)
# --------------------------------------------------------------------------- #


class TopicPatch(PydanticBaseModel):
    name: Optional[str] = None
    importance: Optional[str] = None
    key_terms: Optional[list[str]] = None
    evidence: Optional[list[dict]] = None
    tasks: Optional[list[dict]] = None
    open_questions: Optional[list[dict]] = None
    decisions: Optional[list[dict]] = None


@router.patch("/topics/{topic_id}")
async def patch_topic(topic_id: str, body: TopicPatch):
    """Partially update a topic_updates row by its row id.

    Accepts any subset of: name, importance, key_terms, evidence, tasks,
    open_questions, decisions. When tasks/open_questions/decisions are supplied,
    items get stable ids + added_in_call_id stamped (resolved from the row's
    call_id via a single SELECT shared across all 3 stamping paths). When tasks
    are supplied, topic-level status is rolled up from task statuses.
    """
    logger.info(f"📥 [Topics] PATCH requested: topic_updates.id={topic_id}")
    db = get_client()

    needs_stamping = (
        body.tasks is not None
        or body.open_questions is not None
        or body.decisions is not None
    )
    call_id_for_stamp = None
    if needs_stamping:
        row = db.table("topic_updates").select("call_id").eq("id", topic_id).execute().data
        if not row:
            raise HTTPException(status_code=404, detail="topic not found")
        call_id_for_stamp = row[0]["call_id"]

    payload: dict = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.importance is not None:
        payload["importance"] = body.importance
    if body.key_terms is not None:
        payload["key_terms"] = body.key_terms
    if body.evidence is not None:
        payload["evidence"] = body.evidence
    if body.tasks is not None:
        stamped = _stamp_item_ids({"tasks": body.tasks}, call_id_for_stamp)["tasks"]
        payload["tasks"] = stamped
        payload["status"] = _status_rollup(stamped)
    if body.open_questions is not None:
        stamped_oq = _stamp_item_ids(
            {"open_questions": body.open_questions}, call_id_for_stamp
        )["open_questions"]
        payload["open_questions"] = stamped_oq
    if body.decisions is not None:
        stamped_d = _stamp_item_ids(
            {"decisions": body.decisions}, call_id_for_stamp
        )["decisions"]
        payload["decisions"] = stamped_d

    if not payload:
        raise HTTPException(status_code=400, detail="no fields to update")

    res = db.table("topic_updates").update(payload).eq("id", topic_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="topic not found")

    logger.info(f"✅ [Topics] PATCH applied: topic_updates.id={topic_id}, fields={list(payload)}")
    return res.data[0]


@router.get("/calls/{call_id}/brief")
async def brief(call_id: str):
    logger.info(f"📥 [Topics] Brief requested: call={call_id}")
    try:
        result = await generate_brief(call_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ① /verify-new
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_verify_new as _run_verify_new


async def _run_verify_new_background(call_id: str) -> None:
    """Run Pass ① for every new topic in this call's pending_topics, persist to verify_new_cache."""
    import asyncio
    from backend.services.topics_service import _resolve_workflow_llm_for_category
    from backend.services.topic_verification import ProgressLogger
    db = get_client()
    plog = ProgressLogger(db, call_id, "verify_new_cache")
    try:
        await plog.start()
        await plog.log("Starting Pass ① — Verify new topics")
        call_row = db.table("calls").select("project_id, pending_topics").eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]
        pending = call_row[0].get("pending_topics") or []

        groups = db.table("topic_match_groups").select("call_topic_names, project_topic_ids").eq("call_id", call_id).execute().data
        # A "new" candidate = pending topic whose name is in a group with empty project_topic_ids
        new_group_names = {n.lower().strip() for g in groups if not (g.get("project_topic_ids") or []) for n in (g.get("call_topic_names") or [])}
        new_candidates = [t for t in pending if t["name"].lower().strip() in new_group_names]
        await plog.log(f"Found {len(new_candidates)} new-topic candidate(s) to verify")

        await plog.log("Loading transcripts from all calls in the project…")
        calls = (
            db.table("calls").select("id, transcript, title")
            .eq("project_id", project_id).order("created_at").execute().data
        )
        transcripts = {c["id"]: (c.get("transcript") or "") for c in calls if c.get("transcript")}
        # Map call UUID → human-readable label (Call 1, Call 2, ...) for log messages.
        call_label = {c["id"]: f"Call {i+1}" for i, c in enumerate(calls)}
        await plog.log(f"Loaded {len(transcripts)} transcript(s)")

        # For duplicate detection, the LLM needs more than just the topic name
        # — it needs key_terms + summary + a quick view of tasks so it can tell
        # "is this candidate the same thing as an existing topic?". key_terms,
        # tasks, summary all live on topic_updates (latest per topic). Use
        # _get_previous_topics which already does that aggregation.
        from backend.services.topics_service import _get_previous_topics
        previous = _get_previous_topics(project_id, db)
        project_topics = []
        for t in previous:
            tasks_summary = [
                (task.get("task") or "")[:80]
                for task in (t.get("tasks") or [])[:5]
            ]
            project_topics.append({
                "topic_id": t.get("topic_id"),
                "name": t.get("name"),
                "key_terms": t.get("key_terms") or [],
                "summary": (t.get("summary") or "")[:200],
                "task_briefs": tasks_summary,
            })
        await plog.log(f"Loaded {len(project_topics)} reference topic(s) from previous calls (NOT verified — just used as comparison list: 'is the new candidate a duplicate of any of these existing topics?'). Each ref includes key_terms + summary + task briefs.")

        llm, model = _resolve_workflow_llm_for_category(project_id, "verify_new_topic", db)
        await plog.log(f"Calling LLM ({llm}/{model or 'default'}) on {len(new_candidates)} topic(s) in parallel — this can take 30-60s")

        async def _one(c):
            await plog.log(f"  → Topic \"{c['name']}\": calling LLM…")
            r = await _run_verify_new(c, project_topics, transcripts, llm=llm, model=model, log_fn=plog.log)
            verdict = (r or {}).get("verdict", "?")
            need_review = (r or {}).get("needs_manual_review")
            n_cits = len((r or {}).get("citations") or [])
            n_trans = len(transcripts)
            n_topics = len(project_topics)
            if need_review:
                fails = (r or {}).get("failed_citations") or []
                # Aggregate by call: "3 in Call 1, 2 in Call 2"
                per_call: dict = {}
                for f in fails:
                    for cid, label in call_label.items():
                        if cid in f:
                            per_call[label] = per_call.get(label, 0) + 1
                            break
                    else:
                        per_call["?"] = per_call.get("?", 0) + 1
                pieces = ", ".join(f"{n} in {lbl}" for lbl, n in per_call.items())
                await plog.log(
                    f"  ⚠ Topic \"{c['name']}\": needs manual review — the LLM cited supporting quotes "
                    f"that couldn't be found verbatim in the transcripts ({pieces}). "
                    f"The LLM probably paraphrased instead of copy-pasting — its verdict can't be trusted automatically."
                )
            elif verdict == "truly_new":
                ung = (r or {}).get("ungrounded_items") or []
                msg = f"  ✓ Topic \"{c['name']}\": read {n_trans} past transcript(s), compared against {n_topics} existing topic(s) → confirmed NEW ({n_cits} citation(s))"
                if ung:
                    items = ", ".join((u.get("text") or "?")[:60] for u in ung[:3])
                    msg += f"  ⚠ but {len(ung)} extracted item(s) not grounded in transcript: {items}"
                await plog.log(msg)
            elif verdict == "should_be_merged_with":
                tname = (r or {}).get("matched_topic_name") or "?"
                await plog.log(f"  ↻ Topic \"{c['name']}\": read {n_trans} past transcript(s) → matches existing topic \"{tname}\" (suggesting merge)")
            else:
                await plog.log(f"  ✓ Topic \"{c['name']}\": {verdict}")
            return r

        results = await asyncio.gather(*[_one(c) for c in new_candidates])
        cache = {c["name"]: r for c, r in zip(new_candidates, results)}
        cache["__progress__"] = plog.entries_snapshot()
        cache["__progress__"].append({"ts": __import__("datetime").datetime.utcnow().isoformat() + "Z", "msg": f"Pass ① complete — {len(results)} topic(s) verified"})

        db.table("calls").update(
            {"verify_new_cache": cache, "verify_new_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [verify_new] done for call {call_id} ({len(results)} candidates)")
    except Exception as e:
        logger.exception(f"❌ [verify_new] failed for call {call_id}: {e}")
        try:
            await plog.log(f"❌ ERROR: {e}")
        except Exception:
            pass
        db.table("calls").update({"verify_new_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()


@router.post("/calls/{call_id}/topics/verify-new")
async def verify_new(call_id: str, background_tasks: BackgroundTasks):
    """EPIC-16 Pass ① — verify that newly-classified topics are truly new + extraction-grounded."""
    logger.info(f"📥 [verify_new] requested for call {call_id}")
    db = get_client()
    db.table("calls").update({"verify_new_status": "processing", "verify_new_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(_run_verify_new_background, call_id)
    return {"status": "processing"}


# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ② /verify-not-discussed (lean transcript-only check)
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_verify_not_discussed as _run_verify_not_discussed


async def _run_verify_not_discussed_background(call_id: str) -> None:
    """Pass ② for every old topic not in any match group."""
    import asyncio
    import datetime as _dt2
    from backend.services.topics_service import _resolve_workflow_llm_for_category, _get_previous_topics
    from backend.services.topic_verification import ProgressLogger
    db = get_client()
    plog = ProgressLogger(db, call_id, "verify_not_discussed_cache")
    try:
        await plog.start()
        await plog.log("Starting Pass ② — Verify not discussed")
        call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]
        transcript = call_row[0].get("transcript") or ""
        await plog.log(f"Loaded transcript for current call ({len(transcript)} chars)")

        groups = db.table("topic_match_groups").select("project_topic_ids").eq("call_id", call_id).execute().data
        matched_ids = {pid for g in groups for pid in (g.get("project_topic_ids") or [])}

        previous = _get_previous_topics(project_id, db)
        not_discussed_candidates = [t for t in previous if t["topic_id"] not in matched_ids]
        await plog.log(f"Found {len(not_discussed_candidates)} candidate topic(s) marked not-discussed")

        llm, model = _resolve_workflow_llm_for_category(project_id, "verify_not_discussed", db)
        await plog.log(f"Calling LLM ({llm}/{model or 'default'}) on {len(not_discussed_candidates)} topic(s) in parallel")

        async def _one(t):
            await plog.log(f"  → Topic \"{t['name']}\": scanning current call transcript…")
            r = await _run_verify_not_discussed(
                {"name": t["name"], "key_terms": t.get("key_terms") or []},
                transcript, call_id=call_id, llm=llm, model=model, log_fn=plog.log,
            )
            verdict = (r or {}).get("verdict", "?")
            need_review = (r or {}).get("needs_manual_review")
            if need_review:
                fails = (r or {}).get("failed_citations") or []
                await plog.log(f"  ⚠ Topic \"{t['name']}\": needs manual review — citation issue: {'; '.join(fails[:2])}")
            elif verdict == "not_discussed":
                await plog.log(f"  ✓ Topic \"{t['name']}\": confirmed NOT discussed in this call")
            elif verdict == "actually_discussed":
                cit = (r or {}).get("citation") or {}
                q = (cit.get("quote") or "")[:80]
                await plog.log(f"  ↻ Topic \"{t['name']}\": actually mentioned (\"{q}…\") → moving to Merged section")
            else:
                await plog.log(f"  ✓ Topic \"{t['name']}\": {verdict}")
            return r

        results = await asyncio.gather(*[_one(t) for t in not_discussed_candidates])
        cache = {t["topic_id"]: r for t, r in zip(not_discussed_candidates, results)}
        cache["__progress__"] = plog.entries_snapshot()
        cache["__progress__"].append({"ts": _dt2.datetime.utcnow().isoformat() + "Z", "msg": f"Pass ② complete — {len(results)} topic(s) checked"})
        db.table("calls").update(
            {"verify_not_discussed_cache": cache, "verify_not_discussed_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [verify_not_discussed] done for call {call_id} ({len(results)} candidates)")
    except Exception as e:
        logger.exception(f"❌ [verify_not_discussed] failed for call {call_id}: {e}")
        try:
            await plog.log(f"❌ ERROR: {e}")
        except Exception:
            pass
        db.table("calls").update({"verify_not_discussed_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()


@router.post("/calls/{call_id}/topics/verify-not-discussed")
async def verify_not_discussed(call_id: str, background_tasks: BackgroundTasks):
    """EPIC-16 Pass ② — verify each not-matched project topic truly wasn't discussed in call N."""
    logger.info(f"📥 [verify_not_discussed] requested for call {call_id}")
    db = get_client()
    db.table("calls").update(
        {"verify_not_discussed_status": "processing", "verify_not_discussed_cache": None}
    ).eq("id", call_id).execute()
    background_tasks.add_task(_run_verify_not_discussed_background, call_id)
    return {"status": "processing"}


# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ③ /extract-updates
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_extract_topic_updates as _run_extract


async def _run_extract_updates_background(call_id: str) -> None:
    """Pass ③ — full re-extraction for every merged topic (incl. ones migrated by Pass ① + ②)."""
    import asyncio
    import datetime as _dt3
    from backend.services.topics_service import _resolve_workflow_llm_for_category
    from backend.services.topic_verification import ProgressLogger
    db = get_client()
    plog = ProgressLogger(db, call_id, "extract_updates_cache")
    try:
        await plog.start()
        await plog.log("Starting Pass ③ — Extract updates from transcripts")
        call_row = db.table("calls").select(
            "project_id, verify_new_cache, verify_not_discussed_cache"
        ).eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]

        groups = db.table("topic_match_groups").select("project_topic_ids").eq("call_id", call_id).execute().data
        matched_ids = list({pid for g in groups for pid in (g.get("project_topic_ids") or [])})
        nd_cache = call_row[0].get("verify_not_discussed_cache") or {}
        moved_from_nd = [tid for tid, r in nd_cache.items() if (r or {}).get("verdict") == "actually_discussed"]
        matched_ids = list(set(matched_ids + moved_from_nd))
        vn_cache = call_row[0].get("verify_new_cache") or {}
        moved_from_new = [
            (r or {}).get("matched_topic_id")
            for r in vn_cache.values()
            if (r or {}).get("verdict") == "should_be_merged_with" and (r or {}).get("matched_topic_id")
        ]
        matched_ids = list({*matched_ids, *moved_from_new})
        await plog.log(f"Collected {len(matched_ids)} merged topic anchor(s) (incl. migrations from ① and ②)")

        # key_terms lives on topic_updates, not parent topics. The Pass ③ prompt
        # uses name as anchor; key_terms is optional context (LLM works without it).
        anchors = (
            db.table("topics").select("id, name")
            .in_("id", matched_ids).execute().data
        ) if matched_ids else []

        await plog.log("Loading all transcripts in the project (chronological)…")
        calls = (
            db.table("calls").select("id, transcript")
            .eq("project_id", project_id).order("created_at").execute().data
        )
        transcripts = {c["id"]: (c.get("transcript") or "") for c in calls if c.get("transcript")}
        total_tokens_approx = sum(len(t) for t in transcripts.values()) // 4
        await plog.log(f"Loaded {len(transcripts)} transcript(s) — approx {total_tokens_approx:,} tokens of context per topic")

        llm, model = _resolve_workflow_llm_for_category(project_id, "extract_topic_updates", db)
        await plog.log(f"Calling LLM ({llm}/{model or 'default'}) on {len(anchors)} topic(s) in parallel — this can take 1-2 min")

        async def _one(t):
            await plog.log(f"  → Topic \"{t['name']}\": re-extracting from transcripts…")
            r = await _run_extract(
                {"name": t["name"], "key_terms": t.get("key_terms") or []},
                transcripts, llm=llm, model=model, log_fn=plog.log,
            )
            need_review = (r or {}).get("needs_manual_review")
            snapshot = (r or {}).get("extracted_snapshot") or {}
            tasks_n = len(snapshot.get("tasks") or [])
            decs_n = len(snapshot.get("decisions") or [])
            oqs_n = len(snapshot.get("open_questions") or [])
            trail_n = len((r or {}).get("evidence_trail") or [])
            if need_review:
                fails = (r or {}).get("failed_citations") or []
                summary = "; ".join(fails[:3])
                if len(fails) > 3:
                    summary += f"; +{len(fails)-3} more"
                await plog.log(f"  ⚠ Topic \"{t['name']}\": needs manual review — citations failed: {summary}")
            else:
                await plog.log(f"  ✓ Topic \"{t['name']}\": extracted {tasks_n} task(s), {oqs_n} OQ, {decs_n} decision(s) with {trail_n} chronological citation(s)")
            return r

        results = await asyncio.gather(*[_one(t) for t in anchors])
        cache = {t["id"]: r for t, r in zip(anchors, results)}
        cache["__progress__"] = plog.entries_snapshot()
        cache["__progress__"].append({"ts": _dt3.datetime.utcnow().isoformat() + "Z", "msg": f"Pass ③ complete — {len(results)} topic(s) extracted"})
        db.table("calls").update(
            {"extract_updates_cache": cache, "extract_updates_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [extract_updates] done for call {call_id} ({len(results)} topics)")
    except Exception as e:
        logger.exception(f"❌ [extract_updates] failed for call {call_id}: {e}")
        try:
            await plog.log(f"❌ ERROR: {e}")
        except Exception:
            pass
        db.table("calls").update({"extract_updates_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()


@router.post("/calls/{call_id}/topics/extract-updates")
async def extract_updates(call_id: str, background_tasks: BackgroundTasks):
    """EPIC-16 Pass ③ — full re-extraction of merged topics from raw transcripts with chronological evidence_trail."""
    logger.info(f"📥 [extract_updates] requested for call {call_id}")
    db = get_client()
    db.table("calls").update(
        {"extract_updates_status": "processing", "extract_updates_cache": None}
    ).eq("id", call_id).execute()
    background_tasks.add_task(_run_extract_updates_background, call_id)
    return {"status": "processing"}
