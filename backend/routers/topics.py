from typing import Optional

from backend.database.supabase_client import get_client
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_call_topics, extract_call_topics, aggregate_topics,
    get_pending_topics, save_match_groups, run_merge_preview, validate_project_updates,
    TopicUpdate,
)
from backend.utils.logger import get_logger
from fastapi import APIRouter, HTTPException
from openai import APIStatusError as OpenAIStatusError
from pydantic import BaseModel as PydanticBaseModel

router = APIRouter(prefix="/api", tags=["topics"])
logger = get_logger("topics_router")


@router.post("/calls/{call_id}/topics/extract")
async def extract(call_id: str):
    logger.info(f"📥 [Topics] Extract requested: call={call_id}")
    try:
        result = await extract_topics(call_id)
        total = sum(len(v) for v in result.values() if isinstance(v, list))
        logger.info(f"✅ [Topics] Extracted {total} topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed")


@router.post("/calls/{call_id}/topics/extract_call")
async def extract_call(call_id: str):
    """Step 1: extract topics from this call's transcript only (no previous context)."""
    logger.info(f"📥 [Topics] Step-1 extract requested: call={call_id}")
    try:
        result = await extract_call_topics(call_id)
        logger.info(f"✅ [Topics] Step-1 extracted {len(result)} topics")
        return result
    except ValueError as e:
        msg = str(e)
        if msg == "no_transcript":
            raise HTTPException(status_code=422, detail="Call has no transcript")
        raise HTTPException(status_code=404, detail=msg)
    except OpenAIStatusError as e:
        if e.status_code in (413, 429) or "rate_limit" in str(e).lower():
            logger.warning(f"⚠️ [Topics] LLM rate limit on Step-1: {e}")
            raise HTTPException(
                status_code=429,
                detail="Transcript too large for current LLM tier — wait a moment and try again",
            )
        logger.exception(f"❌ [Topics] Step-1 extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed")
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-1 extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed")


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

    # When saving topics on a done call, mark artifacts as stale (non-blocking)
    try:
        db = get_client()
        call_row = db.table("calls").select("kanban_stage").eq("id", call_id).execute().data
        if call_row and call_row[0]["kanban_stage"] == "done":
            artifacts = db.table("artifacts").select("id").eq("call_id", call_id).execute().data
            artifact_ids = [a["id"] for a in artifacts]
            if artifact_ids:
                db.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
                logger.info(f"⚠️ [Topics] Marked {len(artifact_ids)} artifacts stale after topic save: {call_id}")
    except Exception as stale_err:
        logger.warning(f"⚠️ [Topics] Could not mark artifacts stale (non-fatal): {stale_err}")

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
    project_topic_id: Optional[str] = None
    call_topic_names: list[str]


@router.post("/calls/{call_id}/topics/save-matches", status_code=200)
async def save_matches(call_id: str, groups: list[MatchGroupPayload]):
    """Save manual match groups and advance to project_updates."""
    logger.info(f"📥 [Topics] Save matches: call={call_id}, groups={len(groups)}")
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups])
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save matches failed: {e}")
        raise HTTPException(status_code=500, detail="Save matches failed")


@router.post("/calls/{call_id}/topics/merge-preview")
async def merge_preview(call_id: str):
    """Run parallel LLM merge for all match groups — returns preview, does not save."""
    logger.info(f"📥 [Topics] Merge preview requested: call={call_id}")
    try:
        result = await run_merge_preview(call_id)
        logger.info(f"✅ [Topics] Merge preview: {len(result)} topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Merge preview failed: {e}")
        raise HTTPException(status_code=500, detail="Merge preview failed")


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


@router.get("/calls/{call_id}/brief")
async def brief(call_id: str):
    logger.info(f"📥 [Topics] Brief requested: call={call_id}")
    try:
        result = await generate_brief(call_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
