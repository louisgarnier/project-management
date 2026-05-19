from typing import Optional

from backend.database.supabase_client import get_client
from backend.services.topic_lineage import (
    get_topic_lineage,
    get_lineage_topic_updates,
)
from backend.services.topics_service import (
    save_topics, validate_call, generate_brief,
    list_project_topics, list_call_topics, extract_call_topics, aggregate_topics,
    get_pending_topics, save_match_groups, run_merge_preview, validate_project_updates,
    run_extraction_background, run_merge_background, run_verification_background,
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
async def save_matches(call_id: str, groups: list[MatchGroupPayload], background_tasks: BackgroundTasks):
    """Save manual match groups and advance to project_updates."""
    logger.info(f"📥 [Topics] Save matches: call={call_id}, groups={len(groups)}")
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups])
        # Trigger not-discussed verification in background
        db = get_client()
        db.table("calls").update({"verification_status": "processing", "verification_cache": None}).eq("id", call_id).execute()
        background_tasks.add_task(run_verification_background, call_id)
        logger.info(f"✅ [Topics] Triggered background verification for call {call_id}")
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


@router.post("/calls/{call_id}/topics/merge-preview")
async def merge_preview(call_id: str, background_tasks: BackgroundTasks):
    """Fire-and-forget merge preview. Result saved to calls.merge_cache."""
    logger.info(f"📥 [Topics] Background merge requested: call={call_id}")
    db = get_client()

    call_row = db.table("calls").select("merge_status").eq("id", call_id).execute().data
    if not call_row:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    status = call_row[0].get("merge_status", "idle")
    if status == "processing":
        logger.info(f"⚠️ [Topics] Merge already in progress: call={call_id}")
        return {"status": "processing"}

    # Mark as processing and fire background task
    db.table("calls").update({"merge_status": "processing", "merge_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(run_merge_background, call_id)

    logger.info(f"✅ [Topics] Background merge started: call={call_id}")
    return {"status": "processing"}


@router.post("/calls/{call_id}/topics/verify-not-discussed")
async def verify_not_discussed(call_id: str, background_tasks: BackgroundTasks):
    """Trigger not-discussed verification in background."""
    logger.info(f"📥 [Topics] Verify not-discussed: call={call_id}")
    db = get_client()

    call_row = db.table("calls").select("verification_status").eq("id", call_id).execute().data
    if not call_row:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    status = call_row[0].get("verification_status", "idle")
    if status == "processing":
        logger.info(f"⚠️ [Topics] Verification already in progress: call={call_id}")
        return {"status": "processing"}

    db.table("calls").update({"verification_status": "processing", "verification_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(run_verification_background, call_id)
    logger.info(f"✅ [Topics] Background verification started: call={call_id}")
    return {"status": "processing"}


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


@router.patch("/topics/{topic_id}")
async def patch_topic(topic_id: str, body: TopicPatch):
    """Partially update a topic_updates row by its row id.

    Accepts any subset of: name, importance, key_terms, evidence, tasks.
    When tasks are supplied, task_ids are stamped on any new tasks and
    status is auto-rolled-up from task statuses.
    """
    logger.info(f"📥 [Topics] PATCH requested: topic_updates.id={topic_id}")
    db = get_client()

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
        # Stamp ids + added_in_call_id (resolve call_id from the row)
        row = db.table("topic_updates").select("call_id").eq("id", topic_id).execute().data
        if not row:
            raise HTTPException(status_code=404, detail="topic not found")
        call_id_for_stamp = row[0]["call_id"]
        stamped = _stamp_item_ids({"tasks": body.tasks}, call_id_for_stamp)["tasks"]
        payload["tasks"] = stamped
        payload["status"] = _status_rollup(stamped)

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
