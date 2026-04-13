from backend.database.supabase_client import get_client
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, extract_call_topics, aggregate_topics, TopicUpdate,
)
from backend.utils.logger import get_logger
from fastapi import APIRouter, HTTPException
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
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-1 extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed")


class AggregatePayload(PydanticBaseModel):
    topics: list[dict]


@router.post("/calls/{call_id}/topics/aggregate")
async def aggregate(call_id: str, payload: AggregatePayload):
    """Step 2: match call topics against project topics → 3 buckets or auto-advance."""
    logger.info(
        f"📥 [Topics] Step-2 aggregate requested: call={call_id}, "
        f"input_topics={len(payload.topics)}"
    )
    try:
        result = await aggregate_topics(call_id, payload.topics)
        if result.get("auto_advanced"):
            logger.info(f"✅ [Topics] Auto-advanced Call 1: {call_id}")
        else:
            total = sum(len(result.get(k, [])) for k in ("followed_up", "not_discussed", "new_topics"))
            logger.info(f"✅ [Topics] Step-2 returned {total} classified topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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


@router.get("/projects/{project_id}/topics")
async def list_topics(project_id: str):
    logger.info(f"📥 [Topics] Dashboard requested: project={project_id}")
    db = get_client()
    result = await list_project_topics(project_id, db)
    logger.info(f"✅ [Topics] Returned {len(result)} topics")
    return result


@router.get("/calls/{call_id}/brief")
async def brief(call_id: str):
    logger.info(f"📥 [Topics] Brief requested: call={call_id}")
    try:
        result = await generate_brief(call_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
