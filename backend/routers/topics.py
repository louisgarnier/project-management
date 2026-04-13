from backend.database.supabase_client import get_client
from backend.services.topics_service import TopicUpdate, extract_topics, save_topics, validate_call, generate_brief
from backend.utils.logger import get_logger
from fastapi import APIRouter, HTTPException

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


@router.post("/calls/{call_id}/topics")
async def save(call_id: str, topics: list[TopicUpdate]):
    logger.info(f"📥 [Topics] Save requested: call={call_id}, count={len(topics)}")
    try:
        result = await save_topics(call_id, topics)
        logger.info(f"✅ [Topics] Saved {result['saved']} topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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


@router.get("/calls/{call_id}/brief")
async def brief(call_id: str):
    logger.info(f"📥 [Topics] Brief requested: call={call_id}")
    try:
        result = await generate_brief(call_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
